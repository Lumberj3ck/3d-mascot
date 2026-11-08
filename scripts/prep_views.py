"""Cut the turnaround sheet into posed RGBA views for Pixal3D (inference_mv.py + inference.py).

Views share one pixel scale (sheet is near-orthographic), so every crop uses the same
square window centered on that view's bbox; the object's longest axis fills ~91% of the
frame, matching the training renders (unit cube, 20deg fov, distance 3.119).
"""
import json, sys
import numpy as np
from PIL import Image
from scipy import ndimage

SRC, OUT = sys.argv[1], sys.argv[2]
GROUND_Y = 633          # first row of the ground line
TOP_Y = 24
FILL = 0.91
DIST = 3.1192049980163574
# x-extents of each view on the sheet (measured)
VIEWS = {"front": (106, 590), "side": (662, 1009), "back": (1087, 1573)}

im = np.asarray(Image.open(SRC).convert("RGB")).astype(np.float32)
H, W, _ = im.shape

# --- matte: anything noticeably non-white, then keep components connected to the views
dist_white = 255.0 - im.min(-1)
sat = im.max(-1) - im.min(-1)
fg = (dist_white > 14) | (sat > 12)
fg[GROUND_Y - 1:, :] = False
fg = ndimage.binary_closing(fg, iterations=2)
fg = ndimage.binary_fill_holes(fg)
lab, n = ndimage.label(fg)
sizes = ndimage.sum(fg, lab, range(1, n + 1))
fg = np.isin(lab, 1 + np.where(sizes > 2000)[0])
# soft edge: feather 1px using the colour distance in a thin band
band = ndimage.binary_dilation(fg, iterations=1) & ~ndimage.binary_erosion(fg, iterations=1)
soft = np.clip((np.maximum(dist_white, sat * 1.2) - 4) / 20, 0, 1)
alpha = np.where(band, soft, fg.astype(np.float32))
alpha[GROUND_Y - 1:, :] = 0

rgba = np.dstack([im, alpha * 255]).clip(0, 255).astype(np.uint8)
height = GROUND_Y - TOP_Y
S = int(round(height / FILL))
cy = (TOP_Y + GROUND_Y) / 2

def crop(xa, xb):
    cx = (xa + xb) / 2
    src = rgba.copy()
    src[:, :max(xa - 3, 0), 3] = 0          # drop neighbouring views
    src[:, xb + 4:, 3] = 0
    out = np.zeros((S, S, 4), np.uint8)
    x0, y0 = int(round(cx - S / 2)), int(round(cy - S / 2))
    sx0, sy0 = max(x0, 0), max(y0, 0)
    sx1, sy1 = min(x0 + S, W), min(y0 + S, H)
    out[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = src[sy0:sy1, sx0:sx1]
    out[out[..., 3] == 0, :3] = 0
    return Image.fromarray(out).resize((1024, 1024), Image.Resampling.LANCZOS)

import os
os.makedirs(OUT, exist_ok=True)
crops = {k: crop(a, b) for k, (a, b) in VIEWS.items()}
crops["side_mirror"] = crops["side"].transpose(Image.Transpose.FLIP_LEFT_RIGHT)

def T(azim):
    # camera-to-world, Z-up, camera at azimuth `azim` around the object (example rig)
    m = {0:   [[1,0,0,0],[0,0,-1,-DIST],[0,1,0,0],[0,0,0,1]],
         90:  [[0,0,1,DIST],[1,0,0,0],[0,1,0,0],[0,0,0,1]],
         180: [[-1,0,0,0],[0,0,1,DIST],[0,1,0,0],[0,0,0,1]],
         270: [[0,0,-1,-DIST],[-1,0,0,0],[0,1,0,0],[0,0,0,1]]}[azim]
    return m

frames = []
for i, (key, azim) in enumerate([("front", 0), ("side", 90), ("back", 180), ("side_mirror", 270)]):
    fn = f"view{i:02d}_azim{azim:03d}.png"
    crops[key].save(os.path.join(OUT, fn))
    frames.append({"file_path": fn, "name": f"azim{azim:03d}", "transform_matrix": T(azim)})
json.dump({"camera_angle_x": 0.3490658503988659, "mesh_scale": 1.0, "frames": frames},
          open(os.path.join(OUT, "transforms.json"), "w"), indent=2)
crops["front"].save(os.path.join(OUT, "..", "front_single.png"))
print("crop size", S, "->1024; views:", [f["file_path"] for f in frames])
