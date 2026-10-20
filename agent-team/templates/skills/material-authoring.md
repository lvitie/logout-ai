# Material authoring
- Name the target (platform, quality tier) and budget (instructions, samplers, texture memory) first; record the numbers before and after.
- Build a master material with parameters and author variants as instances; reuse material functions instead of copying graphs.
- Keep static switches and permutations few; share texture samplers and pack masks into channels (ORM-style) where the engine allows.
- Match the existing naming, parameter groups and texture import settings (sRGB, compression, mips); name the asset paths touched.
- Verify visually in the editor or a capture on the lowest supported tier.
