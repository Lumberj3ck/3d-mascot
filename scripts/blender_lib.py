"""Shared Blender helpers for the body and item pipelines (import with sys.path.insert(0, <scripts dir>)).

- remesh_smooth_decimate(obj, voxel, taubin_iters, target_tris)
- unwrap_no_overlap(obj)                       -> remaining overlapping face count
- add_bake_material(obj, size, maps)           -> (material, {name: (image, node)})
- bake_normal(src, dst, nodes, path, ...)      ray-cast tangent normal bake (selected-to-active)
- transfer_maps(src, dst, nodes, tex_dir, ...) nearest-surface colour transfer (robust on thin parts)
"""
import os
import bpy, bmesh, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


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


def select_only(obj):
    for o in bpy.context.scene.objects:
        o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj


def remove_small_components(obj, min_verts):
    """Delete disconnected pieces with fewer than min_verts vertices (Pixal3D outputs contain floating debris;
    after voxel remeshing each fragment becomes a tiny closed blob that decimation cannot remove)."""
    bm = bmesh.new(); bm.from_mesh(obj.data); bm.verts.ensure_lookup_table()
    seen = np.zeros(len(bm.verts), bool); kill = []; ncomp = 0
    for v in bm.verts:
        if seen[v.index]: continue
        stack, comp = [v], []; seen[v.index] = True
        while stack:
            x = stack.pop(); comp.append(x)
            for e in x.link_edges:
                w = e.other_vert(x)
                if not seen[w.index]: seen[w.index] = True; stack.append(w)
        if len(comp) < min_verts: kill.extend(comp); ncomp += 1
    if kill: bmesh.ops.delete(bm, geom=kill, context="VERTS")
    bm.to_mesh(obj.data); bm.free()
    return ncomp


def remesh_smooth_decimate(obj, voxel, taubin_iters=10, target_tris=8000, lam=0.5, mu=-0.53, min_verts=100):
    """Weld -> [voxel remesh if voxel>0] -> drop debris -> Taubin smoothing (no shrink) -> decimate to target."""
    select_only(obj)
    # glTF imports carry custom split normals + sharp-edge marks; collapse decimation will not cross them and
    # stalls far above the target on Pixal3D meshes, so drop them (we bake a normal map anyway).
    if obj.data.has_custom_normals:
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
    for name in ("sharp_edge", "sharp_face"):
        a = obj.data.attributes.get(name)
        if a is not None: obj.data.attributes.remove(a)
    bm = bmesh.new(); bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    # welding Pixal3D's double-layer thin shells leaves edges shared by >2 faces; collapse decimation refuses
    # to touch them and stalls far above the target. Split them into boundaries first.
    nm = [e for e in bm.edges if len(e.link_faces) > 2]
    if nm:
        bmesh.ops.split_edges(bm, edges=nm)
        print(f"  split {len(nm)} non-manifold edges", flush=True)
    bm.to_mesh(obj.data); bm.free()
    if voxel and voxel > 0:  # voxel remesh: best for solid volumes; shatters paper-thin double-layer shells
        rm = obj.modifiers.new("Remesh", "REMESH"); rm.mode = "VOXEL"; rm.voxel_size = voxel; rm.adaptivity = 0.0
        bpy.ops.object.modifier_apply(modifier="Remesh")
    removed = remove_small_components(obj, min_verts)
    if removed: print(f"  removed {removed} floating debris components (<{min_verts} verts)", flush=True)
    me = obj.data; n = len(me.vertices)
    co = np.empty(n * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
    ed = np.empty(len(me.edges) * 2, np.int64); me.edges.foreach_get("vertices", ed); ed = ed.reshape(-1, 2)
    src, dst = np.r_[ed[:, 0], ed[:, 1]], np.r_[ed[:, 1], ed[:, 0]]
    deg = np.maximum(np.bincount(src, minlength=n), 1).astype(float)
    avg = lambda x: np.stack([np.bincount(src, weights=x[dst, k], minlength=n) for k in range(3)], 1) / deg[:, None]
    for _ in range(taubin_iters):
        co = co + lam * (avg(co) - co)
        co = co + mu * (avg(co) - co)
    me.vertices.foreach_set("co", co.ravel()); me.update()
    ntris = sum(len(p.vertices) - 2 for p in me.polygons)
    for _ in range(4):  # collapse decimation can undershoot the ratio on remeshed quads; repeat until close
        ntris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
        if ntris <= target_tris * 1.1: break
        dec = obj.modifiers.new("Decimate", "DECIMATE"); dec.ratio = min(1.0, target_tris / ntris); dec.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier="Decimate")
        print(f"  decimate: {ntris} -> {sum(len(p.vertices) - 2 for p in obj.data.polygons)} (target {target_tris})", flush=True)
    for p in obj.data.polygons:
        p.use_smooth = True
    return len(obj.data.polygons)


def unwrap_xatlas(obj, resolution=2048, padding=4):
    """Chart + pack with xatlas (few large charts, never overlapping), run in the project .venv.
    Triangle meshes only; returns False otherwise."""
    import subprocess, tempfile
    me = obj.data
    if not all(len(p.vertices) == 3 for p in me.polygons): return False
    root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    V = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", V)
    F = np.empty(len(me.polygons) * 3, np.int64); me.polygons.foreach_get("vertices", F)
    d = tempfile.mkdtemp(); fi, fo = os.path.join(d, "in.npz"), os.path.join(d, "out.npz")
    np.savez(fi, V=V.reshape(-1, 3), F=F.reshape(-1, 3))
    py = os.environ.get("XATLAS_PY", os.path.join(root, ".venv", "bin", "python"))
    r = subprocess.run([py, "-I", os.path.join(root, "scripts", "xatlas_uv.py"), fi, fo, str(resolution), str(padding)],
                       check=True, capture_output=True, text=True)
    print("  " + r.stdout.strip(), flush=True)
    UV = np.load(fo)["UV"]
    while me.uv_layers: me.uv_layers.remove(me.uv_layers[0])
    me.uv_layers.new(name="UVMap")
    me.uv_layers.active.data.foreach_set("uv", UV.reshape(-1).astype(np.float32))
    return True


def unwrap_no_overlap(obj, margin=0.004, passes=(0.8, 0.55, 0.35, 0.2, 0.1)):
    """UVs without overlaps: xatlas for triangle meshes; otherwise smart-project charts re-flattened with ABF and
    re-split until clean. Overlapping UVs make two surface regions share texels (wrong colours after baking).
    (A per-face fallback was removed: tens of thousands of sub-texel charts leave nothing to bake into.)"""
    if unwrap_xatlas(obj):
        return 0
    select_only(obj)
    while obj.data.uv_layers:
        obj.data.uv_layers.remove(obj.data.uv_layers[0])
    obj.data.uv_layers.new(name="UVMap")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.scene.tool_settings.use_uv_select_sync = False
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.2, island_margin=0.0, area_weight=0.0, scale_to_bounds=False)
    bpy.ops.uv.seams_from_islands()
    bpy.ops.uv.unwrap(method="ANGLE_BASED", fill_holes=True, margin=0.0)

    def pack():
        bpy.ops.mesh.select_all(action="SELECT"); bpy.ops.uv.select_all(action="SELECT")
        bpy.ops.uv.pack_islands(shape_method="CONCAVE", rotate=True, margin_method="FRACTION", margin=margin)

    def overlapping():
        bpy.ops.mesh.select_all(action="SELECT"); bpy.ops.uv.select_all(action="DESELECT"); bpy.ops.uv.select_overlap()
        bm = bmesh.from_edit_mesh(obj.data)
        return [f.index for f in bm.faces if all(l.uv_select_vert for l in f.loops)]

    pack()
    bad = overlapping()
    for angle in passes:
        if not bad:
            break
        bm = bmesh.from_edit_mesh(obj.data); bm.faces.ensure_lookup_table()
        for f in bm.faces: f.select = False
        for i in bad: bm.faces[i].select = True
        bmesh.update_edit_mesh(obj.data)
        bpy.ops.mesh.select_more()
        bpy.ops.uv.smart_project(angle_limit=angle, island_margin=0.0, area_weight=0.0, scale_to_bounds=False)
        bpy.ops.uv.seams_from_islands()
        bpy.ops.uv.unwrap(method="ANGLE_BASED", fill_holes=True, margin=0.0)
        pack()
        bad = overlapping()
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    return len(bad)


def add_bake_material(obj, size, name="Baked", maps=("basecolor", "normal", "roughness", "emission")):
    noncolor = {"normal", "roughness", "position"}
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    nt = mat.node_tree; bsdf = nt.nodes["Principled BSDF"]
    imgs = {}
    for m in maps:
        img = bpy.data.images.new(f"{name}_{m}", size, size, alpha=False, float_buffer=(m == "position"))
        if m in noncolor: img.colorspace_settings.name = "Non-Color"
        if m == "normal": img.generated_color = (0.5, 0.5, 1.0, 1.0)  # missed bake rays stay flat, not black
        if m in ("basecolor", "roughness", "emission"): img.generated_color = (1.0, 0.0, 1.0, 1.0)  # miss sentinel
        node = nt.nodes.new("ShaderNodeTexImage"); node.image = img; node.name = m
        imgs[m] = (img, node)
    obj.data.materials.clear(); obj.data.materials.append(mat)
    return mat, imgs


def wire_material(mat, imgs, emission_strength=0.0):
    nt = mat.node_tree; bsdf = nt.nodes["Principled BSDF"]
    if "basecolor" in imgs: nt.links.new(imgs["basecolor"][1].outputs["Color"], bsdf.inputs["Base Color"])
    if "roughness" in imgs: nt.links.new(imgs["roughness"][1].outputs["Color"], bsdf.inputs["Roughness"])
    if "normal" in imgs:
        nm = nt.nodes.new("ShaderNodeNormalMap"); nt.links.new(imgs["normal"][1].outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if "emission" in imgs and emission_strength > 0:
        nt.links.new(imgs["emission"][1].outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    bsdf.inputs["Metallic"].default_value = 0.0
    # 'position' is a helper map: drop it so it isn't exported
    if "position" in nt.nodes: nt.nodes.remove(nt.nodes["position"])


def _set_active_node(nt, node):
    for n in nt.nodes: n.select = False
    nt.nodes.active = node; node.select = True


def bake_normal(src, dst, imgs, path, cage=0.004, max_ray=0.03, margin=12):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 1
    bk = sc.render.bake
    bk.use_selected_to_active = True; bk.cage_extrusion = cage; bk.max_ray_distance = max_ray; bk.margin = margin
    bk.normal_space = "TANGENT"
    src.hide_set(False); src.hide_render = False
    for o in sc.objects: o.select_set(o in (src, dst))
    bpy.context.view_layer.objects.active = dst
    img, node = imgs["normal"]
    _set_active_node(dst.data.materials[0].node_tree, node)
    bpy.ops.object.bake(type="NORMAL")
    img.filepath_raw = path; img.file_format = "PNG"; img.save()


def _src_image(mat, socket):
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None: return None
    links = bsdf.inputs[socket].links
    node = links[0].from_node if links else None
    while node is not None and node.type != "TEX_IMAGE":
        node = node.inputs[0].links[0].from_node if node.inputs and node.inputs[0].links else None
    return node.image if node else None


def _sample(img, uv):
    w, h = img.size
    px = np.array(img.pixels[:], np.float32).reshape(h, w, 4)
    x = np.clip(uv[:, 0] * w - 0.5, 0, w - 1); y = np.clip(uv[:, 1] * h - 0.5, 0, h - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    return px[y0, x0] * (1 - fx) * (1 - fy) + px[y0, x1] * fx * (1 - fy) + px[y1, x0] * (1 - fx) * fy + px[y1, x1] * fx * fy


def ray_bake_colors(src, dst, imgs, cage, max_ray, margin=12):
    """Ray-cast bake (projects along the surface normal from a cage outside dst) of base colour, emission and
    roughness from src. Hits the OUTER surface first, unlike nearest-point lookups which land on Pixal3D's dark
    inner layers. Texels whose ray misses keep the magenta sentinel."""
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 1
    bk = sc.render.bake
    bk.use_selected_to_active = True; bk.cage_extrusion = cage; bk.max_ray_distance = max_ray; bk.margin = margin
    bk.margin_type = "ADJACENT_FACES"
    bk.use_pass_direct = False; bk.use_pass_indirect = False; bk.use_pass_color = True
    src.hide_set(False); src.hide_render = False
    for o in sc.objects: o.select_set(o in (src, dst))
    bpy.context.view_layer.objects.active = dst
    nt = dst.data.materials[0].node_tree
    for name, btype, kw in (("basecolor", "DIFFUSE", {"pass_filter": {"COLOR"}}), ("emission", "EMIT", {}), ("roughness", "ROUGHNESS", {})):
        if name in imgs:
            _set_active_node(nt, imgs[name][1]); bpy.ops.object.bake(type=btype, **kw)


def transfer_maps(src, dst, imgs, tex_dir, prefix, margin=12, cage=None, max_ray=None):
    """Colour maps for dst: ray-cast bake from src (if cage/max_ray given), with the closest-point-on-src value as
    fallback for missed texels (or for everything when no cage is given).
    Returns (texel positions HxWx3 with NaN outside islands, valid mask)."""
    sc = bpy.context.scene
    nt = dst.data.materials[0].node_tree
    if cage is not None:
        ray_bake_colors(src, dst, imgs, cage, max_ray, margin)
    size = imgs["basecolor"][0].size[0]
    if "position" not in imgs:
        img = bpy.data.images.new(f"{prefix}_position", size, size, alpha=False, float_buffer=True)
        img.colorspace_settings.name = "Non-Color"
        node = nt.nodes.new("ShaderNodeTexImage"); node.image = img; node.name = "position"; imgs["position"] = (img, node)
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 1
    sc.render.bake.use_selected_to_active = False; sc.render.bake.margin = margin
    select_only(dst)
    _set_active_node(nt, imgs["position"][1])
    bpy.ops.object.bake(type="POSITION")
    P = np.array(imgs["position"][0].pixels[:], np.float32).reshape(size, size, 4)[..., :3]
    valid = np.abs(P).sum(-1) > 1e-6
    # position bake is in world space; sample the source in world space too
    dg = bpy.context.evaluated_depsgraph_get()
    se = src.evaluated_get(dg); sm = se.to_mesh(); sm.transform(src.matrix_world); sm.calc_loop_triangles()
    nt_ = len(sm.loop_triangles)
    tri_v = np.empty(nt_ * 3, np.int64); sm.loop_triangles.foreach_get("vertices", tri_v); tri_v = tri_v.reshape(-1, 3)
    tri_l = np.empty(nt_ * 3, np.int64); sm.loop_triangles.foreach_get("loops", tri_l); tri_l = tri_l.reshape(-1, 3)
    V = np.empty(len(sm.vertices) * 3); sm.vertices.foreach_get("co", V); V = V.reshape(-1, 3)
    UV = np.empty(len(sm.loops) * 2); sm.uv_layers.active.data.foreach_get("uv", UV); UV = UV.reshape(-1, 2)
    good = (tri_v >= 0).all(1) & (tri_v < len(V)).all(1)
    if not good.all():
        print(f"transfer_maps: dropping {(~good).sum()} invalid source triangles of {nt_}", flush=True)
        tri_v, tri_l = tri_v[good], tri_l[good]
    bvh = BVHTree.FromPolygons(V.tolist(), tri_v.tolist())  # (vertices, polygons), plain Python types
    pts = P[valid]
    loc = np.empty_like(pts); tri = np.empty(len(pts), np.int64)
    for k, p in enumerate(pts):
        l, _, fi, _ = bvh.find_nearest(Vector(p)); loc[k] = l; tri[k] = fi
    A, B, C = V[tri_v[tri, 0]], V[tri_v[tri, 1]], V[tri_v[tri, 2]]
    v0, v1, v2 = B - A, C - A, loc - A
    d00 = (v0 * v0).sum(1); d01 = (v0 * v1).sum(1); d11 = (v1 * v1).sum(1); d20 = (v2 * v0).sum(1); d21 = (v2 * v1).sum(1)
    den = np.maximum(d00 * d11 - d01 * d01, 1e-20)
    wb = (d11 * d20 - d01 * d21) / den; wc = (d00 * d21 - d01 * d20) / den
    bary = np.clip(np.stack([1 - wb - wc, wb, wc], 1), 0, 1); bary /= bary.sum(1, keepdims=True)
    uv = (UV[tri_l[tri]] * bary[..., None]).sum(1)
    smat = src.data.materials[0]
    for name, sock, chan in [("basecolor", "Base Color", None), ("emission", "Emission Color", None), ("roughness", "Roughness", 1)]:
        if name not in imgs: continue
        simg = _src_image(smat, sock)
        out = np.zeros((size, size, 4), np.float32); out[..., 3] = 1
        if simg is not None:
            vals = _sample(simg, uv)
            out[valid, :3] = vals[:, chan:chan + 1] if chan is not None else vals[:, :3]
        elif name == "roughness":
            out[valid, :3] = 0.75
        if cage is not None:  # keep ray-baked texels; nearest-surface only where the ray missed
            baked = np.array(imgs[name][0].pixels[:], np.float32).reshape(size, size, 4)
            missed = (np.abs(baked[..., 0] - 1) < 0.02) & (baked[..., 1] < 0.02) & (np.abs(baked[..., 2] - 1) < 0.02)
            use = valid & ~missed
            out[use, :3] = baked[use, :3]
        out = dilate(out, valid)
        img = imgs[name][0]; img.pixels = out.ravel()
        img.filepath_raw = os.path.join(tex_dir, f"{prefix}_{name}.png"); img.file_format = "PNG"; img.save()
    se.to_mesh_clear()
    return np.where(valid[..., None], P, np.nan), valid
