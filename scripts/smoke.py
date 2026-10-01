"""Exercise every benchmark schema and replay the previously failing request."""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import systems_bench as b
from local_api import AuditedClient

parser = argparse.ArgumentParser()
parser.add_argument('--output-dir', type=Path, required=True)
args = parser.parse_args()


async def main():
    rule_count = b.DEFAULT_COUNTS['rules']
    requests = [{'aspect': f'aspect {i}', 'factors': ['wind', 'cloud'][:1 + i % 2]} for i in range(rule_count)]
    cases = [
        ('setting', b.obj(shared=b.STRING, requests=b.request_schema(rule_count)), {'shared': 'A weather station.', 'requests': requests}),
        ('plan', b.obj(worlds=b.arr(b.arr(b.STRING, rule_count), b.WORLD_COUNT)), {'worlds': [['rule'] * rule_count] * b.WORLD_COUNT}),
        ('world', b.obj(rules=b.arr(b.STRING, rule_count)), {'rules': ['rule'] * rule_count}),
        ('consistency', b.CONSISTENCY, {'consistent': True, 'sufficient_complexity': True, 'reason': 'OK'}),
        ('collisions', b.collision_schema(rule_count), {'distinct': True, 'shared_support': True, 'neutral_setting': True, 'reason': 'OK', 'rule_examples': [{'distinguishable': True, 'question': f'Question {i}?', 'answers': [f'Outcome {w}' for w in range(b.WORLD_COUNT)], 'reason': 'OK'} for i in range(rule_count)]}),
        ('questions-1', b.obj(questions=b.arr(b.STRING, 1)), {'questions': ['What happens?']}),
        (f'questions-{rule_count}', b.obj(questions=b.arr(b.STRING, rule_count)), {'questions': ['What happens?'] * rule_count}),
        ('answer', b.ANSWER, {'answer': 'It moves.', 'answerable': True}),
        ('truth', b.TRUTH, dict.fromkeys(b.OPTION_LABELS, True)),
        ('uniqueness', b.UNIQUENESS, dict.fromkeys(b.OPTION_LABELS, True)),
        ('language', b.LANGUAGE, dict.fromkeys(b.LANGUAGE['properties'], True)),
    ]
    results = []
    async with AuditedClient(args.output_dir / 'api_audit', timeout=600) as client:
        models = b.Models(client, args.output_dir / 'calls', concurrency=16)
        # Sequential: fail immediately if any production schema cannot compile.
        for name, schema, expected in cases:
            start = time.monotonic()
            result = await models.call(name, b.MODEL, 'Return this JSON instance exactly:\n' + json.dumps(expected), schema, thinking=(name == "collisions"))
            assert result == expected, (name, result)
            results.append({'case': name, 'seconds': time.monotonic() - start})
            print('schema passed', name, flush=True)
        await models.call('thinking-answer', b.MODEL, 'Predict the otter swims. Set answerable true.', b.ANSWER, thinking=True, max_tokens=2048)
        await models.call('thinking-setting', b.MODEL, 'Return this JSON instance exactly:\n' + json.dumps(cases[0][2]), cases[0][1], thinking=True, max_tokens=2048)
        previous = Path('/mnt/shared/nc-synthetic-data/runs/otter-256-100/calls/system-000/round-0003/item-77/answer-4.json')
        record = json.loads(previous.read_text())
        task = record['request']['messages'][-1]['content']
        await b.settled(*(models.call(f'regression-{i}', b.MODEL, task, b.ANSWER, thinking=False) for i in range(8)))
        print('Thinking modes and eight replays of the previously failing answer passed.', flush=True)
        question = 'Which direction does the weather vane point?'
        duplicate = await b.deduplicate_answers(models, 'semantic-pair/deduplication', question, ['The vane points north.', 'The vane points toward the north.', 'The vane points south.', 'The vane points east.'])
        assert duplicate == dict(zip(b.OPTION_LABELS, [False, False, True, True])), duplicate
        distinct = await b.deduplicate_answers(models, 'semantic-distinct/deduplication', question, [f'The vane points {direction}.' for direction in ['north', 'south', 'east', 'west']])
        assert distinct == dict.fromkeys(b.OPTION_LABELS, True), distinct
        print('Semantic duplicate-pair and distinct-answer checks passed.', flush=True)
    (args.output_dir / 'smoke.json').write_text(json.dumps({'schema_cases': results, 'thinking_checks': 2, 'regression_replays': 8, 'deduplication_checks': 2, 'passed': True}, indent=2) + '\n')


asyncio.run(main())
