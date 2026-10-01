import asyncio
import copy
import json
import itertools
import re
from collections import Counter
import httpx
import pytest
import systems_bench as b


def ok(schema):
    return {k: True if v == b.BOOL else "OK" for k, v in schema["properties"].items()}


class FakeModels:
    def __init__(self, reject_first_worlds=False, collide=False):
        self.calls = []
        self.reject_first_worlds = reject_first_worlds
        self.collide = collide

    async def call(self, key, model, task, schema, *, thinking, **kwargs):
        self.calls.append((key, model, task, thinking))
        if key.endswith("/setting"):
            n = schema["properties"]["requests"]["minItems"]
            return {
                "shared": "A class observes a river otter.",
                "requests": [
                    {
                        "aspect": f"Situation {i}",
                        "factors": ["water clarity", "bank cover"][: 1 + i % 2],
                    }
                    for i in range(n)
                ],
            }
        if key.endswith("/plan"):
            n = schema["properties"]["worlds"]["items"]["minItems"]
            return {
                "worlds": [
                    [f"WORLD_{i} intent {j}" for j in range(n)]
                    for i in range(b.WORLD_COUNT)
                ]
            }
        if "/write-" in key:
            plan = json.loads(task.split("\n", 1)[1])["plan"]
            return {"rules": plan}
        if "/consistent-" in key:
            return {
                "consistent": not (self.reject_first_worlds and "worlds-0/" in key),
                "sufficient_complexity": True,
                "reason": "Resolve the bank conflict.",
            }
        if key.endswith("/collisions"):
            count = schema["properties"]["rule_examples"]["minItems"]
            return {**ok(b.COLLISIONS), "rule_examples": [
                {"distinguishable": True, "question": f"Inspection example for aspect {i}?",
                 "answers": [f"Distinct outcome {w}" for w in range(b.WORLD_COUNT)], "reason": "OK"}
                for i in range(count)
            ]}
        if "/questions-" in key:
            n = schema["properties"]["questions"]["minItems"]
            return {
                "questions": [
                    f"What does the otter do beside the clear pool? Scene {key} {i}"
                    for i in range(n)
                ]
            }
        if "/answer-" in key:
            i = re.search(r"WORLD_(\d)", task).group(1)
            return {"answer": f"The otter gives response {i}.", "answerable": True}
        if "/verify-" in key:
            i = re.search(r"WORLD_(\d)", task).group(1)
            return {
                c: self.collide or f"response {i}." in o
                for c, o in re.findall(r"([ABCD])\. (.*)", task)
            }
        if "/possible-" in key:
            return dict.fromkeys(b.OPTION_LABELS, True)
        if key.endswith("/language"):
            return ok(schema)
        if key.endswith("/deduplication"):
            return dict.fromkeys(b.OPTION_LABELS, True)
        raise AssertionError(key)


@pytest.mark.parametrize("train,test,rules", [(32, 8, 4), (256, 100, 16)])
def test_offline_resume_export_and_reject_tampering(tmp_path, train, test, rules):
    args = b.parse_args(
        [
            "--systems",
            "1",
            "--rules",
            str(rules),
            "--train",
            str(train),
            "--test",
            str(test),
            "--output-dir",
            str(tmp_path),
        ]
    )
    models = FakeModels()
    state = asyncio.run(b.generate(args, models))
    s = state["systems"][0]
    assert len(s["items"]) == train + test
    assert len(s["drafts"]) == train + test  # Passing drafts never exceed remaining quotas.
    assert len({b.question_key(q["question"]) for q in s["items"]}) == train + test
    resumed = FakeModels()
    assert asyncio.run(b.generate(args, resumed)) == state
    assert resumed.calls == []
    b.export(state, tmp_path)
    row = json.loads((tmp_path / "systems_bench.jsonl").read_text())
    assert "question_world_answer" not in json.dumps(row)
    assert "inspection only" in (tmp_path / "review.md").read_text()
    assert set(row) == {"Setting", "World", "num_train", "num_test", "train_data", "test_data"}
    assert row["Setting"] == s["shared"]
    assert row["World"] == b.world_text(s["shared"], s["worlds"][s["gold"]])
    assert (len(row["train_data"]), len(row["test_data"])) == (train, test)
    exported = row["train_data"] + row["test_data"]
    assert [q["question"] for q in exported] != [q["question"] for q in s["items"]]
    assert {q["question"] for q in exported} == {q["question"] for q in s["items"]}
    for split in ("train", "test"):
        counts = Counter(q["correct_option"] for q in row[split + "_data"])
        assert len({counts.get(i, 0) for i in range(b.OPTION_COUNT)}) > 1
        for q in row[split + "_data"]:
            assert f"response {s['gold']}." in q["options"][q["correct_option"]]
    b.export(state, tmp_path)
    assert json.loads((tmp_path / "systems_bench.jsonl").read_text()) == row
    altered = copy.deepcopy(state)
    altered["systems"][0]["items"][0]["gold_check"] = dict.fromkeys("ABCD", True)
    with pytest.raises(ValueError, match="provenance"):
        b.export(altered, tmp_path)
    altered = copy.deepcopy(state)
    item = altered["systems"][0]["items"][0]
    item["possible_check"] = dict(item["gold_check"])
    with pytest.raises(ValueError, match="provenance"):
        b.export(altered, tmp_path)
    altered = copy.deepcopy(state)
    altered["systems"][0]["items"][0]["uniqueness"]["B"] = False
    with pytest.raises(ValueError, match="provenance"):
        b.export(altered, tmp_path)
    altered = copy.deepcopy(state)
    del altered["systems"][0]["items"][0]["uniqueness"]
    with pytest.raises(ValueError, match="provenance"):
        b.export(altered, tmp_path)
    altered = copy.deepcopy(state)
    altered["systems"][0]["consistency"][0]["consistent"] = False
    with pytest.raises(ValueError, match="world set"):
        b.export(altered, tmp_path)


@pytest.mark.parametrize("thinking", [False, True])
def test_cached_requests_preserve_thinking_toggle_and_validate_json(tmp_path, monkeypatch, thinking):
    monkeypatch.setitem(b.THINKING, "answers", thinking)
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {"answer": "It swims.", "answerable": True}
                            )
                        },
                    }
                ]
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            models = b.Models(client, tmp_path)
            first = await b.answer(models, "a", "WORLD", "QUESTION", "STYLE")
            assert await b.answer(models, "a", "WORLD", "QUESTION", "STYLE") == first
            with pytest.raises(ValueError, match="Changed request"):
                await b.answer(models, "a", "CHANGED", "QUESTION", "STYLE")

    asyncio.run(run())
    assert len(requests) == 1
    assert requests[0]["chat_template_kwargs"] == {"enable_thinking": thinking}
    assert "provider" not in requests[0]
    assert "reasoning" not in requests[0]
    assert requests[0]["max_tokens"] == (b.MAX_OUTPUT_TOKENS if thinking else b.NO_THINKING_OUTPUT_TOKENS)
    assert requests[0]["model"] == b.MODEL
    assert requests[0]["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "benchmark_response", "strict": True, "schema": b.ANSWER},
    }
    assert requests[0]["temperature"] == 1.0
    assert (
        json.loads(requests[0]["messages"][0]["content"].split("Response schema:\n")[1])
        == b.ANSWER
    )


def test_stable_world_prefix_and_no_arithmetic():
    models = FakeModels()
    asyncio.run(
        b.answer(
            models, "x/answer-0", "WORLD_0 " * 200, "first question", "first style"
        )
    )
    asyncio.run(
        b.answer(
            models, "y/answer-0", "WORLD_0 " * 200, "second question", "second style"
        )
    )
    p, q = [call[2] for call in models.calls]
    assert p.split("\nStyle:")[0] == q.split("\nStyle:")[0]
    assert "without arithmetic" in b.SYSTEM_PROMPT
    models.calls.clear()
    asyncio.run(b.language_check(models, "x/language", "One plus one."))
    assert "Reject every calculation" in models.calls[0][2]
    assert models.calls[0][3] is False


def test_model_calls_are_parallel_but_bounded(tmp_path):
    async def run():
        active = peak = 0

        async def respond(request):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": '{"answer":"It swims.","answerable":true}'
                            },
                        }
                    ]
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            models = b.Models(client, tmp_path, concurrency=2)
            await b.settled(
                *(
                    b.answer(models, str(i), "WORLD", "QUESTION", "STYLE")
                    for i in range(6)
                )
            )
        assert peak == 2

    asyncio.run(run())


def test_question_batches_exclude_full_rules_and_cap_each_remaining_quota():
    system = {"quota": [45, 45, 44, 44], "items": [
        {"target": rule} for rule, count in enumerate([45, 44, 41, 0])
        for _ in range(count)
    ]}
    targets = b.question_targets(system, 16)
    assert len(targets) == 16
    assert Counter(i for batch in targets for i in batch) == {1: 1, 2: 3, 3: 16}
    assert targets[0] == [1, 2, 3]
    assert targets[3:] == [[3]] * 13
    system["items"] = [{"target": i} for i, quota in enumerate(system["quota"]) for _ in range(quota)]
    assert b.question_targets(system, 16) == []
    system["items"].pop()
    assert b.question_targets(system, 16) == [[3]]


@pytest.mark.parametrize("initial_bad", [3, 16])
def test_retirement_cap_is_cumulative_and_preserves_questions_and_total_quota(initial_bad):
    assert b.parse_args([]).rules == 16
    system = {
        "rule_results": [
            {"generated": 230 if i < initial_bad else 20, "checked": 20, "passed": 4 if i < initial_bad else 12, "rejected_rounds": [0, 1, 2]}
            for i in range(16)
        ],
        "retired": [], "substitutions": [], "round": 3,
        "quota": [23 if i < 4 else 22 for i in range(16)],
        "items": [{"target": i} for i in range(16) for _ in range(4 if i < initial_bad else 12)],
    }
    items = copy.deepcopy(system["items"])
    b.retire_rules(system)
    assert len(system["retired"]) == min(initial_bad, 4)
    for stats in system["rule_results"]:
        stats["generated"] = 10000  # Remaining rules now also exceed their candidate budgets.
    system["round"] = 4
    b.retire_rules(system)
    assert len(system["retired"]) == 4
    assert sum(system["quota"]) == 356
    assert system["items"] == items
    counts = Counter(item["target"] for item in items)
    assert all(system["quota"][i] == counts[i] for i in system["retired"])
    saved = copy.deepcopy(system)
    b.retire_rules(system)
    assert system == saved


@pytest.mark.parametrize("non_unique", list(b.OPTION_LABELS))
def test_non_unique_answer_rejects_question_even_when_other_checks_pass(non_unique):
    class DuplicateModels(FakeModels):
        async def call(self, key, model, task, schema, **kwargs):
            result = await super().call(key, model, task, schema, **kwargs)
            if key.endswith("/deduplication"):
                result[non_unique] = False
            return result

    models = DuplicateModels()
    system = {"shared": "A river otter.", "worlds": [[f"WORLD_{i}"] for i in range(5)], "gold": 0, "question_world": 4}
    item, reason = asyncio.run(b.evaluate_question(models, "q", system, {"question": "What does the otter do?", "target": 0}, 42))
    assert item is None
    assert reason == "duplicate_answers"
    call = next(c for c in models.calls if c[0].endswith("/deduplication"))
    assert call[3] is False
    assert "What does the otter do?" in call[2]
    assert len(re.findall(r"^[ABCD]\. ", call[2], re.MULTILINE)) == 4
    assert "WORLD_" not in call[2]  # No privileged world or correct-answer context.


def test_schema_echo_is_rejected_even_when_transport_returns_http_200(tmp_path, monkeypatch):
    monkeypatch.setattr(b, "REQUEST_ATTEMPTS", 1)
    async def run():
        def respond(request):
            payload = json.loads(request.content)
            assert payload["response_format"]["json_schema"]["schema"] == b.ANSWER
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(b.ANSWER)}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with pytest.raises(b.SettingExhausted):
                await b.answer(b.Models(client, tmp_path), "answer", "WORLD", "QUESTION", "STYLE")
        assert not (tmp_path / "answer.json").exists()
    asyncio.run(run())


def test_invalid_server_schema_request_fails_without_eight_retries(tmp_path):
    requests = []
    async def run():
        def respond(request):
            requests.append(request)
            return httpx.Response(400, json={"error": "unsupported schema"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await b.answer(b.Models(client, tmp_path), "answer", "WORLD", "QUESTION", "STYLE")
    asyncio.run(run())
    assert len(requests) == 1


def test_setting_schema_preserves_both_factor_counts_without_contains():
    from jsonschema import Draft202012Validator
    schema = b.request_schema(8)
    assert '"contains"' not in json.dumps(schema)
    validator = Draft202012Validator(schema)
    for counts in itertools.product((1, 2), repeat=8):
        value = [{"aspect": f"response {i}", "factors": ["wind", "cloud"][:n]} for i, n in enumerate(counts)]
        assert validator.is_valid(value) == (len(set(counts)) == 2)
    valid = [{"aspect": "response", "factors": ["wind", "cloud"][:1 + i % 2]} for i in range(8)]
    assert not validator.is_valid(valid[:-1])
    assert not validator.is_valid(valid + valid[:1])


def test_parallel_rows_resume_and_global_question_uniqueness(tmp_path, monkeypatch):
    args = b.parse_args(['--systems', '3', '--rules', '4', '--train', '32',
                         '--test', '8', '--row-concurrency', '2',
                         '--output-dir', str(tmp_path)])
    original = b.prepare_system
    active = peak = 0

    async def prepare(*a, **kw):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        try:
            return await original(*a, **kw)
        finally:
            active -= 1

    monkeypatch.setattr(b, 'prepare_system', prepare)
    class RepeatingModels(FakeModels):
        async def call(self, key, *a, **kw):
            result = await super().call(key, *a, **kw)
            if '/round-0000/questions-0' in key:
                result['questions'][0] = 'What does the otter do beside the clear pool?'
            return result

    state = asyncio.run(b.generate(args, RepeatingModels()))
    assert peak == 2
    assert len(state['systems']) == 3
    assert all(len(s['items']) == 40 for s in state['systems'])
    questions = [b.question_key(i['question']) for s in state['systems'] for i in s['items']]
    assert len(questions) == len(set(questions)) == 120
    resumed = FakeModels()
    assert asyncio.run(b.generate(args, resumed)) == state
    assert not resumed.calls
    b.export(state, tmp_path)
    assert len((tmp_path / 'systems_bench.jsonl').read_text().splitlines()) == 3


def test_parallel_failure_cancels_other_rows_and_resumes(tmp_path, monkeypatch):
    args = b.parse_args(['--systems', '3', '--rules', '4', '--train', '32',
                         '--test', '8', '--row-concurrency', '2',
                         '--output-dir', str(tmp_path)])
    original = b.prepare_system
    cancelled = []

    async def scenario():
        entered = asyncio.Event()

        async def prepare(models, key, *a):
            if key == 'system-001':
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.append(key)
            await entered.wait()
            return await original(models, key, *a)

        class FailingModels(FakeModels):
            async def call(self, key, *a, **kw):
                if '/questions-' in key:
                    raise RuntimeError('injected failure')
                return await super().call(key, *a, **kw)

        monkeypatch.setattr(b, 'prepare_system', prepare)
        with pytest.raises(ExceptionGroup, match='TaskGroup'):
            await b.generate(args, FailingModels())

    asyncio.run(scenario())
    assert cancelled == ['system-001']
    saved = json.loads((tmp_path / 'checkpoint.json').read_text())
    assert saved['systems'][0] is not None
    assert saved['systems'][1:] == [None, None]
    monkeypatch.setattr(b, 'prepare_system', original)
    state = asyncio.run(b.generate(args, FakeModels()))
    assert all(len(s['items']) == 40 for s in state['systems'])


@pytest.mark.parametrize('failure', ['world', 'question', 'request'])
def test_exhausted_setting_is_replaced_once_and_resume_keeps_assignment(tmp_path, monkeypatch, failure):
    args = b.parse_args(['--systems', '2', '--rules', '4', '--train', '32', '--test', '8',
                         '--row-concurrency', '2', '--output-dir', str(tmp_path)])
    original_prepare, original_evaluate = b.prepare_system, b.evaluate_question

    async def prepare(models, key, *a):
        if key == 'system-000' and failure in ('world', 'request'):
            raise b.SettingExhausted(f'{failure} limit exhausted')
        return await original_prepare(models, key, *a)

    async def evaluate(models, key, *a):
        if key.startswith('system-000/round-') and failure == 'question':
            return None, 'duplicate_answers'
        return await original_evaluate(models, key, *a)

    monkeypatch.setattr(b, 'prepare_system', prepare)
    monkeypatch.setattr(b, 'evaluate_question', evaluate)
    state = asyncio.run(b.generate(args, FakeModels()))
    assert state['assignments'] == [2, 1]
    assert state['next_setting'] == 3
    assert len(state['discarded']) == 1
    assert state['discarded'][0]['catalogue_index'] == 0
    assert all(len(s['items']) == 40 for s in state['systems'])
    if failure == 'question':
        assert sum(r['generated'] for r in state['discarded'][0]['system']['rule_results']) == 20 * 40
    resumed = FakeModels()
    assert asyncio.run(b.generate(args, resumed)) == state
    assert not resumed.calls
    b.export(state, tmp_path)


def test_catalogue_exhaustion_preserves_discarded_rows(tmp_path, monkeypatch):
    args = b.parse_args(['--systems', '2', '--rules', '4', '--train', '32', '--test', '8',
                         '--row-concurrency', '2', '--output-dir', str(tmp_path)])
    ideas = b.catalogue()[:4]
    monkeypatch.setattr(b, 'catalogue', lambda: ideas)
    attempted = []

    async def fail(models, key, idea, *a):
        attempted.append(idea['name'])
        await asyncio.sleep(0)
        raise b.SettingExhausted('world limit')

    monkeypatch.setattr(b, 'prepare_system', fail)
    with pytest.raises(ExceptionGroup) as error:
        asyncio.run(b.generate(args, FakeModels()))
    assert any(isinstance(e, b.CatalogueExhausted) for e in error.value.exceptions)
    state = json.loads((tmp_path / 'checkpoint.json').read_text())
    assert len(attempted) == len(set(attempted)) == 4
    assert len(state['discarded']) == 4
    assert state['next_setting'] == 4


@pytest.mark.parametrize('generated,accepted,quota,retired', [
    (29, 2, 3, False), (30, 2, 3, True), (31, 3, 3, False), (30, 2, 4, False),
])
def test_retirement_uses_generated_count_and_current_unfilled_quota(generated, accepted, quota, retired):
    system = {
        'rule_results': [
            {'generated': generated, 'checked': accepted, 'passed': accepted, 'rejected_rounds': []},
            {'generated': 1, 'checked': 1, 'passed': 1, 'rejected_rounds': []},
        ],
        'quota': [quota, 3], 'items': [{'target': 0}] * accepted + [{'target': 1}],
        'retired': [], 'substitutions': [], 'round': 1,
    }
    b.retire_rules(system)
    assert (0 in system['retired']) == retired


def test_question_targets_never_exceed_remaining_row_budget():
    system = {'quota': [23, 23, 22, 22], 'items': []}
    assert b.question_targets(system, 16, 6) == [[0, 1, 2, 3], [0, 1]]
    assert b.question_targets(system, 16, 0) == []


def test_duplicate_generated_questions_consume_row_budget(tmp_path, monkeypatch):
    args = b.parse_args(['--systems', '1', '--rules', '4', '--train', '32', '--test', '8',
                         '--output-dir', str(tmp_path)])
    original = b.question_batch

    async def questions(models, key, system, targets, seed):
        if '/setting-' not in key:
            return [{'question': 'What does the otter do beside the clear pool?', 'target': i}
                    for i in targets]
        return await original(models, key, system, targets, seed)

    monkeypatch.setattr(b, 'question_batch', questions)
    state = asyncio.run(b.generate(args, FakeModels()))
    discarded = state['discarded'][0]['system']
    assert sum(r['generated'] for r in discarded['rule_results']) == 800
    assert len(discarded['drafts']) == len(discarded['items']) == 1
    assert len(state['systems'][0]['items']) == 40
    assert state['assignments'] == [1]


def test_last_budgeted_candidates_are_evaluated_before_discard(tmp_path, monkeypatch):
    args = b.parse_args(['--systems', '1', '--rules', '4', '--train', '32', '--test', '8',
                         '--output-dir', str(tmp_path)])
    monkeypatch.setattr(b, 'ROW_CANDIDATE_MULTIPLIER', 1)
    state = asyncio.run(b.generate(args, FakeModels()))
    assert not state['discarded']
    assert len(state['systems'][0]['items']) == 40
    assert sum(r['generated'] for r in state['systems'][0]['rule_results']) == 40


def test_collision_examples_gate_revision_and_are_inspection_only(tmp_path):
    class ExampleModels(FakeModels):
        async def call(self, key, *a, **kw):
            result = await super().call(key, *a, **kw)
            if key.endswith('/collisions'):
                for i, example in enumerate(result['rule_examples']):
                    example['question'] = f'INSPECTION_ONLY_EXAMPLE_{i}'
                if '/worlds-0/' in key:
                    # The per-rule result must override a mistaken global true.
                    result['rule_examples'][0].update(
                        distinguishable=False, question='', answers=[''] * 5,
                        reason='Worlds one and two make the same prediction for rule one.',
                    )
            return result

    args = b.parse_args(['--systems', '1', '--rules', '4', '--train', '32', '--test', '8',
                         '--output-dir', str(tmp_path)])
    models = ExampleModels()
    state = asyncio.run(b.generate(args, models))
    assert sum('/write-' in key for key, *_ in models.calls) == 10
    revision = next(task for key, _, task, _ in models.calls if '/worlds-1/plan' in key)
    assert 'rule_checks' in revision
    assert 'Worlds one and two' in revision
    assert 'INSPECTION_ONLY_EXAMPLE' not in revision
    assert all('INSPECTION_ONLY_EXAMPLE' not in task for key, _, task, _ in models.calls
               if '/questions-' in key)
    b.export(state, tmp_path)
    assert 'INSPECTION_ONLY_EXAMPLE' in (tmp_path / 'review.md').read_text()
    assert 'INSPECTION_ONLY_EXAMPLE' not in (tmp_path / 'systems_bench.jsonl').read_text()
    assert len(state['systems'][0]['drafts']) == 40
    damaged = copy.deepcopy(state)
    damaged['systems'][0]['collisions']['rule_examples'][0]['question'] = ''
    with pytest.raises(ValueError, match='world set'):
        b.export(damaged, tmp_path)


def test_collision_evidence_requires_every_rule_and_five_distinct_answers():
    check = {**ok(b.COLLISIONS), 'rule_examples': [
        {'distinguishable': True, 'question': f'Question {i}?',
         'answers': [f'Outcome {w}' for w in range(5)], 'reason': 'OK'} for i in range(16)
    ]}
    assert b.collisions_passed(check, 16)
    for modification in ('missing_rule', 'false', 'empty_answer', 'duplicate_answer'):
        bad = copy.deepcopy(check)
        if modification == 'missing_rule':bad['rule_examples'].pop()
        elif modification == 'false':bad['rule_examples'][0]['distinguishable'] = False
        elif modification == 'empty_answer':bad['rule_examples'][0]['answers'][3] = ''
        else:bad['rule_examples'][0]['answers'][3] = bad['rule_examples'][0]['answers'][0]
        assert not b.collisions_passed(bad, 16)
