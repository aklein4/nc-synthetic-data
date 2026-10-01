"""Download a pinned official checkpoint directly onto shared storage."""
import json
import os
import shutil
from pathlib import Path

# Xet reconstructs chunks with random writes. Sequential HTTP is gentler on
# this cluster's hard NFS mount (observed CPU-worker writeback stall).
os.environ["HF_HUB_DISABLE_XET"] = "1"
from huggingface_hub import snapshot_download

ROOT = Path("/mnt/shared/nc-synthetic-data")
REPO = "XiaomiMiMo/MiMo-V2.6-Flash-MOPD"
REVISION = "2479e2d0029eca9a34cc7e7f55a121925f81908e"
target = ROOT / "models" / "MiMo-V2.6-Flash-MOPD-http"
target.mkdir(parents=True, exist_ok=True)
marker = target / ".ready.json"
if marker.exists():
    assert json.loads(marker.read_text())["revision"] == REVISION
    print("Pinned checkpoint already staged", flush=True)
else:
    free = shutil.disk_usage(ROOT).free
    print(f"Shared storage free: {free / 2**30:.1f} GiB", flush=True)
    # Avoid walking large partially written files on a busy NFS client.
    if free < 200 * 2**30:
        raise RuntimeError("Need 200 GiB for checkpoint and download headroom")
    snapshot_download(REPO, revision=REVISION, local_dir=target, max_workers=4,
                      token=os.environ.get("HF_TOKEN") or None)
    marker.write_text(json.dumps({"repo": REPO, "revision": REVISION}) + "\n")
    print("Checkpoint download complete", flush=True)
