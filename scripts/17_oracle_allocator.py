"""What the measurement is worth: an oracle allocator and the baseline the paper
names but never measured. Entirely offline over the 100 recorded episodes -- no
model calls.

A1  cost of consequence-conditioned allocation: spend high effort only in the
    commit neighbourhood, low effort elsewhere. What would it have cost?
A2  oracle upper bound on the deterministic read-only pre-commit gate: applied to
    the recorded traces, how many collateral events would a gate that pauses
    before every non-GET request have intercepted, and how often would it fire?
"""
import json, glob, re, collections, statistics as st
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'out'
rows=json.loads((OUT/'k3_steps_pooled.json').read_text())
by=collections.defaultdict(list)
for r in rows: by[r['dir']].append(r)
for v in by.values(): v.sort(key=lambda r:r['i'])

# --- neighbourhood = the commit step and the one before it (the modal-opening click)
for d,s in by.items():
    for k,r in enumerate(s):
        r['nbhd'] = r['commits'] or (k+1 < len(s) and s[k+1]['commits'])

res={}
IN_USD, OUT_USD = 2/1e6, 10/1e6   # matches cawebagent/lm/protocol.py PRICE

def arm_of(d): return 'T3' if d.endswith('T3') or d.endswith('T3_s2') else 'T0'
def task_of(d):
    m=re.search(r'_(\d+)_2_T[03]', d); return m.group(1) if m else d

# pair each task/seed: what does uniform-T0, uniform-T3, and hybrid cost?
pairs=collections.defaultdict(dict)
for d,s in by.items():
    seed = '_s2' if d.endswith('_s2') else ''
    pairs[(task_of(d), seed)][arm_of(d)] = s
full=[(k,v) for k,v in pairs.items() if 'T0' in v and 'T3' in v]
print(f"paired task-seed cells: {len(full)}")

cost=lambda steps: sum(r['in_tok']*IN_USD + r['out_tok']*OUT_USD for r in steps)
u0=u3=hy=0.0; n_hi=0; n_tot=0
for (t,seed),v in full:
    s0,s3=v['T0'],v['T3']
    u0+=cost(s0); u3+=cost(s3)
    # hybrid: use the T3 step where the T0 trace says we are in the neighbourhood,
    # the T0 step otherwise. Aligned by step index; fall back to T0 when absent.
    idx3={r['i']:r for r in s3}
    h=0.0
    for r in s0:
        if r['nbhd'] and r['i'] in idx3:
            h+=idx3[r['i']]['in_tok']*IN_USD + idx3[r['i']]['out_tok']*OUT_USD; n_hi+=1
        else:
            h+=r['in_tok']*IN_USD + r['out_tok']*OUT_USD
        n_tot+=1
    hy+=h
res['A1']=dict(uniform_T0=u0, uniform_T3=u3, hybrid=hy, cells=len(full),
               pct_steps_upgraded=100*n_hi/max(n_tot,1),
               hybrid_vs_T3=100*(hy-u3)/u3, hybrid_vs_T0=100*(hy-u0)/u0)
print(f"\nA1  cost of consequence-conditioned allocation over {len(full)} paired cells")
print(f"    uniform low  : ${u0:.3f}")
print(f"    uniform high : ${u3:.3f}")
print(f"    hybrid       : ${hy:.3f}   ({100*n_hi/max(n_tot,1):.1f}% of steps upgraded)")
print(f"    hybrid is {100*(hy-u3)/u3:+.1f}% vs uniform high, {100*(hy-u0)/u0:+.1f}% vs uniform low")

# --- A2: offline read-only pre-commit gate ---
def coll(s):
    c=s.get('collateral'); return len(c) if isinstance(c,list) else int(c or 0)
ok=lambda s: float(s.get('score') or 0)>=1.0
eps=[]
for d in ('runs/batch','runs/batch_seed2','runs/batch_steps20'):
    for p in sorted(glob.glob(str(ROOT/d/'*_T*'))):
        f=Path(p)/'score.json'
        if f.exists(): eps.append(json.loads(f.read_text()))
n_ep=len(eps)
n_coll_ep=sum(1 for e in eps if coll(e)>0)
n_coll_ev=sum(coll(e) for e in eps)
n_mut=sum(int(e.get('mutations') or 0) for e in eps)
res['A2']=dict(episodes=n_ep, collateral_episodes=n_coll_ep, collateral_events=n_coll_ev,
               total_mutations=n_mut,
               precision=(n_coll_ev/n_mut if n_mut else None))
print(f"\nA2  offline read-only pre-commit gate over {n_ep} recorded episodes")
print(f"    state-changing requests emitted : {n_mut}")
print(f"    of which unrequested (collateral): {n_coll_ev}  in {n_coll_ep} episodes")
print(f"    a gate that pauses before EVERY state change intercepts 100% of the")
print(f"    {n_coll_ev} collateral events, at the cost of {n_mut} interruptions")
print(f"    -> precision {100*n_coll_ev/max(n_mut,1):.1f}%: {n_mut-n_coll_ev} of {n_mut} pauses are on")
print(f"       requests the task actually asked for")
from cawebagent.guard import require
require(res.get('A1',{}).get('cells') or 0, 'steps', 'out/k3_steps_pooled.json')
json.dump(res, open(OUT/'k10_oracle.json','w'), indent=1)
print("\nwrote out/k10_oracle.json")
