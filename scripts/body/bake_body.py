"""UV-unwrap the quad 'Body' and bake maps from the smoothed 'Clean' model.
Usage: blender -b --factory-startup -P scripts/body/bake_body.py -- <retopo.blend> <out.blend> <tex_dir> [size=2048]
Bakes: normal (tangent, OpenGL), basecolor, emission, roughness, position (object space, for face masking).
"""
import os, sys, time
import bpy

args = sys.argv[sys.argv.index("--") + 1:]
IN, OUT, TEX = args[0], args[1], os.path.abspath(args[2])
SIZE = int(args[3]) if len(args) > 3 else 2048
os.makedirs(TEX, exist_ok=True)
t0 = time.time()
bpy.ops.wm.open_mainfile(filepath=IN)
sc = bpy.context.scene
src, body = bpy.data.objects["Clean"], bpy.data.objects["Body"]
src.hide_set(False); src.hide_render = False

# ---- UVs
for o in sc.objects: o.select_set(o == body)
bpy.context.view_layer.objects.active = body
while body.data.uv_layers: body.data.uv_layers.remove(body.data.uv_layers[0])
body.data.uv_layers.new(name="UVMap")
bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
# smart project only picks the charts (its planar projection folds on curved tips like the horns);
# re-unwrap every chart with angle-based flattening (no fold-overs), then pack.
# Charts that wrap around tubes/cones (horns, tail) still fold, so overlapping regions are re-split with a
# tighter angle limit until no face overlaps (overlaps make two body parts share texels -> wrong colours).
import bmesh
bpy.context.scene.tool_settings.use_uv_select_sync = False
bpy.context.tool_settings.mesh_select_mode = (False, False, True)
bpy.ops.uv.smart_project(angle_limit=1.2, island_margin=0.0, area_weight=0.0, scale_to_bounds=False)
bpy.ops.uv.seams_from_islands()
bpy.ops.uv.unwrap(method="ANGLE_BASED", fill_holes=True, margin=0.0)

def pack():
    bpy.ops.mesh.select_all(action="SELECT"); bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(shape_method="CONCAVE", rotate=True, margin_method="FRACTION", margin=0.003)

def overlapping_faces():
    bpy.ops.mesh.select_all(action="SELECT"); bpy.ops.uv.select_all(action="DESELECT"); bpy.ops.uv.select_overlap()
    bm = bmesh.from_edit_mesh(body.data)
    return [f.index for f in bm.faces if all(l.uv_select_vert for l in f.loops)]

pack()
for it, angle in enumerate([0.8, 0.55, 0.35, 0.2, 0.1]):
    bad = overlapping_faces()
    print(f"uv pass {it}: {len(bad)} overlapping faces", flush=True)
    if not bad: break
    bm = bmesh.from_edit_mesh(body.data); bm.faces.ensure_lookup_table()
    for f in bm.faces: f.select = False
    for i in bad: bm.faces[i].select = True
    bmesh.update_edit_mesh(body.data)
    bpy.ops.mesh.select_more()  # include a ring so the re-split region has clean borders
    bpy.ops.uv.smart_project(angle_limit=angle, island_margin=0.0, area_weight=0.0, scale_to_bounds=False)
    bpy.ops.uv.seams_from_islands()
    bpy.ops.uv.unwrap(method="ANGLE_BASED", fill_holes=True, margin=0.0)
    pack()
print(f"uv final: {len(overlapping_faces())} overlapping faces", flush=True)
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.object.mode_set(mode="OBJECT")
print(f"unwrapped {time.time()-t0:.0f}s", flush=True)

# ---- target material with one image node per map
mat = bpy.data.materials.new("DragonBody"); mat.use_nodes = True
nt = mat.node_tree; bsdf = nt.nodes["Principled BSDF"]
imgs = {}
for name, noncolor, flt in [("basecolor", False, False), ("normal", True, False), ("emission", False, False),
                             ("roughness", True, False), ("position", True, True)]:
    img = bpy.data.images.new(f"body_{name}", SIZE, SIZE, alpha=False, float_buffer=flt)
    if noncolor: img.colorspace_settings.name = "Non-Color"
    n = nt.nodes.new("ShaderNodeTexImage"); n.image = img; n.name = name
    imgs[name] = (img, n)
body.data.materials.clear(); body.data.materials.append(mat)

sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 1
bk = sc.render.bake
bk.use_selected_to_active = True; bk.cage_extrusion = 0.004; bk.max_ray_distance = 0.03; bk.margin = 12
bk.normal_space = "TANGENT"
for o in sc.objects: o.select_set(o in (src, body))
bpy.context.view_layer.objects.active = body

def bake(name, btype, ext="png", **kw):
    img, node = imgs[name]
    for n in nt.nodes: n.select = False
    nt.nodes.active = node; node.select = True
    bpy.ops.object.bake(type=btype, **kw)
    if ext == "exr":
        img.filepath_raw = os.path.join(TEX, f"body_{name}.exr"); img.file_format = "OPEN_EXR"
    else:
        img.filepath_raw = os.path.join(TEX, f"body_{name}.png"); img.file_format = "PNG"
    img.save(); print(f"baked {name} {time.time()-t0:.0f}s", flush=True)

bk.use_pass_direct = False; bk.use_pass_indirect = False; bk.use_pass_color = True
bake("basecolor", "DIFFUSE", pass_filter={"COLOR"})
bake("normal", "NORMAL")
bake("emission", "EMIT")
bake("roughness", "ROUGHNESS")
bake("position", "POSITION", ext="exr")

# wire the material for previewing
nt.links.new(imgs["basecolor"][1].outputs["Color"], bsdf.inputs["Base Color"])
nt.links.new(imgs["roughness"][1].outputs["Color"], bsdf.inputs["Roughness"])
nt.links.new(imgs["emission"][1].outputs["Color"], bsdf.inputs["Emission Color"])
bsdf.inputs["Emission Strength"].default_value = 3.0
nm = nt.nodes.new("ShaderNodeNormalMap"); nt.links.new(imgs["normal"][1].outputs["Color"], nm.inputs["Color"])
nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
src.hide_set(True); src.hide_render = True
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("saved", OUT)
