# Platform certification and compliance
## When to use
- Preparing a build for console or store submission: platform requirements (Xbox XRs, PlayStation TRC, Nintendo guidelines), store policies (Steam, Epic, mobile), first-party features (achievements, presence, activities).
- Not for: age ratings and legal → `legal-ratings`; build mechanics → `build-ci-release`.
## Inputs
- The current requirement documents for each platform (under NDA except public Xbox XRs; read them from the developer portal, never guess), the submission schedule, platform SDK versions, previous failure reports.
## Method
1. Build a requirement checklist per platform with an owner and a test for each item; reuse the previous submission's list and update to the current requirement version.
2. Cover the common areas: user sign-in/out and profile switching, suspend/resume, controller disconnect, save data integrity and space errors, network loss, system language and region, platform terminology and glyphs, achievements/trophies, parental controls, install and patch size, crash-free and memory limits.
3. Test on retail-configured dev kits with the submission build configuration.
4. Track waivers explicitly; never assume one.
5. Pre-check before submission; keep the failure report (for example an Xbox FMA) items as regression tests.
## Checks
- Every checklist item has a pass result on the submission build with evidence (video, log, screenshot).
- Long-play soak and suspend/resume cycles without crash or leak.
- Achievement/trophy unlocks tested from a clean profile; all unlockable.
## Pitfalls
- Using another platform's terminology (for example "controller" vs the platform's official name) or wrong button glyphs.
- Save corruption when power is cut or the user signs out mid-save.
- Relying on an old requirement version; requirements change between submissions.
## Engine notes
- Unreal: platform extensions and SDKs come from the console developer programs; use `UGameplayStatics`/Online Subsystem platform implementations, `FCoreDelegates` application lifecycle delegates (suspend/resume), platform save game system.
- Unity: platform packages from the console programs; `Application` lifecycle callbacks; PlayerPrefs not for console saves.
- Godot: console ports go through third-party porting partners; plan cert work with them.
