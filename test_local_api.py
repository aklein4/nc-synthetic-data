import asyncio
import json

import httpx
import pytest

from local_api import AuditedClient


def test_records_usage_and_http_errors_without_headers(tmp_path):
    def respond(request):
        assert request.headers["Authorization"] == "Bearer test-secret"
        assert "provider" not in json.loads(request.content)
        return httpx.Response(200, json={"usage": {
            "prompt_tokens": 100, "completion_tokens": 10,
            "prompt_tokens_details": {"cached_tokens": 80},
        }})

    async def run():
        async with AuditedClient(tmp_path / "audit", headers={"Authorization": "Bearer test-secret"},
                                 transport=httpx.MockTransport(respond)) as client:
            await client.post("http://mimo:8000/v1/chat/completions", json={"model": "mimo"})

    asyncio.run(run())
    usage = json.loads((tmp_path / "usage.json").read_text())
    assert usage["cached_prompt_tokens"] == 80
    assert usage["http_successes"] == 1
    assert "cost_usd" not in usage
    for path in tmp_path.rglob("*.json"):
        assert "test-secret" not in path.read_text()


def test_usage_resume_counts_old_records_once(tmp_path):
    async def run():
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200, json={'usage': {'prompt_tokens': 7, 'completion_tokens': 3}}))
        async with AuditedClient(tmp_path / 'audit', transport=transport) as client:
            await client.post('http://mimo:8000/v1/chat/completions', json={})
    asyncio.run(run())
    asyncio.run(run())
    usage = json.loads((tmp_path / 'usage.json').read_text())
    assert usage['attempts'] == usage['http_successes'] == 2
    assert usage['prompt_tokens'] == 14
    assert usage['completion_tokens'] == 6


@pytest.mark.parametrize("mode", ["complete", "truncated", "malformed"])
def test_reasoning_never_reaches_disk(tmp_path, mode):
    secret = "PRIVATE_REASONING_SENTINEL"
    body = dict(choices=[dict(finish_reason="stop" if mode == "complete" else "length",
        message=dict(content=(f"<think>{secret}</think>final" if mode == "complete"
                              else f"<think>{secret}"), reasoning_content=secret,
                     reasoning=secret, thinking=[dict(text=secret)]))],
        reasoning=secret, usage=dict(completion_tokens=123,
                                    completion_tokens_details=dict(reasoning_tokens=120)))
    def respond(request):
        if mode == "malformed":
            return httpx.Response(502, text=secret)
        return httpx.Response(200, json=body)
    async def run():
        async with AuditedClient(tmp_path / "audit", transport=httpx.MockTransport(respond)) as client:
            response = await client.post("http://mimo/v1/chat/completions", json={"messages": []})
            assert secret in response.text  # The caller still gets the original response.
    asyncio.run(run())
    for path in tmp_path.rglob("*.json"):
        assert secret not in path.read_text()
    record = json.loads(next((tmp_path / "audit").glob("*.json")).read_text())
    if mode == "complete":
        assert record["response"]["choices"][0]["message"]["content"] == "final"
        assert record["response"]["usage"]["completion_tokens_details"]["reasoning_tokens"] == 120
    if mode == "malformed":
        assert "response_text" not in record
