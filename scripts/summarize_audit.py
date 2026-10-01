"""Summarize audit timing and incomplete attempts without loading all records."""
import argparse
import datetime
import json
from collections import Counter
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("directory", type=Path)
args = parser.parse_args()
starts, finishes = [], []
statuses, reasons, errors = Counter(), Counter(), Counter()
missing = 0
for path in (args.directory / "api_audit").glob("*.json"):
    record = json.loads(path.read_text())
    starts.append(record["started_at"])
    if "elapsed_seconds" in record:
        finishes.append(record["started_at"] + record["elapsed_seconds"])
    statuses[str(record.get("status_code", "unrecorded"))] += 1
    if "transport_error" in record:
        errors[record["transport_error"].split(":", 1)[0]] += 1
    if "response" not in record and "response_text" not in record:
        missing += 1
    for choice in (record.get("response") or {}).get("choices", []):
        reasons[str(choice.get("finish_reason"))] += 1
iso = lambda value: datetime.datetime.fromtimestamp(value, datetime.timezone.utc).isoformat()
report = {
    "attempts": len(starts),
    "started_at": iso(min(starts)),
    "last_finished_at": iso(max(finishes)),
    "elapsed_seconds": max(finishes) - min(starts),
    "http_statuses": dict(statuses),
    "finish_reasons": dict(reasons),
    "transport_errors": dict(errors),
    "attempts_without_recorded_response": missing,
    "note": "HTTP success includes responses rejected by benchmark schema validation. Missing responses can arise from cancellation; their outcome is not asserted.",
}
(args.directory / "audit-summary.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
