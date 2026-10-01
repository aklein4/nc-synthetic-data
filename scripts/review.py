"""Regenerate only review.md from a saved checkpoint; preserve dataset/provenance."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from systems_bench import CHECKPOINT_FILE, REVIEW_FILE, render_review

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("directory", type=Path)
args = parser.parse_args()
state = json.loads((args.directory / CHECKPOINT_FILE).read_text())
(args.directory / REVIEW_FILE).write_text(render_review(state))
print(args.directory / REVIEW_FILE)
