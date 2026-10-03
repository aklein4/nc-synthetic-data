from functools import partial
from http.server import ThreadingHTTPServer
import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from view_run import Handler, Run, prompt_parts


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_lineage_preserves_exact_calls_and_rejects_duplicate(tmp_path):
    details = [dict(attribute="Name", value="<script>not markup</script>")]
    item = dict(question="What happens?", options=["a", "b", "c", "d"], sampling=dict(details=details))
    save(tmp_path / "checkpoint.json", dict(config={}, systems=[dict(train=[item], test=[])]))
    spec = dict(metric="Motion", details=details)
    payload = dict(messages=[dict(role="user", content="Write naturally.\n" + json.dumps(spec))])
    verdict = dict(valid=True, reason="OK")
    review = dict(question=verdict, distractors=verdict, answers=[verdict] * 4)
    for index in [0, 1]:
        key = f"0-train-{index}"
        save(tmp_path / "calls" / f"{key}-question.json", dict(request=payload, result=dict(question=item["question"])))
        save(tmp_path / "calls" / f"{key}-check.json", dict(request=payload, result=review))
        for i, answer in enumerate(item["options"]):
            save(tmp_path / "calls" / f"{key}-answer-{i}.json", dict(request=payload, result=dict(answer=answer)))
    run = Run(tmp_path)
    summary = run.summary()
    assert summary["systems"][0]["train"][0]["key"] == "0-train-0"
    assert [c["retained"] for c in summary["candidates"]] == [True, False]
    call = run.call("0-train-0-question")
    assert call["request"] == payload
    assert call["instructions"] == "Write naturally."
    assert call["inputs"] == spec
    with pytest.raises(ValueError):
        run.call("../../api_audit/private")


def test_live_run_and_http_routes_never_serve_audits(tmp_path):
    save(tmp_path / "api_audit" / "private.json", dict(reasoning_content="DO_NOT_SERVE"))
    run = Run(tmp_path)
    assert run.summary()["systems"] == []
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, run=run))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/api/run") as response:
            assert json.load(response)["complete"] is False
        with urlopen(base + "/") as response:
            assert "Content-Security-Policy" in response.headers
            assert b"SystemsBench" in response.read()
        for path in ["/api_audit/private.json", "/../api_audit/private.json", "/api/call?key=../private", "/api/call?key=missing"]:
            with pytest.raises(HTTPError) as error:
                urlopen(base + path)
            assert error.value.code == 404
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_prompt_json_is_separated_without_losing_content():
    text = 'Instructions with {braces}.\n{"a": "one\\ntwo", "b": [1, 2]} '
    instructions, inputs = prompt_parts(text)
    assert instructions == "Instructions with {braces}."
    assert inputs == dict(a="one\ntwo", b=[1, 2])
    assert prompt_parts("No structured input") == ("No structured input", None)
