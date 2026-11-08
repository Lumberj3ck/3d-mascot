"""Render every pixal3d item (inputs/items/items.json) from two angles into one strip image (run from repo root).
Usage: blender -b --factory-startup -P scripts/tools/item_sheet.py -- outputs/items <out.png>"""
import sys, os, math, json, bpy, numpy as np, tempfile
from mathutils import Vector
a = sys.argv[sys.argv.index("--") + 1:]; d, out = a[0], a[1]
ids = [i["id"] for i in json.load(open("inputs/items/items.json"))["items"] if i["method"] == "pixal3d"]
S = 300; tiles = []
for iid in ids:
    bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=os.path.join(d, iid + ".glb"))
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    bb = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector([min(v[i] for v in bb) for i in range(3)]); hi = Vector([max(v[i] for v in bb) for i in range(3)])
    c, r = (lo + hi) / 2, (hi - lo).length / 2
    sc = bpy.context.scene; sc.render.engine = "CYCLES"; sc.cycles.samples = 24; sc.cycles.device = "CPU"
    sc.render.resolution_x = sc.render.resolution_y = S; sc.view_settings.view_transform = "Standard"
    sc.world = bpy.data.worlds.new("W"); sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.95, 0.94, 0.92, 1)
    cam = bpy.data.objects.new("C", bpy.data.cameras.new("C")); sc.collection.objects.link(cam); sc.camera = cam; cam.data.angle = math.radians(30)
    sun = bpy.data.objects.new("S", bpy.data.lights.new("S", "SUN")); sc.collection.objects.link(sun); sun.data.energy = 2.5
    row = []
    for az, el in [(30, 25), (210, 20)]:
        ar, e = math.radians(az), math.radians(el)
        dv = Vector((-math.sin(ar) * math.cos(e), math.cos(ar) * math.cos(e), math.sin(e)))
        cam.location = c + dv * (r / math.tan(math.radians(15)) * 1.05)
        cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
        sun.rotation_euler = (-(dv + Vector((0.3, 0, 0.9)))).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = tempfile.mktemp(suffix=".png"); bpy.ops.render.render(write_still=True)
        row.append(np.array(bpy.data.images.load(sc.render.filepath).pixels[:], np.float32).reshape(S, S, 4))
    tiles.append(np.concatenate(row, 1))
grid = np.concatenate(tiles[::-1], 0)
im = bpy.data.images.new("g", grid.shape[1], grid.shape[0]); im.pixels = grid.ravel().tolist()
im.filepath_raw = out; im.file_format = "PNG"; im.save(); print("saved", ids)
