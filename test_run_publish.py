"""Launcher lifecycle tests: no live cluster, upload or billing writes."""

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess

import pytest

import run_publish as p


@pytest.mark.parametrize("exit_code", [0, 7])
def test_full_run_arguments_and_cleanup(monkeypatch, exit_code):
    events = []
    monkeypatch.setattr(p, "preflight", lambda token: events.append("preflight"))
    monkeypatch.setattr(p, "release_gpu", lambda token: events.append("release"))
    monkeypatch.setattr(p.signal, "signal", lambda *args: None)

    class Child:
        def __init__(self, command, **kwargs):
            assert command == ["bash", "run_full.sh", "test-run", "--systems", "64",
                               "--train", "256", "--test", "100", "--subject", "mixed",
                               "--concurrency", "512", "--upload", "aklein4/AlwaysLearningBench-v2"]
            assert kwargs["start_new_session"]
            events.append("generate-upload-copy")

        def wait(self):
            return exit_code

        def poll(self):
            return exit_code

    monkeypatch.setattr(p.subprocess, "Popen", Child)
    assert p.run("test-run", "not-a-real-token") == exit_code
    assert events == ["preflight", "generate-upload-copy", "release"]


def test_failed_preflight_does_not_stop_another_run(monkeypatch):
    def fail(token):
        raise RuntimeError("Another run exists")
    monkeypatch.setattr(p, "preflight", fail)
    monkeypatch.setattr(p, "release_gpu", lambda token: pytest.fail("Must not stop existing run"))
    with pytest.raises(RuntimeError, match="Another run"):
        p.run("test-run", "not-a-real-token")


def test_interruption_stops_child_and_releases_gpu(monkeypatch):
    events = []
    monkeypatch.setattr(p, "preflight", lambda token: None)
    monkeypatch.setattr(p, "release_gpu", lambda token: events.append("release"))
    monkeypatch.setattr(p.signal, "signal", lambda *args: None)
    monkeypatch.setattr(p.os, "killpg", lambda pid, sig: events.append((pid, sig)))

    class Child:
        pid = 12345
        interrupted = False

        def wait(self, **kwargs):
            if not self.interrupted:
                self.interrupted = True
                raise KeyboardInterrupt
            events.append("reaped")
            return 143

        def poll(self):
            return None

    monkeypatch.setattr(p.subprocess, "Popen", lambda *a, **kw: Child())
    assert p.run("test-run", "not-a-real-token") == 130
    assert events == [(12345, signal.SIGTERM), "reaped", "release"]


def test_bid_withdrawal_uses_fresh_version(monkeypatch):
    requests = []
    def request(token, body=None):
        requests.append(body)
        return dict(max_price_per_gpu_hour=3, version=42) if body is None else dict(max_price_per_gpu_hour=0)
    monkeypatch.setattr(p, "bid_request", request)
    p.withdraw_bid("not-a-real-token")
    assert requests == [None, dict(cluster=p.CLUSTER, max_price_per_gpu_hour=0, expected_version=42)]


def test_job_cleanup_failure_still_withdraws_bid(monkeypatch):
    attempts = []
    def fail(command, **kwargs):
        attempts.append(command)
        raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(p.subprocess, "run", fail)
    monkeypatch.setattr(p.time, "sleep", lambda delay: None)
    withdrawn = []
    monkeypatch.setattr(p, "withdraw_bid", lambda token: withdrawn.append(True))
    with pytest.raises(RuntimeError, match="delete MiMo job"):
        p.release_gpu("not-a-real-token")
    assert len(attempts) == 3 and withdrawn == [True]
    assert all(command[:5] == p.KUBECTL for command in attempts)


@pytest.mark.parametrize("exit_code", [0, 9])
def test_run_full_preserves_artifacts_after_upload_failure(tmp_path, exit_code):
    shutil.copyfile(Path(__file__).with_name("run_full.sh"), tmp_path / "run_full.sh")
    executable = tmp_path / "kubectl"
    executable.write_text('''#!/usr/bin/env python3
import io, json, os, sys, tarfile
from pathlib import Path
args = sys.argv[1:]
with Path(os.environ['FAKE_CALLS']).open('a') as f:
    f.write(json.dumps(args) + '\\n')
if 'exec' in args and 'python' in args and any(a.endswith('/systems_bench.py') for a in args):
    sys.exit(int(os.environ['FAKE_EXIT']))
if 'exec' in args and 'tar' in args:
    with tarfile.open(fileobj=sys.stdout.buffer, mode='w|') as out:
        data = b'{"preserved": true}'
        item = tarfile.TarInfo('checkpoint.json'); item.size = len(data)
        out.addfile(item, io.BytesIO(data))
''')
    executable.chmod(0o755)
    calls = tmp_path / "calls.jsonl"
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ["PATH"],
               FAKE_CALLS=str(calls), FAKE_EXIT=str(exit_code))
    result = subprocess.run(["bash", str(tmp_path / "run_full.sh"), "test-run", "--upload", p.REPOSITORY],
                            env=env, capture_output=True, text=True)
    assert result.returncode == exit_code
    assert json.loads((tmp_path / "local_data/test-run/checkpoint.json").read_text()) == dict(preserved=True)
    commands = [json.loads(line) for line in calls.read_text().splitlines()]
    assert commands[-1][4:7] == ["delete", "pod", "systems-bench-full"]
    generation = next(c for c in commands if any(a.endswith('/systems_bench.py') for a in c))
    assert generation[-2:] == ["--upload", p.REPOSITORY]
