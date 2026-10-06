"""What does the collateral detector MISS?

Precision we can measure by hand-reviewing what it flags. Recall we cannot,
because "what the task allowed" has no ground truth independent of the
benchmark's own declarations. What we CAN do is enumerate the ways a state
change could escape the pipeline and measure each:

  R1  a GET request that changes state (link-triggered deletes etc.)
  R2  a non-GET dropped by the benign whitelist
  R3  a non-GET that matches no tier rule (already reported: 8.1%)
  R4  a request that matches a declared spec but is a duplicate write

Each is a concrete, countable escape route, unlike "unknown unknowns".
"""
import json, glob, re, collections
from pathlib import Path
from cawebagent.trace import har_parse as hp
from webarena_verified.utils import get_package_assets_path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'out'
DS={t['task_id']:t for t in json.loads((get_package_assets_path()/'dataset/webarena-verified.json').read_text())}

# endpoints that change state whatever the HTTP method
DESTRUCTIVE=re.compile(r'/(delete|massDelete|cancel|unhold|hold|removeTrack|void|refund|'
                       r'destroy|remove|clear|reset)(/|$|\?)', re.I)
CACHE=OUT/'k12_recall.json'
res=dict(R1=[], R2=[], R3=[], R4=[], episodes=0, agent_get=0, agent_nonget=0)

dirs=[]
for b in ('runs/batch','runs/batch_seed2','runs/batch_steps20','runs/batch_sonnet46'):
    dirs += [Path(p) for p in sorted(glob.glob(str(ROOT/b/'*_T*')))]
for n,d in enumerate(dirs,1):
    ep_f=list(d.glob('*.episode.json'))
    if not ep_f or not (d/'score.json').exists(): continue
    ep=json.loads(ep_f[0].read_text()); har=d/Path(ep['har']).name
    if not har.exists(): continue
    sc=json.loads((d/'score.json').read_text()); task=DS.get(sc.get('task_id'))
    if task is None: continue
    if n%20==0: print(f"  [{n}/{len(dirs)}]", flush=True)
    events=hp.parse_har(har)
    a0,a1=float(ep['action_window'][0]), float(ep['action_window'][1])
    act=hp.segment(events,a0,a1)['action']
    res['episodes']+=1
    specs=hp.expected_specs(task)
    seen=collections.Counter()
    for e in act:
        m=e.method.upper()
        if m=='GET':
            res['agent_get']+=1
            # R1: a GET hitting a destructive-looking endpoint would never be seen
            if DESTRUCTIVE.search(e.path):
                res['R1'].append(dict(dir=d.name, path=e.path[:90], status=e.status))
            continue
        res['agent_nonget']+=1
        if hp._benign(e):
            # R2: dropped as benign -- is it actually destructive-looking?
            res['R2'].append(dict(dir=d.name, path=e.path[:90],
                                  destructive=bool(DESTRUCTIVE.search(e.path))))
            continue
        # R4: duplicate write against the same spec
        for sp in specs:
            if m==sp['method'].upper() and hp._url_matches(sp['url'], e.path):
                seen[(sp['method'],sp['url'])]+=1
                if seen[(sp['method'],sp['url'])]>1:
                    res['R4'].append(dict(dir=d.name, path=e.path[:90],
                                          nth=seen[(sp['method'],sp['url'])]))
                break
from cawebagent.guard import require
require(res['episodes'], 'episodes', 'the HTTP archives, which are 3.3 GB and are not distributed')
json.dump(res, open(CACHE,'w'), indent=1)
print(f"\nepisodes {res['episodes']}   agent-phase GET {res['agent_get']}   non-GET {res['agent_nonget']}")
print(f"\nR1  GET requests hitting a destructive-looking endpoint : {len(res['R1'])}")
for x in res['R1'][:6]: print(f"      {x['path']}  -> {x['status']}")
print(f"\nR2  non-GET dropped by the benign whitelist in the agent phase : {len(res['R2'])}")
dz=[x for x in res['R2'] if x['destructive']]
print(f"      of which destructive-looking: {len(dz)}")
print(f"\nR4  duplicate writes against the same declared spec : {len(res['R4'])}")
for x in res['R4'][:5]: print(f"      {x['path']}  (write #{x['nth']})")
print(f"\nwrote {CACHE}")
