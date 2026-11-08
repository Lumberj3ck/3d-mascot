#!/bin/bash
# On the VM: single-view Pixal3D for every ~/items/*.png -> ~/runs/items/<id>.glb (+ preview), N parallel.
# Usage: bash batch_items.sh [parallel=3] [seed=42]
P=${1:-3}; SEED=${2:-42}
mkdir -p ~/runs/items
ls ~/items/*.png | xargs -P "$P" -I{} bash -c '
  id=$(basename {} .png)
  [ -f ~/runs/items/$id.glb ] && { echo "$id skip"; exit 0; }
  bash ~/run.sh item_$id inference.py --image {} --output ~/runs/items/$id.glb --seed '"$SEED"' > ~/runs/items/$id.out 2>&1
  if [ -f ~/runs/items/$id.glb ]; then
    source ~/miniconda3/etc/profile.d/conda.sh; conda activate trellis2
    python ~/render_glb.py ~/runs/items/$id.glb ~/runs/items/$id.png 384 > /dev/null 2>&1
    echo "$id ok $(grep -o "Elapsed.*" ~/runs/items/$id.out)"
  else echo "$id FAILED"; fi'
echo BATCH_DONE
