"""Build the explorer index for one completed run (one-time, about a minute)."""

import json
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path

import ingest
import reconstruct

INDEX_VERSION = 1
STAGE_LABELS = {
    "verify": "Gold-world verification",
    "possible": "Answer-only possibility check",
    "language": "Language check",
    "deduplication": "Answer uniqueness check",
}
PROMPT_NAMES = (
    "SYSTEM_PROMPT", "SETTING_PROMPT", "PLAN_PROMPT", "REVISION_PROMPT", "WORLD_PROMPT",
    "CONSISTENCY_PROMPT", "COLLISION_PROMPT", "QUESTION_PROMPT", "QUESTION_VARIATIONS",
    "ANSWER_PROMPT", "ANSWER_VARIATIONS", "VERIFY_PROMPT", "POSSIBLE_PROMPT",
    "LANGUAGE_PROMPT", "QUESTION_LANGUAGE_PROMPT", "DEDUPLICATION_PROMPT", "THINKING",
)


def discard_reason(store, setting):
    last = setting["trials"][-1]
    if setting["accepted"]:
        return ("Worlds were accepted, but the setting was discarded during question "
                "generation (row budget of 7,120 candidates or repeated request failures). "
                "The filtered audit excludes question calls for discarded settings.")
    errors = Counter(
        row[0] for row in store.db.execute(
            "SELECT COALESCE(error, 'no response recorded') FROM calls WHERE id IN (%s)"
            % ",".join(map(str, last["plan_call"]))
        )
    )
    detail = ", ".join(f"{n}× {e.strip().rstrip(':')}" for e, n in errors.most_common())
    return (f"Attempt {last['index'] + 1}'s planning call never completed ({detail}). "
            "Each request gets 8 attempts with a 30-minute timeout; exhausting them "
            "discards the setting and assigns an unused catalogue entry to the row.")


def build(run, index, log=print):
    start = time.time()
    index.parent.mkdir(parents=True, exist_ok=True)
    temporary = index.with_suffix(".building")
    temporary.unlink(missing_ok=True)
    log("Stage 1/2: ingesting filtered_audit/model_io.jsonl.gz")
    ingest.ingest(run / "filtered_audit" / "model_io.jsonl.gz", temporary)

    log("Stage 2/2: reconstructing settings, worlds and question traces")
    store = reconstruct.Store(temporary)
    db = store.db
    constants = reconstruct.frozen_constants(run / "code" / "systems_bench.py")
    catalogue = json.loads((run / "code" / "system_data" / "catalogue.json").read_text())
    rows = [json.loads(line) for line in open(run / "systems_bench.jsonl")]
    selection = [json.loads(line) for line in open(run / "filtered_audit" / "selection.jsonl")]
    retired = reconstruct.parse_review(run / "review.md")

    settings = reconstruct.build_settings(store, catalogue)
    row_of = {r["Setting"]: i for i, r in enumerate(rows)}
    for s in settings:
        s["row"] = row_of.get(s["shared"])
        if s["row"] is not None:
            gold_world = s["shared"] + "\n\n" + "\n\n".join(s["trials"][-1]["worlds"][s["gold"]])
            assert s["accepted"] and gold_world == rows[s["row"]]["World"], s["idea"]["name"]
        else:
            s["discard_reason"] = discard_reason(store, s)
    assert sorted(s["row"] for s in settings if s["row"] is not None) == list(range(len(rows)))
    log(f"  {len(settings)} settings; {len(rows)} final rows; gold worlds match the dataset")

    drafts, generations = reconstruct.build_questions(store, settings, rows, selection, constants)
    mismatched = sum(not d["recomputed_ok"] for d in drafts)
    log(f"  {len(drafts)} question traces; {mismatched} recomputed verdicts differ from the run")

    db.executescript("""
        DROP TABLE IF EXISTS meta; DROP TABLE IF EXISTS settings;
        DROP TABLE IF EXISTS drafts; DROP TABLE IF EXISTS generations;
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE settings (id INTEGER PRIMARY KEY, row INTEGER, name TEXT, data TEXT);
        CREATE TABLE drafts (id INTEGER PRIMARY KEY, row INTEGER, rule INTEGER, status TEXT,
            reason TEXT, split TEXT, split_index INTEGER, question TEXT, data TEXT);
        CREATE TABLE generations (id INTEGER PRIMARY KEY, row INTEGER, data TEXT);
        ALTER TABLE calls ADD COLUMN setting_id INTEGER;
        ALTER TABLE calls ADD COLUMN draft_id INTEGER;
        ALTER TABLE calls ADD COLUMN label TEXT;
    """)

    def label(ids, text, setting_id=None, draft_id=None):
        db.executemany(
            "UPDATE calls SET label=?, setting_id=COALESCE(?, setting_id), "
            "draft_id=COALESCE(?, draft_id) WHERE id=?",
            [(text, setting_id, draft_id, i) for i in ids],
        )

    setting_of_row = {}
    for sid, s in enumerate(settings):
        if s["row"] is not None:
            setting_of_row[s["row"]] = sid
        label(s["call_ids"], "World building", sid)
        label(s["setting_call"], "Setting and rule requests", sid)
        for t in s["trials"]:
            n = t["index"] + 1
            label(t["plan_call"], f"Attempt {n} · plan" + (" (revision)" if t["feedback"] else ""), sid)
            for w, ids in t.get("write_calls", {}).items():
                label(ids, f"Attempt {n} · write world {w + 1}", sid)
            for w, ids in t.get("consistency_calls", {}).items():
                label(ids, f"Attempt {n} · consistency world {w + 1}", sid)
            label(t.get("collision_calls", []), f"Attempt {n} · collision check", sid)
        db.execute("INSERT INTO settings VALUES (?,?,?,?)",
                   (sid, s["row"], s["idea"]["name"], json.dumps(s, ensure_ascii=False)))

    for gid, g in generations.items():
        label(g["attempts"], "Question batch")
        db.execute("INSERT INTO generations VALUES (?,?,?)", (gid, g["row"], json.dumps(g, ensure_ascii=False)))

    for did, d in enumerate(drafts):
        for w, a in d["answers"].items():
            label(a["attempts"], f"Answer · world {w + 1}", draft_id=did)
        for k, c in d["checks"].items():
            label(c["attempts"], STAGE_LABELS[k], draft_id=did)
        p = d["placement"] or {}
        db.execute(
            "INSERT INTO drafts VALUES (?,?,?,?,?,?,?,?,?)",
            (did, d["row"], d["rule"], d["status"], d["reason"], p.get("split"), p.get("index"),
             d["question"], json.dumps(d, ensure_ascii=False)),
        )
    # Answer-only calls that were sent for unsampled drafts with identical prompts.
    db.execute("UPDATE calls SET label='Answer-only possibility check (identical request from an unsampled draft)' "
               "WHERE stage='possible' AND draft_id IS NULL")
    db.execute("UPDATE calls SET setting_id=(SELECT s.id FROM settings s WHERE s.row=calls.sel_row) "
               "WHERE setting_id IS NULL AND sel_row IS NOT NULL")
    db.execute("UPDATE calls SET setting_id=(SELECT s.id FROM settings s JOIN drafts d ON d.row=s.row "
               "WHERE d.id=calls.draft_id) WHERE draft_id IS NOT NULL")
    db.execute("CREATE INDEX calls_setting ON calls(setting_id, started_at)")
    db.execute("CREATE INDEX calls_draft ON calls(draft_id)")
    db.execute("CREATE INDEX drafts_row ON drafts(row)")
    db.execute("CREATE INDEX generations_row ON generations(row)")

    # Per-row summaries for navigation and the overview.
    usage = defaultdict(Counter)
    for sid, stage, n, prompt, completion, reasoning in db.execute(
        "SELECT setting_id, stage, COUNT(*), SUM(COALESCE(prompt_tokens,0)), "
        "SUM(COALESCE(completion_tokens,0)), SUM(COALESCE(reasoning_tokens,0)) "
        "FROM calls GROUP BY setting_id, stage"
    ):
        usage[sid][stage + ":calls"] += n
        usage[sid]["calls"] += n
        usage[sid]["prompt_tokens"] += prompt
        usage[sid]["completion_tokens"] += completion
        usage[sid]["reasoning_tokens"] += reasoning
    by_row = defaultdict(list)
    for d in drafts:
        by_row[d["row"]].append(d)
    row_summaries = []
    for r, row in enumerate(rows):
        sid = setting_of_row[r]
        s = settings[sid]
        accepted = Counter(d["rule"] for d in by_row[r] if d["status"] == "accepted")
        rejected = Counter(d["rule"] for d in by_row[r] if d["status"] != "accepted")
        quota = [sum(j % 16 == i for j in range(356)) for i in range(16)]
        row_summaries.append(dict(
            row=r, setting=sid, name=s["idea"]["name"], subject=s["idea"]["subject"],
            catalogue_index=s["catalogue_index"], attempts=len(s["trials"]),
            gold=s["gold"], question_world=s["question_world"],
            train=len(row["train_data"]), test=len(row["test_data"]),
            rules=[dict(rule=i, aspect=s["requests"][i]["aspect"], factors=s["requests"][i]["factors"],
                        initial_quota=quota[i], accepted=accepted[i], rejected_sample=rejected[i],
                        retired=i in retired[r]) for i in range(16)],
            reasons=Counter(d["reason"] for d in by_row[r] if d["status"] != "accepted"),
            usage=usage[sid],
        ))
    discarded = [dict(setting=sid, name=s["idea"]["name"], subject=s["idea"]["subject"],
                      catalogue_index=s["catalogue_index"], attempts=len(s["trials"]),
                      worlds_accepted=s["accepted"], reason=s["discard_reason"], usage=usage[sid])
                 for sid, s in enumerate(settings) if s["row"] is None]
    totals = Counter()
    for u in usage.values():
        totals.update(u)
    meta = dict(
        index_version=INDEX_VERSION,
        run=run.name,
        built_at=time.time(),
        rows=row_summaries,
        discarded=discarded,
        manifest=json.loads((run / "filtered_audit" / "manifest.json").read_text()),
        usage_all=json.loads((run / "usage.json").read_text()),
        upload=json.loads((run / "upload.json").read_text()),
        retained_usage=totals,
        reasons=Counter(d["reason"] for d in drafts if d["status"] != "accepted"),
        drafts=dict(accepted=sum(d["status"] == "accepted" for d in drafts),
                    rejected=sum(d["status"] != "accepted" for d in drafts),
                    mismatched=mismatched),
        prompts={k: constants[k] for k in PROMPT_NAMES},
        limits={k: constants[k] for k in (
            "WORLD_COUNT", "MAX_ANSWER_WORDS", "RULE_MIN_WORDS", "RULE_MAX_WORDS",
            "WORLD_ATTEMPTS", "REQUEST_ATTEMPTS", "RULE_CANDIDATE_MULTIPLIER",
            "ROW_CANDIDATE_MULTIPLIER", "MAX_RETIRED_RULES", "DEFAULT_COUNTS", "VERSION",
            "NO_THINKING_OUTPUT_TOKENS", "LONG_OUTPUT_TOKENS")},
        catalogue_size=len(catalogue),
        stage_calls=dict(db.execute("SELECT stage, COUNT(*) FROM calls GROUP BY stage").fetchall()),
    )
    db.execute("INSERT INTO meta VALUES ('overview', ?)", (json.dumps(meta, ensure_ascii=False),))
    db.commit()
    db.close()
    temporary.replace(index)
    log(f"Index ready: {index} ({index.stat().st_size / 1e9:.1f} GB, {time.time() - start:.0f}s)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("index", type=Path)
    args = parser.parse_args()
    build(args.run.resolve(), args.index.resolve())
