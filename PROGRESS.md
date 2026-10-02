# Run progress

- 2026-09-30: User authorized $3/GPU-hour, MiMo-V2.6-Flash-MOPD, one otter
  system with 256/100 train/test items. Stop serving on completion; leave bid set.
- Submitted `mimo-serve` placeholder; market granted `id-8` at 19:58 UTC.
  CPU job `systems-bench` stages data directly to shared storage.
- Shared volume has 1 TiB; MOPD checkpoint is about 178 GB. Download underway.
- Standard vLLM ROCm nightly image pinned by digest; built 2026-09-30.
- Standalone benchmark adapted from supplied source. Initial offline checks pass.
- Outstanding: finish download/provisioning, validate server, generate real row,
  record metrics and actual costs, validate exports, stop service without withdrawing bid.
- GPU ultimately granted as `bg-1`; Ready around 20:06 UTC. `mimo-serve-8dh6z`
  runs official ROCm vLLM `0.30.1rc1.dev396+gac68c3087`, torch 2.13, ROCm 7.2;
  verified eight visible GPUs and support for the checkpoint's mxfp4 storage.
  Live market rate is $24/hour. Billing ledger still stale at last check.
- Initial Xet download stalled NFS writeback. Stopped it, disabled Xet, and
  restarted into `models/MiMo-V2.6-Flash-MOPD-http`. Four sequential HTTP file
  streams are making steady progress. Original partial directory is unused;
  old CPU processes can remain in kernel I/O waits until writeback resolves.
- `START` marker exists. GPU script waits for the new model directory's
  `.ready.json`. `RUN` marker does NOT yet exist: run `scripts/smoke.py` in the
  CPU job once `/health` responds, then create RUN for the full benchmark.
- Tests: five inherited transport/export/concurrency/prefix checks plus one
  local audit test passed. Bash syntax and Python compilation passed.
- User clarified: stop the service when done, DO NOT withdraw the $3 bid.
- CPU NFS writeback stalled again near 38/154 files at ~10 GiB dirty pages.
  Moved downloader to GPU pod (about 2.8 TiB host RAM), same `-http` directory,
  reusing completed files. Four HTTP streams now advance beyond the stall.
  Follow `/mnt/shared/nc-synthetic-data/logs/download-gpu.log` in GPU pod.
- Download completed around 20:25 UTC. GPU downloader took ~9 minutes including
  reuse of completed files. A code sync replaced the script while the waiting
  shell held it open, causing a stale NFS handle; Job retried on the same node.
  Current server pod is `mimo-serve-p6xl5`, loading vLLM successfully so far.
  Avoid overwriting live script files during a wait; sync before launch.
- CPU background `scripts/start_benchmark.sh` now automatically waits for health,
  runs smoke checks, and writes RUN only on success. Its log is
  `/mnt/shared/nc-synthetic-data/logs/start-benchmark.log`. No real examples yet.
- Server became healthy at 20:44 UTC after initial AITER compilation and graph
  capture. Smoke checks passed in both thinking modes. Full benchmark started
  at 20:45 UTC, with 256 concurrent requests and 16 question batches.
- vLLM reports 225.41 GiB KV memory per GPU and 6,988,836 token capacity.
- User approved temporary node-local compiler scratch. Future `serve.sh`
  launches restore completed AITER modules from shared storage and persist new
  modules every 15 seconds/on shutdown. The current process completed its NFS
  build without restart; do not disrupt it merely to switch scratch paths.
- Initial world set needed one revision: consistency failed only world 2;
  collision checks passed, so four worlds were explicitly preserved. Revision
  passed. Three question rounds accepted 214 examples; surfacing-pattern rule
  retired after 11/48 passed, retaining its accepted examples and redistributing
  remaining quota under the unchanged source algorithm.
- At ~20:56 UTC one answer call exhausted eight schema-validation retries
  (returned schema instead of an instance). CPU job restarted from the same
  checkpoint and cached calls; no prompt or acceptance changes. Initial Job
  status preserved in shared `logs/benchmark-job-first-attempt.json`.
- COMPLETE at 21:01:56 UTC: one validated 256/100 otter row. 31 rounds,
  3,979 drafts, 356 accepted. See RESULTS.md for measurements and limitations.
- Serving Job/Service deleted and GPU pods absent by 21:03:28 UTC. Bid remains
  $3/GPU-hour, version 11. Node still held/billable; ledger is delayed.
- Final telemetry: 96.98% prefix-cache reuse, peak sampled 128 active requests
  and 4,259 generated tokens/second. All primary artifacts remain shared.
- At final inspection, old CPU pod `systems-bench-vmzh9` remained Terminating
  after deletion; its earlier downloads had NFS-blocked processes. The
  replacement `systems-bench-fr9fg` completed successfully. No GPU pods remain.
  START/RUN markers were removed. Temporary storage-access pod is deleted
  after final copies; its manifest can recreate access without GPUs.

## Second row, in progress

- User requested schema enforcement and no redundant generation for filled
  rules, followed by a new 256/100 setting and a full `local_data/` copy.
- At 21:22 UTC submitted a new eight-GPU placeholder with standing $3 bid
  unchanged. Previous node had been released; market is provisioning again.
- Updated reasoning labels from the original outer-loop source: world medium,
  consistency high. Verified checkpoint template exposes only enable_thinking,
  so non-none labels still map to the same thinking-on mode; informed user.
- Selected next catalogue setting, Backyard Weather Station, subject weather,
  seed 42, output shared `runs/weather-256-100`. Optional clarification sent.
- Version 51 uses strict response_format=json_schema plus client validation.
  Permanent HTTP 4xx errors fail immediately. Per-rule generation is capped by
  remaining slots and batch limit. Nine offline tests pass.
- CPU pod `systems-bench-r86b6` is staged. Background start_benchmark.sh waits
  for server health, runs all-schema/thinking/regression smoke checks, and
  creates RUN only on success. Logs under the new run's start-benchmark.log.
- Existing weights/caches reused. GPU launcher uses approved local AITER
  compilation scratch with finished modules persisted to shared storage.
- User confirmed Backyard Weather Station and requested native boolean toggles
  instead of effort labels. Replaced EFFORT with THINKING and changed all call
  sites/tests/smoke checks to boolean thinking; original outer-loop untouched.
- IMPORTANT latest shutdown instruction: after this second row, KEEP the GPU
  serving pod running idle with the model loaded, ready for the next run. Do
  NOT delete the serving Job/Service. Bid remains $3/GPU-hour; user informed
  that holding eight GPUs continues billing up to $24/hour.
- Setting schema's `contains` constraint rewritten equivalently using anyOf
  and prefixItems; compiled with llguidance 1.9.1 offline and exhaustively
  checked across all 256 one/two-factor patterns. Eleven tests pass.
- At 21:36 UTC, provisioning still pending (no GPU node joined); marketplace
  has cycled grants lw-1, bg-1, id-13, id-12, id-5. Live GPU spend remains zero.
- At 21:41 UTC user explicitly authorized cancelling/restarting the GPU job
  and raising ceiling to $4/GPU-hour. Deleted pending Job/Service, PUT bid with
  expected_version 11 (new version 12, max 4.0), and resubmitted. Stored bid
  change evidence under weather run. New max node rate is $32/hour. KEEP GPU
  serving pod loaded/idle after completion; do not withdraw the $4 bid.
- At 21:56 UTC, the restarted request remains unprovisioned after ~14 minutes
  (~34 minutes total). Grants moved id-2 -> id-16 -> id-4 -> id-3; no GPU
  node or pending CSR appeared. Kueue only reports 0 of 1 granted nodes ready.
  API quotes $3/GPU-hour to win, below authorized $4, no billing hold; live
  market spend is zero. Requested user check with National Compute about
  provisioning. Job remains queued and CPU startup waits for server health.
- User said provisioning can take time; retained request. GPU pod
  `mimo-serve-vtctj` subsequently joined and became healthy. Original 20 smoke
  checks passed; world-building began before the next user instruction.
- User requested semantic answer deduplication, then explicitly requested STOP
  the current benchmark and report back BEFORE launching the full row. Removed
  RUN and deleted the current CPU benchmark Job. No checkpoint/questions had
  been produced; completed world-building calls remain cached on shared storage.
  Do NOT relaunch the full benchmark until the user gives the next go-ahead.
- KEEP provisioned GPU Job/Service and model running. Health returned HTTP 200
  after stopping the CPU client. Do not withdraw or lower the authorized $4 bid.
- Version 52 adds a separate four-label semantic uniqueness check, in parallel
  with the existing checks. Every duplicate member is false; any false rejects
  the candidate. Store labels and enforce them during export. The dedicated
  THINKING[deduplication] toggle defaults false. Fifteen offline tests pass.
- Live smoke checks passed, including new uniqueness schema and two semantic
  checks: north/north paraphrases -> false,false,true,true; four distinct
  directions -> all true. All 23 smoke checks pass (20 prior cached successes,
  three new calls). GPU node is bg-2; healthy mimo-serve-vtctj remains running.
  At 22:18 UTC live rate is $24/node-hour, under the $32 ceiling. Full benchmark
  remains stopped, RUN absent. Copy partial results/smoke evidence locally;
  no complete weather row is claimed. Await user's go-ahead to start full row.
- User changed the next run to 16 rules per world and a cumulative maximum of
  four low-acceptance retirements per system. Updated defaults, both benchmark
  launcher commands, and smoke dimensions. All other generation/acceptance
  settings stay unchanged. Full row remains paused; keep the GPU server running.
  The old eight-rule world-building cache must not be resumed as a 16-rule run;
  use a fresh output directory or preserve/archive the old attempt before launch.
- User approved shortening each world rule paragraph to a target of 80–120
  words (previously 140–220). Only the two word-target constants changed;
  other settings remain unchanged. Full row remains paused.
- User renamed exported row columns Institution -> Setting and Handbook ->
  World. Export, review generation, validation, and export tests use the new
  names; field contents are unchanged. Historical saved results are preserved.
- User authorized the full 256/100 row for Bean Seedling Growth (plant-growth),
  superseding the paused weather run. Use fresh runs/bean-seedling-256-100;
  16 rules/world, 80–120 words/rule, at most four retirements, same checks and
  boolean thinking configuration. Leave the server and bid running afterward.
- First Bean attempt hit the 32,768-token planning limit (32,767 reasoning
  tokens, no final plan). User authorized the highest supported thinking output
  limit. Xiaomi documents 131,072; increased both thinking ceilings accordingly,
  retaining 512 for non-thinking. Raised server context from 65,536 to 262,144.
  Stop CPU client and archive old attempt; replace only the serving pod under
  its existing GPU Job/bid so the provisioned node remains held, then restart
  the full row. No generation prompts or quality criteria changed.
- Server pod replacement completed on the SAME bg-2 node; current pod
  mimo-serve-vnq2w is healthy, context 262,144. Current CPU pod is
  systems-bench-s4x6x. All 23 smoke checks passed before restart at ~22:48 UTC.
- Bean worlds attempt 0: four consistency failures, one pass; cross-world pass.
  Revision planner completed in 1222.4 s with 121,681 generated tokens (113,922
  reasoning). Attempt 1 repaired three worlds; one leaf-health/edge-color
  conflict remains. Attempt 2 now revises only world index 0, preserving four.
- User asked about reducing thinking, but has NOT authorized an 8,192-token
  thinking budget. Keep existing benchmark payload unchanged. Two isolated
  probes confirmed vLLM thinking_token_budget works mechanically (budget 1 ->
  exactly one reasoning token then valid JSON). MiMo-specific planning quality
  under forced cutoffs remains unvalidated. Probe records and official report
  saved under this run. Telemetry includes two diagnostic calls (210 output,
  52 input tokens); benchmark API audits exclude them.
- Bean row completed at 23:28:38 UTC: 256/100, 22 rounds, 1,011 evaluated,
  356 accepted, four retirements. Zero schema-invalid HTTP 200 responses;
  22 transport failures recovered. Local full copy and core SHA256 checks pass.
  All final worlds have 16 rules; all accepted uniqueness labels are true.
  Four of 80 paragraphs miss the prompted 80–120-word target (76–136 range).
- GPU mimo-serve-vnq2w remains healthy on bg-2, Job/Service/START retained,
  RUN removed. Standing bid remains $4/GPU-hour version 12, actual $24/node-hour.
  Do not stop the server or withdraw the bid after this completed row.
- Detailed report is RESULTS.md; local artifacts are gitignored under
  local_data/bean-seedling-256-100. Current source must remain unchanged for
  any reproduction/export using its archived source/configuration manifest.
- Updated review rendering at user request: all five worlds, questions grouped
  by rule, fixed world-labeled answer order (gold first), original split indices.
  scripts/review.py regenerates only presentation from saved checkpoints; the
  Bean dataset/checkpoint hashes and original source archive remain unchanged.
  Regenerated local/shared Bean review; 17 tests and artifact assertions pass.
- Prepared (NOT launched) full 64 x 256/100 generation/upload at user request.
  Local run_full.sh accepts optional HF repo, defaults aklein4/AlwaysLearningBench-v1.
  Eight concurrent rows, shared 256-request bound; version 53 supports partial
  indexed checkpoints, TaskGroup cancellation, global dedup and resume.
  Audit logger uses streaming reload and running counters for full-run scale.
- Full launcher freezes code under runs/full-64-256-100/code on first execution,
  validates/creates upload destination before generation, uploads after complete
  export, copies full artifacts locally on success, removes CPU pod only.
  GPU Job/bid remain untouched. 20 tests, YAML dry-run, shell syntax and mocked
  terminal-error behavior pass. Live GPU health HTTP 200; shared free space 819G.
- Upload preflight discovery: cluster HF_TOKEN authenticates as evinsi; default
  aklein4/AlwaysLearningBench-v1 returned 404. User asked to preserve this default
  while allowing an argument. User has been asked whether to update token or
  override destination. No repository has been created and no upload attempted.
- User identified the correct token source: ~/.config/nc-baseline/credentials.env,
  as documented by nc-baseline/full-baseline.yaml. Verified account aklein4 and
  write role, patched ONLY api-keys.HF_TOKEN, and read back/verified the stored
  credential via whoami. Other keys and live GPU pod unchanged. Destination
  still not visible; launcher creates/verifies it on user execution. This
  resolves the previously recorded evinsi credential mismatch for new workers.
- User changed full-run row concurrency from 8 to 32. Updated launcher and
  README; shared in-flight request limit remains 256. No run launched.
- Row completion now prints the total completed rows (e.g. 12/64), counting
  checkpointed rows on resume. Startup also prints the current completed total.
- User explicitly stopped the full run during preparation of v54 changes.
  systems-bench-full pod was already absent at stop check; no new run launched.
  Checkpoint retains 585 accepted questions, zero complete rows. GPU server
  mimo-serve-vnq2w stays healthy on bg-2; Job and standing bid unchanged.
  Local v54 work adds 32 catalogue entries, fallback on exhausted settings,
  and 512 limits; 24 tests pass. These changes are NOT deployed, the live
  server is still at 256 sequences, and the old full-run source/checkpoint
  has NOT been migrated. Do not resume or restart serving without next go-ahead.
- User revised retirement budgets. Local v55 retires an unfilled rule at
  generated >= 10 * current quota, retaining cumulative four-rule cap and quota
  redistribution. Removed prior 20-evaluated/three-rejected-round/<30% criteria.
- Row question exhaustion is now 20 * (train+test) raw returned candidates:
  7,120 for 256/100. Duplicates count; final batch is trimmed to remaining budget
  and evaluated before discard. Removed max-rounds setting/limit entirely.
  Generated counters are checkpointed per rule; request/world limits unchanged.
- 31 tests pass, including thresholds/current quotas, duplicate accounting,
  exact row-budget cap and successful completion on final budgeted candidates.
  All changes remain local; no run or serving restart authorized/performed.
  Old frozen full-run snapshot/checkpoint still needs migration before new logic
  can apply. README now explicitly warns that the existing launcher resumes v53.
- Local v56 collision verifier now returns one per-rule distinguishing example
  with five world-ordered answers, or an explicit failure. Every rule must pass;
  helper validates cardinality/nonempty evidence/exact answer uniqueness and
  per-rule flags, in addition to existing global collision checks.
- Examples are inspection-only: saved in cached calls/checkpoint and rendered
  in review, excluded from train/test pool and counters, and stripped from
  revision feedback (only rule flags/reasons forwarded). No extra answer calls.
  33 offline tests pass, including failed-rule revision gating, export rejection
  of missing evidence, and no example leakage into generation or dataset.
  Live smoke fixture updated but not run; stopped run/server unchanged.
- Simplified COLLISION_PROMPT into short instructions for each rule, output
  fields, and the three global checks. Same evidence schema and acceptance
  behavior; no live deployment or run restart.
- Consistency prompt now receives WORLD_COUNT as context while explicitly
  checking only the supplied world. Collision prompt retains the same count.
- User corrected the prior prompt request: removed world_count context and
  formatting from CONSISTENCY_PROMPT. COLLISION_PROMPT retains world_count and
  per-rule distinguishing questions. Run remains stopped.
- User requested preparation of a NEW full run/upload. run_full.sh now targets
  runs/full-64-256-100-v56 and local_data/full-64-256-100-v56, leaving stopped v53
  run untouched. Current code snapshots on first execution; no migration needed.
- Server prepared for 512 sequences: atomically replaced shared serve.sh, deleted
  only the serving pod under the retained Job, and kept the SAME bg-2 node.
  New pod mimo-serve-vtgcn is Ready/healthy; live process args confirm 512.
  Job and bid unchanged. Benchmark worker is absent; full run NOT launched.
- Verified cluster token is aklein4 and write access to the default Hub dataset.
  33 offline tests, shell syntax, full-run CLI settings (64/96, 32 rows, 512
  requests), and a live expanded collision-schema probe passed. Probe results
  are on shared storage and copied locally under the new run's preflight/.
  Schema probe is diagnostic only; it did not generate benchmark candidates.
- Clarified collision distinct flag: successful per-rule examples are necessary
  but not sufficient. Verifier must also judge whole-system predictive differences,
  matching factors, interactions/exceptions and semantic incompatibility. Overall
  distinct=false still rejects even when all per-rule flags are true.

- Full v56 completed 64 rows (16,384 train / 6,400 test) and uploaded to
  aklein4/AlwaysLearningBench-v1 at commit 3f59ce209d6b5ec3afb585d7602760a803036233.
- User stopped the raw audit transfer. Filtered actual API attempts with
  scripts/filter_audit.py: all accepted questions, first up to 10 rejected
  drafts per rule of each final row, and all world-building attempts. Removed
  reasoning; mixed generation outputs explicitly filtered/re-encoded. Original
  usage counters still include thinking/excluded outputs; token IDs unavailable.
- Copied and fully validated filtered_audit/ locally: 302,476 records, 22,784
  accepted questions, 9,871 rejected examples. SHA256 matches shared archive.
  Removed the partial local raw api_audit/ and unfiltered checkpoint.json;
  complete originals remain on shared storage. Dataset/review/code retained.
  GPU server and bid remain running; full CPU worker was removed by launcher.
- 2026-10-02: Added read-only `explorer/` web server for the v56 run (stdlib only).
  It rebuilds structure from `filtered_audit/` into `local_data/explorer/*.sqlite`.
  All 64 gold worlds match the dataset; all 32,655 sampled drafts' recomputed
  verdicts match accepted/rejected status; every accepted item maps to its
  published options and correct answer. No run artifacts were modified.
