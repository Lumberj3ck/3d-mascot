"""Render clay + wireframe previews of an object in a .blend (topology check).
Usage: blender -b --factory-startup -P scripts/body/preview_wire.py -- <in.blend> <object> <out.png> [size=640]
"""
import sys, math, os, tempfile
import bpy, numpy as np
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.open_mainfile(filepath=args[0])
obj = bpy.data.objects[args[1]]; dst = args[2]; size = int(args[3]) if len(args) > 3 else 640
sc = bpy.context.scene
for o in sc.objects: o.hide_render = o is not obj
clay = bpy.data.materials.new("clay"); clay.use_nodes = True
clay.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.62, 0.68, 0.52, 1)
clay.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.8
wire = bpy.data.materials.new("wire"); wire.use_nodes = True
wire.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.05, 0.07, 0.05, 1)
obj.data.materials.clear(); obj.data.materials.append(clay); obj.data.materials.append(wire)
w = obj.modifiers.new("W", "WIREFRAME"); w.thickness = 0.0012; w.use_replace = False; w.material_offset = 1; w.use_even_offset = True
bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
lo = Vector([min(v[i] for v in bb) for i in range(3)]); hi = Vector([max(v[i] for v in bb) for i in range(3)])
c, r = (lo + hi) / 2, (hi - lo).length / 2
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 16; sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = size; sc.view_settings.view_transform = "Standard"
sc.world = bpy.data.worlds.new("W"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.95, 0.94, 0.92, 1)
cam = bpy.data.objects.new("C", bpy.data.cameras.new("C")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.angle = math.radians(30)
sun = bpy.data.objects.new("S", bpy.data.lights.new("S", "SUN")); sc.collection.objects.link(sun); sun.data.energy = 3
tiles, tmp = [], tempfile.mkdtemp()
for i, (az, el, zoom) in enumerate([(0, 5, 1.0), (90, 5, 1.0), (180, 5, 1.0), (25, 10, 0.45)]):
    a, e = math.radians(az), math.radians(el)
    dirv = Vector((-math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
    target = c if zoom == 1.0 else Vector((c.x, c.y, lo.z + (hi.z - lo.z) * 0.72))
    cam.location = target + dirv * (r / math.tan(math.radians(15)) * 1.05 * zoom)
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    sun.rotation_euler = (-(dirv + Vector((0.4, 0, 0.8)))).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(tmp, f"{i}.png"); bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(sc.render.filepath)
    tiles.append(np.array(im.pixels[:], np.float32).reshape(size, size, 4))
strip = np.concatenate(tiles, 1)
out = bpy.data.images.new("o", strip.shape[1], size); out.pixels = strip.ravel().tolist()
out.filepath_raw = os.path.abspath(dst); out.file_format = "PNG"; out.save(); print("saved", dst)
