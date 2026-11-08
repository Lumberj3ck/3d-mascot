"""Export the 'Body' object of a .blend to GLB (textures packed into the GLB) and save a packed .blend.
Usage: blender -b --factory-startup -P scripts/body/export_glb.py -- <in.blend> <out.glb> <out.blend>
"""
import sys, bpy
args = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.open_mainfile(filepath=args[0])
for name in ("Clean",):
    if name in bpy.data.objects: bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
body = bpy.data.objects["Body"]
nt = body.data.materials[0].node_tree
if "position" in nt.nodes: nt.nodes.remove(nt.nodes["position"])  # debug map, not shipped
bpy.ops.outliner.orphans_purge(do_recursive=True)
bpy.ops.file.pack_all()
for o in bpy.context.scene.objects: o.select_set(o == body)
bpy.ops.export_scene.gltf(filepath=args[1], export_format="GLB", use_selection=True, export_yup=True)
bpy.ops.wm.save_as_mainfile(filepath=args[2])
print("saved", args[1], args[2])
