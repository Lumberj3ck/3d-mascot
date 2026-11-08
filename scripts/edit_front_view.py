"""Paint the peeking tail out of the multi-view front input (inputs/mv_dragon/view00_azim000.png).

The turnaround sheet's front view shows the tail poking out beside the right leg; Pixal3D reconstructed it as
a stray forward-pointing hip spike. Everything left of the leg contour (measured line (309,800)->(333,928) in
the 1024^2 crop) between y=788..936 is made transparent with a ~1.5 px soft edge.
Usage: python scripts/edit_front_view.py <in.png> <out.png>
"""
import sys
import numpy as np
from PIL import Image

a = np.asarray(Image.open(sys.argv[1])).copy().astype(np.float32)
H, W, _ = a.shape
yy, xx = np.mgrid[0:H, 0:W]
x0, y0, x1, y1 = 309.0, 800.0, 333.0, 928.0
xl = x0 + (yy - y0) * (x1 - x0) / (y1 - y0)
band = (yy >= 788) & (yy <= 936) & (xx >= 200)
soft = np.clip((xl - 1.0 - xx) / 1.5, 0, 1)
a[..., 3] = np.where(band, a[..., 3] * (1 - soft), a[..., 3])
a[a[..., 3] == 0, :3] = 0
Image.fromarray(a.clip(0, 255).astype(np.uint8)).save(sys.argv[2])
