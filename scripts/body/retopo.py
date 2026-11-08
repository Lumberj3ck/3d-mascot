"""Quad retopology of the clean dragon with Blender's QuadriFlow.
Usage: blender -b --factory-startup -P scripts/body/retopo.py -- <clean.glb> <out.blend> [target=12000] [color_src.glb|-] [quadriflow|decimate]
mode quadriflow: all-quad remesh (target = quads); decimate: collapse decimation (target = triangles).
color_src (optional): textured mesh (object 'ColorSrc') used for the colour/roughness/emission bakes, while the
normal map is baked from <clean.glb>. The dragon uses the raw Pixal3D mesh: the smoothed mesh has hidden folded
triangles inside grooves whose dark texels show up as specks when baked onto a new surface.
Result objects: 'Clean' (textured source, hidden) and 'Body' (quad mesh, no UVs yet).
"""
import sys, time
import bpy, bmesh

args = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = args[0], args[1]
TARGET = int(args[2]) if len(args) > 2 else 12000
t0 = time.time()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
src = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
src.name = "Clean"
COLOR_SRC = args[3] if len(args) > 3 and args[3] != "-" else None
MODE = args[4] if len(args) > 4 else "quadriflow"
body = src.copy(); body.data = src.data.copy(); body.name = "Body"
bpy.context.scene.collection.objects.link(body)
body.data.materials.clear()
# weld UV-seam splits so QuadriFlow sees one manifold surface
bm = bmesh.new(); bm.from_mesh(body.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.to_mesh(body.data); bm.free()
while body.data.uv_layers: body.data.uv_layers.remove(body.data.uv_layers[0])
for o in bpy.context.scene.objects: o.select_set(o == body)
bpy.context.view_layer.objects.active = body
if MODE == "decimate":
    # Collapse-decimate the (already smooth) surface instead of quad-remeshing: QuadriFlow folds the paper-thin
    # wing membranes; decimation keeps them and removes tiny/bunched edges first. TARGET = triangles.
    ntri = sum(len(p.vertices) - 2 for p in body.data.polygons)
    dec = body.modifiers.new("Decimate", "DECIMATE"); dec.ratio = TARGET / ntri; dec.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier="Decimate")
    r = "decimated"
else:
  r = bpy.ops.object.quadriflow_remesh(target_faces=TARGET, use_preserve_sharp=False, use_preserve_boundary=False,
                                       preserve_attributes=False, smooth_normals=True, mode="FACES", seed=0)
print("quadriflow", r, f"{time.time()-t0:.0f}s", flush=True)
me = body.data
quads = sum(1 for p in me.polygons if len(p.vertices) == 4)
print(f"Body: {len(me.vertices)} verts, {len(me.polygons)} faces ({quads} quads), tris={sum(len(p.vertices)-2 for p in me.polygons)}")
for p in me.polygons: p.use_smooth = True
if COLOR_SRC:  # extra textured source for colour bakes ('ColorSrc'); the normal map is still baked from 'Clean'
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=COLOR_SRC)
    csrc = [o for o in bpy.context.scene.objects if o not in before and o.type == "MESH"][0]
    csrc.name = "ColorSrc"; csrc.hide_set(True); csrc.hide_render = True
    print("colour source:", COLOR_SRC, flush=True)
src.hide_set(True); src.hide_render = True
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("saved", OUT)
