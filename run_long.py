#!/usr/bin/env python3
"""Run the prepared 10-world 2048/100 extension, publish, and release GPUs."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import prepare_long as seed
import run_publish as publish


def wait_for_server(timeout=2400):
    """Permit launching from tmux while the allocated node is still booting."""
    subprocess.run(publish.KUBECTL + ['get', 'job', 'mimo-serve'], check=True, timeout=60)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = subprocess.check_output(publish.KUBECTL + [
            'get', 'pods', '-l', 'app=mimo-serve', '-o', 'json'], text=True, timeout=60)
        pods = json.loads(result)['items']
        if any(not pod['metadata'].get('deletionTimestamp') and any(
                c['type'] == 'Ready' and c['status'] == 'True'
                for c in pod.get('status', {}).get('conditions', [])) for pod in pods):
            return
        print('Waiting for the eight-GPU MiMo server to become ready...', flush=True)
        time.sleep(30)
    raise TimeoutError('MiMo is not ready after 40 minutes; inspect the cluster before retrying')


def main():
    if not seed.DESTINATION.exists():
        seed.prepare()
    manifest = json.loads((seed.DESTINATION / 'reuse.json').read_text())
    config = manifest['target_config']
    if (config['systems'], config['train'], config['test']) != (10, 2048, 100):
        raise ValueError('Unexpected prepared run configuration')
    if seed.source_hash(seed.DESTINATION / 'code') != config['source']:
        raise ValueError('Prepared source snapshot was modified')
    os.environ['RUN_SEED_DIR'] = str(seed.DESTINATION)
    token = (Path.home() / '.config/nationalcompute/token').read_text().strip()

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    wait_for_server()
    return publish.run(seed.RUN_NAME, token, systems=10, train=2048, test=100,
                       repository='aklein4/AlwaysLearningBench-v2-long', shuffle_train=True)


if __name__ == '__main__':
    sys.exit(main())
