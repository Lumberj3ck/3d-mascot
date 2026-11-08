# Handoff — 3D dragon mascot

Everything a new agent/person needs to continue this project. Read this first, then `README.md`.

## 1. Goal

Turn the 2D character sheets in `inputs/raw/` (a sage-green chibi dragon: turnaround sheet + 6-expression
sheet) into a 3D model. Approach: generate a strong **baseline with an image-to-3D model (Pixal3D)**, then
**edit it** (smoothing, cleanup, expressions, rigging) — mainly in Blender.

## 2. Current status (2026-11-08)

**Current model: `outputs/dragon_clean.glb`** (+ `dragon_clean.blend`, preview `dragon_clean.png`).
Smoothed, game-weight version of the raw baseline, made by the clean pipeline (§5a):
- 80k triangles, single closed manifold shell (0 boundary / 0 non-manifold edges; trimesh reports
  "not watertight" only because UV seams split vertices), 6 MB.
- Material `Dragon`: 2048² base colour (shifted toward the concept's sage), roughness, emissive gem
  (`KHR_materials_emissive_strength` = 3). No normal map yet.
- Same frame/scale as the raw baseline (Y-up, faces −Z).
- Known nits: fang slightly blurry after re-bake; Smart-UV packing uses only ~46 % of the texture.
- Face (eyes/mouth/fang) is **painted into the base colour** — neutral expression only. Expressions,
  rig, retopology etc. are not done yet → see `docs/ROADMAP.md`.

**Raw source: `outputs/dragon_mv3_s7.glb`** — Pixal3D multi-view, 3 views (front/side/back), seed 7.
- ✅ Correct face (`:3` mouth + single fang, big eyes), horns, head crest, ear frills, two-tone wings, glowing
  chest gem, cream belly plates, back spine ridge, tail stub, feet.
- ⚠️ Lumpy voxel-extraction surface, ~1M triangles, 4096² texture, ~33 MB (fixed by the clean pipeline).
- `dragon_mv3_s7.png` = flat-shaded nvdiffrast preview; `dragon_mv3_s7_blender.png` = Blender preview
  (same renderer/lighting as `dragon_clean.png`, for a fair comparison).

Other raw results in `outputs/` (kept for comparison / parts):

| File | Views | Verdict |
|---|---|---|
| `dragon_mv3_s7.glb` | front, side, back · seed 7 | **Best.** |
| `dragon_mv3_s42.glb` | front, side, back · seed 42 | Good; small stray dark marks next to eyes. |
| `dragon_mv4.glb` | + mirrored side as 4th (right) view | Body good, **mouth broken** (wide jagged grin, many teeth). Cause: mirroring the side view puts the fang on the wrong side; multi-view fusion averages features → extra teeth. **Don't use mirrored views.** |
| `dragon_single.glb` | front only (single-image mode) | Face good, but invents a long curled tail and a plain back. |

Each `.glb` has a `.png` turntable strip: **front, left side, back, right side, 3/4 view**.

`outputs/single_to_mv4.npy` — 4×4 transform (ICP, scale ≈1.19, rot ≈5°) mapping `dragon_single` onto
`dragon_mv4` (GLB coords). Made for a possible face transplant in Blender; probably unnecessary now that
`mv3_s7` has a good face. If reused against `mv3_s7`, recompute (the code is easy: sample surfaces, ICP with
scale on the head region `y > 0.05`).

## 3. Conventions (important, easy to get wrong)

- **Pixal3D input cameras** (`inputs/mv_dragon/transforms.json`): Blender/NeRF convention, camera-to-world 4×4,
  **world Z-up**, camera looks −Z. `camera_angle_x = 20°`, distance `3.1192`, object normalised to the unit
  cube. Frame 0 **must** be the canonical front view (camera at (0,−d,0)).
  - azim000 = front, azim090 = character's **left** side (snout points to image-left — matches the sheet's
    "Side" view), azim180 = back, azim270 = right side.
  - Crops: all views share one pixel scale (sheet is near-orthographic); longest object axis (height) fills
    ~91 % of the 1024² frame, like the training renders. Alpha is pre-matted, so the pipeline's rembg is skipped.
- **Output GLB**: **Y-up, character faces −Z**, fits roughly in [−0.5, 0.5]³ (height ≈ 0.97).
- The source sheet is AI-generated and not perfectly consistent (e.g. front view shows the tail poking out on
  the left, back view shows a centred stub). The sheet's "Top" view is unused.
- The **expression sheet** shows only the upper body — not used for generation. Intended use: reference for
  face textures / blendshapes (neutral, happy, sleepy, sad, excited, proud).

## 4. Infrastructure

### Nebius
- Nebius CLI: `~/.nebius/bin/nebius`, profile **`voice-demo`** (service-account auth, already configured on
  the user's machine). Credentials live in the user's local `.env` and `nebius-keys/` — **gitignored, never
  commit them**.
- Two projects available: **eu-west1** (has `gpu-h200-sxm`) and eu-north1 (has `gpu-b300-sxm`).
  We use **H200 in eu-west1** — B300 (Blackwell) needs driver ≥580 and many 3D CUDA extensions are untested there.
- VM **`mascot-3d`**: `gpu-h200-sxm` / `1gpu-16vcpu-200gb`, image family `ubuntu22.04-cuda12`
  (Ubuntu 22.04, CUDA toolkit 12.4, driver 550), 300 GB network SSD boot disk `mascot-3d-boot`.
  **State: STOPPED, disk kept** (disk ≈ $21/month; H200 ≈ $2.5–3.5/h while running).
  - Template: `infra/instance.example.json` → copy to `infra/instance.json` (gitignored), fill IDs + SSH key.
  - Do **not** touch the other VM in that project (`voice-demo-fish`) — unrelated project.

```bash
N=~/.nebius/bin/nebius
P=<eu-west1 project id from .env: NEBIS_PROJECT_ID_EU_WEST1>
$N compute instance list --parent-id $P                       # find mascot-3d id
$N compute instance start --id <id>                           # resume (env + weights already on disk)
$N compute instance get --id <id> --format json | grep -A2 public_ip_address   # IP may change after restart
ssh -i nebius-keys/vm_ed25519 mascot@<ip>                     # user: mascot
$N compute instance stop --id <id>                            # ALWAYS stop when done
```

### On the VM (already installed, survives stop/start)
- Conda env **`trellis2`**: `source ~/miniconda3/etc/profile.d/conda.sh && conda activate trellis2`
  (Python 3.10, torch 2.6.0+cu124, flash-attn 2.7.3, nvdiffrast, nvdiffrec, CuMesh, O-Voxel, FlexGEMM, natten 0.21.0 sm_90, utils3d custom wheel).
- `~/Pixal3D` (commit `f7cf384` + `infra/vm-patches/pixal3d.diff`), `~/TRELLIS.2`.
- Weights cached: `~/.cache/huggingface/hub/models--TencentARC--Pixal3D` (43 GB) + DINOv3, BiRefNet, MoGe, NAF.
- `~/run.sh` (= `infra/run.sh`), `~/render_glb.py` (= `scripts/render_glb.py`), inputs `~/mv_dragon`,
  `~/front_single.png`, results `~/runs/`.

```bash
# multi-view (what produced the baseline) — ~3–4 min, 100 % GPU
bash ~/run.sh mv3_s7 inference_mv.py --views_dir ~/mv_dragon --num_views 3 --seed 7 --output ~/runs/dragon_mv3_s7.glb
# single image
bash ~/run.sh sv inference.py --image ~/front_single.png --output ~/runs/dragon_single.glb
# preview strip (CUDA rasteriser; the VM has no OpenGL/EGL)
python ~/render_glb.py ~/runs/dragon_mv3_s7.glb ~/runs/dragon_mv3_s7.png 512
```
Two runs fit on the GPU concurrently (peak 42–93 GB of 141 GB). Default resolution is 1536 (`--resolution`).
Never pass `--low_vram` on the H200 (keeps models on CPU between stages, slower).

### Install gotchas (already fixed on the VM; needed if rebuilding from scratch)
1. TRELLIS.2 `setup.sh --flash-attn` fails (build isolation can't see torch) → install the prebuilt wheel
   `https://github.com/Dao-AILab/flash-attention/releases/download/v2.7.3/flash_attn-2.7.3+cu12torch2.6cxx11abiFALSE-cp310-cp310-linux_x86_64.whl`.
   (Fallback: `ATTN_BACKEND=sdpa`.)
2. Pixal3D `requirements.txt` pins `trimesh==4.10.1`, which conflicts with MoGe → unpin trimesh.
3. MoGe overwrites the custom `utils3d` → reinstall the Pixal3D wheel with `--force-reinstall --no-deps` afterwards.
4. Pixal3D's pipeline config loads gated `briaai/RMBG-2.0` → patched to open `ZhengPeng7/BiRefNet`
   (`infra/vm-patches/pixal3d.diff`). Alternatively `huggingface-cli login` with access to RMBG-2.0.
5. natten compiles ~268 CUDA files: ~15 min at 16 vCPU (`NATTEN_CUDA_ARCH=9.0`).
6. Pixal3D/TRELLIS.2 need `CUDA_HOME=/usr/local/cuda-12.4`.

## 5a. Clean pipeline (local, headless Blender, CPU, ~40 s)

```bash
PYTHON=.venv/bin/python scripts/clean/run_pipeline.sh outputs/dragon_mv3_s7.glb /tmp/clean \
    [voxel=0.003] [taubin_iters=10] [target_tris=80000] [tex=2048]
# -> /tmp/clean/dragon_clean.glb, dragon_clean.blend, baked PNGs, intermediate blends
```
Steps (`scripts/clean/`):
1. `remesh.py` — weld → voxel remesh (adaptivity 0) → Taubin smoothing (λ=0.5, μ=−0.53; numpy only,
   Blender's Python has no scipy) → decimate to target **triangles** → smooth shading.
   Keeps the textured high-poly as object `Original`, result as `Clean`.
2. `bake.py` — Smart UV Project on `Clean`, Cycles *Selected to Active* bake from `Original`
   (cage 0.006, max ray 0.02): base colour (DIFFUSE colour pass) + roughness → PNGs in the work dir.
3. `recolor.py` (plain Python, numpy+pillow) — shifts green texels toward the concept sage (linear-RGB
   ratio 1.508/1.371/1.64, measured from renders vs the sheet; cream/eyes/mouth/gem masked out) and builds
   the gem emissive map.
4. `finalize.py` — wires sage base colour + emission (strength 3) into the material, deletes `Original`,
   packs textures, saves `.blend`, exports GLB.

History: steps 1–3 were written by another agent session; `outputs/dragon_clean.*` are its artifacts
(exact voxel/iteration params not recorded). This session made the scripts run under `blender -b -P`,
removed the scipy dependency, fixed a hard-coded texture path, fixed the decimate target (it counted
quads, giving 2× the requested triangles), and added `finalize.py` + `run_pipeline.sh`. A re-run with the
defaults above reproduces the committed result visually.

Preview any GLB: `blender -b --factory-startup -P scripts/render_blender.py -- in.glb out.png 512 32`
(strip: front, left, back, right, 3/4; ~13 s).

## 5. Local machine
- Blender 5.2 is installed: `/usr/bin/blender` (headless: `blender -b --factory-startup -P script.py -- args`).
- Downloaded/third-party `.blend` files: inspect with `--disable-autoexec` (blend files can embed scripts).
- Python tooling via `uv`; local venv `.venv/` (gitignored) with scipy, pillow, numpy, trimesh:
  `uv venv .venv && uv pip install --python .venv/bin/python scipy pillow numpy trimesh`.
- Viewer: `python -m http.server` in repo root → http://localhost:8000/viewer/ (lists every GLB in `outputs/`).
- `scripts/prep_views.py inputs/raw/turnaround.png inputs/mv_dragon` regenerates the matted views
  (bbox constants for the sheet are hard-coded at the top).

## 6. Next steps

Smoothing is **done** (§5a). The product vision and full plan — rig, facial expressions, wardrobe/clothes
fitting, rooms/items, premium web rendering — live in **`docs/ROADMAP.md`**. Start there.

## 7. Repo map
```
inputs/raw/               original sheets (turnaround.png, expressions.png)
inputs/mv_dragon/         Pixal3D multi-view input (4 matted views + transforms.json)
inputs/front_single.png   single-view input
outputs/                  dragon_clean.* (current), raw Pixal3D GLBs, previews, ICP transform
scripts/prep_views.py     sheet → matted posed views
scripts/render_glb.py     headless GLB preview (nvdiffrast CUDA; runs on the VM)
scripts/render_blender.py headless GLB preview (local Blender, Cycles CPU, real materials)
scripts/clean/            raw GLB → clean game-weight GLB pipeline (§5a)
docs/ROADMAP.md           product vision + phased plan
infra/instance.example.json  Nebius VM spec template
infra/install.sh          env build script (see gotchas above for the fixes it lacks)
infra/run.sh              inference wrapper with GPU-utilisation logging
infra/vm-patches/         local patch applied to Pixal3D on the VM
logs/                     full logs + nvidia-smi CSVs of every run
viewer/index.html         model-viewer page for outputs/
```
