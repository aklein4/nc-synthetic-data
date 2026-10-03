"""Read-only, local viewer for a SystemsBench run: python view_run.py RUN_DIR."""

import argparse
import base64
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import gzip
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit


def read_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def prompt_parts(text):
    """Separate the instruction from the final JSON input without changing either."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r'(?m)^[{\["]', text):
        try:
            value, end = decoder.raw_decode(text[match.start():])
            if not text[match.start() + end:].strip():
                return text[:match.start()].strip(), value
        except ValueError:
            pass
    return text, None


class Run:
    def __init__(self, directory, rows=None, worlds=None):
        self.directory = directory
        self.rows = rows
        self.worlds = worlds

    def call(self, key):
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", key):
            raise ValueError("Invalid call key")
        call = read_json(self.directory / "calls" / f"{key}.json")
        if call is None:
            raise FileNotFoundError(key)
        request = call["request"]
        instructions, inputs = prompt_parts(request["messages"][-1]["content"])
        # Only successful structured final results are read. Raw HTTP audits,
        # including reasoning in historical runs, are never served.
        return dict(key=key, request=request, instructions=instructions,
                    inputs=inputs, result=call["result"])

    def summary(self):
        state = read_json(self.directory / "checkpoint.json", dict(config={}, systems=[]))
        total_systems = len(state["systems"])
        indices = self.worlds if self.worlds is not None else list(range(total_systems))[:self.rows]
        if any(i < 0 or i >= total_systems for i in indices):
            raise ValueError("Selected world is not present in this run")
        positions = {source: position for position, source in enumerate(indices)}
        state["systems"] = [dict(state["systems"][i], source_index=i) for i in indices]
        retained = {item["question"]: (i, split, j)
                    for i, row in enumerate(state["systems"])
                    for split in ("train", "test") for j, item in enumerate(row[split])}
        candidates = []
        paths = sorted((self.directory / "calls").glob("*-question.json"),
                       key=lambda p: int(p.stem.split("-")[-2]))
        claimed = set()
        for path in paths:
            key = path.stem.removesuffix("-question")
            match = re.fullmatch(r"(\d+)-(train|test)-(\d+)", key)
            if not match:
                continue
            if int(match[1]) not in positions:
                continue
            call = self.call(path.stem)
            question = call["result"]["question"].strip()
            review = read_json(self.directory / "calls" / f"{key}-check.json")
            checks = review["result"] if review else None
            valid = (all(v["valid"] for v in [checks["question"], checks["distractors"], *checks["answers"]])
                     if checks else None)
            location = retained.get(question)
            if location is not None:
                item = state["systems"][location[0]][location[1]][location[2]]
                answers = [read_json(self.directory / "calls" / f"{key}-answer-{i}.json", {})
                           .get("result", {}).get("answer", "").strip() for i in range(4)]
                if (location in claimed or not valid or answers != item["options"]
                        or (call["inputs"] or {}).get("details") != item["sampling"]["details"]):
                    location = None
                else:
                    item["key"] = key
                    claimed.add(location)
            candidates.append(dict(key=key, system=positions[int(match[1])], split=match[2], attempt=int(match[3]),
                                   question=question, metric=(call["inputs"] or {}).get("metric"),
                                   retained=location is not None, reviewed=checks is not None,
                                   model_passed=valid))
        candidates.sort(key=lambda c: (c["system"], c["split"] == "test", c["attempt"]))
        world_calls = [p.stem for p in (self.directory / "calls").glob("*-world*.json")
                       if int(p.stem.split("-")[0]) in positions]
        return dict(name=self.directory.name, **state, candidates=candidates,
                    total_systems=total_systems,
                    world_calls=sorted(world_calls), complete=(self.directory / "systems_bench.jsonl").exists(),
                    status=read_json(self.directory / "status.json", {}),
                    usage=read_json(self.directory / "usage.json", {}))


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, run, **kwargs):
        self.run = run
        super().__init__(*args, **kwargs)

    def do_GET(self):
        route = urlsplit(self.path)
        try:
            if route.path == "/":
                body = Path(__file__).with_name("viewer.html").read_bytes()
                kind = "text/html; charset=utf-8"
            elif route.path == "/api/run":
                body = json.dumps(self.run.summary(), ensure_ascii=False).encode()
                kind = "application/json; charset=utf-8"
            elif route.path == "/api/call":
                key = parse_qs(route.query).get("key", [""])[0]
                body = json.dumps(self.run.call(key), ensure_ascii=False).encode()
                kind = "application/json; charset=utf-8"
            else:
                self.send_error(404)
                return
        except (ValueError, FileNotFoundError, KeyError):
            self.send_error(404, "Artifact not available")
            return
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def export_html(run, destination):
    summary = run.summary()
    selected = {row["source_index"] for row in summary["systems"]}
    calls = {path.stem: run.call(path.stem) for path in (run.directory / "calls").glob("*.json")
             if int(path.stem.split("-")[0]) in selected}
    payload = json.dumps(dict(run=summary, calls=calls), ensure_ascii=False, separators=(",", ":"))
    encoded = base64.b64encode(gzip.compress(payload.encode(), mtime=0)).decode()
    template = Path(__file__).with_name("viewer.html").read_text()
    embedded = '<script type="application/octet-stream" id="embedded-data">' + encoded + '</script>\n'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(template.replace("<script>\n'use strict';", embedded + "<script>\n'use strict';"))
    print(f"Saved {destination.resolve()} ({destination.stat().st_size / 1024**2:.1f} MB). Open directly in a browser.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="Directory containing checkpoint.json and calls/")
    parser.add_argument("--port", type=int, default=8765)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--rows", type=int, help="Show only the first N worlds from the run")
    selection.add_argument("--worlds", type=int, nargs="+", help="Show these world numbers (1-based)")
    parser.add_argument("--html", type=Path, help="Export one self-contained HTML file instead of starting a server")
    args = parser.parse_args()
    if not args.run.is_dir():
        parser.error(f"Run directory does not exist: {args.run}")
    if args.rows is not None and args.rows < 1:
        parser.error("--rows must be positive")
    if args.worlds and (min(args.worlds) < 1 or len(set(args.worlds)) != len(args.worlds)):
        parser.error("--worlds must contain distinct positive world numbers")
    worlds = [i - 1 for i in args.worlds] if args.worlds else None
    run = Run(args.run.resolve(), args.rows, worlds)
    if args.html:
        export_html(run, args.html)
        return
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, run=run))
    print(f"Viewing {args.run.resolve()}\nOpen http://localhost:{server.server_port} (Ctrl-C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
