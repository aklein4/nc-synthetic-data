# SystemsBench

Generate systems that a model learns implicitly from examples. Each catalogue
setting has five or six shared input attributes with three or four qualitative
values each, and eight distinct output metrics with four to six outcomes each.
The catalogue supplies the setting. The model chooses short category labels;
Python independently randomizes the causal mappings. One model call reviews all
inputs and metrics together. If that review fails, one call revises the entire
blueprint. There are no per-property repair loops. Python validates graph structure
and reachability after construction. These are synthetic relationships, not
claims about real science.

Every graph first tests one input. Some values directly select an outcome
(depth one); other values select an anonymous intermediate that tests the second
input and routes to an outcome (depth two). The second input is not read on a
direct branch. The number of direct branches, their conditions, intermediate
routes and outcome assignments vary. Every intermediate actually depends on the
second input. Direct and depth-two outcomes are disjoint, every outcome is
reachable, each graph uses two inputs overall, and every input affects at least
two graphs. A sampled question requires one or two conditions.

Each question independently samples zero or one environmental distractor and
one or two wholly acausal decorations. The environmental distractor is an input
outside the active path: either an input outside the graph, or the second input
when the first condition already selects a direct outcome. Python verifies that
varying that distractor cannot change the result on the sampled path.
Decorations are fresh subject/site names generated from only the setting and
requested count; they have no physical effects or backstories and are not stored
in the world. Python computes the gold outcome, samples three other possible
outcomes from the same graph, and shuffles the four options.

The question writer receives only the setting, metric name, shuffled facts and a
writing variation: no reference question, graph or answer. It weaves those facts
into a short science word problem of at most 55 words. Variations change sentence
structure without adding a narrator or story. Each answer is generated separately
from the brief setting, metric, assigned outcome and one shared answer variation. Answer calls
receive no question, sampled facts, other answers or indication of correctness.
Answers are short phrases (at most 16 words), with no first-person report or
extra context. One combined verification call checks the question and all four
answers, returning an individual verdict for each and a separate distractor
verdict. The verifier receives the environmental/acausal distractor plan, including
whether an environmental fact is an unused second criterion. It checks their
counts, faithful inclusion and acausality, and rejects added distracting facts.
It quotes evidence for every sampled detail, with the count fixed by the response
schema; Python rejects missing quotes or quotes absent from the question. The
answer writer receives no causal tables.

Graph evaluation and sampling are exact; natural-language fidelity still relies
on model judgment. Random assignment does not itself prove measured zero-shot
accuracy is exactly 25%. Intermediate table slots spread outcomes as evenly as possible. Both splits balance questions across the eight metrics and independently
sample scenarios from the same system, so input combinations may recur. Normalized
duplicate question text is rejected. Failed candidates are automatically filtered
and new candidates fill the remaining metric quotas; existing drafts are not
rewritten. The inspection pilot is generated in one run without manual curation.

## Generate

```sh
python -m pip install -r requirements.lock
API_URL=http://localhost:8000/v1/chat/completions python systems_bench.py \
  --subject animal-behavior --systems 1 --train 16 --test 8 \
  --output-dir local_data/causal-pilot
```

World generation, its combined review/revision, fresh names and questions use
reasoning. Answers and the combined QA verification call do not.
Calls omit sampling overrides and use the server defaults.
Every call allows 131,072 output tokens, matching MiMo-V2.6-Flash's
[official 128K maximum](https://mimo.mi.com/models/en-US/mimo-v2.6-flash).
This is the generation ceiling, including reasoning; the short question/answer
word limits are still checked separately.

`MODEL` defaults to `mimo-v2.6-flash`. `INFERENCE_API_KEY` is optional. Use
`--subject mixed` for the existing catalogue, `--concurrency` to bound requests,
and `--upload owner/dataset` only when a Hub upload is intended.
World preparation and train/test candidates from every world run in one global,
round-robin pool. A slow world cannot block preparation or examples in other
worlds. `--concurrency` bounds both the total scheduled tasks and simultaneous API
requests, rather than multiplying that limit by the number of worlds. Finished
candidates are checkpointed together after each completion wave; a failed candidate frees its metric
slot for a replacement without waiting for other requests. Pending reservations
are checkpointed too, so interruption resumes the same sampled candidates.
Question writing overlaps with its independent answer-writing sequence; the four
answers still use separate, sequential calls. The request semaphore and HTTP
connection pool both respect `--concurrency`. The full-row command uses 512,
matching the current server's sequence limit. Prefix caching stays enabled.
Concurrency naturally falls as the remaining output slots finish; the generator
does not create surplus candidates just to keep GPUs occupied.

A run saves its checkpoint, cached final model responses, API attempt audits, token
usage, and `systems_bench.jsonl`. Each dataset row has `Setting`, `World`, and
nested `train_data`/`test_data` containing question, four options, a zero-based
`correct_option`, and `verification` results. `World` is graph metadata for inspection; **do not include it
in the learner's question prompt**. Sampling provenance stays in the checkpoint.
Reusing a run directory resumes completed work and cached calls. Changed source
or run settings require a new directory. Historical runs remain separate.
New audits save prompts, final content, timings and token counts, **not reasoning
traces**. Reasoning fields and inline thinking blocks are discarded before writing;
unparseable HTTP bodies retain only their byte count. Historical audits are not
rewritten. The viewer reads structured final-response caches, never raw audits.

## Inspect a run

The local viewer needs only Python's standard library:

```sh
python view_run.py local_data/causal-full-256-100-continuous --port 8765
```

To inspect three varied worlds from the completed 64-row run:

```sh
python view_run.py local_data/alwayslearning-v2-64-256-100-parallel --worlds 7 26 56 --port 8765
```

These are the weather station, spider web and chromatography worlds. Use the
header selector to switch rows; each keeps its exact prompts and source calls.
`--worlds` accepts 1-based row numbers; `--rows N` instead shows the first N rows.
The viewer filters what is displayed without modifying the dataset.

To share a single offline file, add `--html` instead of starting the server:

```sh
python view_run.py local_data/alwayslearning-v2-64-256-100-parallel --worlds 26 51 2 --html local_data/SystemsBench-Three-Worlds.html
```

The HTML embeds the selected examples, graphs, prompts and structured final
outputs as compressed data. Open it directly in a modern browser; no server or
network connection is needed. API audits and reasoning traces are not included.

Open **http://localhost:8765**. If Python runs on another machine, forward that
machine's port 8765 to your browser's machine. The server binds to loopback only.

The five stages follow the data from world draft and combined review/revision,
through Python's randomized causal graphs, sampled facts and question writing,
independent answer writing and combined verification, to the final dataset.
Prompts and final outputs sit side by side; exact request JSON is expandable.
Graph diagrams show every conditional route and can highlight an example's path.
Browse one example at a time, filter by metric or split, reveal its answer, and
inspect retained or filtered candidates. There are no animations or external
assets. The evidence inspector flags quotes absent from the actual question,
including candidates that the model approved but Python filtered out.
Refresh reloads a run's latest local checkpoint and completed calls.
The National Compute launcher copies the run locally when generation finishes.

## National Compute

Use cluster `us-mi355-k8s-niveditha`. The authorized ceiling is $3 per GPU-hour,
or $24/hour maximum for one eight-MI355X node. The actual assessed rate comes
from `python scripts/nc_snapshot.py`. A standing bid does not reserve capacity;
an eight-GPU workload requests it. The token remains at
`~/.config/nationalcompute/token`. Follow the current
[National Compute setup instructions](https://nationalcompute.com/FIRST-JOB.md).

`k8s/serve.yaml` starts the pinned ROCm vLLM server on eight GPUs. It reads
`scripts/serve.sh` from `/mnt/shared/nc-synthetic-data/code/`, waits for
`control/START`, and uses cached weights under
`models/MiMo-V2.6-Flash-MOPD-http`. `scripts/download.py` stages missing weights;
`scripts/cache_sync.py` preserves the AITER compilation cache. All paths are
relative to `/mnt/shared/nc-synthetic-data`. The service endpoint is
`http://mimo:8000/v1/chat/completions` inside the cluster.

Once the service is healthy and the temporary CPU worker is absent:

```sh
# Small review pilot:
bash run_full.sh causal-review-pilot --systems 1 --train 16 --test 8 --subject animal-behavior
# Full dataset (no automatic upload):
bash run_full.sh causal-64-256-100
# One full row:
bash run_full.sh causal-full-256-100-continuous --systems 1 --train 256 --test 100 --subject animal-behavior --concurrency 512
```

The launcher freezes source in the run directory, runs a temporary CPU worker,
copies artifacts into `local_data/<run>`, and removes that worker on exit. It
leaves the GPU server running. Stop held GPU capacity with:

```sh
kubectl --context us-mi355-k8s-niveditha delete job mimo-serve
```

For the complete **64-row, 256-train / 100-test** release to
`aklein4/AlwaysLearningBench-v2`, use the dedicated launcher while MiMo is ready:

```sh
mkdir -p local_data
nohup python3 run_publish.py > local_data/alwayslearning-v2.log 2>&1 &
```

It uses the mixed catalogue and concurrency 512, validates/exports the complete
dataset, uploads it using the CPU worker's `HF_TOKEN`, and copies artifacts to
`local_data/alwayslearning-v2-64-256-100`. Follow progress with
`tail -f local_data/alwayslearning-v2.log`. The upload commit is recorded in
`upload.json`; raw calls and audits are kept locally/shared, not uploaded.

After the run exits, including generation/upload failure or a handled interrupt,
the launcher deletes the MiMo job and withdraws the cluster's GPU bid using
`~/.config/nationalcompute/token`. Both cleanup operations are retried on errors;
failed cleanup is reported with a nonzero exit. Shared checkpoints survive node
release. Preflight refuses an existing CPU worker, an unready MiMo server, or a
bid outside the authorized $3/GPU-hour ceiling, without stopping existing work.
`nohup` lets it continue when the terminal disconnects; host loss or SIGKILL
cannot run cleanup. Check the log's final shutdown confirmation. An interrupted
run can be resumed with the same name after restarting MiMo and restoring its bid.
`--run-name NAME` chooses a separate run directory.

The interrupted v2 run has been copied to a separate directory with the parallel
world scheduler. Resume its preserved examples and cached calls from tmux with:

```sh
python3 run_publish.py --run-name alwayslearning-v2-64-256-100-parallel
```

The original run remains unchanged. `scheduler-upgrade.json` records the old/new
source hashes and compatibility checks; `previous-code/` preserves its original
source. Only the scheduler changed, with no changes to prompts, model settings,
world mappings or saved examples. The same upload and GPU cleanup apply.

For runs using `run_full.sh` directly, withdraw the bid separately through the
National Compute API when no further GPU work is wanted.
Historical experiments are recorded in `RESULTS.md` and
the earlier sections of `PROGRESS.md`; their old pipelines were removed.

## Check

```sh
python -m pip install pytest
python -m pytest -q test_systems_bench.py test_local_api.py test_view_run.py test_run_publish.py
```
