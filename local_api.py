"""Audit a self-hosted OpenAI-compatible endpoint; billing is node-based."""

import fcntl
import json
import re
import time
from pathlib import Path
from uuid import uuid4

import httpx


def atomic_json(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def final_content(text):
    """Remove inline thinking, including an unfinished block on truncation."""
    if not isinstance(text, str):
        return None
    return re.sub(r"<(think|thinking|reasoning)\b[^>]*>.*?(?:</\1\s*>|$)",
                  "", text, flags=re.DOTALL | re.IGNORECASE)


def audit_response(body):
    """Allowlist final text and token counts; never persist model reasoning."""
    if not isinstance(body, dict):
        return {}
    result = {"choices": [dict(
        finish_reason=choice.get("finish_reason"),
        message=dict(role="assistant", content=final_content(
            (choice.get("message") or {}).get("content"))))
        for choice in body.get("choices", []) if isinstance(choice, dict)]}
    usage = body.get("usage") or {}
    result["usage"] = {k: usage[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens")
                       if isinstance(usage.get(k), int)}
    for name in ("prompt_tokens_details", "completion_tokens_details"):
        result["usage"][name] = {k: v for k, v in (usage.get(name) or {}).items()
                                if isinstance(v, int)}
    return result


class AuditedClient(httpx.AsyncClient):
    """Persist prompts, final outputs and usage, without credentials or reasoning."""

    def __init__(self, audit_dir: Path, **kwargs):
        super().__init__(**kwargs)
        self.audit_dir = audit_dir
        audit_dir.mkdir(parents=True, exist_ok=True)
        self.lock = (audit_dir / ".lock").open("a")
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.totals = dict(attempts=0, http_successes=0, prompt_tokens=0,
                           completion_tokens=0, cached_prompt_tokens=0)
        # Stream old audits on resume; never retain all prompts/responses in RAM.
        for path in audit_dir.glob("*.json"):
            self.totals["attempts"] += 1
            self.count_response(json.loads(path.read_text()))

    async def __aexit__(self, *args):
        try:
            return await super().__aexit__(*args)
        finally:
            self.lock.close()

    def save(self, key, record):
        atomic_json(self.audit_dir / f"{key}.json", record)

    def count_response(self, record):
        usage = (record.get("response") or {}).get("usage") or {}
        self.totals["http_successes"] += record.get("status_code") == 200
        for key in ("prompt_tokens", "completion_tokens"):
            self.totals[key] += usage.get(key, 0)
        self.totals["cached_prompt_tokens"] += (
            usage.get("prompt_tokens_details") or {}
        ).get("cached_tokens", 0)

    def summary(self):
        atomic_json(self.audit_dir.parent / "usage.json", {
            "billing_basis": "National Compute node-hours; token counts are not dollar charges",
            **self.totals,
        })

    async def post(self, url, *, json, **kwargs):
        key = uuid4().hex
        record = {"request": json, "started_at": time.time(), "url": str(url)}
        self.save(key, record)
        self.totals["attempts"] += 1
        start = time.monotonic()
        try:
            response = await super().post(url, json=json, **kwargs)
            record["status_code"] = response.status_code
            try:
                record["response"] = audit_response(response.json())
            except ValueError:
                # A malformed/truncated response can contain unparsed reasoning.
                record["response_bytes"] = len(response.content)
            return response
        except httpx.HTTPError as error:
            record["transport_error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            record["elapsed_seconds"] = time.monotonic() - start
            self.save(key, record)
            self.count_response(record)
            self.summary()
