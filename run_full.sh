#!/usr/bin/env bash
# Run with bash, not source. Only the CPU worker is removed on exit.
(
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
DESTINATION=${1:-aklein4/AlwaysLearningBench-v1}
RUN_NAME=full-64-256-100-v56
RUN=/mnt/shared/nc-synthetic-data/runs/$RUN_NAME
K=(kubectl --context us-mi355-k8s-niveditha -n default)
"${K[@]}" create -f k8s/full-worker.yaml
trap '"${K[@]}" delete pod systems-bench-full --wait=false >/dev/null' EXIT
"${K[@]}" wait --for=condition=Ready pod/systems-bench-full --timeout=300s
# Freeze code on first launch; retries reuse that exact snapshot and checkpoint.
if ! "${K[@]}" exec systems-bench-full -- test -f "$RUN/code/.ready"; then
  "${K[@]}" exec systems-bench-full -- mkdir -p "$RUN/code"
  tar -cf - systems_bench.py local_api.py requirements.lock system_data scripts |
    "${K[@]}" exec -i systems-bench-full -- tar -C "$RUN/code" -xf -
  "${K[@]}" exec systems-bench-full -- touch "$RUN/code/.ready"
fi
"${K[@]}" exec systems-bench-full -- bash "$RUN/code/scripts/full-run.sh" "$DESTINATION"
mkdir -p "local_data/$RUN_NAME"
"${K[@]}" exec systems-bench-full -- tar -C "$RUN" -cf - . |
  tar -C "local_data/$RUN_NAME" -xf -
echo "Complete: uploaded to $DESTINATION; copied to local_data/$RUN_NAME. GPU server remains running."
)
