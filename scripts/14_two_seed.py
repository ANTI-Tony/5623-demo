"""Combine seed 1 and seed 2: per-seed flip counts, between-seed variance, and
the pooled exact McNemar. This is the test the single-seed design could not pass:
with b=5, c=0 the minimum attainable two-sided p is 0.0625.
"""
import json, glob, os, math, collections
from math import comb
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'out'

def load(d):
    E={}
    for p in sorted(glob.glob(str(ROOT/d/'*_T*'))):
        f=Path(p)/'score.json'
        if not f.exists(): continue
        s=json.loads(f.read_text())
        E.setdefault(str(s['task_id']),{})[s['tier']]=s
    return E
def ok(s): return float(s.get('score') or 0)>=1.0
def coll(s):
    c=s.get('collateral'); return len(c) if isinstance(c,list) else int(c or 0)
def mcnemar(b,c):
    n=b+c
    if n==0: return 1.0
    return min(1.0, 2*sum(comb(n,k)*0.5**n for k in range(0,min(b,c)+1)))

S={'seed1':load('runs/batch'), 'seed2':load('runs/batch_seed2')}
res={}; per=[]
for name,E in S.items():
    P={t:v for t,v in E.items() if 'T0' in v and 'T3' in v}
    if not P: print(f"{name}: no paired tasks yet"); continue
    b=sum(1 for v in P.values() if not ok(v['T0']) and ok(v['T3']))
    c=sum(1 for v in P.values() if ok(v['T0']) and not ok(v['T3']))
    s0=sum(1 for v in P.values() if ok(v['T0'])); s3=sum(1 for v in P.values() if ok(v['T3']))
    n=len(P)
    d=dict(n=n, succ_T0=s0, succ_T3=s3, pp=100*(s3-s0)/n, b=b, c=c, p=mcnemar(b,c),
           coll_T0=sum(1 for v in P.values() if coll(v['T0'])>0),
           coll_T3=sum(1 for v in P.values() if coll(v['T3'])>0))
    res[name]=d; per.append((name,P))
    print(f"[{name}] n={n}  T0 {s0}/{n} -> T3 {s3}/{n} = {d['pp']:+.1f}pp | "
          f"discordant b={b} c={c}  exact p={d['p']:.4f} | collateral {d['coll_T0']} vs {d['coll_T3']}")

if len(per)==2:
    B=sum(res[k]['b'] for k in res); C=sum(res[k]['c'] for k in res)
    N=sum(res[k]['n'] for k in res)
    p=mcnemar(B,C)
    res['pooled']=dict(n_pairs=N, b=B, c=C, p=p,
                       pp=(sum(res[k]['succ_T3'] for k in res if k!='pooled')-
                           sum(res[k]['succ_T0'] for k in res if k!='pooled'))*100/N)
    print(f"\n[POOLED] {N} paired episodes  b={B} c={C}  exact McNemar two-sided p={p:.4f} "
          f"-> {'SIGNIFICANT at 0.05' if p<0.05 else 'still not significant'}")
    # per-task agreement between seeds
    t1,t2=per[0][1],per[1][1]
    both=set(t1)&set(t2)
    agree=sum(1 for t in both if ok(t1[t]['T3'])==ok(t2[t]['T3']))
    agree0=sum(1 for t in both if ok(t1[t]['T0'])==ok(t2[t]['T0']))
    res['stability']=dict(tasks=len(both), agree_T3=agree, agree_T0=agree0,
                          flip_rate_T3=100*(len(both)-agree)/max(len(both),1),
                          flip_rate_T0=100*(len(both)-agree0)/max(len(both),1))
    print(f"\nbetween-seed outcome stability on {len(both)} tasks:")
    print(f"   T0 same outcome {agree0}/{len(both)}  -> run-to-run flip rate {100*(len(both)-agree0)/len(both):.1f}%")
    print(f"   T3 same outcome {agree}/{len(both)}  -> run-to-run flip rate {100*(len(both)-agree)/len(both):.1f}%")
    print("   (the paper cites 12-14% published flip rate on WebArena; this is our own measurement)")
from cawebagent.guard import require
require(res.get('n_pairs') or res.get('pairs') or 0, 'paired tasks', 'runs/batch and runs/batch_seed2')
json.dump(res, open(OUT/'k7_two_seed.json','w'), indent=1)
print("\nwrote out/k7_two_seed.json")
