"""Stage 2: rebuild the run's structure from the ingested audit records.

The filtered audit has no cache keys, so structure is recovered from request
contents: settings are grouped by their shared background, world-building
attempts are chained through the revision feedback embedded in each plan
prompt, and question evaluations are grouped by the selection metadata.
Rejection reasons are recomputed with the frozen v56 acceptance logic.
"""

import ast
import json
import random
import re
import sqlite3
import unicodedata
import zlib
from collections import Counter, defaultdict
from pathlib import Path

WORLD_COUNT = 5
LABELS = "ABCD"
SEED = 42
DECODER = json.JSONDecoder()


def frozen_constants(source):
    """Read prompt templates and limits from the run's frozen source."""
    values = {}
    for node in ast.parse(source.read_text()).body:
        if not (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)):
            continue
        name = node.targets[0].id
        try:
            values[name] = ast.literal_eval(node.value)
        except ValueError:
            if name == "TEXT_DEBRIS":  # re.compile(<literal>, re.IGNORECASE)
                values[name] = re.compile(ast.literal_eval(node.value.args[0]), re.IGNORECASE)
    return values


def question_key(text):
    return " ".join(unicodedata.normalize("NFKC", text).split())


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)

    def calls(self, where, args=()):
        sql = (
            "SELECT id, stage, user_prompt, output, started_at, status_code, "
            "finish_reason, digest, sel_row, sel_rule, sel_status, sel_question "
            "FROM calls WHERE " + where + " ORDER BY started_at, id"
        )
        for row in self.db.execute(sql, args):
            yield dict(
                id=row[0], stage=row[1], user=zlib.decompress(row[2]).decode(),
                output=row[3], started_at=row[4], status_code=row[5],
                finish_reason=row[6], digest=row[7], row=row[8], rule=row[9],
                status=row[10], question=row[11],
            )

    def record(self, call_id):
        blob = self.db.execute("SELECT record FROM calls WHERE id=?", (call_id,)).fetchone()[0]
        return json.loads(zlib.decompress(blob))


def logical(records):
    """Group retries into logical calls, in time order.

    The pipeline caches the first attempt that finishes with a parseable JSON
    instance, so a failed attempt is retried with an identical request. An
    identical request after a success belongs to a different call (e.g. a
    later world-building attempt that reproduced the same plan).
    """
    open_groups, result = {}, []
    for record in sorted(records, key=lambda r: (r["started_at"], r["id"])):
        group = open_groups.get(record["digest"])
        if group is None or group["used"] is not None:
            group = dict(attempts=[], result=None, used=None, started_at=record["started_at"],
                         user=record["user"], stage=record["stage"])
            open_groups[record["digest"]] = group
            result.append(group)
        group["attempts"].append(record["id"])
        if group["used"] is None and record["status_code"] == 200 and record["finish_reason"] == "stop":
            try:
                group["result"], group["used"] = json.loads(record["output"]), record["id"]
            except (TypeError, ValueError):
                pass
    return result


def take(calls, after, used, match):
    """First unused logical call starting no earlier than `after` that matches."""
    for call in calls:
        if call["started_at"] >= after and id(call) not in used and match(call):
            used.add(id(call))
            return call
    return None


def embedded_json(user):
    payload, end = DECODER.raw_decode(user[user.index("{"):])
    return payload, user[user.index("{") + end:]


def consistency_passed(check):
    return bool(check) and all(check.get(k) is True for k in ("consistent", "sufficient_complexity"))


def collisions_passed(check, count):
    if not check or not all(check.get(k) is True for k in ("distinct", "shared_support", "neutral_setting")):
        return False
    examples = check.get("rule_examples") or []
    return len(examples) == count and all(
        e.get("distinguishable") is True
        and e.get("question", "").strip()
        and len(e.get("answers", [])) == WORLD_COUNT
        and all(a.strip() for a in e["answers"])
        and len({question_key(a) for a in e["answers"]}) == WORLD_COUNT
        for e in examples
    )


def build_settings(store, catalogue):
    """Return one dict per catalogue setting that reached world building."""
    names = {idea["name"]: i for i, idea in enumerate(catalogue)}
    groups = defaultdict(list)
    for record in store.calls("kind='world_construction'"):
        if record["stage"] == "setting":
            shared = json.loads(record["output"])["shared"]
        else:
            shared = embedded_json(record["user"])[0]["shared"]
        groups[shared].append(record)

    settings = []
    for shared, records in groups.items():
        calls = {stage: logical([r for r in records if r["stage"] == stage])
                 for stage in ("setting", "plan", "write", "consistency", "collisions")}
        setting_call = calls["setting"][0]
        idea = DECODER.raw_decode(setting_call["user"][len("Create a neutral science-class setting from "):])[0]
        design = setting_call["result"]
        count = len(design["requests"])
        catalogue_index = names[idea["name"]]

        for call in calls["plan"]:
            payload, rest = embedded_json(call["user"])
            call["feedback"] = json.loads(rest[rest.index("{"):]) if "Revise the plan" in rest else None
        for stage in ("write", "consistency", "collisions"):
            for call in calls[stage]:
                call["payload"] = embedded_json(call["user"])[0]

        trials = []
        taken = set()
        plan_call = take(calls["plan"], 0, taken, lambda c: c["feedback"] is None)
        feedback = None
        while plan_call is not None:
            trial = dict(index=len(trials), plan_call=plan_call["attempts"],
                         feedback=feedback, complete=False)
            trials.append(trial)
            if plan_call["result"] is None:
                break
            plan = json.loads(json.dumps(plan_call["result"]))
            fixed = feedback["fixed_worlds"] if feedback else []
            for i in fixed:
                plan["worlds"][i] = feedback["plan"]["worlds"][i]
            active = [i for i in range(WORLD_COUNT) if i not in fixed]
            worlds = list(feedback["worlds"]) if feedback else [None] * WORLD_COUNT
            checks = list(feedback["consistency"]) if feedback else [None] * WORLD_COUNT
            write_calls, check_calls = {}, {}
            for i in active:
                write = take(calls["write"], plan_call["started_at"], taken,
                             lambda c: c["payload"]["plan"] == plan["worlds"][i])
                if write:
                    write_calls[i] = write["attempts"]
                    worlds[i] = write["result"]["rules"] if write["result"] else None
            for i in active:
                check = take(calls["consistency"], plan_call["started_at"], taken,
                             lambda c: c["payload"]["rules"] == worlds[i]) if worlds[i] else None
                if check:
                    check_calls[i] = check["attempts"]
                    checks[i] = check["result"]
                else:
                    checks[i] = None
            collision = take(calls["collisions"], plan_call["started_at"], taken,
                             lambda c: c["payload"]["worlds"] == worlds)
            collision_result = collision["result"] if collision else None
            consistency_ok = [consistency_passed(c) for c in checks]
            collision_ok = collisions_passed(collision_result, count)
            trial.update(
                plan=plan["worlds"], raw_plan=plan_call["result"]["worlds"],
                fixed=fixed, active=active, worlds=worlds, consistency=checks,
                consistency_ok=consistency_ok, write_calls=write_calls,
                consistency_calls=check_calls,
                collisions=collision_result,
                collision_calls=collision["attempts"] if collision else [],
                collisions_ok=collision_ok,
                passed=all(consistency_ok) and collision_ok,
                complete=collision is not None and all(i in check_calls for i in active),
            )
            if trial["passed"] or not trial["complete"]:
                break
            feedback = {
                "plan": plan, "worlds": worlds, "consistency": checks,
                "collisions": {
                    **{k: v for k, v in collision_result.items() if k != "rule_examples"},
                    "rule_checks": [
                        {"rule": i + 1, "distinguishable": e["distinguishable"], "reason": e["reason"]}
                        for i, e in enumerate(collision_result["rule_examples"])
                    ],
                },
                "fixed_worlds": [i for i, ok in enumerate(consistency_ok) if ok] if collision_ok else [],
            }
            plan_call = take(calls["plan"], plan_call["started_at"], taken,
                             lambda c: c["feedback"] == feedback)

        accepted = trials[-1].get("passed", False)
        gold, question_world = random.Random(f"roles:{SEED + catalogue_index}").sample(range(WORLD_COUNT), 2)
        used = {i for t in trials for key in ("plan_call",) for i in t[key]}
        for t in trials:
            for key in ("write_calls", "consistency_calls"):
                for ids in t.get(key, {}).values():
                    used.update(ids)
            used.update(t.get("collision_calls", []))
        used.update(setting_call["attempts"])
        settings.append(dict(
            catalogue_index=catalogue_index, idea=idea, shared=shared,
            requests=design["requests"], setting_call=setting_call["attempts"],
            trials=trials, accepted=accepted,
            gold=gold if accepted else None,
            question_world=question_world if accepted else None,
            started_at=min(r["started_at"] for r in records),
            unmatched_calls=[r["id"] for r in records if r["id"] not in used],
            call_ids=[r["id"] for r in records],
        ))
    return sorted(settings, key=lambda s: s["started_at"])


def parse_options(user):
    """Read the four 'A. ...' option lines that end a check prompt."""
    tail = user[user.rindex("\nA. ") + 1:]
    parts = re.split(r"\n(?=[BCD]\. )", tail)
    return [p[3:] for p in parts]


def section(text, start, end=None):
    i = text.rindex(start) + len(start)
    return text[i:text.index(end, i)] if end else text[i:]


def evaluate(draft, system, constants):
    """Recompute the pipeline's accept/reject decision from saved responses."""
    debris = constants["TEXT_DEBRIS"]
    max_words = constants["MAX_ANSWER_WORDS"]

    def clean(text):
        return bool(text.strip()) and not debris.search(text)

    if not clean(draft["question"]):
        return "text_format", "Question text failed the formatting filter (empty, control characters, or a banned meta word)."
    answers = draft["answers"]
    if not answers:
        return "not_evaluated", "Never evaluated: its rule's quota was already filled when this draft's round was evaluated."
    if len(answers) < WORLD_COUNT or any(a["result"] is None for a in answers.values()):
        return "incomplete", "Answer calls are incomplete in the saved audit."
    qw, gold = system["question_world"], system["gold"]
    answer_worlds = [i for i in range(WORLD_COUNT) if i != qw]
    if not all(answers[i]["result"]["answerable"] and answers[i]["result"]["answer"].strip() for i in answer_worlds):
        missing = [i + 1 for i in answer_worlds if not (answers[i]["result"]["answerable"] and answers[i]["result"]["answer"].strip())]
        return "unanswerable", "World(s) " + ", ".join(map(str, missing)) + " declared the question unanswerable from their description."
    options = [answers[i]["result"]["answer"] for i in answer_worlds]
    if not all(clean(o) for o in options):
        return "text_format", "An answer failed the formatting filter (control characters or a banned meta word)."
    if any(len(o.split()) > max_words for o in options):
        return "answer_length", f"An answer exceeded {max_words} words."
    if len({question_key(o) for o in options}) != len(options):
        return "identical_answers", "Two answer worlds returned exactly the same text."
    checks = draft["checks"]
    if any(checks.get(k) is None or checks[k]["result"] is None for k in ("verify", "possible", "language", "deduplication")):
        return "incomplete", "Check calls are incomplete in the saved audit."
    order = draft["option_worlds"]
    if not all(checks["deduplication"]["result"].values()):
        dup = [k for k, v in checks["deduplication"]["result"].items() if not v]
        return "duplicate_answers", "The uniqueness check judged options " + ", ".join(dup) + " to be paraphrases of each other."
    gold_letter = LABELS[order.index(gold)]
    truth = [k for k, v in checks["verify"]["result"].items() if v]
    if truth != [gold_letter]:
        return "answer_validation", (
            f"Gold-world verification marked {', '.join(truth) or 'nothing'} true; it must mark exactly the gold option {gold_letter}."
        )
    possible = [k for k, v in checks["possible"]["result"].items() if v]
    if len(possible) < 2 or gold_letter not in possible:
        return "answer_only", (
            f"Answer-only check found {', '.join(possible) or 'no option'} possible without the question; "
            f"it needs at least two, including gold {gold_letter}, so the answer can't be guessed from the options alone."
        )
    if not all(checks["language"]["result"].values()):
        bad = [k for k, v in checks["language"]["result"].items() if not v]
        return "language", "Language check failed: " + ", ".join(bad) + "."
    return None, None


def build_questions(store, settings, rows, selection, constants):
    """Assemble one trace per selected draft."""
    by_row = {s["row"]: s for s in settings if s.get("row") is not None}
    world_text, gold_text = {}, {}
    for r, s in by_row.items():
        final = s["trials"][-1]["worlds"]
        for i, rules in enumerate(final):
            text = s["shared"] + "\n\n" + "\n\n".join(rules)
            world_text[(r, text)] = i
            if i == s["gold"]:
                gold_text[r] = text

    generations = defaultdict(list)
    for record in store.calls("stage='questions'"):
        generations[record["row"]].append(record)
    gen_index = {}
    gen_calls = {}
    for r, records in generations.items():
        for call in logical(records):
            user = call["user"]
            requests = json.loads(section(user, "\nRequests:\n", "\nStyle:\n"))
            style = section(user, "\nStyle:\n")
            # The filtered output keeps only selected questions; the record notes their positions.
            record = store.record(call["used"] or call["attempts"][-1])
            choice = record["response"]["choices"][0]
            positions = choice.get("filtering", {}).get("retained_indices", [])
            questions = (call["result"] or {}).get("questions", [])
            key = call["attempts"][0]
            gen_calls[key] = dict(
                attempts=call["attempts"], row=r, started_at=call["started_at"],
                requests=requests, style=style,
                original_count=choice.get("filtering", {}).get("original_question_count"),
                retained=[{"position": p, "question": q, "rule": requests[p]["rule"] - 1}
                          for p, q in zip(positions, questions)],
            )
            for p, q in zip(positions, questions):
                # Later repeats of a question were dropped as duplicates; the first one is the draft.
                gen_index.setdefault((r, question_key(q)), (key, p, requests[p]["rule"] - 1))

    # The answer-only ("possible") prompt omits the question, so drafts in one row
    # with identical options send identical requests; the audit filter keyed
    # selections by request hash and may label those records with another draft.
    # Those calls are matched by prompt text and timing instead of by label.
    evaluations = defaultdict(list)
    possible_by_prompt = defaultdict(list)
    for record in store.calls("kind='question_evaluation'"):
        if record["stage"] == "possible":
            possible_by_prompt[(record["row"], record["user"])].append(record)
        else:
            evaluations[(record["row"], question_key(record["question"]))].append(record)
    possible_calls = {key: logical(records) for key, records in possible_by_prompt.items()}

    placement = {}
    for r, row in enumerate(rows):
        for split in ("train", "test"):
            for n, item in enumerate(row[split + "_data"]):
                placement[(r, question_key(item["question"]))] = dict(split=split, index=n, **item)

    drafts = []
    for sel in selection:
        r, key = sel["row"], question_key(sel["question"])
        system = by_row[r]
        draft = dict(row=r, rule=sel["rule"], status=sel["status"], question=sel["question"],
                     answers={}, checks={}, option_worlds=None, options=None, style=None)
        records = evaluations.get((r, key), [])
        for call in logical(records):
            stage = call["stage"]
            entry = dict(attempts=call["attempts"], result=call["result"], started_at=call["started_at"])
            if stage == "answer":
                description = section(call["user"], "\nDescription:\n", "\nStyle:\n")
                world = world_text[(r, description)]
                draft["answers"][world] = entry
                draft["style"] = section(call["user"], "\nStyle:\n", "\nQuestion:\n")
            else:
                draft["checks"][stage] = entry
                if stage in ("verify", "possible", "deduplication") and draft["options"] is None:
                    draft["options"] = parse_options(call["user"])
        if draft["options"]:
            lookup = {a["result"]["answer"]: w for w, a in draft["answers"].items()
                      if a["result"] and w != system["question_world"]}
            draft["option_worlds"] = [lookup[o] for o in draft["options"]]
            gold = system["gold"]
            prompt = (
                constants["POSSIBLE_PROMPT"] + gold_text[r] + "\nOptions:\n"
                + "\n".join(f"{c}. {o}" for c, o in zip(LABELS, draft["options"]))
            )
            anchor = next(draft["checks"][k]["started_at"] for k in ("verify", "deduplication", "language")
                          if k in draft["checks"])
            candidates = possible_calls.get((r, prompt), [])
            if candidates:
                call = min(candidates, key=lambda c: abs(c["started_at"] - anchor))
                draft["checks"]["possible"] = dict(attempts=call["attempts"], result=call["result"],
                                                   started_at=call["started_at"])
        reason, detail = evaluate(draft, system, constants)
        draft["reason"], draft["reason_detail"] = reason, detail
        draft["recomputed_ok"] = (reason is None) == (sel["status"] == "accepted")
        generation = gen_index.get((r, key))
        draft["generation"] = dict(call=generation[0], position=generation[1]) if generation else None
        draft["generation_rule_ok"] = generation is None or generation[2] == sel["rule"]
        draft["placement"] = placement.get((r, key))
        draft["started_at"] = gen_calls[generation[0]]["started_at"] if generation else None
        drafts.append(draft)
    return drafts, gen_calls


def parse_review(path):
    """Retired rules per system, from the exported review."""
    retired = defaultdict(set)
    system = None
    with open(path) as lines:
        for line in lines:
            if line.startswith("# System "):
                system = int(line.split()[2]) - 1
            elif line.startswith("### Rule ") and "retired from further generation" in line:
                retired[system].add(int(line.split()[2].rstrip(":")) - 1)
    return retired
