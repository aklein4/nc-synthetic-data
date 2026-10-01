import asyncio
import json

import httpx

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
