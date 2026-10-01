#!/usr/bin/env bash
set -euo pipefail
ROOT=/mnt/shared/nc-synthetic-data
RUN_DIR="$ROOT/runs/${RUN_NAME:-otter-256-100}"
SUBJECT=${SUBJECT:-animal-behavior}
export HF_HOME="$ROOT/cache/huggingface"
export PIP_CACHE_DIR="$ROOT/cache/pip"
export PYTHONUNBUFFERED=1
export API_URL=http://mimo:8000/v1/chat/completions
export MODEL=mimo-v2.6-flash
cd "$ROOT/code"
python -m pip install -r requirements.lock
mkdir -p "$RUN_DIR"
python -m pip freeze > "$RUN_DIR/benchmark-packages.txt"
python - <<'PY'
import time, urllib.request
while True:
    try:
        with urllib.request.urlopen('http://mimo:8000/health', timeout=10) as r:
            if r.status == 200:
                break
    except Exception:
        pass
    time.sleep(10)
PY
python scripts/metrics.py "$RUN_DIR" &
METRICS_PID=$!
trap 'kill "$METRICS_PID" 2>/dev/null || true' EXIT
python systems_bench.py \
  --systems 1 --rules 16 --train 256 --test 100 \
  --subject "$SUBJECT" --seed 42 \
  --concurrency 256 --question-batches 16 \
  --output-dir "$RUN_DIR"
python systems_bench.py \
  --systems 1 --rules 16 --train 256 --test 100 \
  --subject "$SUBJECT" --seed 42 \
  --concurrency 256 --question-batches 16 \
  --output-dir "$RUN_DIR" --export-only
python scripts/validate.py "$RUN_DIR" --subject "$SUBJECT"
