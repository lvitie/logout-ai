# Shaders and materials
- Name the target (platform, quality tier) and the budget (instruction count, samplers, texture memory) before editing; record the numbers before and after.
- Prefer material functions, parameters and instances over duplicated graphs; keep permutations low.
- Check precision, branching and overdraw on the lowest supported tier; no per-pixel work that can move to vertex or a texture.
- Verify visually in the editor or a capture and name the asset or shader files touched.
