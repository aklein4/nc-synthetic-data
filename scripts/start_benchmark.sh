#!/usr/bin/env bash
set -euo pipefail
ROOT=/mnt/shared/nc-synthetic-data
cd "$ROOT/code"
python -m pip install -r requirements.lock
python - <<'PY'
import time, urllib.request
while True:
    try:
        with urllib.request.urlopen('http://mimo:8000/health', timeout=10) as response:
            if response.status == 200:
                break
    except Exception:
        pass
    time.sleep(10)
print('Server healthy; checking JSON and thinking modes.', flush=True)
PY
python scripts/smoke.py --output-dir "$ROOT/runs/${RUN_NAME:-otter-256-100}/smoke"
touch "$ROOT/control/RUN"
echo 'Smoke checks passed; full benchmark enabled.'
