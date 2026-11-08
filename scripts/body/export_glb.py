"""Export the 'Body' object of a .blend to GLB (textures packed into the GLB) and save a packed .blend.
Usage: blender -b --factory-startup -P scripts/body/export_glb.py -- <in.blend> <out.glb> <out.blend> [basecolor.png emissive.png strength]
Optional: replace the base colour and wire an emissive map (e.g. recolor.py output for the sage shift + gem glow).
"""
import sys, bpy
args = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.open_mainfile(filepath=args[0])
for name in ("Clean", "ColorSrc"):
    if name in bpy.data.objects: bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
body = bpy.data.objects["Body"]
nt = body.data.materials[0].node_tree
if len(args) >= 5:
    nt.nodes["basecolor"].image = bpy.data.images.load(args[3])
    nt.nodes["emission"].image = bpy.data.images.load(args[4])
    bsdf = nt.nodes["Principled BSDF"]
    nt.links.new(nt.nodes["emission"].outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = float(args[5]) if len(args) > 5 else 3.0
if "position" in nt.nodes: nt.nodes.remove(nt.nodes["position"])  # debug map, not shipped
bpy.ops.outliner.orphans_purge(do_recursive=True)
bpy.ops.file.pack_all()
for o in bpy.context.scene.objects: o.select_set(o == body)
bpy.ops.export_scene.gltf(filepath=args[1], export_format="GLB", use_selection=True, export_yup=True)
bpy.ops.wm.save_as_mainfile(filepath=args[2])
print("saved", args[1], args[2])
