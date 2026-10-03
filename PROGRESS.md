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

## Causal-graph rewrite (2026-10-02)

- Replaced counterfactual worlds with eight metrics per catalogue setting. Every
  graph contains both direct outcomes and outcomes through an intermediate;
  sampled questions consequently require one or two conditions.
- Model generates semantic labels only. Python chooses overlapping input pairs,
  then randomizes tables and outcome slots independently of label meanings.
  Metrics vary between four and six outcomes. Three alternative outcomes are
  sampled from the target graph and all four options are shuffled.
- Questions receive only setting, target metric and shuffled sampled details;
  one or two distractors are either decorative or inputs outside the target graph.
  Answers are independent calls using only the system, metric and their assigned
  outcome. Neither question nor gold/distractor status enters an answer prompt.
- User clarified independent train/test sampling from the same learned system,
  qualitative descriptions and default sampling (no client temperature/top-p
  overrides). Labels, label
  verification, questions, and wording verification use reasoning. Answers do not.
  Non-reasoning wording checks missed missing facts and invented behavioral clues
  in exploratory pilots, motivating reasoning for verification too.
- Restored injected writing variations for natural science word problems. One
  question variation and one shared answer variation are sampled per question;
  the four independent answer calls use the same variation and never see gold
  status. Reference questions identify metrics without forcing identical wording.
- Removed explorer and obsolete benchmark, review, metrics and audit-processing
  scripts. Historical runs remain untouched, with their frozen code snapshots.
  Simplified the cluster launcher; Hub upload is explicit rather than automatic.
- Sixteen offline tests pass, including mixed depths, exact evaluation, reachable
  alternatives, irrelevant distractors, prompt isolation, cache/resume, metric
  quotas after rejection, corrupted export rejection, API auditing, and retrying
  empty completion content observed in the second exploratory pilot.
- Set National Compute bid to $3/GPU-hour (version 14). Requested one eight-MI355X
  node through mimo-serve. Node bg-1 joined; live market rate is $24/node-hour.
  MiMo is healthy. User explicitly requested leaving the server ready after the pilot.
- Authorized pilot: river-otter setting, 16 train / 8 test. Current candidate is
  /mnt/shared/nc-synthetic-data/runs/causal-pilot-v5. Earlier exploratory pilots
  remain separate; manual review found wording and overlapping-label problems,
  addressed by simpler decorative attributes and a pre-generation label check.

- Final qualitative pilot completed: 16 training and 8 test questions in
  `local_data/causal-pilot-v5/` and the matching shared run directory. `examples.txt`
  presents the questions/options; `report.json` records validation. No Hub upload.
- Audited every accepted question and answer: question payloads contain only
  setting, reference question, sampled details and variation; answer payloads
  contain only system, metric, assigned outcome and one shared answer variation.
  All API calls omit sampling overrides. Snapshot matches current generator.
- All eight graphs contain direct and mediated outcomes. Outcome counts are
  5/4/6/5/6/4/5/6. The final pilot has 13 one-input and 11 two-input questions,
  and 13 one-distractor and 11 two-distractor questions.
- Manual review replaced five automatically accepted examples for invented
  details or misleading question framing. Their original items and reasons remain
  in checkpoint `review_rejections`; their API calls remain in the audit. Model
  checks are imperfect, so larger datasets still need text review. No empirical
  zero-shot accuracy claim is made.
- Stopped the obsolete explorer server from this repository. Remove only the
  temporary CPU worker after artifact transfer; retain MiMo and its $3/GPU-hour
  bid at the user's request. Live and assessed billing both report $24/node-hour.

## Varied causal graphs and fresh decorations (2026-10-02)

- User requested five or six inputs with three or four values each, more graph
  structures, anonymous intermediates, fresh per-question decorative details,
  and removal of reference questions. The blueprint requests six inputs; schema
  permits five or six and three or four qualitative values per input.
- Graphs now mix three DAG families: one mediated input plus a raw input, a joint
  intermediate, and parallel intermediates. Explicit direct paths test one or two
  input conditions; every graph also has mediated paths. Outcome sets for the
  two depths are disjoint, all outcomes are reachable, and input overlap is checked.
- Decorations are generated per candidate from just the setting and count, with
  no preselected world decoration attributes. Question payloads contain exactly
  setting, metric, details and variation. No reference question, outcomes, causal
  graph or relevance flags are included. Intermediates have integer states only.
- The first new draft (`causal-variety-pilot`) exposed overlapping labels and
  false accepts by the combined wording check. It is preserved as an exploratory
  run. Each input/metric now gets an independent label check, and the question
  and four answers each get independent wording checks. Writing calls still use
  identical answer pipelines and a shared answer variation; sampling overrides
  remain absent. Fresh decoration generation uses reasoning too.
- Twenty-one offline tests pass, including exhaustive evaluation across three
  families, five/six-input worlds, prompt isolation for all decoration counts,
  and quota preservation after either question or answer rejection.
- A whole-world repair in `causal-variety-pilot-v2` hit the 32,768-token reasoning
  cap. Replaced whole-world semantic repair with short per-property repair calls,
  preserving approved definitions and each property's cardinality. The stopped
  run and its audits remain on shared storage. Twenty-two tests now pass.
- Final pilot completed on 2026-10-03 in `local_data/causal-variety-pilot-v3/`
  and `/mnt/shared/nc-synthetic-data/runs/causal-variety-pilot-v3/`: one row,
  16 training and 8 test examples, two/one per metric respectively. Six input
  cardinalities are 3/3/3/4/3/3; outcome counts are 5/4/6/4/5/4/5/6.
- All three DAG families are present. Final examples include eleven direct and
  thirteen mediated outcomes, seven one-input and seventeen two-input scenarios,
  fourteen one-distractor and ten two-distractor scenarios. Ten questions have a
  fresh decorative detail; the others use off-target causal attributes.
- Read all final examples against their sampled facts and assigned outcomes.
  Manual review removed 22 drafts for invented actions, changed facts, drafting
  debris, extra explanation requests, or misleading outcome framing. Original
  items and reasons remain in checkpoint `review_rejections`, with API audits
  intact. Automated wording checks still miss errors; this is a reviewed pilot,
  not evidence that larger runs need no review.
- Final export and audit passed: every gold recomputes, all alternative outcomes
  are reachable, question payloads have exactly setting/metric/details/variation,
  answer calls have exactly system/metric/outcome/variation and share a variation
  per question, reasoning settings match policy, and no sampling overrides occur.
  Source snapshot matches the current generator. `examples.txt` and `report.json`
  are saved locally and on shared storage. Twenty-two offline tests pass.
- No Hub upload. Temporary CPU worker removed; MiMo remains ready on the existing
  eight-GPU node as requested. Exploratory runs remain separate and untouched.

## Language and verification iteration (2026-10-03)

- Shortened questions to at most 55 words and answers to at most 16. Question
  variations now change sentence structure; answer variations request compact,
  literal phrases. Removed narrator/reporting cues and unrelated decorative
  backstories. Fresh decorations name the existing subject or site in 1–3 words.
- The question writer still receives only setting, metric, shuffled details and
  variation. The answer writer now receives the brief setting rather than full
  causal tables, plus metric, assigned outcome and the variation shared across
  its four independent calls. It receives no question, sampled facts, other
  answers or gold flag. Questions use reasoning; answers remain without reasoning
  as explicitly requested. All calls retain default sampling parameters.
- Replaced five wording checks per candidate with one combined review returning
  separate question/answer verdicts. It checks standalone detail preservation,
  question/answer fit and faithful outcomes, without judging arbitrary causality.
- Worlds use the catalogue theme directly. The model chooses short, literal
  labels; property checks include the setting. Repairs preserve both the property
  and its cardinality, and all label tasks finish before a world is retried.
  This prevents the observed out-of-theme repair drift in an exploratory run.
- Exploration and frozen request audits are under `local_data/causal-language*`
  and the matching `/mnt/shared/nc-synthetic-data/runs/` directories. The protocol,
  analysis helper and baseline measurements are in `local_data/causal-language/`.
  No manual refills were used for these measurements. Probe v3 was stopped and
  excluded when the user declined reasoning-enabled answers; production answer
  calls never enabled reasoning.
- Three completed 24-candidate probes had 20, 15 and 13 automatic passes versus
  13 for the old prompts. Mean question/answer lengths were 40.8/6.3, 37.6/8.2
  and 32.7/8.0 words versus 75.5/12.7. Later probes also removed a bookkeeping
  sentence from the old setting. The verifier changed, and manual inspection
  found false accepts, so these are operational yields, not quality scores or
  evidence of a reliable acceptance-rate gain. All revised probes had zero
  first-person answers. Final prompts further remove category jargon and require
  every supplied detail in the question text itself.
- Earlier fresh pilots v1/v3 completed but exposed wording defects; v2 was
  stopped after repairs drifted off theme (some generation finished during
  shutdown). Their artifacts are retained as exploratory results.
- Twenty-four offline tests pass, including prompt isolation, shared answer
  variation, reasoning/default sampling settings, combined-review rejection,
  context-preserving label repair, word limits and the existing graph invariants.
- Added quoted question evidence to the combined review. Its response schema
  requires exactly one quote per sampled detail; Python rejects empty or absent
  quotes. The initial variable-count schema caused 31 count failures in pilot v5;
  the exact-count schema is in the final code. Twenty-seven tests now pass.
- Final wording pilot `local_data/causal-language-pilot-v6/` reuses the world from
  fresh pilot v4; `world_origin.json` records this explicitly. The automatic run
  accepted 24/42 candidates, averaging 32.0 question words and 3.8 answer words,
  with zero first-person answers. This is not an independent quality score.
- Manual review rejected seven accepted drafts for altered outcomes, invented
  swimming that conflicted with dry-fur options, or malformed/rambling text.
  Replacements used complete, unchanged question/answer pipelines. The reviewed
  row has 16 train / 8 test items after 57 total candidates, balanced 2/1 per
  metric. Original automatic checkpoint/report/export and rejected items remain
  intact. `preview.txt`, `examples.txt`, `report.json` and `manual_review.json`
  provide the final artifacts and limitations. No manual text edits were made.
- Final audit validates all gold labels, quotas, default sampling, reasoning
  settings, prompt isolation and shared answer variations. The frozen generator
  matches the current source. Some wording remains stiff; qualitative labels are
  a preference rather than a hard semantic constraint (time ranges remain in
  this world). Automated verification still needs human oversight for fidelity.
- MiMo remains running on the existing eight-GPU node; the temporary CPU worker
  is removed by the launcher. No Hub upload was performed.

## Conditional branches and batched world review

- Replaced the previous mediator families with conditional two-criterion graphs:
  the first input value either selects an outcome or visits an anonymous node
  that tests the second input. Every graph has both depths; each intermediate
  actually depends on its second criterion. Direct outcomes remain disjoint from
  depth-two outcomes. Random label assignment is independent of label meaning.
- World labels now receive one combined semantic review and, if needed, one
  whole-blueprint revision. Removed per-property checks/repair loops. Outcome
  counts stay within 4–6 without requiring all three counts to occur in a world.
- Independently sample 0–1 environmental distractors and 1–2 fresh acausal names.
  Environmental candidates include a graph's unused second criterion after a
  first-criterion shortcut. Python checks path invariance; the single combined
  wording review also checks a typed distractor plan and returns its own verdict.
  These roles are never exposed to the question writer. Answer calls remain
  independent, share one variation, use no reasoning and default sampling.
- User clarified that automatic filtering remains enabled, but there must be no
  manual revisions or review-driven refill. Ran `causal-branches-pilot` once:
  16 train / 8 test from 34 train and 16 test candidates, with zero manual edits.
  Exactly one world review and one world revision were used. The final row has
  10 depth-one / 14 depth-two questions; environmental counts are 13 zero / 11
  one, and acausal counts are 11 one / 13 two. No accepted question happened to
  sample an inactive second criterion; eligibility/invariance are tested across
  many seeded samples. No additional sampling was done to change this result.
- Artifacts: `local_data/causal-branches-pilot/{systems_bench.jsonl,preview.txt,
  graphs.txt,report.json}` and the matching shared run directory. Review results
  are included with exported examples; rejected calls remain in the audit.
  The protocol and read-only audit/preview helper are in
  `local_data/causal-branches/`. No manual semantic quality guarantee is claimed.
- Twenty-four tests pass, including traversal short-circuiting, both causal
  depths, reachability, distractor invariance/counts, whole-world call batching,
  automatic filtering with metric quotas, writer isolation and API defaults.
  Final artifact audit and source-snapshot comparison pass; `git diff --check`
  is clean. MiMo remains ready; the temporary CPU worker was removed. No upload.

## Full-row generation and inspection viewer

- Set every generation call to MiMo-V2.6-Flash's official 128K output limit
  (131072 tokens); sampling parameters remain at model defaults. API audits now
  allowlist final assistant content and token counts, discard reasoning fields
  and tagged reasoning, and record only byte counts for malformed HTTP bodies.
  Historical audit files are not retroactively scrubbed.
- Added the standalone Python viewer (`view_run.py`, `viewer.html`) with five
  stages: world generation, causal graphs, question sampling, independent
  answers and combined verification, and the retained dataset. It exposes exact
  prompts/settings and final outputs, compact static graph diagrams, sampled
  paths, and evidence mismatches. No external assets or animations are used.
- Stopped `causal-full-256-100` at the user's request, preserving its 114 train /
  0 test checkpoint and audit locally with an explicit stopped status.
- Started the fresh one-system 256/100 run
  `causal-full-256-100-qa-no-thinking` with concurrency 128. Only combined QA
  verification changed to reasoning disabled; questions, world calls and fresh
  names retain reasoning, while independent answer calls remain without it.
  The actual cached requests confirm the QA setting and output limit. The run
  is still active; no scheduler changes or manual data revisions were applied.
- All 30 unit tests pass. Browser checks cover all five stages, eight graphs,
  evidence mismatches, answer reveal, navigation and desktop/mobile layouts,
  with no page errors or desktop page overflow. The full artifact audit is
  prepared for completion. The launcher copies finished artifacts locally and
  removes only its CPU worker; MiMo remains ready on the existing GPU node.

## Continuous scheduling restart

- Replaced whole-batch barriers with a continuously replenished pool spanning
  train and test. Each accepted or rejected candidate is checkpointed on
  completion; rejection releases its reserved metric slot immediately. Pending
  reservations preserve the sampled graph and attempt ID across interruption.
  Reservations prevent surplus generation or accepting excess examples for a
  metric. Finished examples are ordered by completion, with the same quotas and
  global duplicate filtering as before.
- Question generation now overlaps with its independent answer sequence. The
  four answers still use separate sequential calls and one shared variation.
  Both the request semaphore and reusable HTTP connection pool permit 512
  concurrent requests in the new full-row run, matching the live vLLM limit.
  Prefix caching and the eight-GPU server remain running; no serving restart or
  sampling/reasoning/output-limit changes were made.
- Stopped and archived `causal-full-256-100-qa-no-thinking`, then launched
  `causal-full-256-100-continuous` for one 256/100 row at concurrency 512.
  World preparation is active; completion is not yet claimed. The launcher will
  copy results locally and a completion watcher will run the artifact audit.
- All 32 tests pass, including regressions proving that one blocked verification
  does not block refill, test generation or checkpointing, that interruptions
  resume only outstanding candidates, and that question/answer writers overlap.
  README commands and scheduling explanation are updated; diff whitespace checks
  pass. QA verification and answers retain reasoning disabled; default sampling,
  131072-token limits and trace-free auditing are unchanged.

- Completion confirmed: `causal-full-256-100-continuous` produced exactly 256
  train / 100 test, using 469 / 173 candidates respectively, with no manual
  revisions. The final artifact audit passed, including graph gold, quotas,
  distractor invariance, isolated prompts, shared variations, default sampling,
  frozen source, export consistency and absence of persisted reasoning traces.
  All artifacts and report.json are local. The viewer at port 8765 serves this
  completed run and matches all 356 retained examples to their source calls.
  The temporary CPU worker exited; the eight-GPU MiMo server remains running
  as requested.

## Prepared full v2 publication launcher

- Added `run_publish.py` for an explicit, user-started run of 64 mixed-catalogue
  systems, each with 256 train / 100 test, at concurrency 512. It delegates to
  the frozen-source launcher and existing validated export/upload pipeline,
  targeting `aklein4/AlwaysLearningBench-v2` with the CPU worker's HF token.
- On completion, generation/upload failure or a handled interrupt, the wrapper
  removes the MiMo job and withdraws the National Compute GPU bid. It reads the
  current bid version before each withdrawal and retries both cleanup operations
  independently. Cleanup failure returns nonzero. Preflight checks the existing
  server, absence of another CPU worker, and the authorized price ceiling.
- `run_full.sh` now attempts local artifact copy after generation/upload errors
  before removing its CPU worker, retaining the original failure exit status.
  Shared checkpoints remain available regardless of local-copy success.
- Documented the nohup invocation, log, output directory, resume prerequisites,
  and shutdown limitations. Forty tests pass, including eight mocked launcher
  lifecycle cases; shell syntax, help and diff whitespace checks pass. No full
  run, upload, bid mutation or GPU shutdown was executed while preparing this.
