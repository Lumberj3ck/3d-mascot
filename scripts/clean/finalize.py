"""Final step of the clean pipeline: wire recolored base color + gem emission into the baked material,
drop the high-poly 'Original', pack textures, save .blend and export the game-ready GLB.
Usage: blender -b --factory-startup -P finalize.py -- <baked.blend> <basecolor_sage.png> <emissive.png> <out.blend> <out.glb> [emission_strength]
"""
import sys
import bpy

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
IN, BASE, EMIS, OUT_BLEND, OUT_GLB = args[:5]
STRENGTH = float(args[5]) if len(args) > 5 else 3.0

bpy.ops.wm.open_mainfile(filepath=IN)
clean = bpy.data.objects["Clean"]
if "Original" in bpy.data.objects:
    bpy.data.objects.remove(bpy.data.objects["Original"], do_unlink=True)
clean.name = "Dragon"

mat = clean.data.materials[0]
nt = mat.node_tree; bsdf = nt.nodes["Principled BSDF"]
nt.nodes["basecolor"].image = bpy.data.images.load(BASE)
emis = nt.nodes.get("emissive") or nt.nodes.new("ShaderNodeTexImage")
emis.name = "emissive"; emis.image = bpy.data.images.load(EMIS)
nt.links.new(emis.outputs["Color"], bsdf.inputs["Emission Color"])
bsdf.inputs["Emission Strength"].default_value = STRENGTH
bsdf.inputs["Metallic"].default_value = 0.0

bpy.ops.outliner.orphans_purge(do_recursive=True)
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
for o in bpy.context.scene.objects: o.select_set(o == clean)
bpy.ops.export_scene.gltf(filepath=OUT_GLB, export_format="GLB", use_selection=True,
                          export_image_format="AUTO", export_yup=True)
print("saved", OUT_BLEND, OUT_GLB)
