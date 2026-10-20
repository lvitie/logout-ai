# Localization and internationalization
## When to use
- Making text, audio, UI and data translatable (internationalization), running the translation and LQA pipeline, adding a language, fonts and right-to-left support.
- Not for: writing source text → `narrative-dialogue`; VO recording → `sound-music`.
## Inputs
- Target languages and regions, string tables or source files, glossary and style guides, character limits, VO language list, vendor and file format (PO, XLIFF, CSV), font licenses.
## Method
1. Internationalize first: every player-facing string in a localizable type with a stable key and a context note; no string concatenation, use format arguments with named placeholders; plural and gender rules.
2. Gather and export strings; send with screenshots, character limits and the glossary.
3. Import translations; build per-culture content; fonts cover every glyph (CJK, Cyrillic, Arabic) with fallbacks.
4. Pseudo-localize (accented and lengthened text) to find hard-coded strings and overflow early.
5. LQA: native testers in the running game check context, truncation, glyphs and terminology; bugs flow back to the vendor.
6. Locale formats: numbers, dates, currency and sorting from the platform locale.
## Checks
- Pseudo-localized build shows no unlocalized text and no truncation.
- Every language: font coverage, longest string fits, RTL layout mirrored where supported.
- Platform system language selects the right culture; fallback language defined.
## Pitfalls
- Text baked into textures; keys reused for different contexts; changed source text that keeps stale translations.
- Assuming one plural form; splitting sentences across widgets.
- Late string freeze: translations arrive after content lock.
## Engine notes
- Unreal: FText with String Tables, Localization Dashboard (gather, export/import PO, compile), `NSLOCTEXT`/`LOCTEXT`, Localize UAT command for automation, `-culture=` to test, pseudo-localization via the dashboard, culture-specific asset localization.
- Unity: Localization package (string and asset tables, Smart Strings, pseudo-localization), TextMeshPro font assets with fallbacks.
- Godot: TranslationServer with PO or CSV, `tr()` and `tr_n()`, auto-translate on Controls, pseudolocalization project settings, BiDi text support.
