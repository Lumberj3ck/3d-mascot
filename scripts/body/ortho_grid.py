"""Orthographic front + side renders of a GLB with a labelled coordinate grid (Blender coords: X right(char left),
Y front, Z up) - used to read off joint positions for rigging.
Usage: blender -b --factory-startup -P scripts/body/ortho_grid.py -- <in.glb> <out_prefix> [step=0.05]
"""
import sys, math, bpy, numpy as np
from mathutils import Vector
args = sys.argv[sys.argv.index("--") + 1:]
src, pre = args[0], args[1]; step = float(args[2]) if len(args) > 2 else 0.05
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"; sc.display.shading.light = "STUDIO"; sc.display.shading.color_type = "TEXTURE"
sc.render.resolution_x = sc.render.resolution_y = 1000; sc.render.film_transparent = False
sc.world = bpy.data.worlds.new("W"); sc.world.color = (1, 1, 1)
cam = bpy.data.objects.new("C", bpy.data.cameras.new("C")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = 1.2
for name, loc, rot in [("front", (0, 3, 0), (math.radians(90), 0, math.radians(180))),
                       ("side", (3, 0, 0), (math.radians(90), 0, math.radians(90)))]:
    cam.location = loc; cam.rotation_euler = rot
    sc.render.filepath = f"{pre}_{name}.png"; bpy.ops.render.render(write_still=True)
print("rendered")
