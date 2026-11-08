"""Raw Pixal3D item GLB -> leveled, cleaned, color-matched, game-ready GLB.

Usage: blender -b --factory-startup -P scripts/items/process_item.py -- <item_id> [--tris N] [--tex 1024]
Inputs:  outputs/items/raw/<id>.glb, outputs/items/level.json, inputs/items/items.json,
         inputs/items/concepts/<id>.png (color reference)
Outputs: outputs/items/<id>.glb, outputs/items/<id>.blend, outputs/items/work/<id>/* (textures)

Steps: level (stable pose / symmetry yaw) -> pivot (props: bottom-center, wearables: bbox center) ->
voxel remesh + Taubin + decimate -> overlap-free UVs -> normal bake + nearest-surface color transfer ->
match render colors to the concept (per-channel linear gain) -> optional emissive mask -> export.
"""
import sys, os, json, math, tempfile
import bpy, numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import blender_lib as bl

args = sys.argv[sys.argv.index("--") + 1:]
IID = args[0]
opt = {args[i]: args[i + 1] for i in range(1, len(args) - 1, 2)}
cfg = {i["id"]: i for i in json.load(open(os.path.join(ROOT, "inputs/items/items.json")))["items"]}[IID]
TRIS = int(opt.get("--tris", cfg.get("tris", 10000 if cfg["type"] == "prop" else 6000)))
TEX = int(opt.get("--tex", cfg.get("tex", 1024)))
WORK = os.path.join(ROOT, "outputs/items/work", IID); os.makedirs(WORK, exist_ok=True)
OUT_GLB = os.path.join(ROOT, "outputs/items", IID + ".glb")
OUT_BLEND = os.path.join(ROOT, "outputs/items", IID + ".blend")

# ---------------------------------------------------------------- import + level + pivot
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(ROOT, "outputs/items/raw", IID + ".glb"))
src = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
src.name = "Original"
M = Matrix(json.load(open(os.path.join(ROOT, "outputs/items/level.json")))[IID])
C = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))  # glTF (Y-up) -> Blender (Z-up)
src.matrix_world = C @ M @ C.inverted() @ src.matrix_world
bl.select_only(src)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
co = np.array([v.co[:] for v in src.data.vertices])
lo, hi = co.min(0), co.max(0)
pivot = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2] if cfg["type"] == "prop" else (lo[2] + hi[2]) / 2])
src.data.transform(Matrix.Translation(Vector(-pivot)))
size = hi - lo
print(f"[{IID}] leveled; size {np.round(size, 3)}, pivot {'bottom' if cfg['type'] == 'prop' else 'center'}", flush=True)

# ---------------------------------------------------------------- clean mesh
clean = src.copy(); clean.data = src.data.copy(); clean.name = IID
bpy.context.scene.collection.objects.link(clean)
clean.data.materials.clear()
while clean.data.uv_layers: clean.data.uv_layers.remove(clean.data.uv_layers[0])
# No voxel remesh for items: Pixal3D builds thin parts (hat cone, brim, ribbons) as paper-thin double shells
# that a voxel remesh shatters. Smooth the welded original surface and decimate it directly instead.
nf = bl.remesh_smooth_decimate(clean, 0, taubin_iters=6, target_tris=TRIS, min_verts=60)
print(f"[{IID}] cleaned: {nf} tris", flush=True)
ov = bl.unwrap_no_overlap(clean)
print(f"[{IID}] unwrapped, overlapping faces left: {ov}", flush=True)

# ---------------------------------------------------------------- bake + transfer
mat, imgs = bl.add_bake_material(clean, TEX, name=IID, maps=("basecolor", "normal", "roughness", "emission"))
diag = float(np.linalg.norm(size))
bl.bake_normal(src, clean, imgs, os.path.join(WORK, f"{IID}_normal.png"), cage=diag * 0.004, max_ray=diag * 0.03)
P, valid = bl.transfer_maps(src, clean, imgs, WORK, IID)
print(f"[{IID}] baked + transferred", flush=True)

# ---------------------------------------------------------------- color match to concept
def lin(c): return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
def srgb(c): c = np.clip(c, 0, 1); return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)

def render_mean(obj, res=256):
    """Mean linear color of the object in a concept-like view (3/4 from above), neutral studio light."""
    sc = bpy.context.scene
    for o in sc.objects: o.hide_render = o is not obj
    sc.render.engine = "CYCLES"; sc.cycles.samples = 16; sc.cycles.device = "CPU"; sc.cycles.use_denoising = False
    sc.render.resolution_x = sc.render.resolution_y = res; sc.render.film_transparent = True
    sc.view_settings.view_transform = "Standard"
    sc.world = bpy.data.worlds.new("W"); sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
    sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam")); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.angle = math.radians(30)
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN")); sc.collection.objects.link(sun); sun.data.energy = 2.5
    bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    l = Vector([min(v[i] for v in bb) for i in range(3)]); h = Vector([max(v[i] for v in bb) for i in range(3)])
    c, r = (l + h) / 2, (h - l).length / 2
    a, e = math.radians(30), math.radians(25)
    d = Vector((-math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
    cam.location = c + d * (r / math.tan(math.radians(15)) * 1.1)
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    sun.rotation_euler = (-(d + Vector((0.3, 0, 0.9)))).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = tempfile.mktemp(suffix=".png"); bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(sc.render.filepath)
    px = np.array(im.pixels[:], np.float32).reshape(res, res, 4)
    m = px[..., 3] > 0.9
    for o in (cam, sun): bpy.data.objects.remove(o, do_unlink=True)
    return lin(px[m, :3]).mean(0)

concept = np.asarray(bpy.data.images.load(os.path.join(ROOT, "inputs/items/concepts", IID + ".png")).pixels[:], np.float32)
concept = concept.reshape(-1, 4)[:, :3]
fg = (concept.min(1) < 0.93)  # concepts are on pure white
target = lin(concept[fg]).mean(0)
bl.wire_material(mat, imgs, emission_strength=0.0)
current = render_mean(clean)
gain = np.clip(target / np.maximum(current, 1e-4), 0.6, 2.2)
print(f"[{IID}] color: render {np.round(current, 3)} vs concept {np.round(target, 3)} -> gain {np.round(gain, 3)}", flush=True)
bimg = imgs["basecolor"][0]
px = np.array(bimg.pixels[:], np.float32).reshape(TEX, TEX, 4)
px[..., :3] = np.where(valid[..., None], srgb(lin(px[..., :3]) * gain), px[..., :3])
bimg.pixels = px.ravel(); bimg.filepath_raw = os.path.join(WORK, f"{IID}_basecolor.png"); bimg.save()

# ---------------------------------------------------------------- optional emissive (e.g. glowing lamp cap)
EM = cfg.get("emissive")  # {"r_min":..,"g_min":..,"b_max":..,"strength":..}
eimg = imgs["emission"][0]
e = np.zeros((TEX, TEX, 4), np.float32); e[..., 3] = 1
if EM:
    c = px[..., :3]
    mask = (c[..., 0] >= EM.get("r_min", 0)) & (c[..., 1] >= EM.get("g_min", 0)) & (c[..., 2] <= EM.get("b_max", 1)) & valid
    e[mask, :3] = c[mask]
    print(f"[{IID}] emissive texels: {mask.mean() * 100:.1f}%", flush=True)
eimg.pixels = e.ravel(); eimg.filepath_raw = os.path.join(WORK, f"{IID}_emission.png"); eimg.save()
if EM:
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    mat.node_tree.links.new(imgs["emission"][1].outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = EM.get("strength", 2.0)
else:
    mat.node_tree.nodes.remove(imgs["emission"][1])

# ---------------------------------------------------------------- export
bpy.data.objects.remove(src, do_unlink=True)
for o in list(bpy.context.scene.objects):
    if o.type != "MESH": bpy.data.objects.remove(o, do_unlink=True)
clean.hide_render = False
clean["item_id"] = IID; clean["slot"] = cfg["slot"]; clean["type"] = cfg["type"]
clean["native_size"] = [float(x) for x in size]
bpy.ops.outliner.orphans_purge(do_recursive=True)
bpy.ops.file.pack_all()
bl.select_only(clean)
bpy.ops.export_scene.gltf(filepath=OUT_GLB, export_format="GLB", use_selection=True, export_yup=True, export_extras=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
print(f"[{IID}] saved {OUT_GLB}", flush=True)
