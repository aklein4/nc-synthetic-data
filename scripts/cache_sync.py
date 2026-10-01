"""Persist completed AITER modules while keeping compiler scratch local."""
import argparse
import os
import shutil
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=["restore", "save", "watch"])
args = parser.parse_args()
shared = Path("/mnt/shared/nc-synthetic-data/cache/aiter")
scratch = Path("/tmp/nc-synthetic-data/aiter")


def sync(source, target):
    target.mkdir(parents=True, exist_ok=True)
    for path in source.glob("*.so"):
        dst = target / path.name
        st = path.stat()
        if dst.exists() and dst.stat().st_size == st.st_size and dst.stat().st_mtime_ns == st.st_mtime_ns:
            continue
        tmp = dst.with_name(f".{dst.name}.{os.getpid()}.tmp")
        shutil.copy2(path, tmp)
        tmp.replace(dst)


if args.mode == "restore":
    sync(shared, scratch)
elif args.mode == "save":
    sync(scratch, shared)
else:
    while True:
        sync(scratch, shared)
        time.sleep(15)
