import asyncio
from copy import deepcopy
import json
import random

import httpx
import pytest

import systems_bench as b


@pytest.fixture
def blueprint():
    return dict(inputs=[dict(name=f"condition {i}", values=[f"state {j}" for j in range(3 + i % 2)]) for i in range(6)],
                metrics=[dict(name=f"metric {i}", outcomes=[f"outcome {i}-{j}" for j in range(4 + i % 3)]) for i in range(8)])


def test_random_mappings_ignore_label_meanings(blueprint):
    world = b.build_world(blueprint, 1, "An otter by a river")
    assert world == b.build_world(blueprint, 1, "An otter by a river")
    renamed = deepcopy(blueprint)
    for metric in renamed["metrics"]:
        metric["outcomes"] = ["renamed " + s for s in metric["outcomes"]]
    routes = lambda w: [(g["root"], g["branches"], g["nodes"]) for g in w["graphs"]]
    assert routes(world) == routes(b.build_world(renamed, 1, "An otter by a river"))
    assert routes(world) != routes(b.build_world(blueprint, 2, "An otter by a river"))


@pytest.mark.parametrize("input_count", [5, 6])
def test_conditional_graphs_cover_all_outcomes_and_both_depths(blueprint, input_count):
    blueprint["inputs"] = blueprint["inputs"][:input_count]
    shapes = set()
    for seed in range(60):
        world = b.build_world(blueprint, seed, "An otter by a river")
        for graph in world["graphs"]:
            direct, mediated = set(), set()
            shapes.add((len(graph["branches"]), len(graph["nodes"])))
            for case in b.assignments(graph):
                required = b.required_inputs(graph, case)
                minimal = {k: case[k] for k in required}
                gold = b.evaluate(graph, case)
                assert b.evaluate(graph, minimal) == gold
                (direct if len(required) == 1 else mediated).add(gold)
                if len(required) == 1:
                    second = next(k for k in graph["inputs"] if k not in minimal)
                    assert all(b.evaluate(graph, minimal | {second:v}) == gold for v in range(graph["inputs"][second]))
                else:
                    assert len({b.evaluate(graph, minimal | {required[1]:v}) for v in range(graph["inputs"][required[1]])}) > 1
            assert direct and mediated and not direct & mediated
            assert direct | mediated == set(range(len(graph["outcomes"])))
    assert len(shapes) >= 3


def test_second_criterion_is_only_read_on_its_branch():
    graph = dict(root="a", branches=[dict(outcome=0),dict(node=0),dict(node=1)],
                 nodes=[dict(input="b",table=[1,2,3]),dict(input="b",table=[3,1,2])])
    assert b.evaluate(graph,{"a":0}) == 0
    assert b.required_inputs(graph,{"a":0}) == ["a"]
    assert [b.evaluate(graph,{"a":1,"b":i}) for i in range(3)] == [1,2,3]
    assert [b.evaluate(graph,{"a":2,"b":i}) for i in range(3)] == [3,1,2]
    with pytest.raises(KeyError):
        b.evaluate(graph,{"a":1})


def test_sampling_counts_and_inactive_second_criterion(blueprint):
    world=b.build_world(blueprint,4,"An otter by a river")
    counts, decorations, positions, depths=set(),set(),set(),set()
    saw_inactive_second=False
    for seed in range(100):
        for i,g in enumerate(world["graphs"]):
            s=b.sample(world,i,random.Random(seed))
            gold=b.evaluate(g,s["conditions"])
            assert s["outcomes"][s["correct_option"]] == gold
            assert len(set(s["outcomes"])) == 4
            assert not set(s["conditions"]) & set(s["distractors"])
            for k in s["distractors"]:
                variable=next(v for v in world["inputs"] if v["id"]==k)
                assert all(b.evaluate(g,s["conditions"]|{k:v})==gold for v in range(len(variable["values"])))
                if k in g["inputs"]:
                    saw_inactive_second=True
                    assert len(s["conditions"])==1
            counts.add(len(s["distractors"])); decorations.add(s["decoration_count"])
            positions.add(s["correct_option"]); depths.add(len(s["conditions"]))
    assert counts=={0,1} and decorations=={1,2} and depths=={1,2}
    assert positions=={0,1,2,3} and saw_inactive_second


@pytest.mark.parametrize("fault",["first_again","incomplete","unreachable","no_second_effect","bad_node"])
def test_invalid_graphs_rejected(blueprint,fault):
    w=b.build_world(blueprint,5,"An otter by a river");g=w["graphs"][0];n=g["nodes"][0]
    if fault=="first_again":n["input"]=g["root"]
    elif fault=="incomplete":n["table"].pop()
    elif fault=="unreachable":g["nodes"].append(deepcopy(n))
    elif fault=="no_second_effect":n["table"]=[n["table"][0]]*len(n["table"])
    else:next(x for x in g["branches"] if "node" in x)["node"]=99
    with pytest.raises((ValueError,b.ValidationError)):b.validate_world(w)


class FakeModels:
    def __init__(self,blueprint):
        self.blueprint,self.calls,self.settings=blueprint,[],{}
        self.reject=False
    async def call(self,key,prompt,schema,**kwargs):
        self.calls.append((key,prompt));self.settings[key]=kwargs
        if schema==b.BLUEPRINT:return deepcopy(self.blueprint)
        if schema==b.CHECK:return dict(valid=not self.reject,reason="World review")
        if schema==b.QUESTION:
            spec=json.loads(prompt[len(b.QUESTION_PROMPT):])
            return dict(question="Scene "+key+". "+spec["metric"]+": "+", ".join(d["value"] for d in spec["details"]))
        if schema==b.ANSWER:return dict(answer=json.loads(prompt[len(b.ANSWER_PROMPT):])["outcome"])
        if prompt.startswith(b.CHECK_PROMPT):
            payload=json.loads(prompt[len(b.CHECK_PROMPT):]);spec=payload["specification"]
            assert schema["properties"]["question"]["properties"]["evidence"]["minItems"]==len(spec["details"])
            return dict(question=dict(evidence=[d["value"] for d in spec["details"]],valid=not self.reject,reason="Question review"),
                        distractors=dict(valid=not self.reject,reason="Distractor review"),
                        answers=[dict(valid=True,reason="Answer review") for _ in range(4)])
        if prompt.startswith(b.DECORATION_PROMPT):
            count=json.loads(prompt[len(b.DECORATION_PROMPT):])["count"]
            return dict(details=[dict(attribute=f"name {i}",value=f"Pip{key}{i}") for i in range(count)])
        raise AssertionError(key)


@pytest.mark.parametrize("decoration_count",[1,2])
def test_isolated_writers_and_shared_answer_variation(blueprint,decoration_count):
    w=b.build_world(blueprint,8,"An otter by a river")
    s=next(s for seed in range(100) if (s:=b.sample(w,0,random.Random(seed)))["decoration_count"]==decoration_count)
    m=FakeModels(blueprint);item=asyncio.run(b.render(m,"q",w,s))
    assert item["verification"]["passed"]
    qp=json.loads(next(p for k,p in m.calls if k=="q-question")[len(b.QUESTION_PROMPT):])
    assert set(qp)=={"setting","metric","details","variation"}
    assert qp["details"]==item["sampling"]["details"]
    answers=[json.loads(p[len(b.ANSWER_PROMPT):]) for k,p in m.calls if "-answer-" in k]
    assert len(answers)==4 and len({a["variation"] for a in answers})==1
    assert all(set(a)=={"system","metric","outcome","variation"} and a["system"]==w["setting"] for a in answers)
    assert m.settings["q-question"]=={"thinking":True}
    assert all(m.settings[f"q-answer-{i}"]=={} for i in range(4))
    assert [k for k,_ in m.calls]==["q-decorations","q-question",*[f"q-answer-{i}" for i in range(4)],"q-check"]
    check=json.loads(next(p for k,p in m.calls if k=="q-check")[len(b.CHECK_PROMPT):])
    assert set(check["distractor_plan"])=={"environmental","acausal"}
    assert len(check["distractor_plan"]["environmental"])==len(s["distractors"])
    assert len(check["distractor_plan"]["acausal"])==decoration_count
    assert "correct_option" not in check
    assert not m.settings["q-check"].get("thinking", False)
    assert [d["inactive_second_criterion"] for d in check["distractor_plan"]["environmental"]] == [k in w["graphs"][0]["inputs"] for k in s["distractors"]]
    other=FakeModels(blueprint)
    with pytest.raises(ValueError,match="disagrees"):
        asyncio.run(b.render(other,"q",w,dict(s,correct_option=(s["correct_option"]+1)%4)))
    assert other.calls == m.calls
    assert all("correct_option" not in p for _,p in m.calls)


@pytest.mark.parametrize("fault",["question","distractors","answer","evidence","length"])
def test_automatic_filtering_preserves_quotas_and_resume(blueprint,tmp_path,fault):
    class Failure(FakeModels):
        async def call(self,key,prompt,schema,**kwargs):
            result=await super().call(key,prompt,schema,**kwargs)
            if fault=="length" and key=="0-train-0-question":result["question"]="word "*(b.QUESTION_WORDS+1)
            if key=="0-train-0-check":
                if fault=="evidence":result["question"]["evidence"][0]="Not in the question"
                elif fault in ("question","distractors"):result[fault]["valid"]=False
                elif fault=="answer":result["answers"][2]["valid"]=False
            return result
    args=b.parse_args(["--output-dir",str(tmp_path)])
    m=Failure(blueprint);state=asyncio.run(b.generate(args,m));row=state["systems"][0]
    assert row["attempts"]==dict(train=17,test=8)
    assert all(q["verification"]["passed"] for q in row["train"])
    assert len([k for k,_ in m.calls if k.endswith("-question")])==25
    calls=len(m.calls);assert asyncio.run(b.generate(args,m))==state and len(m.calls)==calls
    exported=b.export(state,tmp_path)[0]
    assert len(exported["train_data"])==16 and len(exported["test_data"])==8
    assert all(q["verification"]["passed"] for q in exported["train_data"])
    for split,n in [("train",2),("test",1)]:
        assert [sum(q["sampling"]["graph"]==g for q in row[split]) for g in range(8)]==[n]*8


@pytest.mark.parametrize("revise",[False,True])
def test_world_is_checked_and_revised_as_one_batch(blueprint,revise):
    m=FakeModels(blueprint);m.reject=revise
    world=asyncio.run(b.prepare_world(m,"w",dict(name="Otter by river"),42))
    b.validate_world(world)
    assert [k for k,_ in m.calls]==["w-world","w-world-check"]+(["w-world-revise"] if revise else [])
    check=json.loads(m.calls[1][1][len(b.WORLD_CHECK_PROMPT):])
    assert check==dict(setting="Otter by river",blueprint=blueprint)
    if revise:
        revision=json.loads(m.calls[2][1][len(b.WORLD_REVISE_PROMPT):])
        assert revision["blueprint"]==blueprint and revision["feedback"]=="World review"


def test_export_checks_gold_and_distractor_invariance(blueprint,tmp_path):
    args=b.parse_args(["--output-dir",str(tmp_path)]);state=asyncio.run(b.generate(args,FakeModels(blueprint)))
    bad=deepcopy(state);q=bad["systems"][0]["train"][0]
    q["correct_option"]=q["sampling"]["correct_option"]=(q["correct_option"]+1)%4
    with pytest.raises(ValueError,match="disagrees"):b.export(bad,tmp_path)
    bad=deepcopy(state);q=bad["systems"][0]["train"][0]
    k=next(iter(q["sampling"]["conditions"]));q["sampling"]["distractors"]={k:0}
    with pytest.raises(ValueError,match="affects"):b.export(bad,tmp_path)


def test_question_and_answer_writers_overlap(blueprint):
    async def run():
        answers_done = asyncio.Event()
        class Overlap(FakeModels):
            async def call(self, key, *args, **kwargs):
                if key == "q-question":
                    await answers_done.wait()
                result = await super().call(key, *args, **kwargs)
                if key == "q-answer-3":
                    answers_done.set()
                return result
        world = b.build_world(blueprint, 8, "An otter by a river")
        models = Overlap(blueprint)
        item = await asyncio.wait_for(b.render(models, "q", world, b.sample(world, 0, random.Random(1))), 2)
        assert item["verification"]["passed"]
        assert [k for k, _ in models.calls if "-answer-" in k] == [f"q-answer-{i}" for i in range(4)]
    asyncio.run(run())


def test_continuous_refill_checkpoint_and_resume(blueprint, tmp_path):
    async def run():
        blocked = asyncio.Event()
        class Slow(FakeModels):
            async def call(self, key, *args, **kwargs):
                if key == "0-train-0-check":
                    await blocked.wait()
                result = await super().call(key, *args, **kwargs)
                if key == "0-train-1-check":
                    result["question"]["valid"] = False
                return result
        args = b.parse_args(["--output-dir", str(tmp_path), "--concurrency", "24"])
        models = Slow(blueprint)
        task = asyncio.create_task(b.generate(args, models))
        try:
            async def wait_for_progress():
                while True:
                    await asyncio.sleep(0)
                    path = tmp_path / "checkpoint.json"
                    if path.exists():
                        row = json.loads(path.read_text())["systems"][0]
                        if len(row["train"]) == 15 and len(row["test"]) == 8:
                            return row
            before = await asyncio.wait_for(wait_for_progress(), 2)
            assert before["attempts"] == dict(train=17, test=8)
            assert list(before["pending"]) == ["0-train-0"]
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        # Completed examples survive; only the outstanding reservation resumes.
        resumed = FakeModels(blueprint)
        row = (await b.generate(args, resumed))["systems"][0]
        assert len(row["train"]) == 16 and len(row["test"]) == 8
        assert row["train"][:15] == before["train"] and row["test"] == before["test"]
        assert row["attempts"] == before["attempts"] and not row["pending"]
        assert all(k.startswith("0-train-0-") for k, _ in resumed.calls)
        original = dict(models.calls)
        assert all(original[k] == p for k, p in resumed.calls if k in original)
        assert [sum(q["sampling"]["graph"] == g for q in row["train"]) for g in range(8)] == [2]*8
    asyncio.run(run())


def test_api_payload_cache_and_permanent_errors(tmp_path):
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=dict(choices=[dict(finish_reason="stop", message=dict(content='{"answer":"A"}'))]))
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            models = b.Models(client, tmp_path, 1)
            assert await models.call("a", "Say A", b.ANSWER) == dict(answer="A")
            assert await models.call("a", "Say A", b.ANSWER) == dict(answer="A")
            assert await models.call("thinking", "Say A", b.ANSWER, thinking=True) == dict(answer="A")
            with pytest.raises(ValueError, match="changed"):
                await models.call("a", "Say B", b.ANSWER)
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(401))) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await b.Models(client, tmp_path, 1).call("b", "Say B", b.ANSWER)
    asyncio.run(run())
    assert len(requests) == 2
    for request in requests:
        assert request["max_tokens"] == 131072
        assert not set(request) & {"temperature", "top_p", "top_k", "min_p", "seed"}
    assert requests[0]["messages"][-1] == dict(role="user", content="Say A")




def test_retry_empty_completion_content(tmp_path, monkeypatch):
    attempts = []
    def respond(request):
        attempts.append(json.loads(request.content))
        content = None if len(attempts) == 1 else '{"answer":"The otter rests upright."}'
        return httpx.Response(200, json=dict(choices=[dict(finish_reason="stop", message=dict(content=content))]))
    async def no_wait(seconds):
        pass
    monkeypatch.setattr(b.asyncio, "sleep", no_wait)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await b.Models(client, tmp_path, 1).call("answer", "Write an answer", b.ANSWER)
    assert asyncio.run(run())["answer"] == "The otter rests upright."
    assert len(attempts) == 2 and attempts[0] == attempts[1]
