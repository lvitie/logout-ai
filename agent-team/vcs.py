"""VCS adapters for the agent team. A "change" is a string id: an adapter-specific change number, or for git the task id.

Interface (all adapters): new_change(desc, hint) -> str, set_description(change, desc), opened(change) -> str,
opened_files(change) -> [path], diff(change) -> str, others_opened(change) -> str, prepare_edit(path, change) -> (ok, msg),
add(path, change) -> (ok, msg), pending_changes() -> [str], changed_files(change) -> [abs path].
The adapters never submit, commit, stage, revert or shelve."""
import importlib
import subprocess
from pathlib import Path


class Vcs:
    tool = ""
    noun = "working-tree changes"  # what a "change" is called in prompts
    arg_opts = frozenset()  # global options taking an argument (to find the subcommand in vcs-guard)
    state_dir = None  # the team's state dir, set by make(); adapters leave it out of opened/diff
    submit_step = True  # False: nothing to submit, so prompts and reasons do not mention it
    sandbox_network = True  # Codex sandbox needs network for the tool (p4 edit/add reach a server)

    def __init__(self, root, real=None):
        self.root = Path(root)
        self.real = real or self.tool

    def alias(self, global_args, sub):
        """What `sub` expands to (vcs-guard checks the expansion too), or None when it is not an alias."""
        return None

    def run(self, *args, stdin=None):
        r = subprocess.run([self.real, *args], cwd=self.root, capture_output=True, text=True, input=stdin)
        return r

    def out(self, *args, stdin=None):
        r = self.run(*args, stdin=stdin)
        return r.stdout + r.stderr

    def new_change(self, desc, hint=""):
        raise NotImplementedError

    def set_description(self, change, desc):
        pass

    def opened(self, change):
        return ""

    def opened_files(self, change):
        return []

    def diff(self, change):
        return ""

    def others_opened(self, change=None):
        return ""

    def prepare_edit(self, path, change):
        return True, ""

    def add(self, path, change):
        return True, ""

    def pending_changes(self):
        return []

    def changed_files(self, change):
        return [self.root / f for f in self.opened_files(change)]


class Git(Vcs):
    """Git mapping: change id = task id (given as hint), description lives in task state only, all tasks share the
    working tree, so opened = `git status --porcelain -uall`. Nothing is staged or committed."""
    tool = "git"
    sandbox_network = False
    arg_opts = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"})

    def alias(self, global_args, sub):
        r = self.run(*global_args, "config", "--get", f"alias.{sub}")
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None

    def new_change(self, desc, hint=""):
        return hint or "work"

    def _exclude(self):
        """Pathspec that keeps the state dir (logs, prompts, previous diffs) out of status and diff."""
        try:
            return [f":(exclude){Path(self.state_dir).relative_to(self.root.resolve())}"] if self.state_dir else []
        except ValueError:  # state dir outside the workspace
            return []

    def _status(self):
        return [ln for ln in self.out("status", "--porcelain", "-uall", "--", *self._exclude()).splitlines() if ln.strip()]

    def opened(self, change):
        return "\n".join(self._status())

    def opened_files(self, change):
        return [ln[3:].split(" -> ")[-1].strip('"') for ln in self._status()]

    def diff(self, change):
        parts = [self.out("diff", "HEAD", "--", *self._exclude())] if self.run("rev-parse", "--verify", "HEAD").returncode == 0 else []
        for ln in self._status():
            if ln.startswith("??"):  # --no-index exits 1 when files differ
                parts.append(self.run("diff", "--no-index", "--", "/dev/null", ln[3:].strip('"')).stdout)
        return "".join(parts)

    def pending_changes(self):
        return ["work"] if self._status() else []


class NoneVcs(Vcs):
    """No version control: no tool, no guard, no submit step. The edit hook records each file an agent writes in
    <state_dir>/<change>/touched.txt (change = task id), which stands in for opened/changed files; there is no diff."""
    noun = "changes"
    submit_step = False
    sandbox_network = False

    def new_change(self, desc, hint=""):
        return hint or "work"

    def _list(self, change):
        return Path(self.state_dir or self.root / ".agent-team") / str(change) / "touched.txt"

    def _record(self, path, change):
        f = Path(path).resolve()
        if self.state_dir and Path(self.state_dir) in f.parents:
            return True, ""
        try:
            rel = f.relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return True, ""
        log = self._list(change)
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as fh:
            fh.write(rel + "\n")
        return True, ""

    prepare_edit = add = _record

    def opened_files(self, change):
        try:
            return sorted(set(self._list(change).read_text().splitlines()))
        except OSError:
            return []

    def opened(self, change):
        return "\n".join(self.opened_files(change))

    def pending_changes(self):
        return []


def adapter_class(kind):
    """git and none are built in; any other [vcs].kind X is the class `Adapter` in module vcs_X next to this file."""
    if kind == "git":
        return Git
    if kind == "none":
        return NoneVcs
    try:
        return importlib.import_module(f"vcs_{kind}").Adapter
    except ImportError:
        raise ValueError(f"unknown [vcs].kind {kind!r}: no vcs_{kind}.py adapter") from None


def make(cfg, real=None):
    adapter = adapter_class(cfg["vcs"]["kind"])(cfg["root"], real)
    adapter.state_dir = cfg["state"]
    return adapter


def subcommand(opts, argv):
    """-> (subcommand, args after it); opts = global options that take an argument."""
    skip = False
    for i, a in enumerate(argv):
        if skip:
            skip = False
        elif a in opts:
            skip = True
        elif a.startswith("-"):
            continue
        else:
            return a, argv[i + 1:]
    return "", []
