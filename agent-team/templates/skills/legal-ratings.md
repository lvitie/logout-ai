# Legal, compliance and age ratings
## When to use
- Age rating submissions and content descriptors, monetization disclosure (random items), privacy and children's data, third-party license compliance, EULA and terms, likeness and music rights, regional content restrictions.
- Not for: platform technical requirements → `platform-cert`. This skill prepares evidence and flags risks; legal decisions belong to the studio's counsel.
## Inputs
- Target regions and platforms, content inventory (violence, language, sexual content, drugs, gambling-like mechanics, user interaction), monetization design, data collection list, third-party asset and code licenses.
## Method
1. Ratings: inventory content per category with timestamps or captures; fill the rating questionnaires (IARC for digital storefronts; ESRB, PEGI, USK, CERO, ClassInd or others for physical or where required); keep content changes in sync with the submitted answers.
2. Monetization: disclose paid random items where required (for example ESRB/PEGI in-game purchase notices); show odds; check regions with loot box rules.
3. Privacy: data inventory, legal basis, consent flows, age gating and children's rules (COPPA, GDPR-K, UK Age Appropriate Design Code), deletion requests.
4. Licenses: list every third-party library, font, asset, middleware and music track with its license and attribution requirement; ship the notices screen.
5. Flag every open question to counsel with the evidence; never assume approval.
## Checks
- Rating questionnaire answers match the current build content; changes after rating are re-evaluated.
- Credits and third-party notices complete; no asset without a known license.
- Consent and age-gate flows tested; telemetry respects them.
## Pitfalls
- Content added after rating submission (new gore, chat, purchases) without resubmission.
- Fonts or audio libraries licensed for prototypes, not for shipping or streaming.
- Engine EULA royalty and notice terms overlooked.
## Engine notes
- Unreal: follow the Unreal Engine EULA (royalty reporting, notices); include third-party notices from engine plugins; mark text and assets that differ per region with culture-specific assets.
- Unity: Unity terms and plan requirements (splash screen, plan thresholds); package license files.
- Godot: MIT license notice for Godot and its third-party components (see `Engine.get_license_info()`).
