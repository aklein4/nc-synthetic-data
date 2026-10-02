"""Stage 1: load every filtered audit record into SQLite with call metadata.

Each record is stored whole (zlib-compressed JSON) so the explorer can show the
exact request and response. Parsed fields support the reconstruction stage.
"""

import gzip
import hashlib
import json
import multiprocessing as mp
import sqlite3
import time
import zlib

# User-prompt prefixes from the frozen v56 source identify each call's stage.
STAGES = (
    ("setting", "Create a neutral science-class setting from"),
    ("plan", "Plan 5 equally plausible versions"),
    ("write", "Write this one educational system from its plan."),
    ("consistency", "Check for internal contradictions"),
    ("collisions", "Compare these 5 worlds."),
    ("questions", "Write one short science question per request"),
    ("answer", "Using only the description, give the requested outcome"),
    ("verify", "Using only this description and question, judge EACH"),
    ("possible", "Using only this description, judge each option"),
    ("language", "Check natural high-school English."),
    ("deduplication", "Compare the meanings of the four answers"),
)

SCHEMA = """
CREATE TABLE calls (
    id INTEGER PRIMARY KEY,
    audit_file TEXT,
    kind TEXT,
    stage TEXT,
    sel_row INTEGER,
    sel_rule INTEGER,
    sel_status TEXT,
    sel_question TEXT,
    digest TEXT,
    started_at REAL,
    elapsed REAL,
    status_code INTEGER,
    finish_reason TEXT,
    error TEXT,
    thinking INTEGER,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    reasoning_tokens INTEGER,
    user_prompt BLOB,
    output TEXT,
    record BLOB
);
"""


def stage_of(user):
    for name, prefix in STAGES:
        if user.startswith(prefix):
            return name
    return "unknown"


def parse(line):
    record = json.loads(line)
    request = record.get("request") or {}
    messages = request.get("messages", [])
    user = next((m["content"] for m in messages if m["role"] == "user"), "")
    response = record.get("response") or {}
    choice = (response.get("choices") or [{}])[0]
    usage = response.get("usage") or {}
    selection = record.get("selection", {})
    error = record.get("transport_error")
    if record.get("status_code") not in (None, 200):
        error = error or f"HTTP {record.get('status_code')}"
    return (
        record.get("audit_file"),
        selection.get("kind"),
        stage_of(user),
        selection.get("row"),
        selection.get("rule"),
        selection.get("status"),
        selection.get("question"),
        hashlib.sha256(
            json.dumps(request, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
        record.get("started_at"),
        record.get("elapsed_seconds"),
        record.get("status_code"),
        choice.get("finish_reason"),
        error,
        int(bool((request.get("chat_template_kwargs") or {}).get("enable_thinking"))),
        usage.get("prompt_tokens"),
        usage.get("completion_tokens"),
        (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        zlib.compress(user.encode(), 6),
        (choice.get("message") or {}).get("content"),
        zlib.compress(line.encode(), 6),
    )


def ingest(source, database):
    start = time.time()
    db = sqlite3.connect(database)
    db.executescript("DROP TABLE IF EXISTS calls;" + SCHEMA)
    insert = "INSERT INTO calls VALUES (NULL" + ",?" * 20 + ")"
    with gzip.open(source, "rt", encoding="utf-8") as lines, mp.Pool() as pool:
        for count, row in enumerate(pool.imap(parse, lines, chunksize=256), 1):
            db.execute(insert, row)
            if count % 20000 == 0:
                db.commit()
                print(f"  ingested {count:,} records ({time.time() - start:.0f}s)", flush=True)
    db.execute("CREATE INDEX calls_stage ON calls(stage)")
    db.execute("CREATE INDEX calls_row ON calls(sel_row, sel_question)")
    db.commit()
    db.close()
    print(f"  ingest complete in {time.time() - start:.0f}s", flush=True)
