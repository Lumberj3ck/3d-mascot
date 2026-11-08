#!/bin/bash
# Smoothed dragon GLB -> production body: quad retopo, overlap-free UVs, baked normal + transferred colour maps.
# Usage: [FIX="cx cy cz r"] [FIX_MODE=despike|mesh] scripts/body/run_body.sh <clean.glb> <work_dir> [target_quads=16000] [tex=2048]
# FIX: optional sphere repaired on the quad mesh (despike = remove protrusion, mesh = smooth) + normal map flattened.
# RETOPO: quadriflow (default, Q = quads) | decimate (Q = triangles; keeps thin membranes)
# COLOR_SRC: optional textured mesh to bake/transfer colours from (default: <clean.glb>).
# The dragon: see scripts/body/build_dragon_body.sh
set -euo pipefail
IN=$1; W=$2; Q=${3:-16000}; TEX=${4:-2048}
D=$(cd "$(dirname "$0")" && pwd); B="blender -b --factory-startup -P"
mkdir -p "$W/tex"
$B "$D/retopo.py"        -- "$IN" "$W/1_retopo.blend" "$Q" "${COLOR_SRC:--}" "${RETOPO:-quadriflow}"
if [ -n "${FIX:-}" ]; then $B "$D/fix_region.py" -- "${FIX_MODE:-mesh}" "$W/1_retopo.blend" "$W/1_retopo.blend" "$W/tex" $FIX; fi
# SMOOTH: extra ';'-separated spheres "cx cy cz r" smoothed on the quad mesh (e.g. thin wing rims QuadriFlow folds)
IFS=';' read -ra SPHERES <<< "${SMOOTH:-}"
for S in "${SPHERES[@]}"; do [ -n "$S" ] && $B "$D/fix_region.py" -- mesh "$W/1_retopo.blend" "$W/1_retopo.blend" "$W/tex" $S; done
$B "$D/bake_body.py"     -- "$W/1_retopo.blend" "$W/2_baked.blend" "$W/tex" "$TEX"
$B "$D/transfer_maps.py" -- "$W/2_baked.blend" "$W/3_transfer.blend" "$W/tex"
if [ -n "${FIX:-}" ]; then $B "$D/fix_region.py" -- normal "$W/3_transfer.blend" "$W/3_transfer.blend" "$W/tex" $FIX; fi
if [ -n "${RECOLOR:-}" ]; then  # sage shift + gem emissive on the baked raw colours (scripts/clean/recolor.py)
  ${PYTHON:-python3} "$D/../clean/recolor.py" "$W/tex/body_basecolor.png" "$W/tex/body_basecolor_sage.png" "$W/tex/body_emissive.png"
  $B "$D/export_glb.py" -- "$W/3_transfer.blend" "$W/dragon_body.glb" "$W/dragon_body.blend" "$W/tex/body_basecolor_sage.png" "$W/tex/body_emissive.png" 3.0
else
  $B "$D/export_glb.py"    -- "$W/3_transfer.blend" "$W/dragon_body.glb" "$W/dragon_body.blend"
fi
