"""Stage 1 of the instrument: join HAR events to agent steps, cache to out/k3_steps.json.
Slow (598 MB of embedded-content HAR); incremental + resumable."""
import json, glob, os, re, sys
from pathlib import Path
from cawebagent.trace import har_parse as hp

ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT/'out'; OUT.mkdir(exist_ok=True)
import sys
BATCH = sys.argv[1] if len(sys.argv)>1 else 'runs/batch'
TAG = '' if BATCH=='runs/batch' else '_'+BATCH.rstrip('/').split('/')[-1]
CACHE = OUT/f'k3_steps{TAG}.json'

RULES_SRC = (ROOT/'scripts/exp1_consequence_taxonomy.py').read_text()
RULES = eval('[' + re.search(r'^RULES = \[(.*?)^\]', RULES_SRC, re.S|re.M).group(1) + ']')
def classify(u):
    for rx, cls, tier, flags, d, i, o in RULES:
        if re.search(rx, u): return cls, tier
    return 'UNCLASSIFIED', None

done = {}
if CACHE.exists():
    for r in json.loads(CACHE.read_text()): done.setdefault(r['dir'], []).append(r)

dirs = [Path(d) for d in sorted(glob.glob(str(ROOT/BATCH/'*_T*'))) if os.path.isdir(d)]
rows = [r for rs in done.values() for r in rs]
for n, d in enumerate(dirs, 1):
    if d.name in done:
        print(f"[{n}/{len(dirs)}] {d.name} cached", flush=True); continue
    ep_f = list(d.glob('*.episode.json'))
    if not ep_f or not (d/'agent.json').exists():
        print(f"[{n}/{len(dirs)}] {d.name} SKIP (missing)", flush=True); continue
    ep = json.loads(ep_f[0].read_text()); ag = json.loads((d/'agent.json').read_text())
    har = d / Path(ep['har']).name
    if not har.exists():
        print(f"[{n}/{len(dirs)}] {d.name} SKIP (no har)", flush=True); continue
    sz = har.stat().st_size/1e6
    print(f"[{n}/{len(dirs)}] {d.name} parsing {sz:.0f}MB ...", end=' ', flush=True)
    events = hp.parse_har(har)
    a0, a1 = float(ep['action_window'][0]), float(ep['action_window'][1])
    agent_phase = hp.segment(events, a0, a1)['action']
    sc = []
    for ev in agent_phase:
        if ev.method.upper() == 'GET' or hp._benign(ev): continue
        cls, tier = classify(ev.url)
        if tier is None: continue
        sc.append((ev, cls, tier))
    ag_steps = {int(s['i']): s for s in ag['steps']}
    out = []
    for s in ep['steps']:
        i = int(s['i']); t0 = float(s['action_exec_start'])
        t1 = max(float(s['action_exec_stop']), float(s.get('page_load_stop') or 0))
        hits = [(c, tr) for ev, c, tr in sc if t0 <= ev.started_s <= t1]
        a = ag_steps.get(i, {}); act = (s['action'] or '').strip()
        v = re.match(r'^([a-z_]+)\s*\(', act)
        out.append(dict(dir=d.name, task=ep['task'], arm=ag['tier'], i=i,
            verb=v.group(1) if v else 'other', commits=len(hits) > 0,
            max_tier=max([t for _, t in hits], default=None),
            classes=sorted({c for c, _ in hits}),
            out_tok=int(a.get('output_tokens') or 0), in_tok=int(a.get('input_tokens') or 0),
            usd=float(a.get('usd') or 0.0),
            err=bool((a.get('err') or s.get('last_action_error') or '').strip())))
    rows += out
    CACHE.write_text(json.dumps(rows, indent=1))
    print(f"{len(agent_phase)} agent-phase reqs, {len(sc)} state-changing, {len(out)} steps", flush=True)
print(f"\nDONE  {len(rows)} steps from {len({r['dir'] for r in rows})} episodes -> {CACHE}")
