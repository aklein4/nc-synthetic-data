"""Five educational worlds: four answerers and one asker; see docs/systems-bench.md."""

import argparse
import asyncio
import hashlib
import json
import os
import random
import re
import unicodedata
from collections import Counter
from pathlib import Path

import datasets
import httpx
from jsonschema import validate as validate_json
from jsonschema.exceptions import ValidationError as SchemaValidationError
from local_api import AuditedClient

MODEL = os.environ.get("MODEL", "mimo-v2.6-flash")
API_URL = os.environ.get("API_URL", "http://mimo:8000/v1/chat/completions")
DEFAULT_OUTPUT = Path("/mnt/shared/nc-synthetic-data/runs/otter-256-100")
CATALOGUE_PATH = Path(__file__).with_name("system_data") / "catalogue.json"
VERSION = 56


# Configuration: model routing, sampling, limits, defaults and prompts.
WORLD_COUNT = 5
OPTION_COUNT = WORLD_COUNT - 1
MIN_POSSIBLE_OPTIONS = 2
OPTION_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[:OPTION_COUNT]
CATALOGUE_SIZE = 96
MIN_DECIDING_FACTORS = 1
MAX_DECIDING_FACTORS = 2
MAX_OUTPUT_TOKENS = 131072
MAX_ANSWER_WORDS = 24
NO_THINKING_OUTPUT_TOKENS = 512
LONG_OUTPUT_TOKENS = 131072
REQUEST_ATTEMPTS = 8
RETRY_BACKOFF = 2
RETRY_MAX_SECONDS = 30
RETRY_JITTER = (0.5, 1.0)
WORLD_ATTEMPTS = 12
RULE_MIN_WORDS = 80
RULE_MAX_WORDS = 120
MAX_CONCURRENCY = 512
REQUEST_TIMEOUT = 1800
RULE_CANDIDATE_MULTIPLIER = 10
ROW_CANDIDATE_MULTIPLIER = 20
MAX_RETIRED_RULES = 4
MAX_REPLACEMENT_DONORS = 4
DEFAULT_COUNTS = {
    "systems": 64,
    "rules": 16,
    "train": 256,
    "test": 100,
    "seed": 42,
    "question-batches": 16,
}
DEFAULT_SUBJECT = "mixed"
UPLOAD_REPO = "aklein4/AlwaysLearningBench-v1"
UPLOAD_CONFIG = "default"
UPLOAD_SPLIT = "train"
THINKING = {
    "setting": True,
    "plan": True,
    "world": True,
    "consistency": True,
    "collisions": True,
    "questions": True,
    "answers": False,
    "verification": False,
    "deduplication": False,
    "language": False,
}
CHECKPOINT_FILE = "checkpoint.json"
JSONL_FILE = "systems_bench.jsonl"
DATASET_DIR = "dataset"
REVIEW_FILE = "review.md"
CALLS_DIR = "calls"
AUDIT_DIR = "api_audit"
API_KEY_ENV = "INFERENCE_API_KEY"
APP_TITLE = "SystemsBench generation"
REPO_ROOT = Path(__file__).resolve().parent
TEXT_DEBRIS = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]|"
    r"\b(?:json|prompts?|counterfactual|fictional|gold|answer (?:choices?|options?))\b",
    re.IGNORECASE,
)

SYSTEM_PROMPT = (
    "Write natural high-school English, without arithmetic or symbolic processes. "
    "Return only a JSON instance matching the response schema, not the schema itself."
)

LANGUAGE_PROMPT = (
    "Check natural high-school English. Reject every calculation; arithmetic_ok "
    "requires no arithmetic in the question or answers. "
)

PLAN_PROMPT = (
    "Plan {world_count} equally plausible versions of this science-class system, "
    "one rule intent per request. Define what happens, not how to observe or record "
    "it. Each rule covers several related cases; two-factor rules combine both factors. "
    "Resolve exceptions and precedence where rules overlap. Give definite outcomes, "
    "not lists of things that may happen, using only the "
    "observable factors named in each request. Each focused prediction must be "
    "decidable from one or two stated observations, including "
    "exceptions and rule interactions. Shared details "
    "are welcome: vary meaningful aspects that enable distinct predictions, "
    "not every clause or condition. For each request, include an ordinary case "
    "with {world_count} mutually incompatible predictions. Other cases may agree. "
    "For corresponding rules, reuse the same concrete outcomes across versions; "
    "change which conditions lead to each. An outcome alone must not identify its version. No "
    "version is designated correct.\n"
)

COLLISION_PROMPT = """Compare these {world_count} worlds. Read all rules and exceptions.

For each rule, write one simple question about an observable outcome:
- Use the same situation and factor values in every world, without calculations.
- Each world must give a different answer. Different wording is not enough:
  no two answers should describe outcomes that could both happen in that situation.
- Do not mention world names or answer labels in the question.

Return one rule_examples entry per rule, in rule order:
- If you find a question: distinguishable=true, the question, and {world_count}
  short answers in world order. Explain briefly in reason.
- If you cannot: distinguishable=false, an empty question, {world_count} empty
  answer strings, and a reason naming the worlds you could not distinguish.

Also check:
- distinct: A successful example for every rule is NECESSARY, but NOT SUFFICIENT.
  Also assess the worlds as complete systems: do their rules genuinely make
  different predictions, using the same deciding factors for matching rules?
  Check that interactions and exceptions do not erase the claimed differences,
  and that differences are not just wording or compatible descriptions.
  Set distinct=false if this overall assessment fails, even when every rule's
  distinguishable flag is true. Explain the overall decision in reason.
- shared_support: Matching rules reuse outcomes under different conditions,
  so an outcome alone does not identify its world.
- neutral_setting: The shared background does not reveal causal mechanisms.

Worlds may share details and give the same answers in other situations.
Summarize problems in reason. Example questions are saved for inspection only.
"""


QUESTION_LANGUAGE_PROMPT = (
    "The question should concern the subject directly and ask for one outcome in "
    "one situation, with one or two relevant details and at most one incidental "
    "detail. Answers should be short phrases or simple sentences of comparable "
    "style and specificity. Reject explanations, repeated setup, invented stand-ins, "
    "and references to rules, fiction, prompts, or answer labels. "
)

REVISION_PROMPT = (
    "\nRevise the plan to address this review. Preserve the listed fixed_worlds "
    "verbatim; their text and checks will be reused.\n"
)

WORLD_PROMPT = (
    "Write this one educational system from its plan. Return one natural paragraph "
    "per request, in order, about {min_words}–{max_words} words each. Preserve its "
    "predictions and any interactions or exceptions. Resolve priorities "
    "where related rules overlap. Use only the named observable factors and definite "
    "predictions in flowing prose, not a table. State what happens without hedging "
    "or instructions to observers. Each focused prediction must need only one or "
    "two stated details. Do not introduce further deciding factors.\n"
)

CONSISTENCY_PROMPT = (
    "Check for internal contradictions: do the same observations require incompatible "
    "outcomes, or leave conflicting rules without a priority? Different observable "
    "responses can occur together; compatible general and specific statements are "
    "consistent. Do not require coverage of every imaginable "
    "case; unanswerable questions are filtered separately. Set sufficient_complexity=true "
    "only when each rule gives several related, definite predictions across conditions, "
    "combining factors where present, not a single condition-response pair. "
    "Assess complete rule entries, not background or individual sentences. "
    "Ignore disagreement with real-world facts.\n"
)

ANSWER_PROMPT = (
    "Using only the description, give the requested outcome as a short phrase or "
    "simple sentence, at most {max_words} words. No explanations, repeated conditions, "
    "or references to sources. If undetermined, set answerable=false and answer empty.\n"
)

QUESTION_PROMPT = (
    "Write one short science question per request, in the requested order. Describe "
    "the subject directly in one situation with one or two deciding observations "
    "and at most one incidental detail. Use the supplied rules to choose an "
    "answerable case. Ask for one outcome that fits a short phrase or simple sentence. "
    "Assume the shared setting is known. Use qualitative details. No comparisons, "
    "explanations, invented stand-ins, revealed outcomes, or references to rules, "
    "fiction, or answer choices.\n"
)

VERIFY_PROMPT = (
    "Using only this description and question, judge EACH answer A-D true or false "
    "independently. Mark true when its requested prediction agrees with the description, "
    "including compatible paraphrases. Mark false for a conflicting prediction or a "
    "missing essential requested outcome. Do not reject an otherwise correct prediction "
    "merely for extra compatible detail. Multiple answers may be true; never force "
    "uniqueness. Return all false if the question is insufficient or contradictory "
    "or its result is undetermined. Return only the A-D boolean labels, without "
    "explanations.\n"
)

POSSIBLE_PROMPT = (
    "Using only this description, judge each option A-D independently. Mark true "
    "if its outcome can occur under at least one condition supported by the "
    "description; otherwise false. No question is supplied: do not assume a "
    "particular situation. Return only A-D boolean labels.\n"
)

DEDUPLICATION_PROMPT = (
    "Compare the meanings of the four answers A-D in the context of the question. "
    "For EACH answer, mark true only if its requested prediction is meaningfully "
    "different from EVERY other answer. Paraphrases and answers that differ only "
    "in wording or nonessential extra detail are duplicates. Mark EVERY member "
    "of a duplicate group false, not just the later occurrences. Distinct answers "
    "may share some details; they must differ in an essential requested outcome. "
    "Judge uniqueness, not correctness, plausibility, or which answer is best. "
    "Return exactly the four A-D boolean labels, without explanations.\n"
)

SETTING_PROMPT = (
    "Create a neutral science-class setting from {idea}. Return descriptive shared "
    "background and {count} related rule requests. Use a "
    "narrow real-world physical system; "
    "animal examples concern the same species. Each request names a general "
    "predictive aspect and one or two deciding observable factors, without assigning "
    "effects or fixing a particular scenario. "
    "Include both one-factor and two-factor requests. "
    "Cover different but closely related behavioral aspects, rather than repeating "
    "the same prediction in different situations. Each aspect concerns a different "
    "observable response, not a subset of another request's response. Request predictions, not observation "
    "instructions. Support multiple related cases, combining factors where present. Keep "
    "responses overlapping. Shared background describes only the environment, "
    "without mechanisms, default factor values or predicted responses. "
    "Explicitly name the focal subject in the shared background, including the "
    "species for animal systems. "
    "Use qualitative descriptions throughout, not numeric measurements. "
    "The shared text describes the setting, without instructions to observers."
)

QUESTION_VARIATIONS = {
    "framing": (
        "State the conditions, then ask a direct question.",
        "Use a teacher's plain, conversational wording.",
        "Use a student's concise everyday wording.",
        "Describe a brief field observation.",
        "Use the concise style of a science assessment.",
        "Lead with the subject's immediate surroundings.",
        "Start with a brief description of the current situation.",
        "Begin with the question, then describe the setup.",
    ),
    "focus": (
        "Ask what would be observed next.",
        "Ask what happens after a condition changes, giving only the new situation.",
        "Focus on the subject at one moment.",
        "Ask about one aspect of the observable response.",
        "Explore an unusual but physically plausible combination of conditions.",
        "Include a small incidental detail that does not suggest an effect.",
        "Ask for the immediate outcome of an ongoing process.",
        "Describe familiar conditions in a fresh concrete setting.",
    ),
}
ANSWER_VARIATIONS = {
    "form": (
        "Use one concise sentence.",
        "Give a brief standalone prediction.",
        "Use a short phrase when it fully answers the question.",
        "Start with the action or result.",
        "Lead with the main observable response.",
        "Keep the answer short without omitting necessary qualifications.",
        "Keep only details needed to identify the outcome.",
        "State the result directly, without a preamble.",
    ),
    "wording": (
        "Use concrete action or change words.",
        "Match the question's level of detail.",
        "Name the relevant direction, location or behavior plainly.",
        "Use plain everyday English.",
        "Describe observable outcomes without adding unasked causes.",
        "Prefer simple verbs to elaborate phrasing.",
        "Use the voice of a careful observer.",
        "Use language suitable for a student recording a result.",
    ),
}


def obj(**properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def arr(items, count):
    return {"type": "array", "items": items, "minItems": count, "maxItems": count}


def request_schema(count):
    # Require both factor counts without `contains`, which the serving grammar
    # backends do not support. Every valid list has a first position where its
    # factor count changes; enumerating that position preserves the exact rule.
    base = arr(RULE_REQUEST, count)
    return {
        **base,
        "anyOf": [
            {
                **base,
                "prefixItems": [obj(aspect=STRING, factors=arr(STRING, first))] * change
                + [obj(aspect=STRING, factors=arr(STRING, 3 - first))],
            }
            for first in (1, 2)
            for change in range(1, count)
        ],
    }


STRING, BOOL = {"type": "string"}, {"type": "boolean"}
RULE_REQUEST = obj(
    aspect=STRING,
    factors={
        "type": "array",
        "items": STRING,
        "minItems": MIN_DECIDING_FACTORS,
        "maxItems": MAX_DECIDING_FACTORS,
    },
)
CONSISTENCY = obj(consistent=BOOL, sufficient_complexity=BOOL, reason=STRING)
COLLISIONS = obj(
    distinct=BOOL, shared_support=BOOL, neutral_setting=BOOL, reason=STRING
)
def collision_schema(count):
    return obj(
        **COLLISIONS["properties"],
        rule_examples=arr(obj(
            distinguishable=BOOL, question=STRING,
            answers=arr(STRING, WORLD_COUNT), reason=STRING,
        ), count),
    )


def collisions_passed(check, count):
    try:
        validate_json(check, collision_schema(count))
    except SchemaValidationError:
        return False
    return passed(check, COLLISIONS) and all(
        example["distinguishable"] is True
        and bool(example["question"].strip())
        and all(answer.strip() for answer in example["answers"])
        and len({question_key(answer) for answer in example["answers"]}) == WORLD_COUNT
        for example in check["rule_examples"]
    )


LANGUAGE = obj(english=BOOL, arithmetic_ok=BOOL, natural=BOOL, no_meta_cues=BOOL)
TRUTH = obj(**{c: BOOL for c in OPTION_LABELS})
UNIQUENESS = obj(**{c: BOOL for c in OPTION_LABELS})
ANSWER = obj(answer=STRING, answerable=BOOL)


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def question_key(text):
    return " ".join(unicodedata.normalize("NFKC", text).split())


def clean_text(text):
    return bool(text.strip()) and not TEXT_DEBRIS.search(text)


def passed(check, schema):
    return all(
        check.get(k) is True for k, v in schema["properties"].items() if v == BOOL
    )


async def settled(*calls):
    results = await asyncio.gather(*calls, return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException):
            raise result
    return results


def catalogue():
    ideas = json.loads(CATALOGUE_PATH.read_text())
    if (
        len(ideas) != CATALOGUE_SIZE
        or len({x["name"] for x in ideas}) != CATALOGUE_SIZE
    ):
        raise ValueError(f"Expected {CATALOGUE_SIZE} distinct system ideas")
    return ideas


class SettingExhausted(RuntimeError):
    """This catalogue setting exhausted a generation/revision limit."""


class CatalogueExhausted(RuntimeError):
    """No unused setting remains to replace an exhausted row."""


class Models:
    """Cached, audited calls. A cache location never enters the model payload."""

    def __init__(self, client, directory, concurrency=MAX_CONCURRENCY):
        self.client = client
        self.directory = directory
        self.semaphore = asyncio.Semaphore(concurrency)

    async def call(
        self, key, model, task, schema, *, thinking, max_tokens=MAX_OUTPUT_TOKENS
    ):
        if not isinstance(thinking, bool):
            raise TypeError("thinking must be a boolean")
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                    + "\nResponse schema:\n"
                    + json.dumps(schema),
                },
                {"role": "user", "content": task},
            ],
            "chat_template_kwargs": {"enable_thinking": thinking},
            "temperature": 1.0,
            "top_p": 0.95,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "benchmark_response", "strict": True, "schema": schema},
            },
            "max_tokens": NO_THINKING_OUTPUT_TOKENS if not thinking else max_tokens,
        }
        path = self.directory / f"{key}.json"
        if path.exists():
            cached = json.loads(path.read_text())
            if cached["request"] != payload:
                raise ValueError(
                    f"Changed request at {path}; use a new output directory"
                )
            try:
                validate_json(cached["result"], schema)
            except SchemaValidationError:
                path.rename(path.with_suffix(".invalid.json"))
            else:
                return cached["result"]
        for attempt in range(REQUEST_ATTEMPTS):
            try:
                async with self.semaphore:
                    response = await self.client.post(API_URL, json=payload)
                response.raise_for_status()
                body = response.json()
                choice = body["choices"][0]
                if choice.get("finish_reason") != "stop":
                    raise ValueError("Incomplete model response")
                result = json.loads(choice["message"]["content"])
                validate_json(result, schema)
                atomic_json(path, {"request": payload, "result": result})
                print(f"{key}: {model}", flush=True)
                return result
            except (
                httpx.HTTPError,
                KeyError,
                IndexError,
                TypeError,
                ValueError,
                SchemaValidationError,
            ) as error:
                print(f"{key}: attempt {attempt + 1} failed: {type(error).__name__}: {error}", flush=True)
                if isinstance(error, httpx.HTTPStatusError) and 400 <= error.response.status_code < 500 and error.response.status_code not in {408, 409, 425, 429}:
                    raise  # Invalid schema/authentication requests will not improve on retry.
                if attempt == REQUEST_ATTEMPTS - 1:
                    raise SettingExhausted(f"{key}: {REQUEST_ATTEMPTS} request attempts exhausted") from error
                await asyncio.sleep(
                    min(RETRY_MAX_SECONDS, RETRY_BACKOFF**attempt)
                    * random.uniform(*RETRY_JITTER)
                )
        raise AssertionError("unreachable")


def world_text(shared, rules):
    return shared + "\n\n" + "\n\n".join(rules)


async def language_check(models, key, text):
    return await models.call(
        key,
        MODEL,
        LANGUAGE_PROMPT + QUESTION_LANGUAGE_PROMPT + "\n" + text,
        LANGUAGE,
        thinking=THINKING["language"],
    )


async def prepare_system(models, key, idea, count, seed):
    design = await models.call(
        key + "/setting",
        MODEL,
        SETTING_PROMPT.format(idea=json.dumps(idea), count=count),
        obj(shared=STRING, requests=request_schema(count)),
        thinking=THINKING["setting"],
    )
    feedback = None
    for trial in range(WORLD_ATTEMPTS):
        trial_key = f"{key}/worlds-{trial}"
        plan = await models.call(
            trial_key + "/plan",
            MODEL,
            PLAN_PROMPT.format(world_count=WORLD_COUNT)
            + json.dumps(design)
            + (REVISION_PROMPT + json.dumps(feedback) if feedback else ""),
            obj(worlds=arr(arr(STRING, count), WORLD_COUNT)),
            thinking=THINKING["plan"],
            max_tokens=LONG_OUTPUT_TOKENS,
        )
        fixed = feedback["fixed_worlds"] if feedback else []
        active = [i for i in range(WORLD_COUNT) if i not in fixed]
        worlds = list(feedback["worlds"]) if feedback else [None] * WORLD_COUNT
        checks = list(feedback["consistency"]) if feedback else [None] * WORLD_COUNT
        for i in fixed:
            plan["worlds"][i] = feedback["plan"]["worlds"][i]
        written = await settled(
            *(
                models.call(
                    f"{trial_key}/write-{i}",
                    MODEL,
                    WORLD_PROMPT.format(
                        min_words=RULE_MIN_WORDS, max_words=RULE_MAX_WORDS
                    )
                    + json.dumps({**design, "plan": plan["worlds"][i]}),
                    obj(rules=arr(STRING, count)),
                    thinking=THINKING["world"],
                    max_tokens=LONG_OUTPUT_TOKENS,
                )
                for i in active
            )
        )
        for i, result in zip(active, written):
            worlds[i] = result["rules"]
        results = await settled(
            *(
                models.call(
                    f"{trial_key}/consistent-{i}",
                    MODEL,
                    CONSISTENCY_PROMPT
                    + json.dumps({"shared": design["shared"], "rules": worlds[i]}),
                    CONSISTENCY,
                    thinking=THINKING["consistency"],
                )
                for i in active
            ),
            models.call(
                trial_key + "/collisions",
                MODEL,
                COLLISION_PROMPT.format(world_count=WORLD_COUNT)
                + json.dumps({**design, "worlds": worlds}),
                collision_schema(count),
                thinking=THINKING["collisions"],
            ),
        )
        for i, result in zip(active, results[:-1]):
            checks[i] = result
        collision = results[-1]
        if all(passed(c, CONSISTENCY) for c in checks) and collisions_passed(collision, count):
            gold, question_world = random.Random(f"roles:{seed}").sample(
                range(WORLD_COUNT), 2
            )
            return dict(
                **design,
                plan=plan,
                worlds=worlds,
                consistency=checks,
                collisions=collision,
                gold=gold,
                question_world=question_world,
                items=[],
                rule_results=[
                    {"generated": 0, "checked": 0, "passed": 0, "rejected_rounds": []}
                    for _ in range(count)
                ],
                retired=[],
                substitutions=[],
                drafts=[],
                round=0,
                rejections={},
            )
        feedback = {
            "plan": plan,
            "worlds": worlds,
            "consistency": checks,
            "collisions": {
                **{k: v for k, v in collision.items() if k != "rule_examples"},
                "rule_checks": [
                    {"rule": i + 1, "distinguishable": example["distinguishable"],
                     "reason": example["reason"]}
                    for i, example in enumerate(collision["rule_examples"])
                ],
            },
            "fixed_worlds": [i for i, c in enumerate(checks) if passed(c, CONSISTENCY)]
            if collisions_passed(collision, count)
            else [],
        }
    raise SettingExhausted("World iteration limit exhausted; all attempts are preserved")


def variation(rng, banks):
    instructions = [rng.choice(bank) for bank in banks.values()]
    rng.shuffle(instructions)
    return "\n".join(instructions)


async def question_batch(models, key, system, targets, seed):
    rng = random.Random(seed)
    order = list(targets)
    rng.shuffle(order)
    rules = system["worlds"][system["question_world"]]
    response = await models.call(
        key,
        MODEL,
        QUESTION_PROMPT
        + "\nSystem description:\n"
        + system["shared"]
        + "\n"
        + json.dumps([{"rule": i + 1, "text": r} for i, r in enumerate(rules)])
        + "\nRequests:\n"
        + json.dumps([{"rule": i + 1, **system["requests"][i]} for i in order])
        + "\nStyle:\n"
        + variation(rng, QUESTION_VARIATIONS),
        obj(questions=arr(STRING, len(order))),
        thinking=THINKING["questions"],
    )
    return [{"question": q, "target": i} for q, i in zip(response["questions"], order)]


async def answer(models, key, description, question, style):
    return await models.call(
        key,
        MODEL,
        ANSWER_PROMPT.format(max_words=MAX_ANSWER_WORDS)
        + "\nDescription:\n"
        + description
        + "\nStyle:\n"
        + style
        + "\nQuestion:\n"
        + question,
        ANSWER,
        thinking=THINKING["answers"],
    )


def truth_indices(check):
    return [i for i, letter in enumerate(OPTION_LABELS) if check[letter]]


async def deduplicate_answers(models, key, question, options):
    shown = "\n".join(f"{c}. {o}" for c, o in zip(OPTION_LABELS, options))
    return await models.call(
        key,
        MODEL,
        DEDUPLICATION_PROMPT + "\nQuestion:\n" + question + "\nAnswers:\n" + shown,
        UNIQUENESS,
        thinking=THINKING["deduplication"],
    )


async def evaluate_question(models, key, system, draft, seed):
    question = draft["question"]
    if not clean_text(question):
        return None, "text_format"
    rng = random.Random(seed)
    style = variation(rng, ANSWER_VARIATIONS)
    worlds = [i for i in range(WORLD_COUNT) if i != system["question_world"]]
    descriptions = {
        i: world_text(system["shared"], rules)
        for i, rules in enumerate(system["worlds"])
    }
    responses = await settled(
        *(
            answer(models, f"{key}/answer-{i}", text, question, style)
            for i, text in descriptions.items()
        )
    )
    if not all(
        responses[i]["answerable"] and responses[i]["answer"].strip() for i in worlds
    ):
        return None, "unanswerable"
    answers = {str(i): responses[i] for i in worlds}
    order = list(worlds)
    rng.shuffle(order)
    options = [answers[str(i)]["answer"] for i in order]
    if not all(clean_text(o) for o in options):
        return None, "text_format"
    if any(len(o.split()) > MAX_ANSWER_WORDS for o in options):
        return None, "answer_length"
    if len({question_key(o) for o in options}) != OPTION_COUNT:
        return None, "identical_answers"
    shown = "\n".join(f"{c}. {o}" for c, o in zip(OPTION_LABELS, options))
    gold = system["gold"]
    gold_check, possible_check, language, uniqueness = await settled(
        models.call(
            f"{key}/verify-{gold}",
            MODEL,
            VERIFY_PROMPT
            + descriptions[gold]
            + "\nQuestion:\n"
            + question
            + "\n"
            + shown,
            TRUTH,
            thinking=THINKING["verification"],
        ),
        models.call(
            f"{key}/possible-{gold}",
            MODEL,
            POSSIBLE_PROMPT + descriptions[gold] + "\nOptions:\n" + shown,
            TRUTH,
            thinking=THINKING["verification"],
        ),
        language_check(models, key + "/language", question + "\n" + shown),
        deduplicate_answers(models, key + "/deduplication", question, options),
    )
    if not passed(uniqueness, UNIQUENESS):
        return None, "duplicate_answers"
    if truth_indices(gold_check) != [order.index(gold)]:
        return None, "answer_validation"
    if len(truth_indices(possible_check)) < MIN_POSSIBLE_OPTIONS or order.index(
        gold
    ) not in truth_indices(possible_check):
        return None, "answer_only"
    if not passed(language, LANGUAGE):
        return None, "language"
    return dict(
        **draft,
        options=options,
        option_worlds=order,
        gold_check=gold_check,
        possible_check=possible_check,
        uniqueness=uniqueness,
        language=language,
        answers=answers,
        question_world_answer=responses[system["question_world"]],
        answer_style=style,
    ), None


def manifest(args):
    return dict(
        version=VERSION,
        model=MODEL,
        api_url=API_URL,
        transport_sha256=hashlib.sha256(Path(__file__).with_name("local_api.py").read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        catalogue_sha256=hashlib.sha256(CATALOGUE_PATH.read_bytes()).hexdigest(),
        **{
            k: getattr(args, k)
            for k in (
                "systems",
                "rules",
                "train",
                "test",
                "seed",
                "subject",
                "question_batches",
                "row_concurrency",
            )
        },
    )


def retire_rules(system):
    """Reassign unfilled quotas, preserving accepted questions and fixed worlds."""
    remaining_retirements = MAX_RETIRED_RULES - len(system["retired"])
    if remaining_retirements <= 0:
        return
    stats = system["rule_results"]
    active = [i for i in range(len(stats)) if i not in system["retired"]]
    rates = {i: stats[i]["passed"] / max(1, stats[i]["checked"]) for i in active}
    counts = Counter(q["target"] for q in system["items"])
    bad = [
        i for i in active
        if counts[i] < system["quota"][i]
        and stats[i]["generated"] >= RULE_CANDIDATE_MULTIPLIER * system["quota"][i]
    ]
    if bad and len(bad) == len(active):
        bad.remove(max(active, key=lambda i: rates[i]))
    bad = bad[:remaining_retirements]
    donors = sorted((i for i in active if i not in bad), key=lambda i: (-rates[i], i))[
        :MAX_REPLACEMENT_DONORS
    ]
    counts = Counter(q["target"] for q in system["items"])
    for target in bad:
        remaining = system["quota"][target] - counts[target]
        system["quota"][target] = counts[target]
        for _ in range(remaining):
            replacement = min(
                donors, key=lambda i: (system["quota"][i] - counts[i], -rates[i], i)
            )
            system["quota"][replacement] += 1
            system["substitutions"].append(
                {"round": system["round"], "old": target, "new": replacement}
            )
    system["retired"].extend(bad)


def question_targets(system, batch_limit, candidate_budget=None):
    """Request at most one candidate per remaining slot and batch per rule."""
    counts = Counter(q["target"] for q in system["items"])
    remaining = [max(0, quota - counts[i]) for i, quota in enumerate(system["quota"])]
    targets = []
    for batch in range(min(batch_limit, max(remaining, default=0))):
        active = [i for i, count in enumerate(remaining) if batch < count]
        if candidate_budget is not None:
            active = active[:candidate_budget]
            candidate_budget -= len(active)
        if active:
            targets.append(active)
    return targets


def completed_count(state, total):
    return sum(s is not None and len(s["items"]) == total for s in state["systems"])


async def generate(args, models):
    path = args.output_dir / CHECKPOINT_FILE
    config = manifest(args)
    state = (
        json.loads(path.read_text())
        if path.exists()
        else {"config": config, "systems": []}
    )
    if state["config"] != config:
        raise ValueError("Source/configuration changed; use a new output directory")
    ideas = [
        i
        for i in catalogue()
        if args.subject == DEFAULT_SUBJECT or i["subject"] == args.subject
    ]
    if len(ideas) < args.systems:
        raise ValueError("Not enough distinct catalogue settings for the requested rows")
    state.setdefault("assignments", list(range(args.systems)))
    state.setdefault("next_setting", args.systems)
    state.setdefault("replacement_counts", [0] * args.systems)
    state.setdefault("discarded", [])
    previous = [*state["systems"], *(d["system"] for d in state["discarded"])]
    seen = {question_key(d["question"]) for s in previous if s for d in s["drafts"]}
    state["systems"].extend([None] * (args.systems - len(state["systems"])))
    total = args.train + args.test
    completed = sum(s is not None and len(s["items"]) == total for s in state["systems"])
    print(f"Progress: {completed}/{args.systems} rows complete", flush=True)

    async def generate_row(index):
        setting_index = state["assignments"][index]
        key = f"system-{index:03d}"
        if state["replacement_counts"][index]:
            key += f"/setting-{setting_index:03d}"
        if state["systems"][index] is None:
            system = await prepare_system(
                models, key, ideas[setting_index], args.rules, args.seed + setting_index
            )
            system["catalogue_index"] = setting_index
            system["catalogue_name"] = ideas[setting_index]["name"]
            system["quota"] = [
                sum(j % args.rules == i for j in range(total))
                for i in range(args.rules)
            ]
            state["systems"][index] = system
            atomic_json(path, state)
        system = state["systems"][index]
        while len(system["items"]) < total:
            round_key = f"{key}/round-{system['round']:04d}"
            seed = f"{args.seed}:{index}:{system['round']}"
            if "pending" not in system:
                generated = sum(r["generated"] for r in system["rule_results"])
                budget = ROW_CANDIDATE_MULTIPLIER * total - generated
                if budget <= 0:
                    raise SettingExhausted(
                        f"Question candidate limit exhausted: {generated}/{ROW_CANDIDATE_MULTIPLIER * total} generated"
                    )
                retire_rules(system)
                targets = question_targets(system, args.question_batches, budget)
                batches = await settled(
                    *(
                        question_batch(
                            models,
                            f"{round_key}/questions-{b}",
                            system,
                            active,
                            f"{seed}:{b}",
                        )
                        for b, active in enumerate(targets)
                    )
                )
                pending = []
                for draft in [d for batch in batches for d in batch]:
                    system["rule_results"][draft["target"]]["generated"] += 1
                    qkey = question_key(draft["question"])
                    if qkey not in seen:
                        seen.add(qkey)
                        pending.append(draft)
                        system["drafts"].append(draft)
                system["pending"] = pending
                atomic_json(path, state)
            counts = Counter(q["target"] for q in system["items"])
            drafts = []
            for i, draft in enumerate(system["pending"]):
                if counts[draft["target"]] < system["quota"][draft["target"]]:
                    drafts.append((i, draft))
                    counts[draft["target"]] += 1
            results = await settled(
                *(
                    evaluate_question(
                        models, f"{round_key}/item-{i}", system, d, f"{seed}:item:{i}"
                    )
                    for i, d in drafts
                )
            )
            for (_, draft), (item, reason) in zip(drafts, results):
                stats = system["rule_results"][draft["target"]]
                stats["checked"] += 1
                if item is not None:
                    stats["passed"] += 1
                    system["items"].append(item)
                else:
                    if system["round"] not in stats["rejected_rounds"]:
                        stats["rejected_rounds"].append(system["round"])
                    system["rejections"][reason] = (
                        system["rejections"].get(reason, 0) + 1
                    )
            system.pop("pending")
            system["round"] += 1
            atomic_json(path, state)
            print(
                f"{key}: accepted={len(system['items'])}/{total}; generated={sum(r['generated'] for r in system['rule_results'])}/{ROW_CANDIDATE_MULTIPLIER * total}; retired={system['retired']}; {system['rejections']}",
                flush=True,
            )
            if len(system["items"]) == total:
                completed = sum(
                    s is not None and len(s["items"]) == total
                    for s in state["systems"]
                )
                print(f"{key}: ROW COMPLETE — {completed}/{args.systems} rows complete", flush=True)
    slots = asyncio.Semaphore(args.row_concurrency)

    async def worker(index):
        async with slots:
            while True:
                if state["assignments"][index] is None:
                    if state["next_setting"] >= len(ideas):
                        raise CatalogueExhausted(
                            f"No unused settings remain: {completed_count(state, total)}/{args.systems} rows complete"
                        )
                    state["assignments"][index] = state["next_setting"]
                    state["next_setting"] += 1
                    atomic_json(path, state)
                try:
                    await generate_row(index)
                    return
                except SettingExhausted as error:
                    setting_index = state["assignments"][index]
                    state["discarded"].append({
                        "row": index, "catalogue_index": setting_index,
                        "name": ideas[setting_index]["name"], "reason": str(error),
                        "system": state["systems"][index],
                    })
                    state["systems"][index] = None
                    state["assignments"][index] = None
                    state["replacement_counts"][index] += 1
                    atomic_json(path, state)
                    print(f"system-{index:03d}: DISCARDED {ideas[setting_index]['name']}: {error}; "
                          f"{len(ideas) - state['next_setting']} unused settings remain", flush=True)

    # Quality-limit failures replace a setting; fatal errors preserve checkpoints.
    async with asyncio.TaskGroup() as group:
        for index in range(args.systems):
            group.create_task(worker(index), name=f"system-{index:03d}")
    return state



def render_review(state):
    """Render inspection order independently of randomized dataset options."""
    review = []
    for index, system in enumerate(state["systems"]):
        gold, question_world = system["gold"], system["question_world"]
        answer_worlds = [gold] + [
            i for i in range(WORLD_COUNT) if i not in (gold, question_world)
        ]
        def world_label(i):
            role = " — gold" if i == gold else (
                " — question-writing, inspection only" if i == question_world else ""
            )
            return f"World {i + 1}{role}"

        review.extend([
            f"# System {index + 1}", "## Setting", system["shared"],
            "Answer order throughout this review: "
            + "; ".join(world_label(i) for i in answer_worlds)
            + ". Dataset answer options retain their randomized order.",
            "## All worlds",
        ])
        for i in [*answer_worlds, question_world]:
            review.append(f"### {world_label(i)}")
            for rule, paragraph in enumerate(system["worlds"][i]):
                review.extend([f"#### Rule {rule + 1}", paragraph])

        examples = system["collisions"].get("rule_examples", [])
        if examples:
            review.extend([
                "## Collision-verifier examples (inspection only)",
                "These questions are not included in the training or test pool. "
                "Answers below are the collision verifier's joint predictions, "
                "not independently generated or validated answers.",
            ])
            for rule, example in enumerate(examples):
                review.extend([
                    f"### Rule {rule + 1}", example["question"] or "No distinguishing question found.",
                    "\n".join(f"- **{world_label(i)}:** {example['answers'][i]}"
                              for i in [*answer_worlds, question_world]),
                    example["reason"],
                ])

        pool = list(system["items"])
        random.Random(f"split:{state['config']['seed']}:{index}").shuffle(pool)
        train = state["config"]["train"]
        references = {
            question_key(item["question"]): (
                f"Train {i + 1}" if i < train else f"Test {i - train + 1}"
            ) for i, item in enumerate(pool)
        }
        review.append("## Questions by rule")
        for rule, request in enumerate(system["requests"]):
            items = [item for item in pool if item["target"] == rule]
            retired = " — retired from further generation" if rule in system["retired"] else ""
            review.extend([
                f"### Rule {rule + 1}: {request['aspect']}{retired}",
                "Deciding factors: " + "; ".join(request["factors"]),
                f"Accepted questions: {len(items)}.",
            ])
            for item in items:
                review.extend([
                    f"#### {references[question_key(item['question'])]}",
                    item["question"],
                    "\n".join(
                        f"- **{letter}. {world_label(i)}:** {item['answers'][str(i)]['answer']}"
                        for letter, i in zip(OPTION_LABELS, answer_worlds)
                    ),
                    "Correct answer in this review: A (gold).",
                    f"Question-writing World {question_world + 1} (inspection only): "
                    + json.dumps(item["question_world_answer"], ensure_ascii=False),
                ])
    return "\n\n".join(review) + "\n"


def export(state, directory):
    config, rows, seen = state["config"], [], set()
    if len(state["systems"]) != config["systems"]:
        raise ValueError("Incomplete systems")
    assignments = state.get("assignments")
    if assignments is not None and (
        len(assignments) != config["systems"]
        or any(i is None for i in assignments)
        or len(set(assignments)) != len(assignments)
        or any(s is None or s.get("catalogue_index") != i
               for s, i in zip(state["systems"], assignments))
    ):
        raise ValueError("Invalid or repeated catalogue assignments")
    for system in state["systems"]:
        if (
            len(system["worlds"]) != WORLD_COUNT
            or len(system["consistency"]) != WORLD_COUNT
            or any(len(r) != config["rules"] for r in system["worlds"])
            or not all(passed(c, CONSISTENCY) for c in system["consistency"])
            or not collisions_passed(system["collisions"], config["rules"])
            or system["gold"] not in range(WORLD_COUNT)
            or system["question_world"] not in range(WORLD_COUNT)
            or system["question_world"] == system["gold"]
        ):
            raise ValueError("Invalid world set")
        row = {
            "Setting": system["shared"],
            "World": world_text(system["shared"], system["worlds"][system["gold"]]),
            "num_train": config["train"],
            "num_test": config["test"],
        }
        if len(system["items"]) != config["train"] + config["test"]:
            raise ValueError("Incomplete question pool")
        pool = list(system["items"])
        random.Random(f"split:{config['seed']}:{len(rows)}").shuffle(pool)
        split_items = {
            "train": pool[: config["train"]],
            "test": pool[config["train"] :],
        }
        for split in ("train", "test"):
            data = []
            rng = random.Random(f"options:{config['seed']}:{len(rows)}:{split}")
            for item in split_items[split]:
                order = item["option_worlds"]
                if (
                    sorted(order)
                    != [i for i in range(WORLD_COUNT) if i != system["question_world"]]
                    or not all(
                        clean_text(t) for t in [item["question"], *item["options"]]
                    )
                    or any(len(o.split()) > MAX_ANSWER_WORDS for o in item["options"])
                    or truth_indices(item["gold_check"])
                    != [order.index(system["gold"])]
                    or len(truth_indices(item["possible_check"])) < MIN_POSSIBLE_OPTIONS
                    or order.index(system["gold"])
                    not in truth_indices(item["possible_check"])
                    or not passed(item["language"], LANGUAGE)
                    or not passed(item.get("uniqueness", {}), UNIQUENESS)
                    or set(item["answers"]) != set(map(str, order))
                    or not all(a["answerable"] for a in item["answers"].values())
                    or item["options"]
                    != [item["answers"][str(i)]["answer"] for i in order]
                ):
                    raise ValueError("Invalid answer provenance")
                qkey = question_key(item["question"])
                if qkey in seen:
                    raise ValueError("Duplicate question")
                seen.add(qkey)
                permutation = list(range(OPTION_COUNT))
                rng.shuffle(permutation)
                options = [item["options"][i] for i in permutation]
                position = permutation.index(order.index(system["gold"]))
                data.append(
                    {
                        "question": item["question"],
                        "options": options,
                        "correct_option": position,
                    }
                )
            row[split + "_data"] = data
        rows.append(row)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / JSONL_FILE).write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    )
    datasets.Dataset.from_list(rows).save_to_disk(str(directory / DATASET_DIR))
    (directory / REVIEW_FILE).write_text(render_review(state))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit-dir", type=Path)
    for name, default in DEFAULT_COUNTS.items():
        parser.add_argument("--" + name, type=int, default=default)
    parser.add_argument("--subject", default=DEFAULT_SUBJECT)
    parser.add_argument("--concurrency", type=int, default=MAX_CONCURRENCY)
    parser.add_argument("--row-concurrency", type=int, default=1)
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--output-dataset", default=UPLOAD_REPO)
    parser.add_argument("--private", action="store_true")
    args = parser.parse_args(argv)
    if (
        min(
            args.concurrency,
            args.row_concurrency,
            args.systems,
            args.rules,
            args.train,
            args.test,
            args.question_batches,
        )
        < 1
        or args.rules < MAX_DECIDING_FACTORS - MIN_DECIDING_FACTORS + 1
        or min(args.train, args.test) < args.rules
    ):
        parser.error(
            "Positive counts, both factor counts, and room for every rule in both splits are required"
        )
    if args.upload and (
        args.systems != DEFAULT_COUNTS["systems"]
        or args.subject != DEFAULT_SUBJECT
        or (args.train, args.test) != (DEFAULT_COUNTS["train"], DEFAULT_COUNTS["test"])
    ):
        parser.error("Upload requires 64 completed rows with 256/100 questions per row")
    return args


async def run(args):
    if args.export_only:
        state = json.loads((args.output_dir / CHECKPOINT_FILE).read_text())
        if state["config"] != manifest(args):
            raise ValueError(
                "Source/configuration changed; export arguments must match"
            )
    else:
        key = os.environ.get(API_KEY_ENV)
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        async with AuditedClient(
            args.audit_dir or args.output_dir / AUDIT_DIR,
            timeout=REQUEST_TIMEOUT,
            limits=httpx.Limits(
                max_connections=args.concurrency,
                max_keepalive_connections=args.concurrency,
            ),
            headers=headers,
        ) as client:
            state = await generate(
                args, Models(client, args.output_dir / CALLS_DIR, args.concurrency)
            )
    export(state, args.output_dir)
    if args.upload:
        dataset = datasets.load_from_disk(str(args.output_dir / DATASET_DIR))
        result = dataset.push_to_hub(
            args.output_dataset,
            config_name=UPLOAD_CONFIG,
            split=UPLOAD_SPLIT,
            private=args.private,
        )
        atomic_json(args.output_dir / "upload.json", {
            "repository": args.output_dataset, "commit": str(result),
            "rows": len(dataset), "config": UPLOAD_CONFIG, "split": UPLOAD_SPLIT,
        })
        print(result, flush=True)


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
