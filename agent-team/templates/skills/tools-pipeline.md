# Tools and content pipeline
## When to use
- Editor tools, importers and exporters, asset validators, batch processing, DCC (Maya, Blender, Houdini, Substance) to engine pipelines, automation scripts used by other disciplines.
- Not for: build farm, packaging and CI → `build-ci-release`; localization extraction → `localization`.
## Inputs
- The users of the tool and their workflow, asset conventions (naming, folders, import settings), the DCC and engine versions, sample assets.
## Method
1. Watch or write down the current manual workflow; build for the user of the tool: clear errors, safe defaults, dry-run for anything that rewrites assets.
2. Encode conventions as validators (naming, texture size, poly count, missing LODs, collision) that run on save and in CI.
3. Keep scripts idempotent; never rewrite or delete assets in bulk without a report of what changed.
4. Version the pipeline: tool version recorded in exported asset metadata where possible.
5. Add a validation or test that exercises the tool on a small sample.
## Checks
- Dry run on a sample produces the expected report; real run matches it.
- Errors name the asset and the fix; tool works for a user without admin rights or local tweaks.
- Runs headless (commandlet or batch mode) when CI needs it.
## Pitfalls
- Tools that depend on one machine's paths or Python packages.
- Silent auto-fixes that hide problems from artists; validators so noisy they get disabled.
- Bulk changes to assets checked out or opened by someone else.
## Engine notes
- Unreal: Editor Utility Widgets and Blueprints, Python editor scripting (`unreal` module), Editor Validator subclasses (Data Validation plugin), commandlets for headless runs, Interchange for import pipelines, Slate for custom editors.
- Unity: Editor scripts (`EditorWindow`, `AssetPostprocessor`, `ScriptedImporter`), run headless with `-batchmode -executeMethod`.
- Godot: `@tool` scripts, EditorPlugin, EditorImportPlugin; headless `--script` runs.
