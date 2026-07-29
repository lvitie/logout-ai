---
name: project-bootstrap
description: Seed or augment a software project with project instructions, planning documents, and only the reusable Codex skills its stack requires. Use when Codex is asked to create, initialize, bootstrap, or add agent configuration to a project; choose workflows for a tech stack; or create a missing project-local skill for uncovered technology.
---

# Project Bootstrap

## Workflow

1. Inspect the target when it exists. Preserve all existing files and current
   changes.
2. Collect any missing inputs before writing:
   - target path
   - project goal, users, and required behavior
   - languages, frameworks, runtimes, tools, and deployment targets
   - constraints, non-goals, and security or privacy boundaries
   - required setup, lint, test, build, run, and manual-validation commands
3. Ask one concise grouped question for the missing inputs. Do not ask again for
   facts already present in the request or target repository.
4. Find the Logout AI source repository:
   - Prefer the repository containing this skill when it also contains
     `scripts/setup-project.sh` and `.agents/skills/`.
   - Otherwise use `LOGOUT_AI_ROOT` when set.
   - Otherwise ask for the path to the cloned Logout AI repository only if
     existing project-local or user-installed skills cannot satisfy the task.
5. Inventory available skills by reading each candidate `SKILL.md` description.
   Select skills because their triggers match an actual requirement, not merely
   because their names mention a language.
6. Always include `ai-project-manager` and `project-bootstrap`. Add
   `pr-readiness` when the project will use pull requests. Include paired skills
   when the stack crosses boundaries, such as `go-web` plus `htmx`, or a DCC
   host skill plus `qt-python`.
7. Preview the additive setup, report the files and skills to be added, and
   surface any existing files that will remain authoritative.
8. Run the platform setup script with one `--skill NAME` or `-Skill NAME` entry
   for every selected skill:

```bash
/path/to/logout-ai/scripts/setup-project.sh --dry-run \
  --skill rust-web --skill htmx /path/to/project
/path/to/logout-ai/scripts/setup-project.sh \
  --skill rust-web --skill htmx /path/to/project
```

```powershell
& C:\path\to\logout-ai\scripts\setup-project.ps1 `
  -TargetPath C:\path\to\project -DryRun -Skill rust-web,htmx
& C:\path\to\logout-ai\scripts\setup-project.ps1 `
  -TargetPath C:\path\to\project -Skill rust-web,htmx
```

9. Adapt only newly created `AGENTS.md`, `SPEC.md`, `ROADMAP.md`, and `TASKS.md`
   from the collected requirements. Never replace or silently rewrite an
   existing project document.
10. Validate the resulting instructions, skill metadata, internal links, and
    the project's documented commands. Inspect the final status and diff.

## Missing skill coverage

When no available skill covers a required technology or workflow:

1. Confirm that the gap is a reusable workflow rather than project-specific
   requirements. Put project-only knowledge in `AGENTS.md` or the planning
   documents.
2. Use the `skill-creator` workflow when available.
3. Create the focused skill under
   `<target>/.agents/skills/<lowercase-hyphen-name>/`.
4. Give `SKILL.md` valid `name` and `description` front matter. Put all trigger
   conditions in the description and keep the body concise and imperative.
5. Add `agents/openai.yaml` with a display name, a 25-64 character short
   description, and a default prompt that explicitly names the skill.
6. Add scripts, references, or assets only when they provide reusable value.
   Document external dependencies; do not silently install them.
7. Validate the new skill with `skill-creator/scripts/quick_validate.py` when
   that validator is available, then run the target project's validation.

Do not add a new generic language skill when an existing framework, host, or
workflow skill already covers the work. Do not add a skill speculatively for a
technology that is not required.

## Safety and completion

- The setup scripts are additive: they create missing directories and files but
  do not overwrite existing paths.
- Stop before dependency installation, repository initialization, deployment,
  or destructive changes unless the user explicitly requested them.
- Report selected skills, newly created skills, preserved files, checks run,
  skipped checks, and unresolved requirements.
