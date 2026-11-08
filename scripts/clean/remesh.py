"""Clean the Pixal3D dragon: weld -> voxel remesh -> Taubin smooth -> decimate.
Saves a blend with 'Original' (textured) and 'Clean' objects.
Usage: blender -b --factory-startup -P remesh.py -- <in.glb> <out.blend> <voxel> <taubin_iters> <target_tris>
   (or `python3 remesh.py ...` with the `bpy` pip module)"""
import sys, time
import numpy as np
import bpy, bmesh

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
GLB, OUT = args[0], args[1]
VOX, ITERS, TARGET = float(args[2]), int(args[3]), int(args[4])
t0 = time.time()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
orig = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
orig.name = "Original"

clean = orig.copy(); clean.data = orig.data.copy(); clean.name = "Clean"
bpy.context.scene.collection.objects.link(clean)
clean.data.materials.clear()

bm = bmesh.new(); bm.from_mesh(clean.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
bnd = sum(1 for e in bm.edges if e.is_boundary)
bm.to_mesh(clean.data); bm.free()
print(f"welded: boundary edges left {bnd}  {time.time()-t0:.0f}s", flush=True)

bpy.context.view_layer.objects.active = clean
for o in bpy.context.scene.objects: o.select_set(o == clean)
rm = clean.modifiers.new("Remesh", "REMESH"); rm.mode = "VOXEL"; rm.voxel_size = VOX; rm.adaptivity = 0.0
bpy.ops.object.modifier_apply(modifier="Remesh")
me = clean.data
print(f"remeshed: {len(me.vertices)} verts {len(me.polygons)} faces  {time.time()-t0:.0f}s", flush=True)

# Taubin smoothing (lambda/mu) — removes lumps without shrinking
n = len(me.vertices)
co = np.empty(n * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
ed = np.empty(len(me.edges) * 2, dtype=np.int64); me.edges.foreach_get("vertices", ed); ed = ed.reshape(-1, 2)
src, dst = np.r_[ed[:, 0], ed[:, 1]], np.r_[ed[:, 1], ed[:, 0]]
deg = np.maximum(np.bincount(src, minlength=n), 1).astype(float)

def avg_neighbours(x):  # uniform Laplacian: mean of 1-ring (numpy only; Blender's Python has no scipy)
    return np.stack([np.bincount(src, weights=x[dst, k], minlength=n) for k in range(3)], 1) / deg[:, None]

lam, mu = 0.5, -0.53
for i in range(ITERS):
    co = co + lam * (avg_neighbours(co) - co)
    co = co + mu * (avg_neighbours(co) - co)
me.vertices.foreach_set("co", co.ravel()); me.update()
print(f"smoothed x{ITERS}  {time.time()-t0:.0f}s", flush=True)

dec = clean.modifiers.new("Decimate", "DECIMATE"); ntris = sum(len(p.vertices) - 2 for p in me.polygons)  # remesh makes quads; target is triangles
dec.ratio = min(1.0, TARGET / ntris); dec.use_collapse_triangulate = True
bpy.ops.object.modifier_apply(modifier="Decimate")
for p in clean.data.polygons: p.use_smooth = True
print(f"decimated: {len(clean.data.polygons)} tris  {time.time()-t0:.0f}s", flush=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("saved", OUT)
