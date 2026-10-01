#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
RUN=$(dirname "$PWD")
export API_URL=http://mimo:8000/v1/chat/completions MODEL=mimo-v2.6-flash
python -m pip install -r requirements.lock
python - "$1" <<'PY'
import sys, urllib.request
from huggingface_hub import HfApi
with urllib.request.urlopen('http://mimo:8000/health', timeout=10) as response:
    assert response.status == 200
api = HfApi()
print('Hugging Face account:', api.whoami()['name'], flush=True)
api.create_repo(sys.argv[1], repo_type='dataset', exist_ok=True)
api.auth_check(sys.argv[1], repo_type='dataset', write=True)
print('Upload destination verified:', sys.argv[1], flush=True)
PY
python -m pip freeze > "$RUN/benchmark-packages.txt"
python scripts/metrics.py "$RUN" &
METRICS_PID=$!
trap 'kill "$METRICS_PID" 2>/dev/null || true' EXIT
python systems_bench.py \
  --systems 64 --rules 16 --train 256 --test 100 --subject mixed --seed 42 \
  --row-concurrency 32 --concurrency 512 --question-batches 16 \
  --output-dir "$RUN" --upload --output-dataset "$1" \
  2>&1 | tee -a "$RUN/benchmark.log"
