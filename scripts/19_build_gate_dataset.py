"""Build the evaluation set for the pre-commit consistency check.

One row per state-changing request the agent emitted, labelled with ground truth:
  expected   -- matches an event the task declared it should cause
  collateral -- matches none, i.e. the task never asked for it

This is the set the deterministic read-only gate fires on (all of it, by
construction). A useful check must keep the collateral recall while firing less.
"""
import json, glob, re, collections
from pathlib import Path
from cawebagent.trace import har_parse as hp
from webarena_verified.utils import get_package_assets_path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'out'
DS={t['task_id']:t for t in json.loads((get_package_assets_path()/'dataset/webarena-verified.json').read_text())}
CACHE=OUT/'gate_dataset.json'

rows=[]
if CACHE.exists():
    rows=json.loads(CACHE.read_text())
    print(f"resuming with {len(rows)} rows from cache")
seen={r['dir'] for r in rows}

dirs=[]
for b in ('runs/batch','runs/batch_seed2','runs/batch_steps20','runs/batch_sonnet46'):
    dirs += [Path(p) for p in sorted(glob.glob(str(ROOT/b/'*_T*')))]
print(f"{len(dirs)} episode dirs")

for n,d in enumerate(dirs,1):
    if f'{d.parent.name}/{d.name}' in seen: continue
    ep_f=list(d.glob('*.episode.json'))
    if not ep_f: continue
    ep=json.loads(ep_f[0].read_text())
    har=d/Path(ep['har']).name
    if not har.exists(): continue
    sc=json.loads((d/'score.json').read_text()) if (d/'score.json').exists() else {}
    task=DS.get(sc.get('task_id'))
    if task is None: continue
    print(f"[{n}/{len(dirs)}] {d.name}", flush=True)
    events=hp.parse_har(har)
    a0,a1=float(ep['action_window'][0]), float(ep['action_window'][1])
    act=hp.segment(events,a0,a1)['action']
    coll={id(e) for e in hp.collateral(act, task)}
    goal=(ep.get('goal') or task.get('intent') or '').split('\n\nFinal response format:')[0].strip()
    # the page the agent was on when the request fired -- what a real interceptor sees
    steps=ep.get('steps') or []
    def page_at(ts):
        best=None
        for st_ in steps:
            t0=float(st_['action_exec_start'])
            t1=max(float(st_['action_exec_stop']), float(st_.get('page_load_stop') or 0))
            if t0<=ts<=t1: return st_['url']
            if t0<=ts: best=st_['url']
        return best
    for e in act:
        if e.method.upper()=='GET' or hp._benign(e): continue
        rows.append(dict(dir=f'{d.parent.name}/{d.name}', batch=str(d.parent.name), task_id=sc.get('task_id'),
                         tier=sc.get('tier'), goal=goal,
                         method=e.method, path=e.path, t=e.started_s,
                         page=page_at(e.started_s),
                         post=(e.post_body or '')[:400],
                         label='collateral' if id(e) in coll else 'expected',
                         episode_score=float(sc.get('score') or 0)))
    CACHE.write_text(json.dumps(rows, indent=1))

c=collections.Counter(r['label'] for r in rows)
print(f"\nDONE  {len(rows)} state-changing requests: {dict(c)}")
print(f"  the deterministic gate fires on all {len(rows)}, catching {c['collateral']}")
print(f"  -> baseline recall 100%, precision {100*c['collateral']/max(len(rows),1):.1f}%")
by=collections.Counter(r['batch'] for r in rows)
print(f"  by batch: {dict(by)}")
