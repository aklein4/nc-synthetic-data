#!/usr/bin/env bash
# Run a frozen snapshot on the CPU worker against the eight-GPU MiMo service.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
RUN_NAME=${1:-causal-64-256-100}
if (($#)); then shift; fi
if [[ ! "$RUN_NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo 'Run name must contain only letters, digits, underscores and hyphens.' >&2
  exit 1
fi
RUN=/mnt/shared/nc-synthetic-data/runs/$RUN_NAME
K=(kubectl --context us-mi355-k8s-niveditha -n default)
"${K[@]}" create -f k8s/full-worker.yaml
trap '"${K[@]}" delete pod systems-bench-full --wait=false >/dev/null' EXIT
"${K[@]}" wait --for=condition=Ready pod/systems-bench-full --timeout=300s
if ! "${K[@]}" exec systems-bench-full -- test -f "$RUN/code/.ready" >/dev/null 2>&1; then
  "${K[@]}" exec systems-bench-full -- mkdir -p "$RUN/code"
  tar -cf - systems_bench.py local_api.py requirements.lock system_data |
    "${K[@]}" exec -i systems-bench-full -- tar -C "$RUN/code" -xf -
  "${K[@]}" exec systems-bench-full -- touch "$RUN/code/.ready"
fi
"${K[@]}" exec systems-bench-full -- python -m pip install -q -r "$RUN/code/requirements.lock"
RUN_STATUS=0
"${K[@]}" exec systems-bench-full -- python "$RUN/code/systems_bench.py" \
  --output-dir "$RUN" --systems 64 --train 256 --test 100 "$@" || RUN_STATUS=$?
mkdir -p "local_data/$RUN_NAME"
if ! "${K[@]}" exec systems-bench-full -- tar -C "$RUN" -cf - . |
  tar -C "local_data/$RUN_NAME" -xf -; then
  echo "Artifact copy failed; the shared run directory remains at $RUN." >&2
  if ((RUN_STATUS == 0)); then RUN_STATUS=1; fi
fi
if ((RUN_STATUS != 0)); then
  echo "Run failed (exit $RUN_STATUS); preserved available artifacts for inspection/resume." >&2
  exit "$RUN_STATUS"
fi
echo "Complete: local_data/$RUN_NAME. GPU server remains running."
