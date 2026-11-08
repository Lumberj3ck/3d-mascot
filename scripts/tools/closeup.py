"""Close-up renders of a GLB around a 3D point (Blender coords: +X char right, +Y front, +Z up).
Usage: blender -b --factory-startup -P scripts/tools/closeup.py -- <in.glb> <out.png> cx cy cz dist az,el [az,el ...]
Used to inspect artifacts (hips, wings, belly, face) up close."""
import sys, math, bpy, numpy as np, tempfile
from mathutils import Vector
a = sys.argv[sys.argv.index("--") + 1:]
src, dst = a[0], a[1]; target = Vector(tuple(float(v) for v in a[2:5])); dist = float(a[5])
views = [(float(v.split(",")[0]), float(v.split(",")[1])) for v in a[6:]]
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=src)
sc = bpy.context.scene; sc.render.engine = "CYCLES"; sc.cycles.samples = 24; sc.cycles.device = "CPU"
S = 400; sc.render.resolution_x = sc.render.resolution_y = S; sc.view_settings.view_transform = "Standard"
sc.world = bpy.data.worlds.new("W"); sc.world.use_nodes = True; sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.92, 0.9, 0.87, 1)
cam = bpy.data.objects.new("C", bpy.data.cameras.new("C")); sc.collection.objects.link(cam); sc.camera = cam; cam.data.angle = math.radians(30)
sun = bpy.data.objects.new("S", bpy.data.lights.new("S", "SUN")); sc.collection.objects.link(sun); sun.data.energy = 3
tiles = []
for az, el in views:
    r, e = math.radians(az), math.radians(el)
    d = Vector((-math.sin(r) * math.cos(e), math.cos(r) * math.cos(e), math.sin(e)))
    cam.location = target + d * dist; cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    sun.rotation_euler = (-(d + Vector((0.3, 0, 0.9)))).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = tempfile.mktemp(suffix=".png"); bpy.ops.render.render(write_still=True)
    tiles.append(np.array(bpy.data.images.load(sc.render.filepath).pixels[:], np.float32).reshape(S, S, 4))
st = np.concatenate(tiles, 1); im = bpy.data.images.new("o", st.shape[1], S); im.pixels = st.ravel().tolist()
im.filepath_raw = dst; im.file_format = "PNG"; im.save(); print("saved", dst)
