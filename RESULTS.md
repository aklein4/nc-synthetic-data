# Completed Bean Seedling Growth row — 2026-09-30

Completed and validated one row with **256 training and 100 test questions**,
five worlds and 16 rules per world, using MiMo-V2.6-Flash-MOPD on eight MI355X
GPUs. The GPU server remains loaded on bg-2 for the next run. The standing
bid remains $4/GPU-hour, version 12; the observed node price is $24/hour.
`control/RUN` is removed; `control/START`, the serving Job and Service remain.

## Artifacts and validation

All run artifacts are copied to the gitignored directory
[local_data/bean-seedling-256-100](local_data/bean-seedling-256-100), including
the archived attempt before the output-limit increase, request/response audits,
validated call cache, logs, metrics, source snapshot, probes and research.
The authoritative shared copy is
`/mnt/shared/nc-synthetic-data/runs/bean-seedling-256-100`.
Weights remain on shared storage; they were not duplicated into the local repo.

- [systems_bench.jsonl](local_data/bean-seedling-256-100/systems_bench.jsonl): one row with `Setting` and `World`, 256/100 splits.
- [review.md](local_data/bean-seedling-256-100/review.md): worlds and accepted questions for inspection.
- [report.json](local_data/bean-seedling-256-100/report.json): counts and usage.
- [quality-audit.json](local_data/bean-seedling-256-100/quality-audit.json): schema, uniqueness and paragraph-length checks.

Generation and export-only validation passed, as did independent local validation
and loading the Hugging Face dataset. SHA256 hashes match the shared copy for
the checkpoint, JSONL, report, usage and source archive. All 356 accepted items
have four true answer-uniqueness labels. Seventeen offline tests and 23 live
smoke checks passed before this run.

## Quality and efficiency

22 rounds generated 1,017 questions. Exact normalized deduplication removed six,
including three repeated within the same parallel round. All 1,011 remaining
unique drafts were evaluated: 356 accepted (35.2%), 655 rejected, none left
unevaluated. This removes the earlier run's redundant unevaluated tail.

| Rejection reason | Count |
| --- | ---: |
| Semantically duplicate answers | 442 |
| Exactly identical answers | 78 |
| Language check | 50 |
| Gold answer validation | 37 |
| Answer-only possibility check | 21 |
| Unanswerable | 14 |
| Answer length | 13 |

The main difficulty was obtaining four distinct predictions across the worlds.
These are rejection categories in check-priority order, not independent counts
of every check that might fail. The model-based checks are not a human quality
guarantee, and the fictional worlds are not biological claims.

Four rules retired, reaching the cumulative cap: rule 2 stem lengthening
(10/47 accepted), rule 5 first true leaf opening (4/47), rule 6 soil appearance
(2/48), and rule 8 unfurled leaf count (1/48). Accepted examples were retained;
only unfilled quotas moved. Rule 13 side-shoot development remained active and
required 177 candidates for 22 accepted, contributing to the final tail.

All five worlds passed after two revision rounds. Four initially had consistency
conflicts involving leaf health, growth, soil conditions and overlapping rules.
The first revision repaired three; the second resolved a remaining conflict
between healthy green older leaves and brown/dry leaf edges. Cross-world checks
passed, so previously valid worlds were retained explicitly.

76 of 80 rule paragraphs met the prompted 80–120-word target. Four missed it;
lengths ranged from 76 to 136 words. This is a prompt target, not a hard filter.

## Technical findings and timing

Current-run requests span **22:47:46–23:28:38 UTC: 40m52s**. World construction
occupied about 33m07s; question generation and filtering took about 7m45s.
One world revision alone took 20m22s and generated 121,681 tokens, including
113,922 reasoning tokens. No thinking-token budget was applied.

The earlier Bean attempt hit the old 32,768-output-token ceiling without
producing a final plan. That attempt is preserved separately. Following user
authorization, the output ceiling became 131,072 and server context 262,144.
Replacing only the serving pod retained the same provisioned node and bid.

The completed run had 8,905 API attempts: 8,883 HTTP successes, **zero
schema-invalid successes**, 21 ReadErrors and one RemoteProtocolError. All
transport failures recovered through retries; every successful response ended
with `stop`, with no output-length truncations. The earlier schema-echo failure
did not recur with actual structured-output schemas enabled.

| Measurement | Result |
| --- | ---: |
| API prompt tokens | 15,328,788 |
| API completion tokens, including reasoning | 632,143 |
| Sampled prefix-cache hit fraction | 95.02% |
| Peak sampled generation tokens/second | 1,628 |
| Peak sampled concurrent requests | 239 |
| Peak sampled KV occupancy | 0.331% |

Metrics use 15-second samples and exclude portions outside the sampled interval.
They also include two tiny thinking-cutoff diagnostic calls (52 prompt and 210
output tokens); benchmark API usage excludes these. Peaks are not sustained rates.
The different setting, rule count, checks and planning workload mean performance
is not directly comparable to the earlier otter row.

At the observed $24/node-hour, the 40m52s inference interval corresponds to about
$16.35 of held-node time. This is an estimate for that interval, not total billed
cost: setup, the archived attempt and ongoing idle service also incur charges.
The saved billing snapshot is delayed and the node remains running as requested.

Thinking-cutoff research: vLLM can force the reasoning-end marker and continue
an answer; a simple live probe worked. Xiaomi's published report does not establish
MiMo-specific quality after arbitrary cutoffs. The full benchmark therefore kept
its thinking toggle enabled without an additional thinking-token budget.

# Completed otter row — 2026-09-30

Completed one North American river-otter behavior system with **256 training
and 100 test questions**, using `XiaomiMiMo/MiMo-V2.6-Flash-MOPD` on eight
MI355X GPUs in `us-mi355-k8s-niveditha`. No OpenRouter inference was used.

The benchmark job completed at **21:01:56 UTC**. Inference requests ran from
20:45:06 to 21:01:53 UTC: **16 minutes 47 seconds**, including a checkpoint
resume. Cold provisioning, download and compilation preceded this interval.
The serving Job, Service and GPU pods were removed by 21:03:28 UTC.
The standing **$3/GPU-hour bid remains unchanged**, version 11.
The completed CPU job remains for status inspection. Its older failed pod
was still Terminating after deletion, following the earlier NFS I/O stall;
it requests no GPU and is separate from the completed replacement.

## Artifacts

The authoritative run directory is on shared storage:
`/mnt/shared/nc-synthetic-data/runs/otter-256-100/`.

| Artifact | Contents |
| --- | --- |
| `systems_bench.jsonl` | Exactly one row, with nested 256/100 splits |
| `dataset/` | Hugging Face dataset export |
| `review.md` | Human-readable worlds, questions, answers and checks |
| `checkpoint.json` | Full generation state and source/configuration hashes |
| `calls/`, `api_audit/` | Cached validated calls and every attempted request |
| `report.json`, `usage.json` | Counts, rejection reasons and token usage |
| `metrics/`, `metrics-summary.json` | Raw server metrics and sampled summary |
| `audit-summary.json` | Timing, HTTP outcomes and transport errors |

Weights remain at
`/mnt/shared/nc-synthetic-data/models/MiMo-V2.6-Flash-MOPD-http`, pinned to
revision `2479e2d0029eca9a34cc7e7f55a121925f81908e` (about 178 GB).
Code, logs and compiled caches also remain under the shared root.
Convenience copies of the row, checkpoint, review and reports are in
`local/otter-256-100/` in this repository; those copies are gitignored.

## Validation and quality observations

- Full generation and `--export-only` provenance validation passed.
- Exactly 356 unique question strings, four options each, valid answer indices,
  and an otter setting were checked by `scripts/validate.py`.
- Six offline tests passed, covering full 256/100 export, resume/tamper
  protection, prefixes, concurrency, payload translation and audit privacy.
- 31 question rounds produced 3,979 drafts; 683 were evaluated, yielding 356
  accepted and 327 rejected candidates. Drafts beyond remaining quotas were
  not evaluated. Rejections: answer validation 151, language 64, identical
  answers 64, answer-only possibility 33, answer length 6, unanswerable 9.
- Surfacing pattern (rule index 3) retired after 11/48 candidates passed across
  three rounds. Its 11 accepted examples remain; only unfilled quota moved.
- One world initially failed consistency. The collision check passed, so the
  other four worlds and their checks were explicitly retained. Only the failed
  world was rewritten; the revised set passed.
- One answer exhausted eight malformed-JSON-schema retries. A checkpoint
  resume reused completed calls and finished without changing prompts or
  acceptance criteria. Audits contain 8,576 attempts, 8,560 HTTP 200 responses
  (all finish reason `stop`) and 16 `ReadError` attempts without a recorded
  response. HTTP 200 includes responses rejected by schema validation.
- Spot inspection found some accepted answer options still contain causal
  wording such as “since …”, despite the language prompt discouraging
  explanations. These are inherited model-based checks, not perfect human
  quality guarantees. The fictional rule worlds are not biological claims.

## Serving efficiency

Standard ROCm vLLM `0.30.1rc1.dev396+gac68c3087`, tensor parallelism 8,
prefix caching, chunked prefill, 256 maximum sequences, 32,768 batched tokens,
65,536 context length and 90% GPU memory utilization. Reported KV capacity:
6,988,836 tokens. Benchmark concurrency was 256, with 16 question batches.

| Measurement | Result |
| --- | ---: |
| Prompt tokens | 14,462,850 |
| Completion tokens, including thinking | 899,465 |
| Prefix-cache hit tokens | 14,026,336 |
| Prefix-cache hit fraction | **96.98%** |
| Peak sampled generation throughput | **4,259 tokens/second** |
| Peak sampled running requests | **128** |
| Peak sampled KV occupancy | 0.154% |

Peaks come from 15-second sampling and are not exact maxima or sustained
rates. API responses omitted cached-token details, so `usage.json` contains
zero for that field; server telemetry above is the cache-reuse evidence.
The benchmark's tail is inefficient: it continues generating many drafts
while evaluating only the remaining quota. This run preserved that algorithm.

Initial NFS downloads and cold kernel compilation dominated setup time.
Completed compiler modules are saved on shared storage. With the user's
approval, subsequent starts use local AITER scratch and copy completed
modules back to shared storage; this run finished its NFS build without a
restart to switch scratch locations.

## Billing and shutdown

Live price stayed at **$24/node-hour**, within the authorized ceiling.
Starting balance was $1,547.408156. The post-stop billing snapshot, whose
ledger was current only through **20:56:45 UTC**, shows $1,527.708642:
**$19.699514 metered so far**, not the final total.

The node was still held at the 21:03:28 read, so billing had not stopped.
National Compute documents a first-hour minimum hold and subsequent idle
shedding; a one-hour hold at this rate costs $24, with any additional held
time charged as well. The standing bid does not guarantee indefinite node
retention. It was deliberately left in place as requested.

References: [National Compute first-job Serve recipe](https://nationalcompute.com/FIRST-JOB.md),
[market and operating rules](https://nationalcompute.com/AGENTS.md), and
[MiMo vLLM recipe](https://recipes.vllm.ai/XiaomiMiMo/MiMo-V2.6-Flash-RL).
