"""Chart + pack UVs for a triangle mesh with xatlas (run with the project .venv, not Blender's Python).
Usage: python scripts/xatlas_uv.py <in.npz with V (n,3), F (m,3)> <out.npz> [resolution=2048] [padding=4]
Writes UV (m,3,2): per-triangle-corner UVs in the input triangle/corner order (xatlas preserves both).
"""
import sys
import numpy as np, xatlas

d = np.load(sys.argv[1]); V, F = d["V"].astype(np.float32), d["F"].astype(np.uint32)
res = int(sys.argv[3]) if len(sys.argv) > 3 else 2048; pad = int(sys.argv[4]) if len(sys.argv) > 4 else 4
atlas = xatlas.Atlas(); atlas.add_mesh(V, F)
co = xatlas.ChartOptions(); co.max_iterations = 4
po = xatlas.PackOptions(); po.resolution = res; po.padding = pad; po.bilinear = True; po.rotate_charts = True
atlas.generate(co, po)
vmap, idx, uv = atlas[0]
assert idx.shape[0] == F.shape[0] and np.all(vmap[idx] == F), "xatlas changed triangle/corner order"
np.savez(sys.argv[2], UV=uv[idx].astype(np.float32))
print(f"xatlas: {atlas.chart_count} charts, utilization {atlas.utilization * 100:.1f}%")
