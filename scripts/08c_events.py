"""Dump every agent-phase non-GET request with timing, for detector validation:
false-positive audit + phase-boundary sensitivity. One HAR pass."""
import json, glob, os, re
from pathlib import Path
from cawebagent.trace import har_parse as hp
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'out'
RULES=eval('['+re.search(r'^RULES = \[(.*?)^\]',(ROOT/'scripts/exp1_consequence_taxonomy.py').read_text(),re.S|re.M).group(1)+']')
def classify(u):
    for rx,cls,tier,f,d,i,o in RULES:
        if re.search(rx,u): return cls,tier
    return 'UNCLASSIFIED',None
rec=[]
dirs=[Path(d) for d in sorted(glob.glob(str(ROOT/'runs/batch/*_T*'))) if os.path.isdir(d)]
for n,d in enumerate(dirs,1):
    ef=list(d.glob('*.episode.json'))
    if not ef: continue
    ep=json.loads(ef[0].read_text()); har=d/Path(ep['har']).name
    if not har.exists(): continue
    print(f"[{n}/{len(dirs)}] {d.name}",flush=True)
    evs=hp.parse_har(har)
    a0,a1=float(ep['action_window'][0]),float(ep['action_window'][1])
    specs=hp.expected_specs(ep.get('task'))if False else None
    for e in evs:
        if e.method.upper()=='GET' or not e.started_s: continue
        cls,tier=classify(e.url)
        rec.append(dict(dir=d.name,task=ep['task'],method=e.method,path=e.path,url=e.url[:200],
            status=e.status,t=e.started_s,a0=a0,a1=a1,rel_start=e.started_s-a0,rel_end=e.started_s-a1,
            benign=hp._benign(e),cls=cls,tier=tier))
    (OUT/'k3_events.json').write_text(json.dumps(rec))
print(f"DONE {len(rec)} non-GET events -> out/k3_events.json")
