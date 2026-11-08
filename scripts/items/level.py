"""Estimate a leveling transform for each raw Pixal3D item (single-view output carries the concept's camera
tilt/yaw). Pose = the trimesh stable resting pose closest to the current orientation; for mirror-symmetric
items, yaw is then chosen so the object is symmetric about the X=0 plane (facing straight ahead).

Usage: python scripts/items/level.py outputs/items/raw outputs/items/level.json
Frame: glTF (Y-up, front = -Z). Writes {id: 4x4 matrix}.
"""
import sys, json, glob, os
import numpy as np, trimesh
from scipy.spatial import cKDTree

SRC, OUT = sys.argv[1], sys.argv[2]
cfg = {i["id"]: i for i in json.load(open("inputs/items/items.json"))["items"]}
NO_LEVEL = {"star_plush"}  # stands upright like the concept; its most stable pose is lying on its back
STAND = {"bow_tie"}        # flat object worn facing forward: take the lying pose, then stand it up facing -Z
SYMMETRIC = {"wizard_hat", "flower_crown", "round_glasses", "bow_tie", "bootie", "tail_ribbon", "star_plush",
             "cushion_bed", "food_bowl", "potted_plant", "mushroom_lamp", "round_rug"}

def rot_between(a, b):
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    v, c = np.cross(a, b), np.dot(a, b)
    if np.linalg.norm(v) < 1e-9: return np.eye(3) if c > 0 else -np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1 / (1 + c))

def yaw(t):
    c, s = np.cos(t), np.sin(t)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])

out = {}
for path in sorted(glob.glob(os.path.join(SRC, "*.glb"))):
    iid = os.path.basename(path)[:-4]
    m = trimesh.load(path).to_geometry()
    m = trimesh.Trimesh(m.vertices, m.faces, process=True)
    c = m.bounds.mean(0)
    # --- stable poses (in a Z-down-gravity convention: pose maps mesh so it rests on z=0)
    poses, probs = trimesh.poses.compute_stable_poses(m, n_samples=1, threshold=0.0)
    # in glTF frame "up" is +Y. A pose T rests the mesh on the XY plane with +Z up. The world-up of that pose,
    # expressed in the current mesh frame, is R^T @ [0,0,1]. Pick the pose whose up is closest to current +Y.
    best = None
    for T, p in zip(poses, probs):
        up_in_mesh = T[:3, :3].T @ np.array([0, 0, 1.0])
        ang = np.degrees(np.arccos(np.clip(up_in_mesh @ np.array([0, 1.0, 0]), -1, 1)))
        if p < 0.01: continue
        if best is None or ang < best[0]: best = (ang, up_in_mesh, p)
    ang, up_in_mesh, p = best
    R = rot_between(up_in_mesh, np.array([0, 1.0, 0]))       # tilt correction only (minimal rotation)
    if iid in NO_LEVEL: R, ang = np.eye(3), 0.0
    if iid in STAND:  # lying pose has the broad face up (+Y); rotate +90 deg about X so it faces front (-Z)
        R = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0.0]]) @ R
    pts = (m.sample(20000) - c) @ R.T
    # --- yaw for symmetry: search t in [-70, 70] deg minimizing mirror (x -> -x) deviation
    Y = np.eye(3); sym_err = None
    if iid in SYMMETRIC:
        tree = cKDTree(pts); best_t = None
        for t in np.radians(np.arange(-70, 71, 1.0)):
            q = pts @ yaw(t).T; q[:, 0] *= -1; q = q @ yaw(t)    # mirror across the rotated plane
            d = np.median(tree.query(q)[0])
            if best_t is None or d < best_t[1]: best_t = (t, d)
        Y = yaw(best_t[0]); sym_err = best_t[1]
    M = np.eye(4); M[:3, :3] = Y @ R; M[:3, 3] = -(Y @ R) @ c
    out[iid] = M.tolist()
    ext = np.ptp(m.vertices, 0)
    print(f"{iid:15s} tilt {ang:5.1f} deg (pose p={p:.2f})  yaw {np.degrees(np.arctan2(Y[0,2], Y[0,0])):6.1f} deg  "
          f"sym_err {sym_err if sym_err is None else round(float(sym_err), 4)}")
json.dump(out, open(OUT, "w"), indent=1)
