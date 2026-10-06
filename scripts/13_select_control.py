"""Select a difficulty-matched tier-0/tier-1 control arm on shopping_admin.

'Compute helps where consequence is high' is a claim about a DIFFERENCE BETWEEN
STRATA; seed-1 observed one stratum only. This picks the comparison stratum,
matching on site and on the observable difficulty proxies available before
running: number of expected events, and evaluator mix.
"""
import json, collections, re
from pathlib import Path
from webarena_verified.utils import get_package_assets_path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'out'
DS=json.loads((get_package_assets_path()/'dataset/webarena-verified.json').read_text())

RULES=eval('['+re.search(r'^RULES = \[(.*?)^\]',
    (ROOT/'scripts/exp1_consequence_taxonomy.py').read_text(),re.S|re.M).group(1)+']')
def tier_of(u):
    for rx,cls,t,f,d,i,o in RULES:
        if re.search(rx,u): return t,cls
    return None,'UNCLASSIFIED'

treated=set(json.loads((OUT/'shopping_admin_tier2.json').read_text())) \
        if (OUT/'shopping_admin_tier2.json').exists() else set()
if treated and isinstance(next(iter(treated)),dict):
    treated={x['task_id'] for x in treated}

rows=[]
for t in DS:
    if t['sites']!=['shopping_admin'] and 'shopping_admin' not in t['sites']: continue
    nev=[e for e in t['eval'] if e['evaluator']=='NetworkEventEvaluator']
    mut=[e for e in nev if (e['expected'].get('http_method') or 'GET').upper()!='GET']
    if not mut: continue                      # need state-changing tasks
    tiers=[tier_of(e['expected']['url'])[0] for e in mut]
    tiers=[x for x in tiers if x is not None]
    if not tiers: continue
    mx=max(tiers)
    rows.append(dict(task_id=t['task_id'], tpl=t['intent_template_id'], max_tier=mx,
                     n_mut=len(mut), n_eval=len(t['eval']),
                     classes=sorted({tier_of(e['expected']['url'])[1] for e in mut}),
                     intent=t['intent'][:70]))

by=collections.Counter(r['max_tier'] for r in rows)
print(f"shopping_admin state-changing tasks: {len(rows)}   by max tier: {dict(sorted(by.items()))}")
t2=[r for r in rows if r['max_tier']==2]
lo=[r for r in rows if r['max_tier']<2 and r['task_id'] not in treated]
print(f"  tier-2: {len(t2)}   tier-0/1 candidates: {len(lo)}")

# match the treated arm's distribution of n_mut
tgt=collections.Counter(r['n_mut'] for r in t2 if r['task_id'] in treated) or \
    collections.Counter(r['n_mut'] for r in t2)
print(f"  treated arm n_mut distribution: {dict(tgt)}")
print(f"  control pool  n_mut distribution: {dict(collections.Counter(r['n_mut'] for r in lo))}")

# take up to 20, spread across templates, preferring matching n_mut
lo.sort(key=lambda r:(-tgt.get(r['n_mut'],0), r['tpl'], r['task_id']))
sel=[]; per_tpl=collections.Counter()
for r in lo:
    if len(sel)>=20: break
    if per_tpl[r['tpl']]>=5: continue
    sel.append(r); per_tpl[r['tpl']]+=1
print(f"\nselected {len(sel)} control tasks over {len(per_tpl)} templates")
print(f"{'task':>6}{'tpl':>6}{'tier':>5}{'nmut':>6}  classes")
for r in sel: print(f"{r['task_id']:>6}{r['tpl']:>6}{r['max_tier']:>5}{r['n_mut']:>6}  {','.join(r['classes'])[:44]}")
json.dump([r['task_id'] for r in sel], open(OUT/'control_tier01.json','w'), indent=1)
json.dump(sel, open(OUT/'control_tier01_detail.json','w'), indent=1)
print(f"\nwrote out/control_tier01.json  ({','.join(str(r['task_id']) for r in sel)})")
