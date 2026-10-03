"""Generate implicitly learned systems with eight shallow causal graphs."""

import argparse
import asyncio
import hashlib
from itertools import product
import json
import os
from pathlib import Path
import random
import re

import httpx
from jsonschema import validate
from jsonschema.exceptions import ValidationError

from local_api import AuditedClient, atomic_json

ROOT = Path(__file__).resolve().parent
MODEL = os.environ.get("MODEL", "mimo-v2.6-flash")
API_URL = os.environ.get("API_URL", "http://mimo:8000/v1/chat/completions")
# https://mimo.mi.com/models/en-US/mimo-v2.6-flash — 128K output tokens.
MAX_OUTPUT_TOKENS = 131072


def obj(**fields):
    return dict(type="object", properties=fields, required=list(fields), additionalProperties=False)


def array(items, minimum, maximum):
    return dict(type="array", items=items, minItems=minimum, maxItems=maximum)


TEXT = dict(type="string", minLength=1)
INDEX = dict(type="integer", minimum=0)
VARIABLE = obj(id=TEXT, name=TEXT, values=array(TEXT, 3, 4))
BRANCH = dict(anyOf=[obj(outcome=INDEX), obj(node=INDEX)])
WORLD = obj(setting=TEXT, inputs=array(VARIABLE, 5, 6),
            graphs=array(obj(metric=TEXT, outcomes=array(TEXT, 4, 6),
                             inputs=dict(type="object", additionalProperties=dict(type="integer", minimum=3, maximum=4), minProperties=2, maxProperties=2),
                             root=TEXT, branches=array(BRANCH, 3, 4),
                             nodes=array(obj(input=TEXT, table=array(INDEX, 3, 4)), 1, 3)), 8, 8))
DETAIL = obj(attribute=TEXT, value=TEXT)
QUESTION = obj(question=TEXT)
ANSWER = obj(answer=TEXT)
CHECK = obj(reason=TEXT, valid=dict(type="boolean"))


def review_schema(detail_count):
    return obj(question=obj(evidence=array(dict(type="string"), detail_count, detail_count),
                            **CHECK["properties"]), distractors=CHECK, answers=array(CHECK, 4, 4))


QUESTION_WORDS = 55
ANSWER_WORDS = 16
BLUEPRINT = obj(inputs=array(obj(name=TEXT, values=array(TEXT, 3, 4)), 5, 6),
                metrics=array(obj(name=TEXT, outcomes=array(TEXT, 4, 6)), 8, 8))
WORLD_PROMPT = """Choose six observable inputs with 3–4 values each and eight distinct output
metrics with 4–6 outcomes each for this theme. Vary the number of outcomes.
Use short, literal phrases in everyday English, not metaphors or jargon.
Use qualitative categories on one dimension, like left/right/straight/backward.
Choose properties whose outcomes have clearly different meanings, not overlapping
descriptions or near-synonyms. Inputs describe conditions, not the outputs themselves.
Give labels only, without causal rules.
Theme: """
WORLD_CHECK_PROMPT = """Review all inputs and metrics together in this setting. Check that the
properties are coherent, distinct and easy to describe, inputs are conditions
rather than outputs, and each property's values have clearly different meanings.
Prefer qualitative categories; no numeric cutoffs are needed. Identify all
problems in one brief review, or approve the whole blueprint.
"""
WORLD_REVISE_PROMPT = """Revise the entire blueprint using this review. Keep the setting, five or six
inputs with 3–4 values each, and eight metrics with 4–6 outcomes each. Fix all
reported issues together. Use short, distinct, qualitative labels and no causal rules.
"""
DECORATION_PROMPT = """Invent short proper names for the subject and/or place already in the setting.
Use distinct attribute names and one name per entity. Each value is just a new
proper name of 1–3 words. Add no entities, traits, actions or background.
"""
QUESTION_PROMPT = f"""Write a natural word problem in 1–2 sentences, at most {QUESTION_WORDS} words.
Include every detail and ask directly about the metric using what or which.
The setting is context, not text to copy. Follow the style cue and attach names
to their subjects. Add no events, explanations, comparisons or labels.
"""
ANSWER_PROMPT = f"""Express only the assigned outcome as a short answer phrase, at most {ANSWER_WORDS} words.
Keep every distinguishing detail; already concise wording may stay unchanged.
Follow the style cue. Add no subject, metric label, new facts or commentary.
"""
CHECK_PROMPT = """Check the question and all four answers. The reader sees only the question,
not the specification: every listed detail must appear in the question itself.
Check the distractor plan: zero or one environmental distractor that is inactive
on this path, plus one or two wholly acausal names. Preserve them without adding
extra distractors, actions or physical traits. An unused second criterion is
allowed when the first criterion already fixes the outcome.
For each detail in order, quote the exact words expressing it in the question;
use an empty string if missing. Do not quote the specification as evidence.
It must ask about the metric. Reject yes/no questions,
counts, changes or comparisons when the answers name categories. Reject invented
behavior that rules out an answer. Reject rambling, explanations or bookkeeping.
Each answer must fit the question and preserve all distinguishing
details of its outcome, with no added claims or speaker. Judge wording, not causal
plausibility. Give each field a verdict and a brief reason.
"""


QUESTION_VARIATIONS = {
    "structure": (
        "Introduce the subject, then ask the question.",
        "Open with a supplied condition, then ask about the outcome.",
        "Ask the question first, then give the conditions.",
        "Write one direct question that incorporates the facts.",
        "Describe the conditions briefly, then ask a direct question.",
    ),
}
ANSWER_VARIATIONS = {
    "wording": (
        "Use a direct descriptive phrase.",
        "Use a compact, literal paraphrase.",
        "Use the simplest wording that keeps the meaning precise.",
        "State the result tersely and naturally.",
    ),
}


def variation(rng, banks):
    instructions = [rng.choice(bank) for bank in banks.values()]
    rng.shuffle(instructions)
    return " ".join(instructions)


def normalized(text):
    return re.sub(r"\W+", " ", text.casefold()).strip()


def required_inputs(graph, assignment):
    """The first criterion selects either a result or a second-criterion node."""
    first = graph["root"]
    branch = graph["branches"][assignment[first]]
    return [first] if "outcome" in branch else [first, graph["nodes"][branch["node"]]["input"]]


def evaluate(graph, assignment):
    branch = graph["branches"][assignment[graph["root"]]]
    if "outcome" in branch:
        return branch["outcome"]
    node = graph["nodes"][branch["node"]]
    return node["table"][assignment[node["input"]]]


def assignments(graph):
    return [dict(zip(graph["inputs"], values))
            for values in product(*(range(size) for size in graph["inputs"].values()))]


def validate_world(world):
    validate(world, WORLD)
    inputs = {v["id"]: len(v["values"]) for v in world["inputs"]}
    if len(inputs) != len(world["inputs"]) or len({normalized(v["name"]) for v in world["inputs"]}) != len(inputs):
        raise ValueError("Input IDs and names must be distinct")
    if len({normalized(g["metric"]) for g in world["graphs"]}) != 8:
        raise ValueError("Metrics must be distinct")
    for labels in [v["values"] for v in world["inputs"]] + [g["outcomes"] for g in world["graphs"]]:
        if len({normalized(v) for v in labels}) != len(labels):
            raise ValueError("Labels must be distinct")
    uses = dict.fromkeys(inputs, 0)
    for graph in world["graphs"]:
        sizes = graph["inputs"]
        if any(inputs.get(k) != v for k, v in sizes.items()) or graph["root"] not in sizes:
            raise ValueError("Invalid graph input")
        for key in sizes:
            uses[key] += 1
        if len(graph["branches"]) != sizes[graph["root"]]:
            raise ValueError("Every first-criterion value needs a branch")
        direct, mediated, visited = set(), set(), set()
        for branch in graph["branches"]:
            if "outcome" in branch:
                direct.add(branch["outcome"])
            else:
                if branch["node"] >= len(graph["nodes"]):
                    raise ValueError("Invalid intermediate reference")
                visited.add(branch["node"])
                node = graph["nodes"][branch["node"]]
                if node["input"] not in sizes or node["input"] == graph["root"]:
                    raise ValueError("Intermediate must test the second criterion")
                if len(node["table"]) != sizes[node["input"]] or len(set(node["table"])) < 2:
                    raise ValueError("Second criterion must route every value and affect the result")
                mediated.update(node["table"])
        if visited != set(range(len(graph["nodes"]))):
            raise ValueError("Unreachable intermediate")
        if not direct or not mediated or direct & mediated:
            raise ValueError("Each graph needs separate depth-one and depth-two outcomes")
        if direct | mediated != set(range(len(graph["outcomes"]))):
            raise ValueError("Every outcome must be reachable")
    if min(uses.values()) < 2:
        raise ValueError("Inputs must overlap across graphs")


def sample(world, graph_index, rng):
    graph = world["graphs"][graph_index]
    assignment = {key: rng.randrange(size) for key, size in graph["inputs"].items()}
    conditions = {key: assignment[key] for key in required_inputs(graph, assignment)}
    gold = evaluate(graph, conditions)
    # Includes a graph's unused second criterion on a direct branch.
    inactive = [v for v in world["inputs"] if v["id"] not in conditions]
    distracting = {v["id"]: rng.randrange(len(v["values"])) for v in rng.sample(inactive, rng.randint(0, 1))}
    details = [dict(attribute=v["name"], value=v["values"][index])
               for key, index in (conditions | distracting).items()
               for v in world["inputs"] if v["id"] == key]
    options = [gold] + rng.sample([i for i in range(len(graph["outcomes"])) if i != gold], 3)
    rng.shuffle(options)
    return dict(graph=graph_index, conditions=conditions, distractors=distracting,
                decoration_count=rng.randint(1, 2), decorations=[], details=details,
                outcomes=options, correct_option=options.index(gold))


class Models:
    """One cached request per artifact; cache keys never enter model prompts."""

    def __init__(self, client, directory, concurrency):
        self.client, self.directory = client, directory
        self.semaphore = asyncio.Semaphore(concurrency)
        directory.mkdir(parents=True, exist_ok=True)

    async def call(self, key, prompt, schema, *, thinking=False):
        payload = dict(model=MODEL, messages=[
                           dict(role="system", content="Write natural, clear English. Return only JSON matching the response schema."),
                           dict(role="user", content=prompt)],
                       chat_template_kwargs=dict(enable_thinking=thinking),
                       max_tokens=MAX_OUTPUT_TOKENS,
                       response_format=dict(type="json_schema", json_schema=dict(
                           name="response", strict=True, schema=schema)))
        path = self.directory / f"{key}.json"
        if path.exists():
            cached = json.loads(path.read_text())
            if cached["request"] != payload:
                raise ValueError("Request changed; use a new output directory")
            validate(cached["result"], schema)
            return cached["result"]
        for attempt in range(4):
            try:
                async with self.semaphore:
                    response = await self.client.post(API_URL, json=payload)
                response.raise_for_status()
                choice = response.json()["choices"][0]
                if choice["finish_reason"] != "stop":
                    raise ValueError("Incomplete response")
                result = json.loads(choice["message"]["content"])
                validate(result, schema)
                atomic_json(path, dict(request=payload, result=result))
                return result
            except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError, ValidationError) as error:
                if isinstance(error, httpx.HTTPStatusError) and error.response.status_code < 500 and error.response.status_code not in (408, 429):
                    raise
                if attempt == 3:
                    raise
                await asyncio.sleep(2 ** attempt)


def build_world(blueprint, seed, setting):
    """Create conditional two-criterion graphs; labels never determine routing."""
    validate(blueprint, BLUEPRINT)
    rng = random.Random(seed)
    inputs = [dict(id=f"x{i}", **v) for i, v in enumerate(blueprint["inputs"])]
    order = rng.sample(range(len(inputs)), len(inputs))
    pairs = [tuple(sorted((a, b))) for a, b in zip(order, order[1:] + order[:1])]
    extras = [(a, b) for a in range(len(inputs)) for b in range(a + 1, len(inputs)) if (a, b) not in pairs]
    pairs += rng.sample(extras, 8 - len(pairs))
    rng.shuffle(pairs)
    graphs = []
    for metric, pair in zip(blueprint["metrics"], pairs):
        first, second = [inputs[j] for j in rng.sample(pair, 2)]
        a, b = first["id"], second["id"]
        na, nb, k = len(first["values"]), len(second["values"]), len(metric["outcomes"])
        direct_count = rng.choice([d for d in range(1, min(na, k - 1)) if (na - d) * nb >= k - d])
        direct_values = rng.sample(range(na), direct_count)
        labels = rng.sample(range(k), k)
        mediated = labels[direct_count:]
        slots = (na - direct_count) * nb
        values = (mediated * slots)[:slots]
        # Ensure every visited intermediate genuinely consults the second input.
        while True:
            rng.shuffle(values)
            if all(len(set(values[i:i + nb])) > 1 for i in range(0, slots, nb)):
                break
        branches, nodes = [], []
        for value in range(na):
            if value in direct_values:
                branches.append(dict(outcome=labels[direct_values.index(value)]))
            else:
                offset = len(nodes) * nb
                branches.append(dict(node=len(nodes)))
                nodes.append(dict(input=b, table=values[offset:offset + nb]))
        graphs.append(dict(metric=metric["name"], outcomes=metric["outcomes"],
                           inputs={a: na, b: nb}, root=a, branches=branches, nodes=nodes))
    world = dict(setting=setting, inputs=inputs, graphs=graphs)
    validate_world(world)
    return world


async def prepare_world(models, key, idea, seed):
    setting = idea["name"]
    blueprint = await models.call(f"{key}-world", WORLD_PROMPT + json.dumps(setting), BLUEPRINT, thinking=True)
    review = await models.call(f"{key}-world-check", WORLD_CHECK_PROMPT + json.dumps(
        dict(setting=setting, blueprint=blueprint)), CHECK, thinking=True)
    if not review["valid"]:
        blueprint = await models.call(f"{key}-world-revise", WORLD_REVISE_PROMPT + json.dumps(
            dict(setting=setting, blueprint=blueprint, feedback=review["reason"])), BLUEPRINT, thinking=True)
    return build_world(blueprint, f"{seed}:{key}", setting)


async def render(models, key, world, spec):
    graph = world["graphs"][spec["graph"]]
    rng = random.Random(f"style:{key}")
    spec = dict(spec, details=list(spec["details"]))
    count = spec["decoration_count"]
    decorations = await models.call(key + "-decorations", DECORATION_PROMPT + json.dumps(
        dict(setting=world["setting"], count=count)), obj(details=array(DETAIL, count, count)), thinking=True)
    spec["decorations"] = decorations["details"]
    spec["details"] += spec["decorations"]
    rng.shuffle(spec["details"])
    question_spec = dict(setting=world["setting"], metric=graph["metric"],
                         details=spec["details"], variation=variation(rng, QUESTION_VARIATIONS))
    outcomes = [graph["outcomes"][i] for i in spec["outcomes"]]
    answer_variation = variation(rng, ANSWER_VARIATIONS)

    async def write_answers():
        # Separate, sequential calls with no question, facts, gold flag or other answers.
        options = []
        for index, outcome in enumerate(outcomes):
            answer_spec = dict(system=world["setting"], metric=graph["metric"], outcome=outcome,
                               variation=answer_variation)
            result = await models.call(f"{key}-answer-{index}", ANSWER_PROMPT + json.dumps(answer_spec), ANSWER)
            options.append(result["answer"].strip())
        return options

    # Neither writer consumes the other's output. Verification waits for both.
    async with asyncio.TaskGroup() as writers:
        question_task = writers.create_task(models.call(
            key + "-question", QUESTION_PROMPT + json.dumps(question_spec), QUESTION, thinking=True))
        answers_task = writers.create_task(write_answers())
    question = question_task.result()["question"].strip()
    options = answers_task.result()
    variables = {v["id"]: v for v in world["inputs"]}
    plan = dict(environmental=[dict(attribute=variables[k]["name"], value=variables[k]["values"][v],
                                    inactive_second_criterion=k in graph["inputs"])
                               for k, v in spec["distractors"].items()],
                acausal=spec["decorations"])
    check = await models.call(key + "-check", CHECK_PROMPT + json.dumps(dict(
        specification=question_spec, distractor_plan=plan, question=question,
        answers=[dict(outcome=o, answer=a) for o, a in zip(outcomes, options)])), review_schema(len(question_spec["details"])))
    errors = []
    names = [normalized(d["attribute"]) for d in spec["decorations"]]
    if len(set(names)) != count or set(names) & {normalized(v["name"]) for v in world["inputs"]} or any(not 1 <= len(d["value"].split()) <= 3 for d in spec["decorations"]):
        errors.append("Decorations must be distinct, short acausal names, not input attributes")
    if not question or len(question.split()) > QUESTION_WORDS or any(c in question for c in "{}[]"):
        errors.append("Question length or formatting")
    if any(not a or len(a.split()) > ANSWER_WORDS for a in options) or len({normalized(a) for a in options}) != 4:
        errors.append("Answer length, empty text or duplicate options")
    evidence = check["question"]["evidence"]
    if len(evidence) != len(question_spec["details"]) or any(not quote.strip() or quote not in question for quote in evidence):
        errors.append("Missing or invented question evidence")
    passed = not errors and all(v["valid"] for v in [check["question"], check["distractors"], *check["answers"]])
    item = dict(question=question, options=options, correct_option=spec["correct_option"], sampling=spec,
                verification=dict(passed=passed, errors=errors, review=check))
    validate_item(world, item)
    return item


async def generate(args, models):
    ideas = json.loads((ROOT / "system_data/catalogue.json").read_text())
    ideas = [idea for idea in ideas if args.subject == "mixed" or idea["subject"] == args.subject]
    if len(ideas) < args.systems:
        raise ValueError("Not enough catalogue settings for requested systems")
    random.Random(args.seed).shuffle(ideas)
    config = dict(seed=args.seed, systems=args.systems, train=args.train, test=args.test,
                  subject=args.subject, model=MODEL, api_url=API_URL,
                  source=hashlib.sha256(b"".join(p.read_bytes() for p in (Path(__file__), ROOT / "local_api.py", ROOT / "system_data/catalogue.json"))).hexdigest())
    path = args.output_dir / "checkpoint.json"
    state = json.loads(path.read_text()) if path.exists() else dict(config=config, systems=[])
    if state["config"] != config:
        raise ValueError("Run configuration/source changed; use a new output directory")
    seen = {normalized(item["question"]) for row in state["systems"] for split in ("train", "test") for item in row[split]}
    for index, idea in enumerate(ideas[:args.systems]):
        if index == len(state["systems"]):
            world = await prepare_world(models, str(index), idea, args.seed)
            state["systems"].append(dict(world=world, train=[], test=[], attempts=dict(train=0, test=0)))
            atomic_json(path, state)
        row = state["systems"][index]
        counts = dict(train=args.train, test=args.test)
        # Reserve each outstanding quota slot; a rejection immediately frees it.
        # Persist reservations before requests so interrupted calls resume unchanged.
        pending = row.setdefault("pending", {})
        tasks = {}
        try:
            while any(len(row[s]) < n for s, n in counts.items()):
                occupied = {(s, g): sum(q["sampling"]["graph"] == g for q in row[s])
                            + sum(j["split"] == s and j["graph"] == g for j in pending.values())
                            for s in counts for g in range(8)}
                while len(pending) < args.concurrency:
                    available = [(s, g) for s, n in counts.items() for g in range(8)
                                 if occupied[s, g] < n // 8 + (g < n % 8)
                                 and row["attempts"][s] < n * 10]
                    if not available:
                        break
                    split, graph = min(available, key=lambda pair: occupied[pair])
                    attempt = row["attempts"][split]
                    key = f"{index}-{split}-{attempt}"
                    pending[key] = dict(split=split, graph=graph, attempt=attempt)
                    row["attempts"][split] += 1
                    occupied[split, graph] += 1
                atomic_json(path, state)
                for key, job in pending.items():
                    if key not in tasks and len(tasks) < args.concurrency:
                        spec = sample(row["world"], job["graph"], random.Random(
                            f"{args.seed}:{index}:{job['split']}:{job['attempt']}"))
                        tasks[key] = asyncio.create_task(render(models, key, row["world"], spec))
                if not tasks:
                    raise ValueError(f"System {index}: candidate budget exhausted")
                done, _ = await asyncio.wait(tasks.values(), return_when=asyncio.FIRST_COMPLETED)
                for key in [key for key, task in tasks.items() if task in done]:
                    item = tasks[key].result()
                    split = pending[key]["split"]
                    text = normalized(item["question"])
                    if item["verification"]["passed"] and text not in seen:
                        seen.add(text)
                        row[split].append(item)
                    del pending[key], tasks[key]
                    atomic_json(path, state)
                print(f"System {index+1}: train {len(row['train'])}/{args.train}, "
                      f"test {len(row['test'])}/{args.test}; {len(pending)} in flight", flush=True)
        finally:
            for task in tasks.values():
                task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)
    return state


def validate_item(world, item):
    spec = item["sampling"]
    if spec["graph"] not in range(8):
        raise ValueError("Invalid target graph")
    graph = world["graphs"][spec["graph"]]
    conditions, distractors = spec["conditions"], spec["distractors"]
    if set(conditions) != set(required_inputs(graph, conditions)):
        raise ValueError("Invalid causal conditions")
    if len(distractors) not in (0, 1) or set(distractors) & set(conditions):
        raise ValueError("Distractor affects the active path")
    if spec["decoration_count"] not in (1, 2):
        raise ValueError("Need one or two acausal distractors")
    validate(spec["decorations"], array(DETAIL, spec["decoration_count"], spec["decoration_count"]))
    variables = {v["id"]: v for v in world["inputs"]}
    for key, value in (conditions | distractors).items():
        if key not in variables or value not in range(len(variables[key]["values"])):
            raise ValueError("Invalid input value")
    expected = [dict(attribute=variables[k]["name"], value=variables[k]["values"][v])
                for k, v in (conditions | distractors).items()] + spec["decorations"]
    if sorted(map(json.dumps, expected)) != sorted(map(json.dumps, spec["details"])):
        raise ValueError("Rendered details differ from sampled conditions")
    outcomes = spec["outcomes"]
    if len(outcomes) != 4 or len(set(outcomes)) != 4 or any(i not in range(len(graph["outcomes"])) for i in outcomes):
        raise ValueError("Options must be distinct reachable outcomes")
    correct = item["correct_option"]
    if correct not in range(4) or correct != spec["correct_option"]:
        raise ValueError("Invalid correct option")
    try:
        gold = evaluate(graph, conditions)
    except KeyError as error:
        raise ValueError("Missing required condition") from error
    if outcomes[correct] != gold:
        raise ValueError("Answer disagrees with graph")
    for key in distractors:
        if any(evaluate(graph, conditions | {key: value}) != gold for value in range(len(variables[key]["values"]))):
            raise ValueError("Environmental distractor changes the outcome")
    if len(item["options"]) != 4:
        raise ValueError("Need four answers")


def export(state, directory):
    rows = []
    for system in state["systems"]:
        validate_world(system["world"])
        row = dict(Setting=system["world"]["setting"], World=json.dumps(system["world"], ensure_ascii=False))
        for split in ("train", "test"):
            if len(system[split]) != state["config"][split]:
                raise ValueError("Incomplete dataset")
            for item in system[split]:
                validate_item(system["world"], item)
            row["num_" + split] = len(system[split])
            row[split + "_data"] = [{k: item[k] for k in ("question", "options", "correct_option", "verification")} for item in system[split]]
        rows.append(row)
    if len(rows) != state["config"]["systems"]:
        raise ValueError("Incomplete dataset")
    (directory / "systems_bench.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    return rows


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--subject", default="mixed")
    for name, default in dict(systems=1, train=16, test=8, seed=42, concurrency=16).items():
        parser.add_argument("--" + name, type=int, default=default)
    parser.add_argument("--upload", metavar="DATASET", help="Optional Hugging Face destination")
    args = parser.parse_args(argv)
    if min(args.systems, args.train, args.test, args.concurrency) < 1:
        parser.error("Counts and concurrency must be positive")
    return args


async def run(args):
    args.output_dir.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("INFERENCE_API_KEY")
    headers = {"Authorization": "Bearer " + token} if token else {}
    async with AuditedClient(args.output_dir / "api_audit", headers=headers, timeout=1800,
                             limits=httpx.Limits(max_connections=args.concurrency,
                                                 max_keepalive_connections=args.concurrency)) as client:
        state = await generate(args, Models(client, args.output_dir / "calls", args.concurrency))
    rows = export(state, args.output_dir)
    if args.upload:
        from datasets import Dataset
        result = Dataset.from_list(rows).push_to_hub(args.upload)
        atomic_json(args.output_dir / "upload.json", dict(repository=args.upload, commit=str(result)))


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
