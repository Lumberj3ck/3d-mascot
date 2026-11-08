#!/bin/bash
# Runs on the VM. Builds the TRELLIS.2 env + Pixal3D deps.
set -x
source ~/miniconda3/etc/profile.d/conda.sh
export CUDA_HOME=/usr/local/cuda-12.4
export PATH=$CUDA_HOME/bin:$PATH
export MAX_JOBS=16
export TORCH_CUDA_ARCH_LIST="9.0"
cd ~/TRELLIS.2
. ./setup.sh --new-env --basic --flash-attn --nvdiffrast --nvdiffrec --cumesh --o-voxel --flexgemm
conda activate trellis2
python -c "import torch;print('torch',torch.__version__,torch.cuda.is_available())"
cd ~/Pixal3D
pip install -r requirements.txt
NATTEN_CUDA_ARCH="9.0" NATTEN_N_WORKERS=16 pip install natten==0.21.0 --no-build-isolation
pip install https://github.com/LDYang694/Storages/releases/download/20260430/utils3d-0.0.2-py3-none-any.whl
pip install -U "huggingface_hub[cli]"
python - <<'PY'
import importlib
for m in ["torch","flash_attn","nvdiffrast.torch","cumesh","o_voxel","flex_gemm","natten","utils3d","transformers","diffusers"]:
    try: importlib.import_module(m); print("OK ", m)
    except Exception as e: print("FAIL", m, repr(e)[:200])
PY
echo INSTALL_DONE
