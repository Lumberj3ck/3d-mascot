# Handoff — 3D dragon mascot

Everything a new agent/person needs to continue this project. Read this first, then `README.md`.

## 1. Goal

Turn the 2D character sheets in `inputs/raw/` (a sage-green chibi dragon: turnaround sheet + 6-expression
sheet) into a 3D model. Approach: generate a strong **baseline with an image-to-3D model (Pixal3D)**, then
**edit it** (smoothing, cleanup, expressions, rigging) — mainly in Blender.

## 2. Current status (2026-11-08, end of session 2)

### Dragon
**Production body: `outputs/body/dragon_body.glb`** (+ `.blend`, previews `dragon_body.png`, `_wire.png`) — the
asset to rig/ship. 30k triangles, xatlas UVs (213 charts, 66 % use), 2048² base colour (sage) + tangent normal
map + roughness + emissive gem (strength 3). Y-up, faces −Z. Rebuild: `scripts/body/build_dragon_body.sh <dir>` (§5b).
Known nit: one pinhead dark speck on the right hand.

Chain: `inputs/mv_dragon` (front view with the peeking tail painted out, `scripts/edit_front_view.py`) →
Pixal3D multi-view seed 42 → **raw `outputs/dragon_mv3nt_s42.glb`** → clean pipeline (§5a) →
**smoothed `outputs/dragon_clean.glb`** (80k) → body pipeline (§5b) → production body.

Why the regeneration: the turnaround's front view shows the tail poking out beside the right leg; Pixal3D turned
it into a stray forward-pointing hip spike (in all older outputs). Patching it on the mesh failed repeatedly;
removing it from the input image fixed it at the source. `outputs/alt/dragon_mv3nt_s7.glb` = seed 7 (red gem).

Face (eyes/mouth/fang) is still **painted into the base colour** — neutral expression only.

### Rig — WIP (`scripts/body/rig.py`, untracked output)
29 bones (VRM humanoid names + tail, wings, ears), automatic heat weights constrained per body region (wings
only follow wing bones, ears only ear bones, collar only trunk…), test-pose strip rendered with world-axis
rotations. Status: rest/sad/step look fine; **arm raises (>~40°) wrinkle the flank/belly** — the stubby arms
grow out of the belly so region masks can't separate arm skin from flank skin. Next: finer arm weights
(geometric arm segmentation or envelope blend) and a chibi-sized arm range; then VRM export.

### Items — 12 generated + processed (`outputs/items/*.glb`, sheet `outputs/items/items_sheet.png`)
Concepts generated with Codex CLI image generation (`scripts/items/gen_concepts.py`), Pixal3D single-view on the
VM (`infra/batch_items.sh`), then `scripts/items/process_item.py` per item (see §5c). All 12 usable at concept
quality. Known issues: tail_ribbon bow has dark marbling; flower_crown has some tangled dark bits inside; food
bowl has a small dark notch at the paw. Procedural garments (scarf, sweater, cape) not built yet.

### Older raw results (kept for comparison)
**`outputs/dragon_mv3_s7.glb`** — previous baseline (has the hip spike). `dragon_mv3_s7_blender.png` = Blender
preview.

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

## 5b. Body pipeline (local, CPU, ~2 min) — `scripts/body/`
`build_dragon_body.sh <work_dir>` = `RETOPO=decimate COLOR_SRC=<raw> RECOLOR=1 run_body.sh <clean.glb> <dir> 30000`:
1. `retopo.py` — collapse-decimate the smoothed mesh to 30k tris (`quadriflow` mode exists but folds the
   paper-thin wing membranes into jagged dark rims — don't use it for the dragon). Imports the raw mesh as
   `ColorSrc`.
2. `bake_body.py` — **xatlas** UVs (`scripts/xatlas_uv.py`, runs in `.venv`); smart-project fragmented the belly
   into hundreds of islands whose borders showed as dark specks. Normal map ray-baked from the smoothed mesh;
   base colour/emission/roughness ray-baked from the **raw** mesh (the smoothed mesh hides folded triangles in
   grooves that bake as dark specks). Normal maps start flat; colour maps start magenta = "ray missed".
3. `transfer_maps.py` — keeps ray-baked texels, nearest-surface fallback only for misses, dilates islands.
4. `recolor.py` (RECOLOR=1) — sage shift + gem emissive; `export_glb.py` packs + exports.
`fix_region.py` (smooth / normal-flatten / despike a sphere) is kept for local repairs; not used now.

## 5c. Item pipeline — `scripts/items/process_item.py <id>` (Blender; ~1–6 min CPU each)
`level.py` (once, writes `outputs/items/level.json`): trimesh stable resting pose closest to the camera frame +
symmetry yaw (overrides: `NO_LEVEL` plush, `STAND` bow tie). Per item (`inputs/items/items.json` options):
- cleanup `remesh`: default = smooth + decimate the raw surface (thin shells: hat, bow tie, plush, plant, rug);
  `"voxel"` = voxel remesh first (chunky items: crown, glasses, bed, lamp, ribbon); `"meshlab"` = MeshLab quadric
  decimation (`scripts/items/meshlab_decimate.py`, needs `pymeshlab` in `.venv`; open/non-manifold raws: bootie,
  bowl). Blender collapse-decimation of raw Pixal3D items to ~1 % shatters them into shards; non-manifold edges
  are split first; floating debris removed.
- xatlas UVs; normal + colour **ray-baked** from the raw mesh (`cage_rel`: raise to ~0.02–0.025 when the cleaned
  surface sinks below the raw outer shell, else rays hit Pixal3D's dark inner layer → black blotches);
  nearest-surface fallback for misses.
- colour matched to the concept (per-channel linear gain from a concept-like render, capped 0.6–2.2);
  optional `emissive` mask (mushroom lamp); pivot bottom-centre for props, centre for wearables.
VM batch: `infra/process_items_vm.sh [ids]` (Blender 5.2.3 tarball + xatlas in the conda env; set `XATLAS_PY`).

## 5. Local machine
- Blender 5.2 is installed: `/usr/bin/blender` (headless: `blender -b --factory-startup -P script.py -- args`).
- Downloaded/third-party `.blend` files: inspect with `--disable-autoexec` (blend files can embed scripts).
- Python tooling via `uv`; local venv `.venv/` (gitignored) with scipy, pillow, numpy, trimesh:
  `uv venv .venv && uv pip install --python .venv/bin/python scipy pillow numpy trimesh`.
- Viewer: `python -m http.server` in repo root → http://localhost:8000/viewer/ (lists every GLB in `outputs/`).
- `scripts/prep_views.py inputs/raw/turnaround.png inputs/mv_dragon` regenerates the matted views
  (bbox constants for the sheet are hard-coded at the top).

## 6. Next steps

Done: smoothing, production body, 12 concept items. Next (see `docs/ROADMAP.md`): finish rig weights (arms) →
VRM 1.0 export → face decal atlas + expressions → procedural garments (scarf/sweater/cape) → Character Lab web app.

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
