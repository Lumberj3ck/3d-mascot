#!/bin/bash
# Usage on VM: bash run.sh <name> <inference.py args...>
# Runs Pixal3D fully on GPU and logs GPU utilisation alongside.
NAME=$1; shift
source ~/miniconda3/etc/profile.d/conda.sh; conda activate trellis2
export CUDA_HOME=/usr/local/cuda-12.4
python -c "import flash_attn" 2>/dev/null || export ATTN_BACKEND=sdpa
echo "ATTN_BACKEND=${ATTN_BACKEND:-flash_attn}"
mkdir -p ~/runs
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv -l 2 > ~/runs/$NAME.gpu.csv &
SMI=$!
cd ~/Pixal3D
/usr/bin/time -v python "$@" 2>&1 | tee ~/runs/$NAME.log
kill $SMI
echo "peak GPU util: $(tail -n +2 ~/runs/$NAME.gpu.csv | cut -d, -f2 | sort -n | tail -1)  peak mem: $(tail -n +2 ~/runs/$NAME.gpu.csv | cut -d, -f3 | sort -n | tail -1)"
