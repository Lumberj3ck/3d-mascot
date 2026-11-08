# 3D mascot — sage green chibi dragon

Image-to-3D baseline for the dragon mascot, generated with [Pixal3D](https://github.com/TencentARC/Pixal3D)
(TencentARC, SIGGRAPH 2026, TRELLIS.2 backbone) on a Nebius H200 VM.

## Results (`outputs/`)

| File | Input | Notes |
|---|---|---|
| **`dragon_mv3_s7.glb`** | front + side + back, seed 7 | **Best baseline** — correct `:3` mouth + fang, faithful back/side |
| `dragon_mv3_s42.glb` | front + side + back, seed 42 | Good, small stray marks near eyes |
| `dragon_mv4.glb` | + mirrored side as 4th view | Body good, mouth broken (mirrored view puts the fang on the wrong side) |
| `dragon_single.glb` | front only | Face good, invents a long tail / plain back |

Each `.glb` has a turntable preview `.png` (front / left / back / right / 3-4).
`single_to_mv4.npy` is the 4x4 ICP transform aligning `dragon_single` onto the multi-view meshes
(scale ~1.19, ~5 deg) for face/part transplanting in Blender.

View locally: `python -m http.server` in the repo root, open http://localhost:8000/viewer/.

## Inputs

- `inputs/raw/` — original turnaround + expression sheets.
- `inputs/mv_dragon/` — matted 1024² views + `transforms.json` (Blender/NeRF convention, Z-up,
  20° fov, distance 3.119 — same rig as Pixal3D's training renders). Built by
  `scripts/prep_views.py inputs/raw/turnaround.png inputs/mv_dragon`.
- `inputs/front_single.png` — front view for single-image mode.

## Reproduce on Nebius

- `infra/instance.example.json` — VM spec template (gpu-h200-sxm 1gpu, Ubuntu 22.04 + CUDA 12.4 image, 300 GB SSD).
  Copy `infra/instance.example.json` to `infra/instance.json` (gitignored), fill in project/subnet IDs and your SSH key, then `nebius compute instance create --file infra/instance.json`.
- `infra/install.sh` — TRELLIS.2 env + Pixal3D deps (natten built for sm_90). Post-install fixes that were needed:
  - Pixal3D `requirements.txt`: unpin `trimesh` (conflicts with MoGe), then reinstall the custom `utils3d` wheel with `--force-reinstall --no-deps`.
  - flash-attn: install the prebuilt wheel `flash_attn-2.7.3+cu12torch2.6cxx11abiFALSE-cp310-cp310-linux_x86_64.whl` (source build fails).
  - `infra/vm-patches/pixal3d.diff`: swaps gated `briaai/RMBG-2.0` for open `ZhengPeng7/BiRefNet`.
- `infra/run.sh <name> <script> <args>` — runs inference with GPU utilisation logged (`logs/`).
  e.g. `bash run.sh mv3_s7 inference_mv.py --views_dir ~/mv_dragon --num_views 3 --seed 7 --output ~/runs/dragon_mv3_s7.glb`
- `scripts/render_glb.py` — headless preview renderer (nvdiffrast CUDA, no OpenGL needed).

Each run: ~3-4 min on H200, 100% GPU, 42–93 GB VRAM.
