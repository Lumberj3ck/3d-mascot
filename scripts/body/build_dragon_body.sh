#!/bin/bash
# Exact recipe for the dragon production body (outputs/body/dragon_body.*):
#  - geometry: the smoothed dragon (outputs/dragon_clean.glb) collapse-decimated to 30k tris, overlap-free UVs
#  - normal map: baked from the smoothed dragon
#  - colours/roughness: baked from the raw Pixal3D dragon (outputs/dragon_mv3nt_s42.glb) - the smoothed mesh has
#    hidden folded triangles in grooves that show up as dark specks when baked - then sage recolor + gem emissive
# (QuadriFlow quads were tried first: they fold the paper-thin wing membranes into jagged, dark rims.)
# Usage: scripts/body/build_dragon_body.sh <work_dir>
set -euo pipefail
D=$(cd "$(dirname "$0")" && pwd); R=$(cd "$D/../.." && pwd)
RETOPO=decimate COLOR_SRC="$R/outputs/dragon_mv3nt_s42.glb" RECOLOR=1 PYTHON="${PYTHON:-$R/.venv/bin/python}" \
  "$D/run_body.sh" "$R/outputs/dragon_clean.glb" "$1" 30000
