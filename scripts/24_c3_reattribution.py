"""Control C3: does the misalignment survive re-attributing the commit?

Magento gates destructive operations behind an in-page modal, so the request
fires on an 'OK' click whose predecessor is the click that opened the modal. If
the DECISION is the predecessor, the instrument attributes the commit to the
wrong step. This re-attributes and re-runs the headline test.

Reported in the paper as p=0.0007; this script is what produces that number.
"""
import json, statistics as st, random, collections, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'k3_steps_pooled.json'
RNG=random.Random(0)
rows=json.loads(SRC.read_text())
by=collections.defaultdict(list)
for r in rows: by[r['dir']].append(r)
for v in by.values(): v.sort(key=lambda r:r['i'])

moved=0
for d,steps in by.items():
    idx={r['i']:k for k,r in enumerate(steps)}
    for r in list(steps):
        if not r['commits'] or r['verb']!='click': continue
        k=idx[r['i']]
        # a short commit click whose predecessor is also a click == modal confirmation
        if k>0 and steps[k-1]['verb']=='click' and not steps[k-1]['commits'] and r['out_tok']<=10:
            steps[k-1]['commits']=True; r['commits']=False; moved+=1
flat=[r for v in by.values() for r in v]
print(f"re-attributed {moved} commits from the confirmation click to the decision click\n")

def perm(R, n=10000):
    g=collections.defaultdict(list)
    for k,r in enumerate(R): g[r['dir']].append(k)
    def stat(lab):
        c=[R[k]['out_tok'] for k in range(len(R)) if lab[k]]
        nc=[R[k]['out_tok'] for k in range(len(R)) if not lab[k]]
        return (st.mean(c)-st.mean(nc)) if c and nc else 0.0
    obs=stat([r['commits'] for r in R]); cnt=0
    for _ in range(n):
        lab=[False]*len(R)
        for _d,ks in g.items():
            m=sum(1 for k in ks if R[k]['commits'])
            for k in RNG.sample(ks,m): lab[k]=True
        if abs(stat(lab))>=abs(obs)-1e-12: cnt+=1
    return obs,(cnt+1)/(n+1)

out={}
for arm in ('T0','T3','ALL'):
    R=[r for r in flat if arm=='ALL' or r['arm']==arm]
    C=[r for r in R if r['commits']]; N=[r for r in R if not r['commits']]
    tot=sum(r['out_tok'] for r in R) or 1
    o,p=perm(R)
    out[arm]=dict(steps=len(R), commits=len(C), pct_steps=100*len(C)/len(R),
                  pct_tok=100*sum(r['out_tok'] for r in C)/tot,
                  med_c=st.median([r['out_tok'] for r in C]),
                  med_n=st.median([r['out_tok'] for r in N]), diff=o, p=p)
    d=out[arm]
    print(f"  {arm:<4} {d['commits']:>3}/{d['steps']:<4} steps ({d['pct_steps']:>4.1f}%) get "
          f"{d['pct_tok']:>4.1f}% of output tokens | median {d['med_c']:.0f} vs {d['med_n']:.0f} | p={d['p']:.4f}")
print("\npaper reports, under decision-step attribution: 9.7% of steps, 3.5% of tokens, p=0.0007")
a=out['ALL']
ok = abs(a['pct_steps']-9.7)<0.15 and abs(a['pct_tok']-3.5)<0.15
print(f"  -> {'REPRODUCES' if ok else 'DOES NOT REPRODUCE -- fix the paper'}")
json.dump(out, open(ROOT/'c3_reattribution.json','w'), indent=1)
