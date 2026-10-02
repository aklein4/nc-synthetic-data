"""Export selected real API attempts without reasoning; never modify run originals."""
import argparse, ast, concurrent.futures as cf, gzip, hashlib, json, os, re, time
from collections import Counter
from pathlib import Path


def key(text):
    import unicodedata
    return ' '.join(unicodedata.normalize('NFKC', text).split())


def digest(request):
    return hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read(path):
    return path, json.loads(path.read_text())


def strip_reasoning(value):
    if isinstance(value, dict):
        return {k: strip_reasoning(v) for k, v in value.items()
                if k not in {'reasoning', 'reasoning_content', 'thinking'}}
    if isinstance(value, list):
        return [strip_reasoning(x) for x in value]
    if isinstance(value, str) and '<think>' in value:
        return re.sub(r'<think>.*?</think>', '', value, flags=re.S).strip()
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--workers', type=int, default=48)
    args = parser.parse_args()
    run = args.run
    out = run / 'filtered_audit'
    out.mkdir(exist_ok=True)
    state = json.loads((run / 'checkpoint.json').read_text())
    assert len(state['systems']) == 64 and all(len(s['items']) == 356 for s in state['systems'])
    wanted = {}
    selected = []
    selected_keys = set()
    world_prefixes = []
    for node in ast.parse((run / 'code/systems_bench.py').read_text()).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in {
            'SETTING_PROMPT', 'PLAN_PROMPT', 'WORLD_PROMPT', 'CONSISTENCY_PROMPT', 'COLLISION_PROMPT'
        }:
            world_prefixes.append(ast.literal_eval(node.value).split('{', 1)[0])
    assert len(world_prefixes) == 5 and all(world_prefixes)
    start = time.time()
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for row, system in enumerate(state['systems']):
            base = run / 'calls' / f'system-{row:03d}'
            if state['replacement_counts'][row]:
                base /= f"setting-{system['catalogue_index']:03d}"
            accepted = {key(x['question']) for x in system['items']}
            chosen = {}
            rejected = Counter()
            for draft in system['drafts']:
                q = key(draft['question'])
                status = 'accepted' if q in accepted else 'rejected'
                rule = draft['target']
                if status == 'rejected':
                    if rejected[rule] >= 10:
                        continue
                    rejected[rule] += 1
                chosen[q] = {'row': row, 'rule': rule, 'status': status, 'question': draft['question']}
            assert len([v for v in chosen.values() if v['status'] == 'accepted']) == 356
            selected.extend(chosen.values())
            selected_keys.update(chosen)
            all_drafts = {key(x['question']) for x in system['drafts']}
            seen = set()
            found = set()
            item_paths = []
            for round_dir in sorted(base.glob('round-*')):
                batches = sorted(round_dir.glob('questions-*.json'), key=lambda p: int(p.stem.split('-')[-1]))
                pending_index = 0
                for path, record in pool.map(read, batches):
                    keep_batch = False
                    for question in record['result']['questions']:
                        q = key(question)
                        if q not in all_drafts or q in seen:
                            continue
                        seen.add(q)
                        if q in chosen:
                            found.add(q)
                            keep_batch = True
                            item_dir = round_dir / f'item-{pending_index}'
                            item_paths.extend((f, chosen[q]) for f in item_dir.glob('*.json'))
                        pending_index += 1
                    if keep_batch:
                        wanted[digest(record['request'])] = {'kind': 'question_generation', 'row': row}
            assert found == set(chosen), (row, 'unmapped questions', len(set(chosen)-found))
            paths = [x[0] for x in item_paths]
            for (_, record), (_, meta) in zip(pool.map(read, paths), item_paths):
                wanted[digest(record['request'])] = {'kind': 'question_evaluation', **meta}
            print(f'Indexed row {row+1}/64: 356 accepted, {sum(rejected.values())} rejected examples', flush=True)
        with (out / 'selection.jsonl').open('w') as f:
            for record in selected:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
        counts = Counter()
        matched = set()
        temporary = out / 'model_io.jsonl.gz.tmp'
        with gzip.open(temporary, 'wt', encoding='utf-8', compresslevel=3) as dest:
            def process(path):
                _, record = read(path)
                request = record['request']
                h = digest(request)
                meta = wanted.get(h)
                user = next((m['content'] for m in request.get('messages', []) if m['role'] == 'user'), '')
                if meta is None:
                    if not any(user.startswith(prefix) for prefix in world_prefixes):
                        return None
                    meta = {'kind': 'world_construction'}
                record = strip_reasoning(record)
                if meta['kind'] == 'question_generation':
                    for choice in (record.get('response') or {}).get('choices', []):
                        message = choice.get('message', {})
                        content = message.get('content')
                        try:
                            parsed = json.loads(content)
                            questions = parsed['questions']
                            kept = [(i, q) for i, q in enumerate(questions) if key(q) in selected_keys]
                            message['content'] = json.dumps({'questions': [q for _, q in kept]}, ensure_ascii=False)
                            choice['filtering'] = {'original_question_count': len(questions), 'retained_indices': [i for i, _ in kept], 'output_reencoded': True}
                        except (ValueError, TypeError, KeyError):
                            message['content'] = None
                            choice['filtering'] = {'unparseable_generation_output_omitted': True}
                    # Arbitrary non-JSON error bodies can contain excluded questions/reasoning.
                    if 'response_text' in record:
                        record['response_text'] = '[non-JSON response body omitted]'
                return h, {'audit_file': path.name, 'selection': meta, **record}
            batch = []
            def export_batch(batch):
                for result in pool.map(process, batch):
                    counts['scanned'] += 1
                    if result is None:
                        continue
                    h, record = result
                    matched.add(h)
                    counts['retained'] += 1
                    counts[record['selection']['kind']] += 1
                    dest.write(json.dumps(record, ensure_ascii=False) + '\n')
            for entry in os.scandir(run / 'api_audit'):
                if not entry.name.endswith('.json'):
                    continue
                batch.append(Path(entry.path))
                if len(batch) == 2048:
                    export_batch(batch)
                    batch = []
                    if counts['scanned'] % 20480 == 0:
                        print(f"Scanned {counts['scanned']:,}; retained {counts['retained']:,}; elapsed {(time.time()-start)/60:.1f} min", flush=True)
            if batch:
                export_batch(batch)
        missing = set(wanted) - matched
        assert not missing, f'{len(missing)} cached requests missing from audit'
        temporary.replace(out / 'model_io.jsonl.gz')
        manifest = {'source_run': str(run), 'rows': 64, 'accepted_questions': sum(x['status']=='accepted' for x in selected),
                    'rejected_examples': sum(x['status']=='rejected' for x in selected), 'max_rejected_per_row_rule': 10,
                    'rejected_selection': 'First up to 10 unique rejected drafts per rule of each final row; discarded settings question calls excluded.',
                    'world_calls': 'All world-construction attempts, including discarded settings and retries.',
                    'outputs': 'Original response content except reasoning removal and explicitly marked mixed-question batch filtering.',
                    'token_ids': 'Not recorded by the original API audit; this export contains input/output text and original usage counters.',
                    'usage_note': 'Original usage counters include thinking and any excluded batch outputs; not filtered token counts.',
                    'counts': dict(counts), 'matched_selected_request_hashes': len(set(wanted)&matched), 'elapsed_seconds': time.time()-start}
        (out / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        print(json.dumps(manifest, indent=2), flush=True)

if __name__ == '__main__':
    main()
