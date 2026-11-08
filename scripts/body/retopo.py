"""Quad retopology of the clean dragon with Blender's QuadriFlow.
Usage: blender -b --factory-startup -P scripts/body/retopo.py -- <clean.glb> <out.blend> [target_quads=12000]
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
body = src.copy(); body.data = src.data.copy(); body.name = "Body"
bpy.context.scene.collection.objects.link(body)
body.data.materials.clear()
# weld UV-seam splits so QuadriFlow sees one manifold surface
bm = bmesh.new(); bm.from_mesh(body.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
bm.to_mesh(body.data); bm.free()
while body.data.uv_layers: body.data.uv_layers.remove(body.data.uv_layers[0])
for o in bpy.context.scene.objects: o.select_set(o == body)
bpy.context.view_layer.objects.active = body
r = bpy.ops.object.quadriflow_remesh(target_faces=TARGET, use_preserve_sharp=False, use_preserve_boundary=False,
                                     preserve_attributes=False, smooth_normals=True, mode="FACES", seed=0)
print("quadriflow", r, f"{time.time()-t0:.0f}s", flush=True)
me = body.data
quads = sum(1 for p in me.polygons if len(p.vertices) == 4)
print(f"Body: {len(me.vertices)} verts, {len(me.polygons)} faces ({quads} quads), tris={sum(len(p.vertices)-2 for p in me.polygons)}")
for p in me.polygons: p.use_smooth = True
src.hide_set(True); src.hide_render = True
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("saved", OUT)
