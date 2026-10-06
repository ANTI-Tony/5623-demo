"""Does the compute/consequence misalignment hold on a second model?

Primary model  : Claude Sonnet 5,   arms low vs xhigh (xhigh is its top level)
Second model   : Claude Sonnet 4.6, arms low vs max   (4.6 rejects xhigh)

The top of the effort scale is therefore NOT held fixed across models; it cannot
be, because the two models expose different level sets. Reported as such.
"""
import json, glob, re, collections, statistics as st, random
from math import comb
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'out'
RNG=random.Random(0)

def steps_for(batch):
    """Join per-step compute to state changes for one batch dir. Requires the
    k3 join to have been run for that batch."""
    tag='' if batch=='runs/batch' else '_'+batch.rstrip('/').split('/')[-1]
    f=OUT/f'k3_steps{tag}.json'
    if not f.exists(): return None, tag
    return json.loads(f.read_text()), tag

def summarise(rows, label):
    out={}
    for arm in sorted({r['arm'] for r in rows}):
        R=[r for r in rows if r['arm']==arm]
        C=[r for r in R if r['commits']]; N=[r for r in R if not r['commits']]
        if not C or not N: continue
        tot=sum(r['out_tok'] for r in R) or 1
        byep=collections.defaultdict(list)
        for k,r in enumerate(R): byep[r['dir']].append(k)
        def stat(lab):
            c=[R[k]['out_tok'] for k in range(len(R)) if lab[k]]
            nc=[R[k]['out_tok'] for k in range(len(R)) if not lab[k]]
            return (st.mean(c)-st.mean(nc)) if c and nc else 0.0
        obs=stat([r['commits'] for r in R]); cnt=0
        for _ in range(10000):
            lab=[False]*len(R)
            for d,ks in byep.items():
                m=sum(1 for k in ks if R[k]['commits'])
                for k in RNG.sample(ks,m): lab[k]=True
            if abs(stat(lab))>=abs(obs)-1e-12: cnt+=1
        out[arm]=dict(steps=len(R), commit=len(C),
            pct_steps=100*len(C)/len(R), pct_tok=100*sum(r['out_tok'] for r in C)/tot,
            med_c=st.median([r['out_tok'] for r in C]),
            med_n=st.median([r['out_tok'] for r in N]), p=(cnt+1)/10001)
        d=out[arm]
        print(f"  {label:<12} {arm:<6} {d['commit']:>3}/{d['steps']:<4} steps ({d['pct_steps']:>4.1f}%) "
              f"get {d['pct_tok']:>4.1f}% of tokens | median {d['med_c']:.0f} vs {d['med_n']:.0f} | p={d['p']:.4f}")
    return out

res={}
print("K3 misalignment by model\n")
for batch,label in (('runs/batch','sonnet-5 s1'), ('runs/batch_seed2','sonnet-5 s2'),
                    ('runs/batch_sonnet46','sonnet-4.6')):
    rows,tag=steps_for(batch)
    if rows is None:
        print(f"  {label}: no join yet (run 08a_join.py {batch})"); continue
    res[label]=summarise(rows,label)

# task success, for context
def sc(d):
    E={}
    for p in sorted(glob.glob(str(ROOT/d/'*_T*'))):
        f=Path(p)/'score.json'
        if f.exists():
            s=json.loads(f.read_text()); E.setdefault(s['task_id'],{})[s['tier']]=s
    return E
ok=lambda s: float(s.get('score') or 0)>=1.0
def mcn(b,c):
    n=b+c
    return 1.0 if n==0 else min(1.0,2*sum(comb(n,k)*0.5**n for k in range(0,min(b,c)+1)))
print("\ntask success by model")
for d,label in (('runs/batch','sonnet-5 s1'),('runs/batch_seed2','sonnet-5 s2'),
                ('runs/batch_sonnet46','sonnet-4.6')):
    E=sc(d)
    arms=sorted({a for v in E.values() for a in v})
    if len(arms)<2: continue
    lo,hi=arms[0],arms[-1]
    P={t:v for t,v in E.items() if lo in v and hi in v}
    if not P: continue
    b=sum(1 for v in P.values() if not ok(v[lo]) and ok(v[hi]))
    c=sum(1 for v in P.values() if ok(v[lo]) and not ok(v[hi]))
    s0=sum(1 for v in P.values() if ok(v[lo])); s1=sum(1 for v in P.values() if ok(v[hi]))
    res.setdefault(label,{})['success']=dict(n=len(P),lo=s0,hi=s1,b=b,c=c,p=mcn(b,c))
    print(f"  {label:<12} n={len(P):<3} {lo} {s0}/{len(P)} -> {hi} {s1}/{len(P)} "
          f"= {100*(s1-s0)/len(P):+.1f}pp | b={b} c={c} p={mcn(b,c):.4f}")
from cawebagent.guard import require
require(res.get('steps') or res.get('n') or 0, 'steps', 'runs/batch_sonnet46')
json.dump(res, open(OUT/'k11_cross_model.json','w'), indent=1)
print("\nwrote out/k11_cross_model.json")
