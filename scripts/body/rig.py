"""Build the dragon skeleton (VRM humanoid naming + extra spring chains) and skin the production body.

Usage: blender -b --factory-startup -P scripts/body/rig.py -- <dragon_body.blend> <out.blend> [poses.png]
Joint positions were measured on outputs/body/dragon_body.glb (Blender coords: +X = character's RIGHT,
+Y = front, +Z = up; see HANDOFF). Right-side joints are listed; left side is mirrored (x -> -x).
"""
import sys, math, os
import bpy
from mathutils import Vector, Matrix

args = sys.argv[sys.argv.index("--") + 1:]
IN, OUT = args[0], args[1]
POSES = args[2] if len(args) > 2 else None

# name: (head, tail, parent, deform)
CENTER = {
    "hips":  ((0, 0.00, -0.36), (0, 0.00, -0.26), None),
    "spine": ((0, 0.00, -0.26), (0, 0.00, -0.16), "hips"),
    "chest": ((0, 0.00, -0.16), (0, 0.00, -0.06), "spine"),
    "neck":  ((0, 0.00, -0.06), (0, 0.00, 0.00), "chest"),
    "head":  ((0, 0.00, 0.00), (0, 0.00, 0.42), "neck"),
    "tail_0": ((0, -0.12, -0.34), (0, -0.20, -0.34), "hips"),
    "tail_1": ((0, -0.20, -0.34), (0, -0.28, -0.33), "tail_0"),
}
RIGHT = {  # VRM: "right*" = character's right = +X here
    "UpperLeg": ((0.10, 0.02, -0.36), (0.11, 0.03, -0.43), "hips"),
    "LowerLeg": ((0.11, 0.03, -0.43), (0.11, 0.04, -0.47), "UpperLeg"),
    "Foot":     ((0.11, 0.04, -0.47), (0.11, 0.12, -0.48), "LowerLeg"),
    "UpperArm": ((0.13, 0.04, -0.13), (0.19, 0.11, -0.19), "chest"),
    "LowerArm": ((0.19, 0.11, -0.19), (0.20, 0.15, -0.25), "UpperArm"),
    "Hand":     ((0.20, 0.15, -0.25), (0.18, 0.18, -0.30), "LowerArm"),
    "Wing_0":   ((0.12, -0.12, -0.08), (0.24, -0.16, -0.05), "chest"),
    "Wing_1":   ((0.24, -0.16, -0.05), (0.33, -0.17, -0.06), "Wing_0"),
    "Wing_2":   ((0.33, -0.17, -0.06), (0.39, -0.15, -0.18), "Wing_1"),
    "Ear_0":    ((0.21, -0.02, 0.22), (0.30, -0.03, 0.22), "head"),
    "Ear_1":    ((0.30, -0.03, 0.22), (0.38, -0.03, 0.25), "Ear_0"),
}

bpy.ops.wm.open_mainfile(filepath=IN)
body = bpy.data.objects["Body"]
for o in bpy.context.scene.objects: o.select_set(False)

arm_data = bpy.data.armatures.new("DragonRig")
rig = bpy.data.objects.new("DragonRig", arm_data)
bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig; rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
eb = arm_data.edit_bones
def add(name, head, tail, parent):
    b = eb.new(name); b.head = Vector(head); b.tail = Vector(tail)
    if parent: b.parent = eb[parent]; b.use_connect = (Vector(parent and eb[parent].tail) - b.head).length < 1e-4
    return b
for n, (h, t, p) in CENTER.items(): add(n, h, t, p)
for side, sx in (("right", 1), ("left", -1)):
    for n, (h, t, p) in RIGHT.items():
        mir = lambda v: (v[0] * sx, v[1], v[2])
        parent = p if p in CENTER else f"{side}{p}"
        add(f"{side}{n}", mir(h), mir(t), parent)
# consistent bone roll: Z axis of every bone points to front (+Y) where possible
for b in eb:
    b.align_roll(Vector((0, 1, 0)) if abs((b.tail - b.head).normalized().y) < 0.9 else Vector((0, 0, 1)))
bpy.ops.object.mode_set(mode="OBJECT")
print("bones:", len(arm_data.bones), flush=True)

# ---- skin: automatic (heat) weights
for o in bpy.context.scene.objects: o.select_set(False)
body.select_set(True); rig.select_set(True); bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type="ARMATURE_AUTO")
groups = {g.index: g.name for g in body.vertex_groups}
unweighted = sum(1 for v in body.data.vertices if not any(g.weight > 0.001 for g in v.groups))
print(f"skinned: {len(groups)} vertex groups, unweighted vertices: {unweighted}", flush=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("saved", OUT, flush=True)

# ---- optional: deformation test poses rendered to a strip
if POSES:
    import numpy as np, tempfile
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"; sc.cycles.samples = 16; sc.cycles.device = "CPU"; sc.cycles.use_denoising = True
    sc.render.resolution_x = sc.render.resolution_y = 420; sc.view_settings.view_transform = "Standard"
    sc.world = bpy.data.worlds.new("W"); sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.93, 0.92, 0.9, 1)
    cam = bpy.data.objects.new("C", bpy.data.cameras.new("C")); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.angle = math.radians(30)
    sun = bpy.data.objects.new("S", bpy.data.lights.new("S", "SUN")); sc.collection.objects.link(sun); sun.data.energy = 3
    a, e = math.radians(30), math.radians(12)
    d = Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
    cam.location = d * 2.6; cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    sun.rotation_euler = (-(d + Vector((0.3, 0, 0.9)))).to_track_quat("-Z", "Y").to_euler()
    P = rig.pose.bones
    def reset():
        for pb in P: pb.rotation_mode = "XYZ"; pb.rotation_euler = (0, 0, 0); pb.location = (0, 0, 0)
    poses = {
        "rest": {},
        "wave": {"rightUpperArm": (0, 0, math.radians(-70)), "rightLowerArm": (0, 0, math.radians(-40)), "head": (0, math.radians(12), 0)},
        "happy": {"head": (math.radians(-10), 0, math.radians(10)), "leftUpperArm": (0, 0, math.radians(60)), "rightUpperArm": (0, 0, math.radians(-60)),
                  "leftWing_0": (0, 0, math.radians(25)), "rightWing_0": (0, 0, math.radians(-25)), "tail_0": (0, 0, math.radians(30))},
        "sad": {"head": (math.radians(18), 0, 0), "neck": (math.radians(8), 0, 0), "leftEar_0": (0, math.radians(-35), 0), "rightEar_0": (0, math.radians(35), 0),
                "leftWing_0": (0, 0, math.radians(-20)), "rightWing_0": (0, 0, math.radians(20))},
        "step": {"leftUpperLeg": (math.radians(-35), 0, 0), "leftLowerLeg": (math.radians(25), 0, 0), "rightUpperLeg": (math.radians(15), 0, 0),
                 "spine": (0, 0, math.radians(8))},
    }
    tiles = []
    for name, rot in poses.items():
        reset()
        for b, r in rot.items(): P[b].rotation_euler = r
        bpy.context.view_layer.update()
        sc.render.filepath = tempfile.mktemp(suffix=".png"); bpy.ops.render.render(write_still=True)
        im = bpy.data.images.load(sc.render.filepath)
        tiles.append(np.array(im.pixels[:], np.float32).reshape(420, 420, 4))
    reset()
    strip = np.concatenate(tiles, 1)
    out = bpy.data.images.new("strip", strip.shape[1], 420); out.pixels = strip.ravel().tolist()
    out.filepath_raw = os.path.abspath(POSES); out.file_format = "PNG"; out.save()
    print("poses saved", POSES, list(poses), flush=True)
