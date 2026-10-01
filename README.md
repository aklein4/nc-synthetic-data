# nc-synthetic-data

Run SystemsBench against MiMo-V2.6-Flash-MOPD on one National Compute node
with eight MI355X GPUs. The service is standard vLLM with an OpenAI-compatible
endpoint (`http://mimo:8000/v1/chat/completions`) and automatic prefix caching.

The otter and Bean Seedling Growth 256/100 rows are complete. See
[RESULTS.md](RESULTS.md) for artifacts, validation and measured performance.
The MiMo server remains running for the next job; held-node billing continues.

All persistent runtime data lives under `/mnt/shared/nc-synthetic-data`:

| Directory | Contents |
| --- | --- |
| `models/MiMo-V2.6-Flash-MOPD-http` | Pinned official weights, downloaded directly to NFS |
| `cache` | Hugging Face, compiler, vLLM and package caches |
| `code` | Standalone copy of this repository used by the jobs |
| `logs` | Download, server and benchmark logs, package versions |
| `runs/otter-256-100` | Checkpoint, audited attempts, validated calls, dataset, review |
| `control` | `START` enables serving; `RUN` enables the benchmark |

The initial task is one river-otter system, eight rules per world, five worlds,
256 training questions and 100 test questions, seed 42. Model quality checks,
independent answer contexts, gold-only verification, answer-only possibility
checks, retirement, split logic and export validation are inherited from the
original benchmark. Reasoning is enabled for planning/writing/question stages
and disabled for answers, verification, and language checks. Each stage uses
an explicit boolean in the `THINKING` configuration. Sampling uses Xiaomi's
recommended temperature 1.0 and top-p 0.95.

The latest completed run uses `bean-seedling-256-100` and Bean Seedling Growth.
It used 16 rules per world. The new full run retains 16 rules and allows at
most four rule retirements per row after candidate-budget exhaustion. Accepted
questions and rule text are preserved; only unfilled quota is redistributed.
Version 52 sends the actual JSON schema to vLLM for constrained decoding,
retains independent client validation, and fails fast on permanent HTTP 4xx
errors. Question batches include only rules with remaining quota and request
at most `min(question_batches, remaining_slots)` candidates per rule per round.
They no longer multiply the call count when fewer rules remain. The full world
description remains in the prompt to preserve context and prefix reuse.
Per the user's clarification, effort labels have been removed. `THINKING`
booleans pass directly to MiMo's `enable_thinking` switch.
Thinking-enabled benchmark calls allow up to 131,072 output tokens, Xiaomi's
documented maximum (reasoning plus visible output). Non-thinking calls retain
their 512-token limit. The vLLM context window is 262,144 tokens to leave room
for prompts alongside the full output budget.

Each candidate also gets an answer-uniqueness call with its question and four
options, without a world description or correct-answer hint. It returns
`{"A": true, "B": true, "C": true, "D": true}` only when every answer makes a
distinct prediction. Paraphrases count as duplicates, and every member of a
duplicate group is marked false. Any false label rejects the question as
`duplicate_answers`; the existing exact-text duplicate check remains. The call
runs alongside verification and language checks, uses `THINKING["deduplication"]`
(false by default), and saves its labels in the checkpoint and call audit.
Export refuses answers with missing or failed uniqueness checks.

The earlier weather benchmark was stopped before question generation. The
subsequently authorized Bean row is complete and copied under gitignored
`local_data/bean-seedling-256-100`. The server stays running, with `control/RUN`
removed. Launch another row only when requested. Small smoke checks are separate
from the full benchmark and do not create the RUN marker.

## Provision and run

Use `--context us-mi355-k8s-niveditha` on every kubectl command. The current
user-authorized market ceiling is $4/GPU-hour ($32/node-hour maximum). Never
raise it without new authorization. Read `/api/k8s/bid?cluster=...` and echo
`version` as `expected_version` when setting it. The API token stays in
`~/.config/nationalcompute/token`; it is never copied into this repository.

1. Apply `k8s/serve.yaml` first. Its eight-GPU Job provisions a node, pulls a
   pinned ROCm vLLM image, and waits for the `START` marker. The same Job becomes
   the service, avoiding a second GPU request.
2. Apply `k8s/benchmark.yaml` for the CPU worker. It waits for `RUN` and gives a
   place to stage code and run the benchmark client.
3. Copy this repository (excluding `.git`, `.venv`, `local`, and `local_data`) to `code/`
   through `kubectl exec -i job/systems-bench -- tar ...`.
4. In the GPU job, run `scripts/download.py` with `HF_HOME` pointing under
   shared `cache/`. The image already includes Hugging Face Hub.
   It pins model revision `2479e2d0029eca9a34cc7e7f55a121925f81908e` and writes
   `.ready.json` only after download completion. The 178 GB checkpoint fits the
   current 1 TiB shared volume. No Kimi weights are needed.
   Use the GPU node's larger host memory for NFS writeback: downloads from the
   64 GiB CPU worker stalled once dirty-page pressure rose. Xet is disabled;
   four HTTP streams write directly to NFS, retaining completed files on retry.
5. Create `control/START`. `scripts/serve.sh` waits for the completed weights,
   records installed packages, and starts vLLM with tensor parallelism 8,
   prefix caching, chunked prefill, 256 sequences and 32,768 batched tokens.
   With user authorization, AITER compilation uses temporary node-local
   `/tmp/nc-synthetic-data/aiter` scratch to avoid NFS compiler stalls.
   Completed kernel modules are restored from shared storage at startup and
   copied back every 15 seconds and on shutdown. Weights and benchmark data
   always remain on shared storage. The first run completed compilation on NFS;
   this scratch configuration applies to subsequent starts.
6. Check `/health` and run `scripts/smoke.py --output-dir <shared-run>/smoke`
   inside the CPU worker after installing `requirements.lock`. It exercises
   every production schema, thinking modes, and eight replays of the previously
   failing answer. Only after success create `control/RUN`. The benchmark uses
   256 concurrent requests and up to 16 question batches per round. Long, stable world prefixes
   precede variable styles/questions, allowing KV reuse.
7. Verify `systems_bench.jsonl` contains exactly one row with 256/100 items;
   run the same command with `--export-only` to revalidate saved provenance.

`bash scripts/submit.sh` implements steps 1–5 without changing the standing bid.
Before a fresh submission, delete the previous completed `systems-bench` Job
and ensure `START`/`RUN` markers are absent; applying a completed Job does not
run it again. Do not overwrite scripts while a live shell is reading them.

The existing optional `api-keys` Kubernetes Secret supplies `HF_TOKEN` using
`secretKeyRef`, following `nc-baseline/full-baseline.yaml`. No OpenRouter key
is used. The service is cluster-internal. Credentials are excluded from audits.
The client audit records usage and latency, not synthetic per-token dollar costs:
actual charges come from National Compute's market and billing APIs.

For the current workflow, leave the GPU serving pod running idle with the model
loaded after the row completes, ready for the next run. The user explicitly
requested this; held-node billing continues. When the user asks to stop it:

```sh
kubectl --context us-mi355-k8s-niveditha -n default delete job mimo-serve
kubectl --context us-mi355-k8s-niveditha -n default delete service mimo
```

Leave the $4 bid in place, as requested. Remove the `START` and `RUN` markers
before a new controlled launch. Shared data remains. Node billing continues
through the first-hour minimum hold and applicable idle grace; a standing bid
does not by itself request a node, but funds future GPU workloads.

For access after the jobs stop, apply `k8s/storage-access.yaml`, then use
`kubectl --context us-mi355-k8s-niveditha -n default exec nc-synthetic-data-storage -- ...`.
It mounts shared storage without requesting a GPU. Delete that pod after use;
it also has a one-hour active deadline.

## Provenance and checks

Copied from `outer-loop/data_preparation/benchmarks/systems_bench.py` at local
source SHA256 `8e510e15b87702ebbd590bc679e75b38c458b11fb214e17c918256bc5c8a7eb6`.
The source repository HEAD was `27d0af28a528890251e4b12d33c1ce180eab6021`;
the content hash is authoritative if that checkout had local edits.
Catalogue SHA256: `75e477c98fe34203993f06aae027476aa89be3f8e710f9fef152db96b31f7a7a`.
No runtime dependency on that repository exists.

Transport changes remove OpenRouter routing and cost reservations, use MiMo's
thinking control, and retain complete local request/response audits. Source,
catalogue and transport hashes enter checkpoint configuration so incompatible
resumes fail explicitly. Do not alter prompts or acceptance checks mid-run.

```sh
uv venv
uv pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q
```

Tests cover a full offline 256/100 export, resume and tamper rejection, stable
prefixes, bounded concurrency, schema-constrained payloads, schema-echo rejection,
permanent HTTP error handling, remaining-quota scheduling, duplicate-answer
rejection for each of the four labels, uniqueness provenance, caching and audit privacy.
Offline fixtures are synthetic tests, not benchmark results.

## References

- [National Compute first-job Serve recipe](https://nationalcompute.com/FIRST-JOB.md)
- [National Compute market and operating rules](https://nationalcompute.com/AGENTS.md)
- [Kubernetes API contract](https://nationalcompute.com/api/k8s/openapi.json)
- [Kimi starter used as a deployment example](https://access.nationalcompute.com/first-job/kimi-k3-serve-amd.yaml)
- [Official MOPD model card](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Flash-MOPD)
- [vLLM MiMo recipe and AMD configuration](https://recipes.vllm.ai/XiaomiMiMo/MiMo-V2.6-Flash-RL)
- [vLLM ROCm installation](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/)

## Reviewing completed rows

`review.md` includes all five worlds with numbered rules, then accepted questions
grouped by their target rule. Each question keeps its original Train/Test index.
Review options always show the gold world first, followed by the remaining
answer worlds in numerical order, with world labels. The question-writing world's
answer is separate and inspection-only. Dataset options remain randomized.

Regenerate only the review of a saved run, without rewriting its dataset or
checkpoint/source provenance:

```sh
.venv/bin/python scripts/review.py local_data/bean-seedling-256-100
```

## Full 64-row run and upload

From this repository, run:

```sh
bash run_full.sh
# Optional destination override:
bash run_full.sh your-account/your-dataset
```

The default destination is `aklein4/AlwaysLearningBench-v1`. The existing upload
behavior is retained: a new repository is public; an existing repository keeps
its visibility. The launcher creates/verifies the destination and write access
before generation. The cluster Secret `api-keys` now uses the `aklein4` write token from
`~/.config/nc-baseline/credentials.env`, as requested. The destination was not
visible during read-only inspection; the launcher will create it and verify
write access before generation. No full generation or upload was launched
during preparation.

The launcher uses the running MiMo service and a temporary CPU pod. Thirty-two rows
run concurrently, including world building. The revised local configuration uses
512 shared in-flight requests and 512 server sequences. It targets 64 completed
rows drawn without reuse from 96 catalogue settings, with 16 rules/world and
256/100 questions. Exact normalized question deduplication is global across rows.
Exhausted settings are archived and replaced using unassigned catalogue entries.
The original 64 entries are reserved for the initial row slots; the added 32 are
replacement settings. Catalogue exhaustion stops the run; permanent API or
unexpected infrastructure/program errors also stop rather than consume settings.

The launcher starts a NEW run under `full-64-256-100-v56`, using these revised
rules and prompts. The stopped v53 run remains untouched under
`full-64-256-100`; its candidates are not reused. The GPU service is prepared
for 512 sequences, while the standing bid and provisioned node are retained.
Generation and upload begin only when you execute the launcher.

Errors print to the terminal and the script returns a nonzero exit status. Run
it with `bash`, not `source`; it does not close your terminal. Keep that terminal
session connected for the run. On exit it removes only the temporary CPU worker;
the GPU model service and standing bid remain untouched. If the local process is
forcibly killed, an existing `systems-bench-full` pod causes the next invocation
to stop rather than interfere with an active run.

Run data and a frozen code snapshot live under
`/mnt/shared/nc-synthetic-data/runs/full-64-256-100-v56`. Repeating the same command
resumes that snapshot; subsequent working-tree edits do not alter it. Upload
occurs only after complete export validation. `upload.json` records the commit.
On success, all run artifacts are copied to gitignored
`local_data/full-64-256-100-v56`. Incomplete runs stay on shared storage. The published
dataset contains 64 rows with nested splits (16,384 training and 6,400 test
questions in total); audits and checkpoint files stay outside the Hub dataset.

Version 53 adds bounded row concurrency with indexed partial checkpoints and
cancellation on row failure. The audit client now streams saved records on resume
and uses constant-size usage counters, retaining full audits on disk rather than
holding every prompt/response in memory. Twenty offline tests pass, including
parallel world building, cross-row deduplication, failure cancellation, resume
from partial checkpoints and audit usage across restarts. Older completed runs
retain their original source archives and provenance.

## Candidate-budget retirement (local version 55)

A rule is eligible for retirement when its current quota is still unfilled and
at least 10 times that quota candidates have been generated targeting it.
The quota is the current quota, including any inherited slots. There is no
acceptance-rate, minimum-evaluated-count, or rejected-round threshold. Eligibility
is checked between completed generation/evaluation rounds, so the threshold may
be crossed within a batch. At most four rules retire per row; the existing
selection and unfilled-quota redistribution order remain unchanged.

A row is discarded after 20 times its total quota candidates have been generated
and evaluated/deduplicated without filling its accepted pool: 7,120 candidates
for a 256/100 row. The last batch is trimmed to the remaining row budget, and
its candidates are processed before deciding whether to discard. This replaces
the old 128-round limit. The separate 12-world-iteration and eight-request-attempt
limits remain, with exhaustion triggering setting replacement in the local code.

Generated counts include duplicate question strings returned by successful,
schema-valid question-generation calls, before deduplication. Each occurrence
counts toward its target rule and the row total. Counts persist in each rule's
`generated` checkpoint field; cached requests replayed during resume are counted
once when the batch is committed. Rejected malformed call responses are request
failures, not generated candidates. Discarded rows retain their partial data and
reason in the checkpoint but are omitted from the final exported dataset.

## Per-rule collision evidence (local version 56)

The collision verifier must construct one question for each rule whose SAME
scenario gives pairwise semantically distinct, mutually incompatible answers in
all five worlds. It returns a rule-ordered `rule_examples` array, each containing
`distinguishable`, `question`, five `answers` in input-world order, and `reason`.
For an unsuccessful rule it returns false and empty question/answer strings,
with an explanation of which worlds it cannot distinguish. Global `distinct`
may pass only if every rule has a successful example. Code also rejects missing
examples, false per-rule flags, empty evidence, or normalized identical answers.
Semantic distinctness remains the verifier's judgment, not an independent test.

Examples are saved in validated collision call records for every attempt and in
the final accepted system checkpoint. Review output includes a separate inspection
section with the five answers labeled by world, gold first. They never enter the
training/test candidate pool or generation counters, and are not sent into
question-generation or revision prompts. Revision feedback includes per-rule
flags and reasons only. Failed per-rule collision evidence follows the existing
collision-failure revision path. The fresh-run launcher uses these checks; the stopped historical run is unchanged.
