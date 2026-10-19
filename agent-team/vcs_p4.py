"""Perforce adapter for the agent team (changelist id = string of the changelist number)."""
import re

from vcs import Vcs


class Adapter(Vcs):
    tool = "p4"
    noun = "changelist"
    arg_opts = frozenset({"-c", "-d", "-u", "-p", "-H", "-P", "-z", "-F", "-x", "-C", "-Q", "-r", "--field"})

    def new_change(self, desc, hint=""):
        form = self.out("--field", f"Description={desc}", "--field", "Files=", "change", "-o")
        m = re.search(r"Change (\d+) created", self.out("change", "-i", stdin=form))
        if not m:
            raise RuntimeError("Could not create a changelist.")
        return m.group(1)

    def set_description(self, change, desc):
        self.out("change", "-i", stdin=self.out("--field", f"Description={desc}", "change", "-o", str(change)))

    def opened(self, change):
        return self.out("opened", "-c", str(change))

    def opened_files(self, change):
        return [f for f in self.out("-F", "%depotFile%", "opened", "-c", str(change)).split() if f.startswith("//")]

    def diff(self, change):
        files = self.opened_files(change)
        return self.out("diff", "-du", *files) if files else ""

    def others_opened(self, change=None):
        rows = [ln for ln in self.out("-F", "%change%|%depotFile%", "opened").splitlines() if "|//" in ln]
        return "\n".join(ln for ln in rows if ln.split("|")[0].split()[-1] != str(change))

    def prepare_edit(self, path, change):
        """Open an existing tracked file in the task changelist before an edit. Default-changelist strays join it;
        files in another numbered changelist are edited in place."""
        cur = self.run("-F", "%change%", "opened", str(path)).stdout.split()[-1:]  # "not opened" goes to stderr
        cur = cur[0] if cur else ""
        if cur and cur != str(change):
            if cur == "default":
                self.run("reopen", "-c", str(change), str(path))
            return True, ""
        if not cur:
            import os
            if not os.access(path, os.W_OK):
                r = self.run("edit", "-c", str(change), str(path))
                text = r.stdout + r.stderr
                if r.returncode or "can't edit" in text or "locked" in text:
                    return False, f"p4 edit failed: {text.strip()}"
        return True, ""

    def add(self, path, change):
        self.run("add", "-c", str(change), str(path))

    def pending_changes(self):
        client = self._client()
        return re.findall(r"^Change (\d+)\b", self.out("changes", "-s", "pending", "-c", client), re.M) if client else []

    def _client(self):
        m = re.search(r"^Client name: (\S+)", self.out("info"), re.M)
        return m.group(1) if m else ""

    def changed_files(self, change):
        """Files of a pending or submitted changelist as local paths (describe works after submit)."""
        from pathlib import Path
        out = []
        for depot in re.findall(r"^\.\.\. (//\S+?)#", self.out("describe", "-s", str(change)), re.M):
            where = self.run("-F", "%path%", "where", depot).stdout.split()
            if where and Path(where[-1]).exists():
                out.append(Path(where[-1]))
        return out
