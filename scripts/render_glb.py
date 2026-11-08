"""Headless turntable preview of a textured GLB using nvdiffrast's CUDA rasterizer (no OpenGL needed).

Run on the GPU VM (trellis2 env):  python render_glb.py in.glb out.png [tile_size]
Output: one PNG strip with front / left / back / right / 3-4 views.
"""
import sys, math
import numpy as np, torch, trimesh
import nvdiffrast.torch as dr
from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
size = int(sys.argv[3]) if len(sys.argv) > 3 else 512
dev = "cuda"

scene = trimesh.load(src)
geoms = list(scene.dump(concatenate=False)) if isinstance(scene, trimesh.Scene) else [scene]

parts = []
for g in geoms:
    v = torch.tensor(g.vertices, dtype=torch.float32, device=dev)
    f = torch.tensor(g.faces, dtype=torch.int32, device=dev)
    vis = g.visual
    uv = tex = None
    if hasattr(vis, "uv") and vis.uv is not None:
        mat = vis.material
        img = getattr(mat, "baseColorTexture", None) or getattr(mat, "image", None)
        if img is not None:
            uv = torch.tensor(vis.uv, dtype=torch.float32, device=dev)
            uv = torch.stack([uv[:, 0], 1 - uv[:, 1]], -1)  # GL -> image-space v
            tex = torch.tensor(np.asarray(img.convert("RGB")), dtype=torch.float32, device=dev) / 255
    if tex is None:
        col = np.asarray(vis.to_color().vertex_colors)[:, :3] / 255.0 if hasattr(vis, "to_color") else np.full((len(g.vertices), 3), 0.7)
        parts.append((v, f, None, torch.tensor(col, dtype=torch.float32, device=dev)))
    else:
        parts.append((v, f, uv, tex))

allv = torch.cat([p[0] for p in parts])
lo, hi = allv.min(0).values, allv.max(0).values
center, radius = (lo + hi) / 2, float((hi - lo).norm() / 2)
print("bounds", lo.cpu().numpy().round(3), hi.cpu().numpy().round(3))

ctx = dr.RasterizeCudaContext()
fov = math.radians(30)
proj = torch.tensor([[1 / math.tan(fov / 2), 0, 0, 0], [0, 1 / math.tan(fov / 2), 0, 0],
                     [0, 0, -1.002, -0.02], [0, 0, -1, 0]], device=dev)
bg = torch.tensor([0.96, 0.95, 0.93], device=dev)


def look_at(eye, target):
    fwd = target - eye; fwd = fwd / fwd.norm()
    right = torch.linalg.cross(fwd, torch.tensor([0., 1., 0.], device=dev)); right = right / right.norm()
    up = torch.linalg.cross(right, fwd)
    m = torch.eye(4, device=dev)
    m[0, :3], m[1, :3], m[2, :3] = right, up, -fwd
    m[:3, 3] = -m[:3, :3] @ eye
    return m


tiles = []
# GLB is Y-up; Pixal3D output faces -Z. Order: front, left side, back, right side, 3-4 view
for azim, elev in [(180, 5), (270, 5), (0, 5), (90, 5), (215, 20)]:
    a, e = math.radians(azim), math.radians(elev)
    d = radius / math.tan(fov / 2) * 1.05
    eye = center + d * torch.tensor([math.sin(a) * math.cos(e), math.sin(e), math.cos(a) * math.cos(e)], device=dev)
    mvp = proj @ look_at(eye, center)
    light = (eye - center) / (eye - center).norm()
    light = light + torch.tensor([0.3, 0.5, 0.0], device=dev); light = light / light.norm()

    # Draw parts back to front using a shared depth buffer: render each, keep nearest.
    img = bg.expand(size, size, 3).clone()
    zbuf = torch.full((size, size), float("inf"), device=dev)
    for v, f, uv, tex in parts:
        vh = torch.cat([v, torch.ones_like(v[:, :1])], -1)
        clip = (vh @ mvp.T)[None]
        rast, _ = dr.rasterize(ctx, clip, f, (size, size))
        mask = rast[0, ..., 3] > 0
        z = rast[0, ..., 2]
        # face normals for flat-ish lambert shading
        fn = torch.linalg.cross(v[f[:, 1].long()] - v[f[:, 0].long()], v[f[:, 2].long()] - v[f[:, 0].long()])
        fn = fn / (fn.norm(dim=-1, keepdim=True) + 1e-12)
        tri = (rast[0, ..., 3].long() - 1).clamp(min=0)
        n = fn[tri]
        shade = 0.45 + 0.55 * (n @ light).abs()
        if tex is not None:
            uvi, _ = dr.interpolate(uv[None], rast, f)
            col = dr.texture(tex[None], uvi, filter_mode="linear")[0]
        else:
            col, _ = dr.interpolate(tex[None], rast, f); col = col[0]
        col = col * shade[..., None]
        closer = mask & (z < zbuf)
        img[closer] = col[closer]
        zbuf[closer] = z[closer]
    tiles.append((img.flip(0).clamp(0, 1) * 255).byte().cpu().numpy())

Image.fromarray(np.concatenate(tiles, 1)).save(dst)
print("saved", dst)
