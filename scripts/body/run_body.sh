#!/bin/bash
# Smoothed dragon GLB -> production body: quad retopo, overlap-free UVs, baked normal + transferred colour maps.
# Usage: scripts/body/run_body.sh <clean.glb> <work_dir> [target_quads=16000] [tex=2048]
set -euo pipefail
IN=$1; W=$2; Q=${3:-16000}; TEX=${4:-2048}
D=$(cd "$(dirname "$0")" && pwd); B="blender -b --factory-startup -P"
mkdir -p "$W/tex"
$B "$D/retopo.py"        -- "$IN" "$W/1_retopo.blend" "$Q"
$B "$D/bake_body.py"     -- "$W/1_retopo.blend" "$W/2_baked.blend" "$W/tex" "$TEX"
$B "$D/transfer_maps.py" -- "$W/2_baked.blend" "$W/3_transfer.blend" "$W/tex"
$B "$D/export_glb.py"    -- "$W/3_transfer.blend" "$W/dragon_body.glb" "$W/dragon_body.blend"
