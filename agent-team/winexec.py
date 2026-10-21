"""Windows programs for sandboxed agents on WSL.

WSL starts a Windows .exe over an AF_VSOCK socket, and Codex's Linux sandbox refuses that socket (and every socket
connect), so `cmd.exe /c ver` fails inside it with "UtilBindVsockAnyPort: socket failed 1". An agent runs
`winexec <program> [args]` instead, or the program's bare name, which a guard-bin shim routes here. The client writes a
request into the spool folder named by TEAM_WINEXEC (a folder the sandbox may write). The team process watches that
folder while the agent runs, starts the program outside the sandbox when [agents] windows_exec lists it, and streams
stdout, stderr and the exit code back through files. Without TEAM_WINEXEC (an unsandboxed agent, or a user shell) the
client runs the program directly. stdin is not forwarded."""
import contextlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

POLL = 0.1
PICKUP = 10  # seconds a request may wait for the broker


def is_wsl():
    try:
        return "microsoft" in Path("/proc/version").read_text(errors="ignore").lower()
    except OSError:
        return False


def resolve(name, allow, path):
    """The program file for name when its file name is allowed (case-insensitive, `.exe` optional), else None."""
    base = Path(name).name.lower()
    allowed = {a.lower() for a in allow}
    if base not in allowed and f"{base}.exe" not in allowed:
        return None
    if "/" in name:
        return name if Path(name).is_file() else None
    return shutil.which(name, path=path) or (shutil.which(f"{name}.exe", path=path) if not base.endswith(".exe") else None)


def _done(spool, rid, rc):
    tmp = spool / f"{rid}.rc.tmp"
    tmp.write_text(str(rc))
    os.replace(tmp, spool / f"{rid}.rc")  # last: the client drains the output files once it sees the exit code


class Broker:
    """Runs spooled requests while an agent runs; stop() kills what is still running."""

    def __init__(self, spool, allow, path):
        self.spool, self.allow, self.path = Path(spool), list(allow), path
        self.stopping = threading.Event()
        self.procs, self.lock = set(), threading.Lock()
        self.thread = threading.Thread(target=self._watch, daemon=True)

    def start(self):
        self.spool.mkdir(parents=True, exist_ok=True)
        self.thread.start()
        return self

    def stop(self):
        self.stopping.set()
        self.thread.join(timeout=5)
        with self.lock:
            for p in self.procs:
                p.kill()

    def _watch(self):
        while not self.stopping.is_set():
            for req in sorted(self.spool.glob("*.req")):
                taken = req.with_suffix(".run")
                try:
                    os.replace(req, taken)  # a request runs once
                except OSError:
                    continue
                threading.Thread(target=self._run, args=(taken,), daemon=True).start()
            self.stopping.wait(POLL)

    def _run(self, taken):
        rid = taken.stem
        try:
            req = json.loads(taken.read_text())
            argv, cwd = [str(a) for a in req["argv"]], str(req.get("cwd") or "")
        except (OSError, ValueError, KeyError, TypeError):
            return _done(self.spool, rid, 125)
        finally:
            taken.unlink(missing_ok=True)
        exe = resolve(argv[0], self.allow, self.path) if argv else None
        if not exe:
            (self.spool / f"{rid}.err").write_text(
                f"winexec: {argv[0] if argv else '(nothing)'} is not in [agents] windows_exec "
                f"({', '.join(self.allow) or 'empty'}) or not found\n")
            return _done(self.spool, rid, 126)
        with (self.spool / f"{rid}.out").open("wb") as out, (self.spool / f"{rid}.err").open("wb") as err:
            try:
                p = subprocess.Popen([exe, *argv[1:]], cwd=cwd if os.path.isdir(cwd) else None,
                                     stdin=subprocess.DEVNULL, stdout=out, stderr=err)
            except OSError as e:
                err.write(f"winexec: {exe}: {e}\n".encode())
                return _done(self.spool, rid, 127)
            with self.lock:
                self.procs.add(p)
            rc = p.wait()
            with self.lock:
                self.procs.discard(p)
        _done(self.spool, rid, rc)


@contextlib.contextmanager
def serving(spool, allow, path):
    """A Broker on spool for the duration of the block; a no-op when spool is None."""
    if spool is None:
        yield
        return
    b = Broker(spool, allow, path).start()
    try:
        yield
    finally:
        b.stop()


def client(argv):
    if not argv:
        sys.exit("usage: winexec <program> [args]")
    spool = os.environ.get("TEAM_WINEXEC")
    if not spool:  # outside a sandboxed run: the program starts directly
        here = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep) if p and "guard-bin" not in p)
        exe = argv[0] if "/" in argv[0] else shutil.which(argv[0], path=here)  # past the shims
        if not exe:
            sys.exit(f"winexec: {argv[0]} not found")
        os.execv(exe, [exe, *argv[1:]])
    d, rid = Path(spool), uuid.uuid4().hex
    tmp = d / f"{rid}.tmp"
    tmp.write_text(json.dumps({"argv": argv, "cwd": os.getcwd()}))
    os.replace(tmp, d / f"{rid}.req")
    start, pos = time.time(), {"out": 0, "err": 0}
    sinks = {"out": sys.stdout.buffer, "err": sys.stderr.buffer}
    while True:
        finished = (d / f"{rid}.rc").exists()  # checked before draining, so no output is left behind
        for k, sink in sinks.items():
            try:
                with (d / f"{rid}.{k}").open("rb") as f:
                    f.seek(pos[k])
                    data = f.read()
            except OSError:
                continue
            if data:
                sink.write(data)
                sink.flush()
                pos[k] += len(data)
        if finished:
            break
        if time.time() - start > PICKUP and (d / f"{rid}.req").exists():
            (d / f"{rid}.req").unlink(missing_ok=True)
            sys.exit(f"winexec: nothing picked up the request in {PICKUP} s (the team run that serves it has ended?)")
        time.sleep(POLL)
    rc = int((d / f"{rid}.rc").read_text())
    for k in ("out", "err", "rc"):
        (d / f"{rid}.{k}").unlink(missing_ok=True)
    sys.exit(rc)


if __name__ == "__main__":
    client(sys.argv[1:])
