"""Shared test config: the shipped templates/team.toml rendered the way setup writes it (write_config.py)."""
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=None)
def config_text(agents="claude", vcs="git", name="myproject"):
    """team.toml text for an agent preset (claude|codex|both) and VCS (git|p4|none)."""
    with tempfile.TemporaryDirectory() as d:
        dst = Path(d) / "team.toml"
        subprocess.run([sys.executable, "-I", str(ROOT / "write_config.py"), str(ROOT / "templates/team.toml"), str(dst),
                        name, agents, vcs], check=True)
        return dst.read_text()


TOML = config_text()
