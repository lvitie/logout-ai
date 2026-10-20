#!/usr/bin/env python3
"""Setup helper: write_config.py TEMPLATE DEST NAME claude|codex|both git|p4|none writes team.toml with the project name,
the role preset for the chosen agent CLIs and the VCS (used by scripts/setup-agent-team.sh and .ps1)."""
import sys
from pathlib import Path

src, dst, name, agents, vcs = sys.argv[1:]
SON, OPUS, FABLE, SOL, ASTRA = "claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1", "gpt-6.1-sol", "gpt-6-astra"
# Every profile a ladder can name: role -> (cli, model, effort). docs/MODEL_LADDER.md has the evidence and how to retune.
PROFILES = {"producer": ("claude", SON, "low"), "mid": ("claude", SON, "medium"), "mid_high": ("claude", SON, "high"),
            "senior": ("claude", OPUS, "high"), "architect": ("claude", OPUS, "high"),
            "director": ("claude", OPUS, "xhigh"), "apex": ("claude", FABLE, "high"),
            "cmid": ("codex", SOL, "medium"), "cmid_high": ("codex", SOL, "high"), "mid_claude": ("claude", SON, "medium"),
            "director_claude": ("claude", OPUS, "xhigh"), "csenior": ("codex", ASTRA, "medium"),
            "cdirector": ("codex", ASTRA, "high"), "capex": ("codex", ASTRA, "xhigh")}
NAMES = {"producer": "Producer", "mid": "Mid Dev", "mid_high": "Mid Dev (high)", "senior": "Senior Dev",
         "architect": "Architect", "director": "Tech Director", "apex": "Apex", "cmid": "Mid Dev (Codex)",
         "cmid_high": "Mid Dev (Codex, high)", "csenior": "Senior Dev (Codex)", "cdirector": "Tech Director (Codex)",
         "capex": "Apex (Codex)", "mid_claude": "Mid Dev (Claude)",
         "director_claude": "Tech Director (Claude)"}
# Canonical roles per preset. Codex implements simple and complex work and Claude reviews it; hard work is planned
# by Codex, built by Claude (both). The codex-only preset gives codex profiles the canonical names.
CANON = {"claude": {k: PROFILES[k] for k in ("producer", "mid", "senior", "architect", "director")},
         "codex": {"producer": ("codex", SOL, "low"), "mid": PROFILES["cmid"], "senior": PROFILES["csenior"],
                   "architect": PROFILES["cdirector"], "director": PROFILES["cdirector"]}}
CANON["both"] = {"producer": CANON["claude"]["producer"], "mid": PROFILES["cmid"], "senior": PROFILES["senior"],
                 "architect": PROFILES["architect"], "director": PROFILES["cdirector"]}
# tier -> {cli: role}, weakest first. low..top are reached by rules and escalation; apex only by escalation (no rule may
# name it) and is the strongest cap. Avoid effort max (little gain over xhigh at far higher cost; see docs/MODEL_LADDER.md).
LADDER = {
    "claude": {"low": {"claude": "mid"}, "mid": {"claude": "mid_high"}, "high": {"claude": "senior"},
               "top": {"claude": "director"}, "apex": {"claude": "apex"}},
    "codex": {"low": {"codex": "mid"}, "mid": {"codex": "cmid_high"}, "high": {"codex": "senior"},
              "top": {"codex": "director"}, "apex": {"codex": "capex"}},
    "both": {"low": {"claude": "mid_claude", "codex": "mid"}, "mid": {"claude": "mid_high", "codex": "cmid_high"},
             "high": {"claude": "senior", "codex": "csenior"}, "top": {"claude": "director_claude", "codex": "director"},
             "apex": {"claude": "apex", "codex": "capex"}}}
# Escalation ladder (team.toml `# --- ladder`): LADDER's five tiers; roles the ladder names are added to [roles].
# Only these rows are replaced; the template's [[heuristic.rule]] tables stay.
# The template ships Perforce; git swaps in the git deny lists.
GIT = """[vcs]
kind = "git"                  # git, p4, none, or any X with a vcs_X.py adapter
guard_names = ["git"]         # tools shadowed on the agents' PATH by bin/vcs-guard
[vcs.deny]                    # subcommands agents may not run per tool, also via aliases; "*" denies the tool entirely
git = ["commit", "push", "pull", "reset", "checkout", "switch", "stash", "clean", "rebase", "merge", "restore", "add",
       "rm", "mv", "cherry-pick", "revert", "am", "tag", "config", "worktree", "update-ref", "update-index",
       "symbolic-ref", "replace", "filter-branch", "gc", "prune", "reflog", "notes", "submodule"]
[vcs.deny_flags]              # tool -> subcommand -> refused flags (also inside combined short flags like -df)
git = { branch = ["-D", "-d", "-f", "-M", "-m", "-C", "-c", "-u", "--delete", "--force", "--move", "--copy",
                  "--set-upstream-to", "--unset-upstream"] }
"""
NONE = """[vcs]
kind = "none"                 # git, p4, none, or any X with a vcs_X.py adapter
guard_names = []              # no VCS: nothing is shadowed on the agents' PATH
[vcs.deny]
[vcs.deny_flags]
"""
preset = dict(CANON[agents])
ladder_rows = LADDER[agents]
for entry in ladder_rows.values():
    for role in entry.values():
        preset.setdefault(role, PROFILES[role])
roles = "".join(f"[roles.{k}]\nname = \"{NAMES[k]}\"\ncli = \"{c}\"\nmodel = \"{m}\"\neffort = \"{e}\"\n"
                for k, (c, m, e) in preset.items())
ladder = "[heuristic.tiers]\n" + "".join(
    f"{tier:<5}= {{ " + ", ".join(f'{c} = "{r}"' for c, r in entry.items()) + " }\n" for tier, entry in ladder_rows.items())
text = Path(src).read_text()
lstart = text.index("\n", text.index("# --- ladder:")) + 1
text = text[:lstart] + ladder + text[text.index("# --- end ladder ---"):]
start = text.index("\n", text.index("# --- roles:")) + 1
end = text.index("# --- end roles ---")
text = text[:start] + roles + text[end:]
if vcs == "git":  # the template ships Perforce
    start, end = text.index("[vcs]\n"), text.index("\n[agents]")
    text = text[:start] + GIT + text[end:]
if vcs == "none":  # no VCS: no guard, no deny rules, no submit step
    start, end = text.index("[vcs]\n"), text.index("\n[agents]")
    text = text[:start] + NONE + text[end:]
Path(dst).write_text(text.replace("name = \"myproject\"", f"name = \"{name}\"", 1))
