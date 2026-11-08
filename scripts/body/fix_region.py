"""Local repair of the production body (used where the source mesh had the hip-spike artifact).

mode "mesh":   smooth Body vertices inside a sphere (smoothstep falloff, Laplacian + Taubin). Run after retopo.
mode "despike": remove a protrusion from the quad Body: vertices inside the sphere and beyond x > XCUT (env,
               default 0.205) connected to the outermost one are relaxed into a membrane (rim fixed), then the
               sphere is smoothed. Even quad spacing keeps this well-behaved (unlike on the raw triangle mesh).
mode "normal": blend the baked normal map to flat (0.5,0.5,1) and the base colour toward the surrounding
               colour inside the sphere, using the per-texel positions
               written by transfer_maps.py (body_position.npy). Run after transfer, before export.

Usage: blender -b --factory-startup -P scripts/body/fix_region.py -- <mode> <in.blend> <out.blend> <tex_dir> cx cy cz r
"""
import sys, os
import bpy, numpy as np

a = sys.argv[sys.argv.index("--") + 1:]
MODE, IN, OUT, TEX = a[0], a[1], a[2], a[3]
C = np.array([float(v) for v in a[4:7]]); R = float(a[7])
bpy.ops.wm.open_mainfile(filepath=IN)
body = bpy.data.objects["Body"]

def falloff(d):
    w = np.clip(1 - d / R, 0, 1); return w * w * (3 - 2 * w)

def mesh_arrays(me):
    n = len(me.vertices)
    co = np.empty(n * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
    ed = np.empty(len(me.edges) * 2, np.int64); me.edges.foreach_get("vertices", ed); ed = ed.reshape(-1, 2)
    src, dst = np.r_[ed[:, 0], ed[:, 1]], np.r_[ed[:, 1], ed[:, 0]]
    deg = np.maximum(np.bincount(src, minlength=n), 1)
    avg = lambda P: np.stack([np.bincount(src, weights=P[dst, k], minlength=n) for k in range(3)], 1) / deg[:, None]
    return n, co, src, dst, avg

if MODE == "despike":
    me = body.data
    n, co, src, dst, avg = mesh_arrays(me)
    xcut = float(os.environ.get("XCUT", "0.205"))
    cand = (np.linalg.norm(co - C, axis=1) < R) & (co[:, 0] > xcut)
    tip = int(np.argmax(np.where(cand, co[:, 0], -1)))
    sel = np.zeros(n, bool); sel[tip] = True; frontier = [tip]
    nbrs = {}
    for s_, d_ in zip(src, dst): nbrs.setdefault(s_, []).append(d_)
    while frontier:
        v = frontier.pop()
        for w in nbrs.get(v, []):
            if cand[w] and not sel[w]: sel[w] = True; frontier.append(w)
    P = co.copy()
    for _ in range(400): P[sel] = avg(P)[sel]
    w = falloff(np.linalg.norm(P - C, axis=1))[:, None]
    for _ in range(40): P = P + w * 0.6 * (avg(P) - P)
    for _ in range(20):
        P = P + w * 0.5 * (avg(P) - P); P = P + w * -0.53 * (avg(P) - P)
    me.vertices.foreach_set("co", P.ravel()); me.update()
    print(f"despike: {sel.sum()} spike verts relaxed (tip {np.round(co[tip], 3)}), max move {np.linalg.norm(P - co, axis=1).max():.4f}", flush=True)
elif MODE == "mesh":
    me = body.data; n = len(me.vertices)
    co = np.empty(n * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
    ed = np.empty(len(me.edges) * 2, np.int64); me.edges.foreach_get("vertices", ed); ed = ed.reshape(-1, 2)
    src, dst = np.r_[ed[:, 0], ed[:, 1]], np.r_[ed[:, 1], ed[:, 0]]
    deg = np.maximum(np.bincount(src, minlength=n), 1)
    avg = lambda P: np.stack([np.bincount(src, weights=P[dst, k], minlength=n) for k in range(3)], 1) / deg[:, None]
    w = falloff(np.linalg.norm(co - C, axis=1))[:, None]
    P = co.copy()
    it = int(os.environ.get("ITERS", "60"))
    for _ in range(it): P = P + w * 0.6 * (avg(P) - P)
    for _ in range(it // 2):
        P = P + w * 0.5 * (avg(P) - P); P = P + w * -0.53 * (avg(P) - P)
    me.vertices.foreach_set("co", P.ravel()); me.update()
    print(f"mesh: smoothed {(w > 0).sum()} verts, max move {np.linalg.norm(P - co, axis=1).max():.4f}", flush=True)
elif MODE == "normal":
    pos = np.load(os.path.join(TEX, "body_position.npy"))
    img = body.data.materials[0].node_tree.nodes["normal"].image
    S = img.size[0]
    px = np.array(img.pixels[:], np.float32).reshape(S, S, 4)
    d = np.linalg.norm(np.nan_to_num(pos, nan=1e3) - C, axis=-1)
    w = falloff(d)[..., None]
    flat = np.array([0.5, 0.5, 1.0], np.float32)
    px[..., :3] = px[..., :3] * (1 - w) + flat * w
    img.pixels = px.ravel(); img.filepath_raw = os.path.join(TEX, "body_normal.png"); img.file_format = "PNG"; img.save()
    print(f"normal: flattened {(w[..., 0] > 0).sum()} texels", flush=True)
    # base colour: the source had baked-in shading at the repaired spot; blend toward the surrounding colour
    cimg = body.data.materials[0].node_tree.nodes["basecolor"].image
    cp = np.array(cimg.pixels[:], np.float32).reshape(S, S, 4)
    ring = (d > R) & (d < 1.4 * R)
    if ring.any():
        ref = np.median(cp[ring, :3], axis=0)
        cp[..., :3] = cp[..., :3] * (1 - w) + ref * w
        cimg.pixels = cp.ravel(); cimg.filepath_raw = os.path.join(TEX, "body_basecolor.png"); cimg.save()
        print(f"basecolor: blended toward ring median {np.round(ref, 3)}", flush=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("saved", OUT)
