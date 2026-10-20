#!/usr/bin/env python3
"""Setup helper: write_config.py TEMPLATE DEST NAME claude|codex|both git|p4|none writes team.toml with the project name,
the role preset for the chosen agent CLIs and the VCS (used by scripts/setup-agent-team.sh and .ps1)."""
import sys
from pathlib import Path

src, dst, name, agents, vcs = sys.argv[1:]
CLAUDE = {"producer": ("claude", "claude-sonnet-5-5", "low"), "mid": ("claude", "claude-sonnet-5-5", "medium"),
          "senior": ("claude", "claude-opus-5-5", "high"), "architect": ("claude", "claude-opus-5-5", "high"),
          "director": ("claude", "claude-opus-5-5", "high")}
CODEX = {"producer": ("codex", "gpt-6.1-sol", "low"), "mid": ("codex", "gpt-6.1-sol", "medium"),
         "senior": ("codex", "gpt-6.1-sol", "high"), "architect": ("codex", "gpt-6-astra", "high"),
         "director": ("codex", "gpt-6-astra", "high")}
# Codex implements simple and complex work and Claude reviews it; hard work is planned by Codex, built by Claude.
BOTH = {"producer": CLAUDE["producer"], "mid": CODEX["mid"], "senior": CLAUDE["senior"],
        "architect": CLAUDE["architect"], "director": CODEX["director"]}
NAMES = {"producer": "Producer", "mid": "Mid Dev", "senior": "Senior Dev", "architect": "Architect",
         "director": "Tech Director"}
P4 = """[vcs]
kind = "p4"                   # git, p4, none, or any X with a vcs_X.py adapter
guard_names = ["p4", "git"]   # tools shadowed on the agents' PATH by bin/vcs-guard
[vcs.deny]                    # subcommands agents may not run per tool, also via aliases; "*" denies the tool entirely
p4 = ["submit", "revert", "shelve", "unshelve", "obliterate", "sync", "clean", "flush", "integrate", "integ",
      "copy", "merge", "populate"]
git = ["*"]
[vcs.deny_flags]              # tool -> subcommand -> refused flags (also inside combined short flags like -df)
p4 = { change = ["-d", "-f"], changelist = ["-d", "-f"] }
"""
NONE = """[vcs]
kind = "none"                 # git, p4, none, or any X with a vcs_X.py adapter
guard_names = []              # no VCS: nothing is shadowed on the agents' PATH
[vcs.deny]
[vcs.deny_flags]
"""
preset = {"claude": CLAUDE, "codex": CODEX, "both": BOTH}[agents]
roles = "".join(f"[roles.{k}]\nname = \"{NAMES[k]}\"\ncli = \"{c}\"\nmodel = \"{m}\"\neffort = \"{e}\"\n"
                for k, (c, m, e) in preset.items())
text = Path(src).read_text()
start = text.index("\n", text.index("# --- roles:")) + 1
end = text.index("# --- end roles ---")
text = text[:start] + roles + text[end:]
if vcs == "p4":  # the template ships git; Perforce work goes in a changelist and agents may not use git at all
    start, end = text.index("[vcs]\n"), text.index("\n[agents]")
    text = text[:start] + P4 + text[end:]
if vcs == "none":  # no VCS: no guard, no deny rules, no submit step
    start, end = text.index("[vcs]\n"), text.index("\n[agents]")
    text = text[:start] + NONE + text[end:]
Path(dst).write_text(text.replace("name = \"myproject\"", f"name = \"{name}\"", 1))
