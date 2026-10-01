#!/usr/bin/env bash
set -euo pipefail
ROOT=/mnt/shared/nc-synthetic-data
MODEL_DIR="$ROOT/models/MiMo-V2.6-Flash-MOPD-http"
export HF_HOME="$ROOT/cache/huggingface"
export XDG_CACHE_HOME="$ROOT/cache/xdg"
export VLLM_CACHE_ROOT="$ROOT/cache/vllm"
export TRITON_CACHE_DIR="$ROOT/cache/triton"
export TORCHINDUCTOR_CACHE_DIR="$ROOT/cache/torchinductor"
export AITER_JIT_DIR=/tmp/nc-synthetic-data/aiter
export CCACHE_DIR="$ROOT/cache/ccache"
export VLLM_ROCM_USE_AITER=1
export MAX_JOBS=64
export TOKENIZERS_PARALLELISM=false
mkdir -p "$HF_HOME" "$XDG_CACHE_HOME" "$VLLM_CACHE_ROOT" "$TRITON_CACHE_DIR" "$TORCHINDUCTOR_CACHE_DIR" "$AITER_JIT_DIR" "$CCACHE_DIR"
until [ -f "$MODEL_DIR/.ready.json" ]; do sleep 15; done
python "$ROOT/code/scripts/cache_sync.py" restore
python "$ROOT/code/scripts/cache_sync.py" watch &
CACHE_PID=$!
cleanup() {
  kill "$CACHE_PID" 2>/dev/null || true
  python "$ROOT/code/scripts/cache_sync.py" save
}
trap cleanup EXIT
python -c 'import torch, vllm; print("vLLM", vllm.__version__, "torch", torch.__version__, "ROCm", torch.version.hip, "GPUs", torch.cuda.device_count(), flush=True)'
python -m pip freeze > "$ROOT/logs/serve-packages.txt"
vllm serve "$MODEL_DIR" \
  --served-model-name mimo-v2.6-flash \
  --host 0.0.0.0 --port 8000 \
  --tensor-parallel-size 8 \
  --trust-remote-code \
  --reasoning-parser mimo \
  --generation-config vllm \
  --enable-prefix-caching \
  --enable-chunked-prefill \
  --gpu-memory-utilization 0.90 \
  --max-model-len 262144 \
  --max-num-seqs 512 \
  --max-num-batched-tokens 32768 &
SERVER_PID=$!
trap 'kill -TERM "$SERVER_PID" 2>/dev/null || true; wait "$SERVER_PID" || true; exit 143' TERM INT
wait "$SERVER_PID"
