# Blender DCC skills

Research behind the four Blender task skills in `agent-team/templates/skills/`: `blender-geometry-nodes`,
`blender-rigging`, `blender-animation` and `blender-vfx`. Each skill is listed in `INDEX.md` and in the `skill:`
frontmatter of `technical_artist` (all four) and `vfx` (`blender-vfx`, `blender-geometry-nodes`). No dedicated animation
agent exists, so `technical_artist` covers rigging and animation. `gameplay` keeps the in-engine `animation` skill only.

## Version

- Checked against **Blender 5.2 LTS** (released 2026-07-14), which is the current stable and the current LTS. The
  previous releases are 5.1 (2026-03-17), 5.0 (2025-11-18) and 4.5 LTS (2025-07-15). Source:
  <https://www.blender.org/download/releases/>.
- Manual: <https://docs.blender.org/manual/en/5.2/>. Python API: <https://docs.blender.org/api/5.2/>. On 2026-10-20 the
  `latest` and `current` URLs both served 5.2.
- The research was done on 2026-10-20 from first-party pages: the Blender Manual, the API reference, the developer
  release notes for 3.1–5.2, Blender Studio and devtalk. Engine facts come from Epic's and Unity's documentation.
  Blender was not run: the snippets are checked against the docs and parsed with Python's `ast`, not executed.

## Size and loading

- `blender-*` skills may have up to 200 lines and 1,800 words. All other skills keep the 60-line and 450-word cap, and
  the library is capped at 45 skills. `tests/test_skill_library.py` enforces both caps.
- Agents read these skills on demand from the "Skills you have" table. Attaching one inline (`team new --skill` or from
  the Producer) prints the over-6000-chars warning (`team.py`, `CLIP`) and costs tokens. Prefer the frontmatter route.

## Version-sensitive API (per skill)

`blender-geometry-nodes`
- 4.0: `tree.interface.new_socket` replaces `tree.inputs`/`tree.outputs`. Node sockets are indexed by identifier.
  `is_modifier` assets appear in the Add Modifier menu.
- 4.1: the Bake node arrives. Store Named Attribute and some other nodes get dynamic sockets.
- 4.2: modifier input IDProperties get fixed types. `new_panel` loses its `parent` argument.
- 4.3: bakes are packed into the .blend by default.
- 5.0: bundles, closures and volume grid sockets arrive. Some inputs become menu sockets. `id` becomes a generic
  attribute and Random Value output changes. The deprecated combine/separate nodes are removed.
- 5.1: `realize_to_point_domain` restores 5.0 behavior. Old node tools must be re-saved.
- 5.2:
  - `new_socket` is keyword-only after `name`.
  - Modifier inputs move to `mod.properties.inputs.<identifier>.value`, so `mod["Socket_N"]` stops working.
  - Lists and geometry bundles arrive, and Compare and Random Value socket identifiers change.
  - Empties can carry GN modifiers.

`blender-rigging`
- 4.0: bone collections and bone colors replace layers and bone groups. `edit_bones.new` no longer assigns a collection.
- 4.1: bone collections become hierarchical (`collections_all`).
- 4.4: removing a modifier, constraint or shape key also removes its drivers.
- 4.5: the C++ FBX importer arrives as experimental.
- 5.0:
  - The C++ FBX importer becomes the default (`bpy.ops.wm.fbx_import`). The Python FBX exporter stays.
  - Selection and visibility move to pose bones, and `Bone.select` is removed.
- 5.1: renaming a bone keeps its drivers. FBX exports shape-key normals. Apply to Basis arrives.
- 5.2: the Duplicate and Rename bone operator arrives. Rigify is still a bundled core add-on.

`blender-animation`
- 3.1: an action can have its own frame range (`use_frame_range`).
- 3.2: `context.temp_override` arrives; context dicts for operators were removed in 4.0.
- 3.5: the legacy pose library is removed in favour of pose assets.
- 4.4: all actions become slotted actions (layers, strips, channelbags), and glTF exports slots.
- 5.0:
  - `Action.fcurves`, `Action.groups` and `Action.id_root` are removed.
  - `anim_utils.action_ensure_channelbag_for_slot` and `channelbag.fcurves.ensure` arrive.
  - `fcurves.new(action_group=)` becomes `group_name=`.
- 5.1: the Gaussian Smooth F-curve modifier arrives. The legacy-action converter is removed.

`blender-vfx`
- 3.3: the Curves hair object arrives. Particle hair is "end of life".
- 4.0: AgX becomes the default view transform. Passing context dicts to operators is removed.
- 4.2: the EEVEE engine id becomes `BLENDER_EEVEE_NEXT`.
- 5.0:
  - The engine id goes back to `BLENDER_EEVEE`.
  - `scene.node_tree` becomes `scene.compositing_node_group`, and `use_nodes` does nothing.
  - The File Output node is redesigned.
  - LZO/LZMA point caches are dropped, and Mantaflow vorticity scaling changes.
  - The Alembic `visible_objects_only` option is removed.
- 5.2: experimental Geometry Nodes cloth and hair (XPBD). Mantaflow receives no new features.

## Caveats

- No snippet was executed in Blender. Before trusting a skill on another version, run it headless with
  `blender -b --python-exit-code 1 --python` against that version.
- Exact context members for `bpy.ops.fluid.bake_all`, `bpy.ops.nla.bake` and `geometry_node_bake_single` are not
  documented. The `temp_override(active_object=..., selected_objects=...)` pattern is inferred from the operator polls.
- Rigify's `bpy.ops.pose.rigify_generate` is not in the API reference; it was confirmed in the add-on source. The
  advice that DEF bones parented to ORG bones break deform-only export comes from devtalk and a Blender Studio blog,
  not from the Rigify developers.
- Two pieces of Unreal advice are community lore, not documented by Epic or Blender: naming the armature object
  `Armature` to avoid an extra root bone, and setting the scene unit scale to 0.01. The skills recommend meters plus
  Convert Scene Unit and a re-import check instead.
- The fluid VDB grid names come from Blender's fluid DNA source on the GitHub mirror, not from the manual.
- There is no first-party Blender exporter for vertex animation textures or for packing flipbook atlases. The skills
  give script outlines, so treat those as project code that needs its own test. Unreal's AnimToTexture is experimental
  and works on skeletal meshes only.
- Unreal Sparse Volume Textures are experimental: Windows editor builds only, DX11/12 only, no mobile.
- USD instancing (point instancer) and the glTF Geometry Nodes instance export are experimental in the Blender exporters.
- Geometry-nodes bake files are a Blender cache, not an interchange format, and may not load in another Blender version.
- Mantaflow is still shipped but gets no new features (code.blender.org, 2023). Bake results changed in 5.0, so pin the
  Blender version for every sim that ships.

## Sources

Blender (first-party):
- <https://www.blender.org/download/releases/>
- <https://docs.blender.org/manual/en/5.2/>
- <https://docs.blender.org/api/5.2/>
- <https://docs.blender.org/api/current/bpy.types.NodeTreeInterface.html>
- <https://docs.blender.org/api/5.2/bpy.types.NodesModifier.html>
- <https://docs.blender.org/api/current/bpy.types.NodesModifierBake.html>
- <https://docs.blender.org/api/current/bpy.types.GeometryNodeTree.html>
- <https://docs.blender.org/api/current/bpy.types.GeometryNodeSimulationInput.html>
- <https://docs.blender.org/api/current/bpy.types.BlendDataMeshes.html>
- <https://docs.blender.org/api/current/bpy.types.AssetMetaData.html>
- <https://docs.blender.org/api/current/bpy.types.EditBone.html>
- <https://docs.blender.org/api/current/info_gotchas_armatures_and_bones.html>
- <https://docs.blender.org/api/current/bpy.types.BoneCollections.html>
- <https://docs.blender.org/api/current/bpy.types.KinematicConstraint.html>
- <https://docs.blender.org/api/current/bpy.types.Driver.html>
- <https://docs.blender.org/api/current/bpy.types.DataTransferModifier.html>
- <https://docs.blender.org/api/current/bpy.types.Action.html>
- <https://docs.blender.org/api/current/bpy.types.ActionChannelbagFCurves.html>
- <https://docs.blender.org/api/current/bpy_extras.anim_utils.html>
- <https://docs.blender.org/api/current/bpy.types.NlaStrip.html>
- <https://docs.blender.org/api/current/bpy.types.FluidDomainSettings.html>
- <https://docs.blender.org/api/current/bpy.types.FluidFlowSettings.html>
- <https://docs.blender.org/api/current/bpy.types.PointCache.html>
- <https://docs.blender.org/api/current/bpy.types.RigidBodyWorld.html>
- <https://docs.blender.org/api/current/bpy.types.FieldSettings.html>
- <https://docs.blender.org/api/current/bpy.ops.object.html>
- <https://docs.blender.org/api/current/bpy.ops.nla.html>
- <https://docs.blender.org/api/current/bpy.ops.poselib.html>
- <https://docs.blender.org/api/current/bpy.ops.fluid.html>
- <https://docs.blender.org/api/current/bpy.ops.rigidbody.html>
- <https://docs.blender.org/api/current/bpy.ops.ptcache.html>
- <https://docs.blender.org/api/current/bpy.ops.export_scene.html>
- <https://docs.blender.org/api/current/bpy.ops.wm.html>
- <https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/performance.html>
- <https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/baking.html>
- <https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/simulation/simulation_zone.html>
- <https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/instances.html>
- <https://docs.blender.org/manual/en/latest/animation/actions.html>
- <https://docs.blender.org/manual/en/latest/animation/armatures/skinning/parenting.html>
- <https://docs.blender.org/manual/en/latest/advanced/scripting/security.html>
- <https://docs.blender.org/manual/en/latest/addons/rigify/index.html>
- <https://docs.blender.org/manual/en/5.2/addons/import_export/scene_fbx.html>
- <https://docs.blender.org/manual/en/5.2/addons/import_export/scene_gltf2.html>
- <https://docs.blender.org/manual/en/5.2/files/import_export/alembic.html>
- <https://docs.blender.org/manual/en/5.2/files/import_export/usd.html>
- <https://docs.blender.org/manual/en/5.2/physics/fluid/type/domain/cache.html>
- <https://docs.blender.org/manual/en/5.2/physics/particles/hair/index.html>
- <https://docs.blender.org/manual/en/5.2/advanced/command_line/render.html>
- <https://docs.blender.org/manual/en/5.2/render/color_management/displays_views.html>
- <https://developer.blender.org/docs/release_notes/4.0/python_api/>
- <https://developer.blender.org/docs/release_notes/4.0/animation_rigging/>
- <https://developer.blender.org/docs/release_notes/4.1/animation_rigging/>
- <https://developer.blender.org/docs/release_notes/4.2/python_api/>
- <https://developer.blender.org/docs/release_notes/4.3/geometry_nodes/>
- <https://developer.blender.org/docs/release_notes/4.4/python_api/>
- <https://developer.blender.org/docs/release_notes/4.4/animation_rigging/>
- <https://developer.blender.org/docs/release_notes/4.5/pipeline_assets_io/>
- <https://developer.blender.org/docs/release_notes/5.0/python_api/>
- <https://developer.blender.org/docs/release_notes/5.0/geometry_nodes/>
- <https://developer.blender.org/docs/release_notes/5.0/pipeline_io/>
- <https://developer.blender.org/docs/release_notes/5.0/physics/>
- <https://developer.blender.org/docs/release_notes/5.0/color_management/>
- <https://developer.blender.org/docs/release_notes/5.1/geometry_nodes/>
- <https://developer.blender.org/docs/release_notes/5.1/animation_rigging/>
- <https://developer.blender.org/docs/release_notes/5.2/python_api/>
- <https://developer.blender.org/docs/release_notes/5.2/geometry_nodes/>
- <https://developer.blender.org/docs/release_notes/5.2/animation_rigging/>
- <https://developer.blender.org/docs/release_notes/5.2/physics/>
- <https://developer.blender.org/docs/features/animation/rigify/utils/naming/>
- <https://devtalk.blender.org/t/changes-to-add-on-and-themes-bundling-4-2-onwards/34593>
- <https://devtalk.blender.org/t/rigify-parent-bones-of-some-def-bones/14745>
- <https://studio.blender.org/blog/character-rigging-for-project-dogwalk/>
- <https://code.blender.org/2023/02/blender-release-cycle-update/>

Engines:
- <https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-import-options-reference-in-unreal-engine>
- <https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-skeletal-mesh-pipeline-in-unreal-engine>
- <https://dev.epicgames.com/documentation/unreal-engine/units-of-measurement-in-unreal-engine>
- <https://dev.epicgames.com/documentation/en-us/unreal-engine/auto-retargeting-in-unreal-engine>
- <https://dev.epicgames.com/documentation/en-us/unreal-engine/ik-rig-animation-retargeting-in-unreal-engine>
- <https://dev.epicgames.com/documentation/en-us/unreal-engine/root-motion-in-unreal-engine>
- <https://dev.epicgames.com/documentation/en-us/unreal-engine/sparse-volume-textures-in-unreal-engine>
- <https://dev.epicgames.com/documentation/en-us/unreal-engine/alembic-file-importer-in-unreal-engine>
- <https://dev.epicgames.com/documentation/en-us/unreal-engine/niagara-flipbook-baker-quick-start-guide-in-unreal-engine>
- <https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Plugins/AnimToTextureEditor/UAnimToTextureBPLibrary>
- <https://docs.unity3d.com/Manual/RootMotion.html>
- <https://docs.unity3d.com/Manual/class-AnimationClip.html>
- <https://docs.unity3d.com/Manual/ConfiguringtheAvatar.html>
- <https://docs.unity3d.com/Manual/FBXImporter-Model.html>
- <https://docs.unity3d.com/Manual/PartSysTexSheetAnimModule.html>
- <https://docs.unity3d.com/Packages/com.unity.formats.alembic@2.4/manual/index.html>
