"""Validate a completed row and emit a compact report beside its artifacts."""
import argparse
import json
from collections import Counter
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("directory", type=Path)
parser.add_argument("--subject")
args = parser.parse_args()
state = json.loads((args.directory / "checkpoint.json").read_text())
rows = [json.loads(line) for line in (args.directory / "systems_bench.jsonl").read_text().splitlines()]
assert len(rows) == 1
row = rows[0]
assert row["num_train"] == len(row["train_data"]) == 256
assert row["num_test"] == len(row["test_data"]) == 100
assert row["Setting"] == state["systems"][0]["shared"]
if args.subject:
    assert state["config"]["subject"] == args.subject
all_questions = row["train_data"] + row["test_data"]
assert len({q["question"].strip() for q in all_questions}) == 356
assert all(len(q["options"]) == 4 and 0 <= q["correct_option"] < 4 for q in all_questions)
system = state["systems"][0]
evaluated = sum(rule["checked"] for rule in system["rule_results"])
assert evaluated == len(system["items"]) + sum(system["rejections"].values())
if state["config"]["version"] >= 51:
    assert len(system["drafts"]) == evaluated, "Generated unique drafts were left unevaluated"
report = {
    "rows": 1, "train": 256, "test": 100,
    "model": state["config"]["model"],
    "setting": row["Setting"],
    "rounds": system["round"],
    "drafts": len(system["drafts"]),
    "evaluated": evaluated,
    "unevaluated_unique_drafts": len(system["drafts"]) - evaluated,
    "accepted": len(system["items"]),
    "retired_rules": system["retired"],
    "rejections": system["rejections"],
    "correct_option_counts": dict(Counter(q["correct_option"] for q in all_questions)),
    "usage": json.loads((args.directory / "usage.json").read_text()),
}
(args.directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
