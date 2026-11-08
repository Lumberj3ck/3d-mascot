#!/bin/bash
# Raw Pixal3D GLB -> clean, smooth, game-ready GLB (all local, headless Blender, CPU).
# Usage: scripts/clean/run_pipeline.sh <in.glb> <work_dir> [voxel=0.003] [taubin_iters=10] [target_tris=80000] [tex=2048]
set -euo pipefail
IN=$1; W=$2; VOX=${3:-0.003}; IT=${4:-10}; TRIS=${5:-80000}; TEX=${6:-2048}
D=$(cd "$(dirname "$0")" && pwd); PY=${PYTHON:-python3}
mkdir -p "$W"
B="blender -b --factory-startup -P"
$B "$D/remesh.py" -- "$IN" "$W/1_remesh.blend" "$VOX" "$IT" "$TRIS"
$B "$D/bake.py"   -- "$W/1_remesh.blend" "$W/2_baked.blend" "$TEX" "$W"
$PY "$D/recolor.py" "$W/dragon_basecolor.png" "$W/dragon_basecolor_sage.png" "$W/dragon_emissive.png"
$B "$D/finalize.py" -- "$W/2_baked.blend" "$W/dragon_basecolor_sage.png" "$W/dragon_emissive.png" "$W/dragon_clean.blend" "$W/dragon_clean.glb"
