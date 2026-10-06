"""Step-budget sweep: does the low-effort arm fail because it runs out of steps,
or because its decisions are worse?

Compares T0 at a 20-step cap against T0 at a 12-step cap (both seeds), paired by
task. If truncation was the binding constraint, raising it should convert the
truncated failures into successes.
"""
import json, glob, statistics as st
from math import comb
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'out'

def load(d, tier='T0'):
    E={}
    for p in sorted(glob.glob(str(ROOT/d/f'*_{tier}'))):
        f=Path(p)/'score.json'
        if f.exists():
            s=json.loads(f.read_text()); E[s['task_id']]=s
    return E
ok=lambda s: float(s.get('score') or 0)>=1.0
def mcnemar(b,c):
    n=b+c
    return 1.0 if n==0 else min(1.0, 2*sum(comb(n,k)*0.5**n for k in range(0,min(b,c)+1)))

A=load('runs/batch'); B=load('runs/batch_seed2'); C=load('runs/batch_steps20')
if not C: print("no runs/batch_steps20 yet"); raise SystemExit
common=sorted(set(C) & set(A) & set(B))
print(f"tasks with T0 at both budgets: {len(common)}\n")

res={'n':len(common)}
for lab,E,cap in (('T0@12 seed1',A,12), ('T0@12 seed2',B,12), ('T0@20',C,20)):
    r=[E[t] for t in common]
    tr=[x for x in r if x['steps']>=cap]
    res[lab]=dict(succ=sum(1 for x in r if ok(x)), n=len(r),
                  truncated=len(tr), mean_steps=st.mean(x['steps'] for x in r),
                  usd=sum(x['usd'] for x in r))
    print(f"{lab:<12} success {res[lab]['succ']}/{len(r)}  truncated {len(tr)}/{len(r)}  "
          f"mean steps {res[lab]['mean_steps']:.1f}  cost ${res[lab]['usd']:.2f}")

# paired: 12-step vs 20-step, using each seed as the baseline
for lab,E in (('seed1',A),('seed2',B)):
    b=sum(1 for t in common if not ok(E[t]) and ok(C[t]))
    c=sum(1 for t in common if ok(E[t]) and not ok(C[t]))
    p=mcnemar(b,c)
    res[f'paired_vs_{lab}']=dict(b=b,c=c,p=p)
    print(f"\nT0@20 vs T0@12 ({lab}): b={b} (gained) c={c} (lost)  exact McNemar p={p:.4f}")

# the decisive subset: tasks that were truncated at 12 in BOTH seeds
tr_both=[t for t in common if A[t]['steps']>=12 and B[t]['steps']>=12]
rescued=[t for t in tr_both if ok(C[t])]
res['truncated_in_both']=dict(tasks=tr_both, n=len(tr_both), rescued=rescued,
                              n_rescued=len(rescued))
print(f"\nTasks truncated at 12 steps in BOTH seeds: {len(tr_both)}  {tr_both}")
print(f"  of these, succeeded once given 20 steps: {len(rescued)}  {rescued}")
if tr_both:
    print(f"  rescue rate {100*len(rescued)/len(tr_both):.0f}%")
    print("\n  -> if HIGH, seed 1's compute effect was a step-budget effect")
    print("  -> if LOW,  those tasks fail for reasons extra steps do not fix")
# how many T0@20 still truncate at 20?
still=[t for t in common if C[t]['steps']>=20]
print(f"\nstill truncated at the 20-step cap: {len(still)}/{len(common)}  {still}")
res['still_truncated_at_20']=still
json.dump(res, open(OUT/'k8_step_budget.json','w'), indent=1)
print("\nwrote out/k8_step_budget.json")
