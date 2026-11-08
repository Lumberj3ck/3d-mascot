"""Turntable preview of a GLB with local headless Blender (Cycles CPU, smooth shading, real materials).

Usage: blender -b --factory-startup -P scripts/render_blender.py -- in.glb out.png [tile_size] [samples]
Output: one PNG strip: front, left side, back, right side, 3/4 view (GLB Y-up, character faces -Z;
Blender imports glTF as Z-up, so the character faces +Y in the scene, its left side is -X).
"""
import sys, math
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
src, dst = argv[0], argv[1]
size = int(argv[2]) if len(argv) > 2 else 512
samples = int(argv[3]) if len(argv) > 3 else 32

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center, radius = (lo + hi) / 2, (hi - lo).length / 2

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = samples
scene.cycles.use_denoising = True
scene.render.resolution_x = scene.render.resolution_y = size
scene.render.film_transparent = False
scene.view_settings.view_transform = "Standard"

world = bpy.data.worlds.new("W"); scene.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.92, 0.90, 0.87, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9

cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam")); scene.collection.objects.link(cam)
cam.data.lens_unit = "FOV"; cam.data.angle = math.radians(30); scene.camera = cam
key = bpy.data.objects.new("Key", bpy.data.lights.new("Key", "SUN")); scene.collection.objects.link(key)
key.data.energy = 3.0; key.data.angle = math.radians(20)

import numpy as np, os, tempfile
tiles = []
tmp = tempfile.mkdtemp()
# azimuth measured from the character's front (+Y); 90 = character's left side (-X)
for i, (azim, elev) in enumerate([(0, 5), (90, 5), (180, 5), (270, 5), (35, 20)]):
    a, e = math.radians(azim), math.radians(elev)
    d = radius / math.tan(math.radians(15)) * 1.05
    direction = Vector((-math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
    cam.location = center + d * direction
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    key.rotation_euler = (-(direction + Vector((0.4, 0, 0.8)))).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = os.path.join(tmp, f"t{i}.png")
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(scene.render.filepath)
    px = np.array(img.pixels[:], dtype=np.float32).reshape(size, size, 4)[::-1, :, :3]
    tiles.append(px)

strip = np.concatenate(tiles, 1)
out = bpy.data.images.new("strip", strip.shape[1], strip.shape[0], alpha=False)
rgba = np.concatenate([strip[::-1], np.ones(strip.shape[:2] + (1,), np.float32)], -1)
out.pixels = rgba.ravel().tolist()
out.filepath_raw = os.path.abspath(dst); out.file_format = "PNG"; out.save()
print("saved", dst)
