"""Read-only, local viewer for a SystemsBench run: python view_run.py RUN_DIR."""

import argparse
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
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
    def __init__(self, directory):
        self.directory = directory

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
            candidates.append(dict(key=key, system=int(match[1]), split=match[2], attempt=int(match[3]),
                                   question=question, metric=(call["inputs"] or {}).get("metric"),
                                   retained=location is not None, reviewed=checks is not None,
                                   model_passed=valid))
        candidates.sort(key=lambda c: (c["system"], c["split"] == "test", c["attempt"]))
        world_calls = [p.stem for p in (self.directory / "calls").glob("*-world*.json")]
        return dict(name=self.directory.name, **state, candidates=candidates,
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="Directory containing checkpoint.json and calls/")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not args.run.is_dir():
        parser.error(f"Run directory does not exist: {args.run}")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, run=Run(args.run.resolve())))
    print(f"Viewing {args.run.resolve()}\nOpen http://localhost:{server.server_port} (Ctrl-C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
