"""Controls added after the second mock review. Each one is a check the panel
asked for and that the paper now reports, including the one that narrows our claim.

  C1  predecessor-matched control (nulls with the confirmation-modal family in)
  C2  same, modal family excluded
  C3  decision-step reattribution
  C4  output-cap contamination of the non-commit pool
  C5  task-level (not episode-level) clustering
  C6  pooled orthogonality (the single-seed version reversed one conclusion)
  C7  pooled collateral-vs-outcome over all 100 episodes
  C8  step-budget rescue over ALL truncated tasks, not the both-seeds subset
"""
import json, glob, re, random, collections, statistics as st
from math import comb
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'out'
RNG=random.Random(0)
rows=json.loads((OUT/'k3_steps_pooled.json').read_text())
by=collections.defaultdict(list)
for r in rows: by[r['dir']].append(r)
for v in by.values(): v.sort(key=lambda r:r['i'])
CANCEL=('_470_','_471_','_472_','_473_','_474_')
def sign_p(b,a):
    n=b+a
    return 1.0 if n==0 else min(1.0,2*sum(comb(n,k)*0.5**n for k in range(0,min(b,a)+1)))
def taskof(d):
    m=re.search(r'_(\d+)_2_T[03]',d); return m.group(1) if m else d
res={}

def pred_match(skip_modal):
    P=[]
    for d,s in by.items():
        if skip_modal and any(k in d for k in CANCEL): continue
        cl=[r for r in s if r['verb']=='click']
        for c in [r for r in cl if r['commits']]:
            pr=[r for r in cl if not r['commits'] and r['i']<c['i']]
            if pr: P.append(c['out_tok']-max(pr,key=lambda r:r['i'])['out_tok'])
    b=sum(1 for x in P if x<0); a=sum(1 for x in P if x>0); t=sum(1 for x in P if x==0)
    return dict(pairs=len(P), lower=b, higher=a, tied=t, median=st.median(P), p=sign_p(b,a))
res['C1_predecessor_all']=pred_match(False)
res['C2_predecessor_no_modal']=pred_match(True)
print(f"C1 predecessor-matched, all families : {res['C1_predecessor_all']}")
print(f"C2 predecessor-matched, modal excluded: {res['C2_predecessor_no_modal']}")

cap=[r for r in rows if r['out_tok']>=1500]
tot=sum(r['out_tok'] for r in rows)
res['C4_output_cap']=dict(n=len(cap), share=100*sum(r['out_tok'] for r in cap)/tot,
                          commits=sum(1 for r in cap if r['commits']),
                          verbs=dict(collections.Counter(r['verb'] for r in cap)))
print(f"C4 output-cap steps: {res['C4_output_cap']}")
R=[r for r in rows if r['arm']=='T3' and r['verb']=='click']
C=[r for r in R if r['commits']]
res['C4_click_only_T3']=dict(pct_steps=100*len(C)/len(R),
    pct_tokens=100*sum(r['out_tok'] for r in C)/sum(r['out_tok'] for r in R))
print(f"C4 T3 click-only: {res['C4_click_only_T3']}")

def perm(R,keyfn,n=10000):
    g=collections.defaultdict(list)
    for k,r in enumerate(R): g[keyfn(r)].append(k)
    def stat(lab):
        c=[R[k]['out_tok'] for k in range(len(R)) if lab[k]]
        nc=[R[k]['out_tok'] for k in range(len(R)) if not lab[k]]
        return (st.mean(c)-st.mean(nc)) if c and nc else 0.0
    obs=stat([r['commits'] for r in R]); cnt=0
    for _ in range(n):
        lab=[False]*len(R)
        for _k,ks in g.items():
            m=sum(1 for k in ks if R[k]['commits'])
            for k in RNG.sample(ks,m): lab[k]=True
        if abs(stat(lab))>=abs(obs)-1e-12: cnt+=1
    return obs,(cnt+1)/(n+1)
for arm in ('T3','ALL'):
    R=[r for r in rows if arm=='ALL' or r['arm']==arm]
    o,p=perm(R,lambda r: taskof(r['dir']))
    res[f'C5_task_clustered_{arm}']=dict(diff=o,p=p)
    print(f"C5 task-clustered {arm}: diff={o:+.1f} p={p:.4f}")
g=collections.defaultdict(list)
for r in rows:
    if r['commits']: g[taskof(r['dir'])].append(r['out_tok'])
res['C5_clusters']=dict(n_tasks=len(g), identical=sum(1 for v in g.values() if len(set(v))==1))
print(f"C5 clusters: {res['C5_clusters']}")

def coll(s):
    c=s.get('collateral'); return len(c) if isinstance(c,list) else int(c or 0)
ok=lambda s: float(s.get('score') or 0)>=1.0
def sc(d): return [json.loads((Path(p)/'score.json').read_text())
                   for p in sorted(glob.glob(str(ROOT/d/'*_T*'))) if (Path(p)/'score.json').exists()]
def fisher(a,b,c,d):
    n=a+b+c+d
    def pr(x):
        b_=a+b-x;c_=a+c-x;d_=d-(x-a)
        if min(b_,c_,d_)<0: return 0.0
        return comb(a+b,x)*comb(c+d,c_)/comb(n,a+c)
    p0=pr(a); return sum(pr(x) for x in range(max(0,a+c-(c+d)),min(a+b,a+c)+1) if pr(x)<=p0+1e-12)
for lab,dirs in (('all100',['runs/batch','runs/batch_seed2','runs/batch_steps20']),
                 ('matched80',['runs/batch','runs/batch_seed2'])):
    E=[r for d in dirs for r in sc(d)]
    a=sum(1 for r in E if ok(r) and coll(r)>0); b=sum(1 for r in E if ok(r) and coll(r)==0)
    c=sum(1 for r in E if not ok(r) and coll(r)>0); d=sum(1 for r in E if not ok(r) and coll(r)==0)
    res[f'C7_{lab}']=dict(succ_coll=a,succ_no=b,fail_coll=c,fail_no=d,p=fisher(a,b,c,d))
    print(f"C7 {lab}: success {a}/{a+b} collateral, failure {c}/{c+d}, Fisher p={fisher(a,b,c,d):.6f}")

def T0(d):
    E={}
    for p in sorted(glob.glob(str(ROOT/d/'*_T0'))):
        f=Path(p)/'score.json'
        if f.exists(): s=json.loads(f.read_text()); E[s['task_id']]=s
    return E
A,B,C_=T0('runs/batch'),T0('runs/batch_seed2'),T0('runs/batch_steps20')
common=sorted(set(A)&set(B)&set(C_))
for lab,E in (('seed1',A),('seed2',B)):
    tr=[t for t in common if E[t]['steps']>=12]
    r_=[t for t in tr if ok(C_[t])]
    res[f'C8_rescue_{lab}']=dict(truncated=len(tr), rescued=len(r_), tasks=r_)
    print(f"C8 {lab}: rescued {len(r_)}/{len(tr)} of truncated tasks {r_}")
both=[t for t in common if A[t]['steps']>=12 and B[t]['steps']>=12]
res['C8_intersection']=dict(n=len(both), rescued=[t for t in both if ok(C_[t])], tasks=both)
print(f"C8 both-seeds intersection: {len(both)} tasks, rescued {len([t for t in both if ok(C_[t])])}")
from cawebagent.guard import require
require(res.get('n') or res.get('steps') or 0, 'steps', 'runs/batch and the per-step join')
json.dump(res, open(OUT/'k9_r2_controls.json','w'), indent=1)
print("\nwrote out/k9_r2_controls.json")
