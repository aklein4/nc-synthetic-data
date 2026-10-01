"""Keep raw vLLM telemetry on shared storage during generation."""
import argparse
import time
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("directory", type=Path)
args = parser.parse_args()
out = args.directory / "metrics"
out.mkdir(parents=True, exist_ok=True)
while True:
    try:
        with urllib.request.urlopen("http://mimo:8000/metrics", timeout=10) as response:
            (out / f"{time.time_ns()}.prom").write_bytes(response.read())
    except Exception as error:
        print(f"Metrics: {type(error).__name__}: {error}", flush=True)
    time.sleep(15)
