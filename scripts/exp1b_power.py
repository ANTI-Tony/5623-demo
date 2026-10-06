"""Experiment 1b — statistical power: how many tasks/templates carry tier-2 actions?
Directly answers gate K4 (is High-consequence error rate even estimable?)."""
import json, collections
from pathlib import Path
OUT = Path(__file__).resolve().parents[1]/'out'
recs = json.load(open(OUT/'exp1_taxonomy.json'))

def maxtier(r):
    ts = [e['tier'] for e in r['seq'] if e['is_mut'] and e['tier'] is not None]
    return max(ts) if ts else None

by = collections.defaultdict(lambda: dict(tasks=set(), tpls=set(), sites=collections.Counter()))
for r in recs:
    mt = maxtier(r)
    if mt is None: continue
    by[mt]['tasks'].add(r['task_id']); by[mt]['tpls'].add(r['tpl'])
    by[mt]['sites']['+'.join(r['sites'])] += 1

print("="*72); print("EXP-1b  Statistical power by max consequence tier (task level)"); print("="*72)
print(f"{'tier':<6}{'tasks':>7}{'templates':>11}   sites")
for t in sorted(by):
    b = by[t]
    print(f"{t:<6}{len(b['tasks']):>7}{len(b['tpls']):>11}   "
          f"{', '.join(f'{k}:{v}' for k,v in b['sites'].most_common(4))}")

hi = by.get(2, dict(tasks=set(), tpls=set()))
print(f"\nHIGH-consequence (tier 2): {len(hi['tasks'])} tasks over {len(hi['tpls'])} templates")
# per action class at tier 2
cls2 = collections.Counter()
tcls2 = collections.defaultdict(set)
for r in recs:
    for e in r['seq']:
        if e['is_mut'] and e['tier']==2:
            cls2[e['cls']] += 1; tcls2[e['cls']].add(r['tpl'])
print("\n[tier-2 action classes]")
for k,v in cls2.most_common(): print(f"  {k:22} {v:4d} events   {len(tcls2[k])} templates")

# K4 projection
print("\n[K4 projection] if a 100-task subset is sampled proportionally:")
tot = sum(len(b['tasks']) for b in by.values())
print(f"  expected tier-2 tasks in 100-task sample ~ {100*len(hi['tasks'])/812:.1f}")
print(f"  at 3 seeds and a 20% per-commit error rate -> ~{3*100*len(hi['tasks'])/812*0.20:.1f} High-consequence error events")
print(f"  (gate K4 threshold was >=15 events)")
