"""Nearest-surface texture transfer: for every texel of 'Body', find the closest point on 'Clean' and copy
its base colour / emission / roughness. Robust on thin parts (horn tips) where ray-cast baking picks up the
wrong surface. Also saves the per-texel object-space position (body_position.npy) for face masking.

Usage: blender -b --factory-startup -P scripts/body/transfer_maps.py -- <baked.blend> <out.blend> <tex_dir>
Expects 'Body' (UVs + material DragonBody with image nodes) and 'Clean' (source, glTF material) in the blend.
"""
import os, sys, time
import bpy, numpy as np
from mathutils.bvhtree import BVHTree
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
IN, OUT, TEX = args[0], args[1], os.path.abspath(args[2])
t0 = time.time()
bpy.ops.wm.open_mainfile(filepath=IN)
sc = bpy.context.scene
src, body = bpy.data.objects.get("ColorSrc") or bpy.data.objects["Clean"], bpy.data.objects["Body"]
src.hide_set(False)
nt = body.data.materials[0].node_tree
SIZE = nt.nodes["basecolor"].image.size[0]

# ---- 1. object-space position of every Body texel (bake without selected-to-active)
pos_img = nt.nodes["position"].image
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 1
sc.render.bake.use_selected_to_active = False; sc.render.bake.margin = 12
for o in sc.objects: o.select_set(o == body)
bpy.context.view_layer.objects.active = body
for n in nt.nodes: n.select = False
nt.nodes.active = nt.nodes["position"]; nt.nodes["position"].select = True
bpy.ops.object.bake(type="POSITION")
P = np.array(pos_img.pixels[:], np.float32).reshape(SIZE, SIZE, 4)[..., :3]
valid = np.abs(P).sum(-1) > 1e-6
np.save(os.path.join(TEX, "body_position.npy"), np.where(valid[..., None], P, np.nan).astype(np.float32))
print(f"position baked, {valid.sum()} texels  {time.time()-t0:.0f}s", flush=True)

# ---- 2. closest point on the source surface
dg = bpy.context.evaluated_depsgraph_get()
src_eval = src.evaluated_get(dg); sm = src_eval.to_mesh()
sm.calc_loop_triangles()
bvh = BVHTree.FromObject(src, dg)
tri_v = np.array([t.vertices[:] for t in sm.loop_triangles]); tri_l = np.array([t.loops[:] for t in sm.loop_triangles])
poly_to_tri = {}
for i, t in enumerate(sm.loop_triangles): poly_to_tri.setdefault(t.polygon_index, []).append(i)
V = np.array([v.co[:] for v in sm.vertices])
UV = np.array([d.uv[:] for d in sm.uv_layers.active.data])
pts = P[valid]
loc = np.empty_like(pts); tri = np.empty(len(pts), np.int64)
for k, p in enumerate(pts):
    l, _, fi, _ = bvh.find_nearest(Vector(p))
    loc[k] = l
    cand = poly_to_tri[fi]
    tri[k] = cand[0]
    if len(cand) > 1:  # pick the triangle of the polygon that contains the point (smallest bary violation)
        best = None
        for c in cand:
            a, b, cc = V[tri_v[c]]
            w = np.linalg.lstsq(np.stack([a - cc, b - cc], 1), l[:] - cc, rcond=None)[0]
            viol = max(0, -w[0]) + max(0, -w[1]) + max(0, w.sum() - 1)
            if best is None or viol < best: best, tri[k] = viol, c
print(f"nearest queries done  {time.time()-t0:.0f}s", flush=True)

# barycentric coords (vectorised)
A, B, C = V[tri_v[tri, 0]], V[tri_v[tri, 1]], V[tri_v[tri, 2]]
v0, v1, v2 = B - A, C - A, loc - A
d00 = (v0 * v0).sum(1); d01 = (v0 * v1).sum(1); d11 = (v1 * v1).sum(1); d20 = (v2 * v0).sum(1); d21 = (v2 * v1).sum(1)
den = np.maximum(d00 * d11 - d01 * d01, 1e-20)
wb = (d11 * d20 - d01 * d21) / den; wc = (d00 * d21 - d01 * d20) / den; wa = 1 - wb - wc
bary = np.clip(np.stack([wa, wb, wc], 1), 0, 1); bary /= bary.sum(1, keepdims=True)
uv = (UV[tri_l[tri]] * bary[..., None]).sum(1)

def dilate(px, valid, iters=24):
    """Grow island colours outward into empty texels (prevents dark seams from texture filtering/mipmaps)."""
    px = px.copy(); filled = valid.copy()
    for _ in range(iters):
        if filled.all(): break
        acc = np.zeros_like(px); cnt = np.zeros(filled.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            f = np.roll(np.roll(filled, dy, 0), dx, 1); p = np.roll(np.roll(px, dy, 0), dx, 1)
            acc += p * f[..., None]; cnt += f
        grow = (~filled) & (cnt > 0)
        px[grow] = acc[grow] / cnt[grow][:, None]; filled |= grow
    if not filled.all(): px[~filled] = px[filled].mean(0)
    return px

# ---- 3. sample the source textures and write the Body maps
smat = src.data.materials[0].node_tree
def src_image(socket_name):
    bsdf = smat.nodes["Principled BSDF"]
    links = bsdf.inputs[socket_name].links
    node = links[0].from_node if links else None
    while node is not None and node.type != "TEX_IMAGE":  # walk through separate-colour etc.
        node = node.inputs[0].links[0].from_node if node.inputs and node.inputs[0].links else None
    return node.image if node else None

def sample(img, uv):
    w, h = img.size
    px = np.array(img.pixels[:], np.float32).reshape(h, w, 4)
    x = np.clip(uv[:, 0] * w - 0.5, 0, w - 1); y = np.clip(uv[:, 1] * h - 0.5, 0, h - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int); x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    return (px[y0, x0] * (1 - fx) * (1 - fy) + px[y0, x1] * fx * (1 - fy) + px[y1, x0] * (1 - fx) * fy + px[y1, x1] * fx * fy)

for name, sock, chan in [("basecolor", "Base Color", None), ("emission", "Emission Color", None), ("roughness", "Roughness", 1)]:
    simg = src_image(sock)
    if simg is None:
        print("no source image for", sock); continue
    vals = sample(simg, uv)
    out = np.zeros((SIZE, SIZE, 4), np.float32); out[..., 3] = 1
    if chan is not None:  # glTF metallicRoughness: roughness in G
        out[valid, :3] = vals[:, chan:chan + 1]
    else:
        out[valid, :3] = vals[:, :3]
    # Prefer the ray-cast bake from bake_body.py (projects along the surface normal); the nearest-surface value
    # is only a fallback for texels whose ray missed (magenta sentinel). Nearest lookups alone jump to the dark
    # inner walls of grooves (belly plates) where the decimated surface cuts across them.
    img = nt.nodes[name].image
    baked = np.array(img.pixels[:], np.float32).reshape(SIZE, SIZE, 4)
    missed = (np.abs(baked[..., 0] - 1) < 0.02) & (baked[..., 1] < 0.02) & (np.abs(baked[..., 2] - 1) < 0.02)
    use_baked = valid & ~missed
    out[use_baked, :3] = baked[use_baked, :3]
    print(f"  {name}: ray-baked {use_baked.sum()} texels, nearest-surface fallback {(valid & missed).sum()}", flush=True)
    out = dilate(out, valid)
    img.pixels = out.ravel()
    img.filepath_raw = os.path.join(TEX, f"body_{name}.png"); img.file_format = "PNG"; img.save()
    print(f"transferred {name} (from {simg.name})  {time.time()-t0:.0f}s", flush=True)

src.hide_set(True)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("saved", OUT)
