"""SystemsBench data explorer: serve one completed run's data and model I/O.

    python3 explorer/server.py                      # default run, port 8765
    python3 explorer/server.py --run local_data/<run> --port 8000

The first start builds an index under local_data/explorer/ (about a minute).
Uses only the Python standard library.
"""

import argparse
import json
import sqlite3
import sys
import threading
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402

REPO = HERE.parent
DEFAULT_RUN = REPO / "local_data" / "full-64-256-100-v56"
CALL_COLUMNS = (
    "id, stage, label, setting_id, draft_id, started_at, elapsed, status_code, finish_reason, "
    "error, thinking, prompt_tokens, completion_tokens, reasoning_tokens"
)
CALL_KEYS = [c.strip() for c in CALL_COLUMNS.split(",")]


class Data:
    def __init__(self, index):
        self.index = index
        self.local = threading.local()
        self.overview = json.loads(self.db().execute("SELECT value FROM meta WHERE key='overview'").fetchone()[0])

    def db(self):
        if not hasattr(self.local, "db"):
            self.local.db = sqlite3.connect(f"file:{self.index}?mode=ro", uri=True)
        return self.local.db

    def one(self, sql, args=()):
        row = self.db().execute(sql, args).fetchone()
        return row[0] if row else None

    def call_rows(self, where, args=(), limit=None):
        sql = f"SELECT {CALL_COLUMNS} FROM calls WHERE {where} ORDER BY started_at, id"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [dict(zip(CALL_KEYS, row)) for row in self.db().execute(sql, args)]

    def setting(self, sid):
        data = self.one("SELECT data FROM settings WHERE id=?", (sid,))
        return json.loads(data) if data else None

    def questions(self, row):
        return [
            dict(id=r[0], rule=r[1], status=r[2], reason=r[3], split=r[4], index=r[5], question=r[6])
            for r in self.db().execute(
                "SELECT id, rule, status, reason, split, split_index, question FROM drafts "
                "WHERE row=? ORDER BY id", (row,))
        ]

    def draft(self, did):
        data = self.one("SELECT data FROM drafts WHERE id=?", (did,))
        if data is None:
            return None
        draft = json.loads(data)
        draft["id"] = did
        if draft["generation"]:
            draft["generation"]["batch"] = json.loads(self.one(
                "SELECT data FROM generations WHERE id=?", (draft["generation"]["call"],)))
        ids = [i for a in draft["answers"].values() for i in a["attempts"]]
        ids += [i for c in draft["checks"].values() for i in c["attempts"]]
        if draft["generation"]:
            ids += draft["generation"]["batch"]["attempts"]
        draft["calls"] = {c["id"]: c for c in self.call_rows(
            "id IN (%s)" % ",".join("?" * len(ids)), ids)} if ids else {}
        return draft

    def dataset(self, row):
        sid = self.overview["rows"][row]["setting"]
        s = self.setting(sid)
        world = s["shared"] + "\n\n" + "\n\n".join(s["trials"][-1]["worlds"][s["gold"]])
        drafts = {(r[1], r[2]): r[0] for r in self.db().execute(
            "SELECT id, split, split_index FROM drafts WHERE row=? AND split IS NOT NULL", (row,))}
        data = {}
        for split in ("train", "test"):
            data[split] = [dict(draft=drafts.get((split, n)), **self.dataset_item(drafts.get((split, n))))
                           for n in range(self.overview["rows"][row][split])]
        return dict(Setting=s["shared"], World=world, num_train=len(data["train"]),
                    num_test=len(data["test"]), train_data=data["train"], test_data=data["test"])

    def dataset_item(self, did):
        d = json.loads(self.one("SELECT data FROM drafts WHERE id=?", (did,)))
        p = d["placement"]
        source = dict(zip(d["options"], d["option_worlds"]))
        return dict(question=p["question"], options=p["options"], correct_option=p["correct_option"],
                    rule=d["rule"], option_worlds=[source.get(o) for o in p["options"]])

    def call(self, cid):
        row = self.db().execute(f"SELECT {CALL_COLUMNS}, record FROM calls WHERE id=?", (cid,)).fetchone()
        if not row:
            return None
        meta = dict(zip(CALL_KEYS, row[:-1]))
        meta["record"] = json.loads(zlib.decompress(row[-1]))
        return meta


class Handler(BaseHTTPRequestHandler):
    data: Data = None

    def log_message(self, *args):
        pass

    def send(self, body, content_type="application/json", status=200):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        d = self.data
        try:
            if not parts:
                return self.send((HERE / "static" / "index.html").read_bytes(), "text/html")
            if parts[0] != "api":
                return self.send({"error": "not found"}, status=404)
            route = parts[1:]
            if route == ["overview"]:
                result = d.overview
            elif len(route) == 2 and route[0] == "setting":
                result = d.setting(int(route[1]))
            elif len(route) == 3 and route[0] == "row" and route[2] == "questions":
                result = d.questions(int(route[1]))
            elif len(route) == 3 and route[0] == "row" and route[2] == "dataset":
                result = d.dataset(int(route[1]))
            elif len(route) == 3 and route[0] == "setting" and route[2] == "calls":
                where, args = "setting_id=?", [int(route[1])]
                if query.get("stage"):
                    where += " AND stage=?"
                    args.append(query["stage"])
                result = d.call_rows(where, args)
            elif len(route) == 2 and route[0] == "draft":
                result = d.draft(int(route[1]))
            elif len(route) == 2 and route[0] == "call":
                result = d.call(int(route[1]))
            else:
                result = None
            if result is None:
                return self.send({"error": "not found"}, status=404)
            return self.send(result)
        except (ValueError, IndexError) as error:
            return self.send({"error": str(error)}, status=400)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--index", type=Path, help="default: local_data/explorer/<run>.sqlite")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    run = args.run.resolve()
    index = (args.index or REPO / "local_data" / "explorer" / f"{run.name}.sqlite").resolve()
    stale = True
    if index.exists() and not args.rebuild:
        try:
            stale = Data(index).overview.get("index_version") != build.INDEX_VERSION
        except sqlite3.Error:
            pass
    if stale:
        print(f"Building explorer index for {run.name} (about a minute)...", flush=True)
        build.build(run, index, log=lambda m: print(m, flush=True))
    Handler.data = Data(index)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Serving {run.name} at http://{args.host}:{args.port}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
