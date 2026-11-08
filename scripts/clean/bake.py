"""UV-unwrap the Clean mesh and bake base color + roughness from the Original.
Usage: blender -b --factory-startup -P bake.py -- <in.blend> <out.blend> <tex_size> <tex_dir>
Writes <tex_dir>/dragon_basecolor.png and dragon_roughness.png."""
import os, sys, time
import bpy

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
IN, OUT, SIZE = args[0], args[1], int(args[2])
TEX_DIR = os.path.abspath(args[3] if len(args) > 3 else os.path.dirname(os.path.abspath(OUT)))
os.makedirs(TEX_DIR, exist_ok=True)
t0 = time.time()
bpy.ops.wm.open_mainfile(filepath=IN)
scene = bpy.context.scene
orig, clean = bpy.data.objects["Original"], bpy.data.objects["Clean"]

# --- UV unwrap
for o in scene.objects: o.select_set(o == clean)
bpy.context.view_layer.objects.active = clean
while clean.data.uv_layers: clean.data.uv_layers.remove(clean.data.uv_layers[0])
clean.data.uv_layers.new(name="UVMap")
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.004, area_weight=0.0, scale_to_bounds=False)
bpy.ops.uv.pack_islands(margin=0.004)
bpy.ops.object.mode_set(mode="OBJECT")
print(f"unwrapped {time.time()-t0:.0f}s", flush=True)

# --- target material with bake images
mat = bpy.data.materials.new("Dragon"); mat.use_nodes = True
nt = mat.node_tree; bsdf = nt.nodes["Principled BSDF"]
imgs = {}
for name in ("basecolor", "roughness"):
    img = bpy.data.images.new(f"dragon_{name}", SIZE, SIZE, alpha=False, float_buffer=False)
    if name == "roughness": img.colorspace_settings.name = "Non-Color"
    node = nt.nodes.new("ShaderNodeTexImage"); node.image = img; node.name = name
    imgs[name] = (img, node)
nt.links.new(imgs["basecolor"][1].outputs["Color"], bsdf.inputs["Base Color"])
nt.links.new(imgs["roughness"][1].outputs["Color"], bsdf.inputs["Roughness"])
clean.data.materials.clear(); clean.data.materials.append(mat)

scene.render.engine = "CYCLES"; scene.cycles.samples = 1; scene.cycles.device = "CPU"
bk = scene.render.bake
bk.use_selected_to_active = True; bk.cage_extrusion = 0.006; bk.max_ray_distance = 0.02; bk.margin = 8
for o in scene.objects: o.select_set(o in (orig, clean))
bpy.context.view_layer.objects.active = clean

def bake(name, btype, **kw):
    img, node = imgs[name]
    for n in nt.nodes: n.select = False
    nt.nodes.active = node; node.select = True
    bpy.ops.object.bake(type=btype, **kw)
    img.filepath_raw = os.path.join(TEX_DIR, f"dragon_{name}.png"); img.file_format = "PNG"; img.save()
    print(f"baked {name} {time.time()-t0:.0f}s", flush=True)

bk.use_pass_direct = False; bk.use_pass_indirect = False; bk.use_pass_color = True
bake("basecolor", "DIFFUSE", pass_filter={"COLOR"})
bake("roughness", "ROUGHNESS")
orig.hide_render = True; orig.hide_set(True)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("saved", OUT)
