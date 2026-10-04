"""Seed a separate long run from the first ten completed v2 worlds."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import systems_bench as bench

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'local_data/alwayslearning-v2-64-256-100-parallel'
RUN_NAME = 'alwayslearning-v2-long-10-2048-100'
DESTINATION = ROOT / 'local_data' / RUN_NAME


def source_hash(directory):
    return hashlib.sha256(b''.join((directory / name).read_bytes() for name in
        ('systems_bench.py', 'local_api.py', 'system_data/catalogue.json'))).hexdigest()


def seed_state(state):
    if any(state['config'][k] != v for k, v in dict(systems=64, train=256, test=100).items()):
        raise ValueError('Expected the completed 64-row 256/100 source run')
    if len(state['systems']) != 64 or any(len(r['train']) != 256 or len(r['test']) != 100
                                        or r.get('pending') for r in state['systems']):
        raise ValueError('Source run is incomplete')
    # JSON round trip prevents modifications to the source objects.
    result = json.loads(json.dumps(state))
    result['systems'] = result['systems'][:10]
    result['config'].update(systems=10, train=2048, shuffle_train=True, source=source_hash(ROOT))
    seen = set()
    for row in result['systems']:
        bench.validate_world(row['world'])
        for split in ('train', 'test'):
            quotas = [0] * 8
            for item in row[split]:
                bench.validate_item(row['world'], item)
                text = bench.normalized(item['question'])
                if text in seen or not item['verification']['passed']:
                    raise ValueError('Duplicate or unverified source example')
                seen.add(text)
                quotas[item['sampling']['graph']] += 1
            n = len(row[split])
            if quotas != [n // 8 + (g < n % 8) for g in range(8)]:
                raise ValueError('Source metric quotas differ')
    return result


def prepare(source=SOURCE, destination=DESTINATION):
    if destination.exists():
        raise FileExistsError(f'Refusing to overwrite {destination}')
    original = (source / 'checkpoint.json').read_bytes()
    state = json.loads(original)
    if source_hash(source / 'code') != state['config']['source']:
        raise ValueError('Source snapshot hash mismatch')
    seeded = seed_state(state)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=destination.name + '.staging-', dir=destination.parent))
    try:
        code = temporary / 'code'
        code.mkdir()
        for name in ('systems_bench.py', 'local_api.py', 'requirements.lock'):
            shutil.copy2(ROOT / name, code / name)
        shutil.copytree(ROOT / 'system_data', code / 'system_data')
        (code / '.ready').touch()
        calls = temporary / 'calls'
        calls.mkdir()
        for path in (source / 'calls').glob('*.json'):
            if path.name.split('-')[0].split('.')[0] in {str(i) for i in range(10)}:
                shutil.copy2(path, calls / path.name)
        (temporary / 'checkpoint.json').write_text(json.dumps(seeded, ensure_ascii=False))
        (temporary / 'reuse.json').write_text(json.dumps(dict(
            source_run=source.name, source_checkpoint_sha256=hashlib.sha256(original).hexdigest(),
            source_config=state['config'], target_config=seeded['config'],
            source_rows=list(range(1, 11)), reused_train=2560, reused_test=1000,
            new_train=17920, test_policy='Original test examples remain unchanged in test',
            settings=[r['world']['setting'] for r in seeded['systems']]), indent=2))
        temporary.rename(destination)
    except BaseException:
        shutil.rmtree(temporary)
        raise
    print(f'Prepared {destination}: 10 worlds, 2560 retained train, 1000 retained test; 17920 train to add.')


if __name__ == '__main__':
    prepare()
