#!/usr/bin/env bash
# Submit the placeholder first, then stage code and weights. Does not change bids.
set -euo pipefail
CLUSTER=us-mi355-k8s-niveditha
REPO=$(cd "$(dirname "$0")/.." && pwd)
kubectl --context "$CLUSTER" -n default apply -f "$REPO/k8s/serve.yaml"
kubectl --context "$CLUSTER" -n default apply -f "$REPO/k8s/benchmark.yaml"
kubectl --context "$CLUSTER" -n default wait --for=condition=Ready pod -l app=systems-bench --timeout=300s
tar -C "$REPO" --exclude=.git --exclude=.venv --exclude=local --exclude=local_data \
  --exclude=__pycache__ --exclude=.pytest_cache -cf - . | \
  kubectl --context "$CLUSTER" -n default exec -i job/systems-bench -- \
  bash -c 'mkdir -p /mnt/shared/nc-synthetic-data/code && tar -C /mnt/shared/nc-synthetic-data/code -xf -'
kubectl --context "$CLUSTER" -n default exec job/systems-bench -- bash -c '
  ROOT=/mnt/shared/nc-synthetic-data
  touch "$ROOT/control/START"
'
# Use the GPU node's larger host memory for NFS writeback. No model data is
# written to node-local disk. The image already includes huggingface_hub.
until kubectl --context "$CLUSTER" -n default exec job/mimo-serve -- true 2>/dev/null; do sleep 10; done
kubectl --context "$CLUSTER" -n default exec job/mimo-serve -- bash -c '
  export HF_HOME=/mnt/shared/nc-synthetic-data/cache/huggingface
  nohup python /mnt/shared/nc-synthetic-data/code/scripts/download.py \
    > /mnt/shared/nc-synthetic-data/logs/download-gpu.log 2>&1 < /dev/null &
'
echo 'After /health is ready, run scripts/smoke.py inside job/systems-bench, then create control/RUN.'
