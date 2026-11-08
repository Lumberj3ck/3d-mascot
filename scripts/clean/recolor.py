"""Shift the green areas of a baked base-color texture toward the concept sage, and build a gem emission map.
Cream, eyes, mouth and gem are left untouched (soft mask on hue/saturation).
Usage (plain Python + numpy/pillow, no Blender): python3 recolor.py <basecolor.png> <out_basecolor.png> <out_emissive.png> [r g b linear ratio]
Default ratio was measured from renders vs the concept sheet: (1.508, 1.371, 1.64)."""
import sys
import numpy as np
from PIL import Image, ImageFilter

def lin(c): return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
def srgb(c): c = np.clip(c, 0, 1); return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)
def ss(x, a, b): t = np.clip((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)

src, out_base, out_emis = sys.argv[1:4]
ratio = np.array([float(x) for x in sys.argv[4:7]]) if len(sys.argv) >= 7 else np.array([1.508, 1.371, 1.64])
tex = np.asarray(Image.open(src).convert("RGB")).astype(float) / 255
r, g, b = tex[..., 0], tex[..., 1], tex[..., 2]
mx, mn = tex.max(2), tex.min(2); sat = (mx - mn) / np.maximum(mx, 1e-6)
w = ss(g - r, -0.015, 0.03) * ss(g - b, 0.02, 0.08) * ss(sat, 0.08, 0.18) * ss(mx, 0.10, 0.22)
L = lin(tex)
out = srgb(L * (1 - w[..., None]) + L * ratio * w[..., None])
Image.fromarray((out * 255 + 0.5).astype(np.uint8)).save(out_base)
gem = ss(r, 0.75, 0.9) * ss(g, 0.6, 0.75) * ss(r - b, 0.35, 0.5) * ss(sat, 0.45, 0.6)
gem = np.asarray(Image.fromarray((gem * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.5))).astype(float) / 255
Image.fromarray((out * gem[..., None] * 255 + 0.5).astype(np.uint8)).save(out_emis)
print(f"recolored {w.mean()*100:.1f}% of pixels, gem mask {gem.mean()*100:.2f}%")
