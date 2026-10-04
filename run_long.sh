#!/usr/bin/env bash
# Start inside tmux: bash run_long.sh
# Extends the first ten v2 worlds to 2048/100, uploads, then releases the GPUs.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
exec .venv/bin/python -u run_long.py "$@"
