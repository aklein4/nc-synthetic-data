#!/usr/bin/env python3
"""Generate 64 SystemsBench rows, publish them, then release MiMo's GPU capacity."""

import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
CLUSTER = "us-mi355-k8s-niveditha"
REPOSITORY = "aklein4/AlwaysLearningBench-v2"
KUBECTL = ["kubectl", "--context", CLUSTER, "-n", "default"]
BID_URL = "https://nationalcompute.com/api/k8s/bid"


def bid_request(token, body=None):
    # Contract: https://nationalcompute.com/api/k8s/openapi.json
    request = Request(
        BID_URL + ("?cluster=" + CLUSTER if body is None else ""),
        data=None if body is None else json.dumps(body).encode(),
        method="GET" if body is None else "PUT",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def withdraw_bid(token):
    current = bid_request(token)
    if current["max_price_per_gpu_hour"] == 0:
        return
    result = bid_request(token, dict(cluster=CLUSTER, max_price_per_gpu_hour=0,
                                     expected_version=current["version"]))
    if result["max_price_per_gpu_hour"] != 0:
        raise RuntimeError("National Compute did not confirm bid withdrawal")


def release_gpu(token):
    """Try both independent cleanup operations, even if one fails."""
    operations = [
        ("delete MiMo job", lambda: subprocess.run(
            KUBECTL + ["delete", "job", "mimo-serve", "--ignore-not-found=true",
                       "--cascade=foreground", "--wait=true", "--timeout=120s"],
            check=True, timeout=150)),
        ("withdraw GPU bid", lambda: withdraw_bid(token)),
    ]
    failed = []
    for name, operation in operations:
        for attempt in range(3):
            try:
                operation()
                break
            except Exception as error:
                print(f"Cleanup: could not {name} ({type(error).__name__}); attempt {attempt + 1}/3",
                      file=sys.stderr, flush=True)
                if attempt == 2:
                    failed.append(name)
                else:
                    time.sleep(5)
    if failed:
        raise RuntimeError("GPU cleanup failed: " + ", ".join(failed))
    print("MiMo job removed; GPU bid withdrawn. National Compute will release the node.", flush=True)


def preflight(token):
    bid = bid_request(token)
    if not 0 < bid["max_price_per_gpu_hour"] <= 3:
        raise RuntimeError("Expected an active GPU bid at or below the authorized $3/GPU-hour ceiling")
    worker = subprocess.check_output(
        KUBECTL + ["get", "pod", "systems-bench-full", "--ignore-not-found=true", "-o", "name"],
        text=True, timeout=60)
    if worker.strip():
        raise RuntimeError("systems-bench-full already exists; another run may be active")
    subprocess.run(KUBECTL + ["get", "job", "mimo-serve"], check=True, timeout=60)
    subprocess.run(KUBECTL + ["wait", "--for=condition=Ready", "pod", "-l", "app=mimo-serve",
                              "--timeout=60s"], check=True, timeout=90)


def run(run_name, token):
    preflight(token)
    child = None
    status = 1
    try:
        print(f"Generating 64 rows × (256 train + 100 test); uploading to {REPOSITORY}.", flush=True)
        child = subprocess.Popen(
            ["bash", "run_full.sh", run_name, "--systems", "64", "--train", "256",
             "--test", "100", "--subject", "mixed", "--concurrency", "512",
             "--upload", REPOSITORY], cwd=ROOT, start_new_session=True)
        status = child.wait()
    except KeyboardInterrupt:
        status = 130
    finally:
        # Finish cleanup even if a second interrupt arrives.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        try:
            if child is not None and child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
        finally:
            try:
                release_gpu(token)
            except Exception as error:
                print(str(error), file=sys.stderr, flush=True)
                status = status or 1
    if status == 0:
        print(f"Uploaded: https://huggingface.co/datasets/{REPOSITORY}\n"
              f"Local artifacts: {ROOT / 'local_data' / run_name}", flush=True)
    else:
        print(f"Run failed (exit {status}). Check the log; shared checkpoints remain at "
              f"/mnt/shared/nc-synthetic-data/runs/{run_name}.", file=sys.stderr, flush=True)
    return status if status >= 0 else 128 - status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", default="alwayslearning-v2-64-256-100")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.run_name):
        parser.error("Run name must contain only letters, digits, underscores and hyphens")
    token = (Path.home() / ".config/nationalcompute/token").read_text().strip()
    if not token:
        parser.error("National Compute token is empty")

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    return run(args.run_name, token)


if __name__ == "__main__":
    sys.exit(main())
