#!/bin/bash
# On the VM: install Blender (once) and run scripts/items/process_item.py for all items in parallel.
# Usage: bash ~/mascot/infra/process_items_vm.sh [ids...]
set -e
BL=~/blender-5.2.3-linux-x64/blender
if [ ! -x $BL ]; then
  sudo apt-get install -y -qq libxi6 libxkbcommon0 libsm6 libxrender1 libgl1 libegl1 libxfixes3 libxxf86vm1 >/dev/null
  cd ~ && curl -sSL https://download.blender.org/release/Blender5.2/blender-5.2.3-linux-x64.tar.xz | tar xJ
fi
cd ~/mascot
export XATLAS_PY=${XATLAS_PY:-$HOME/miniconda3/envs/trellis2/bin/python}  # .venv lives on the laptop; VM uses the conda env
IDS=${@:-$(python3 -c "import json;print(' '.join(i['id'] for i in json.load(open('inputs/items/items.json'))['items'] if i['method']=='pixal3d'))")}
mkdir -p logs/items_process
for id in $IDS; do
  ( $BL -b --factory-startup -P scripts/items/process_item.py -- $id > logs/items_process/$id.log 2>&1 \
      && echo "$id ok" || echo "$id FAILED" ) &
done
wait
echo PROCESS_DONE
