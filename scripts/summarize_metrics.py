"""Summarize recorded vLLM counters and sampled throughput for one run."""
import argparse
import json
import re
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("directory", type=Path)
args = parser.parse_args()
samples = []
for path in sorted((args.directory / "metrics").glob("*.prom")):
    values = {}
    for line in path.read_text().splitlines():
        match = re.fullmatch(r"(vllm:[a-zA-Z0-9_:]+)(?:\{.*\})? ([0-9.eE+-]+)", line)
        if match:
            key, value = match.groups()
            values[key] = values.get(key, 0) + float(value)
    samples.append((int(path.stem) / 1e9, values))
assert len(samples) >= 2, "Need at least two telemetry samples"
first, last = samples[0][1], samples[-1][1]
delta = lambda key: last.get("vllm:" + key, 0) - first.get("vllm:" + key, 0)
queries = delta("prefix_cache_queries_total")
rates = [
    (b[1].get("vllm:generation_tokens_total", 0) - a[1].get("vllm:generation_tokens_total", 0)) / (b[0] - a[0])
    for a, b in zip(samples, samples[1:])
]
report = {
    "note": "Counter deltas cover the sampled interval; peak values are sampled, not exact maxima. Prefix hits are server telemetry; API usage may omit cached-token details.",
    "sample_count": len(samples),
    "sampled_seconds": samples[-1][0] - samples[0][0],
    "prompt_tokens": delta("prompt_tokens_total"),
    "generation_tokens": delta("generation_tokens_total"),
    "prefix_cache_queried_tokens": queries,
    "prefix_cache_hit_tokens": delta("prefix_cache_hits_total"),
    "prefix_cache_hit_fraction": delta("prefix_cache_hits_total") / queries if queries else None,
    "peak_sampled_generation_tokens_per_second": max(rates),
    "peak_sampled_running_requests": max(v.get("vllm:num_requests_running", 0) for _, v in samples),
    "peak_sampled_waiting_requests": max(v.get("vllm:num_requests_waiting", 0) for _, v in samples),
    "peak_sampled_kv_cache_fraction": max(v.get("vllm:kv_cache_usage_perc", 0) for _, v in samples),
}
(args.directory / "metrics-summary.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
