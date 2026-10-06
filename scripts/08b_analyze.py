"""Stage 2: K3 misalignment + K4 orthogonality, from the cached per-step join."""
import json, random, statistics as st
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT/'out'
RNG = random.Random(0)
import sys
TAG = sys.argv[1] if len(sys.argv)>1 else ''
rows = json.loads((OUT/f'k3_steps{TAG}.json').read_text())

def perm_diff(R, key='out_tok', n=10000):
    byep = {}
    for k, r in enumerate(R): byep.setdefault(r['dir'], []).append(k)
    def stat(lab):
        c=[R[k][key] for k in range(len(R)) if lab[k]]; nc=[R[k][key] for k in range(len(R)) if not lab[k]]
        return (st.mean(c)-st.mean(nc)) if c and nc else 0.0
    obs_lab=[r['commits'] for r in R]; obs=stat(obs_lab); cnt=0
    for _ in range(n):
        lab=[False]*len(R)
        for d,ks in byep.items():
            m=sum(1 for k in ks if R[k]['commits'])
            for k in RNG.sample(ks,m): lab[k]=True
        if abs(stat(lab))>=abs(obs)-1e-12: cnt+=1
    return obs,(cnt+1)/(n+1)

def rank(v):
    o=sorted(range(len(v)),key=lambda k:v[k]); r=[0.0]*len(v); k=0
    while k<len(o):
        j=k
        while j+1<len(o) and v[o[j+1]]==v[o[k]]: j+=1
        for t in range(k,j+1): r[o[t]]=(k+j)/2+1
        k=j+1
    return r
def spearman(x,y):
    rx,ry=rank(x),rank(y); mx,my=st.mean(rx),st.mean(ry)
    num=sum((a-mx)*(b-my) for a,b in zip(rx,ry))
    den=(sum((a-mx)**2 for a in rx)*sum((b-my)**2 for b in ry))**.5
    return num/den if den else 0.0
def perm_rho(x,y,g,n=10000):
    obs=spearman(x,y); byg={}
    for k,gg in enumerate(g): byg.setdefault(gg,[]).append(k)
    cnt=0
    for _ in range(n):
        yy=list(y)
        for gg,ks in byg.items():
            v=[y[k] for k in ks]; RNG.shuffle(v)
            for k,val in zip(ks,v): yy[k]=val
        if abs(spearman(x,yy))>=abs(obs)-1e-12: cnt+=1
    return obs,(cnt+1)/(n+1)

res={'n_steps':len(rows),'n_episodes':len({r['dir'] for r in rows})}
print(f"steps={len(rows)}  episodes={res['n_episodes']}")

# ---------- K3 misalignment ----------
for arm in ('T3','T0','ALL'):
    R=[r for r in rows if arm=='ALL' or r['arm']==arm]
    C=[r for r in R if r['commits']]; NC=[r for r in R if not r['commits']]
    if not C or not NC: continue
    tot=sum(r['out_tok'] for r in R) or 1
    obs,p=perm_diff(R)
    d=dict(steps=len(R),commit_steps=len(C),
        pct_steps=100*len(C)/len(R), pct_outtok=100*sum(r['out_tok'] for r in C)/tot,
        med_commit=st.median([r['out_tok'] for r in C]), med_non=st.median([r['out_tok'] for r in NC]),
        mean_commit=st.mean([r['out_tok'] for r in C]), mean_non=st.mean([r['out_tok'] for r in NC]),
        perm_diff=obs, perm_p=p)
    res[f'K3_{arm}']=d
    print(f"\n[K3 {arm}] {d['commit_steps']}/{d['steps']} steps commit "
          f"({d['pct_steps']:.1f}%) but receive {d['pct_outtok']:.1f}% of output tokens")
    print(f"   out_tok median commit={d['med_commit']:.0f} vs non-commit={d['med_non']:.0f} | "
          f"mean {d['mean_commit']:.1f} vs {d['mean_non']:.1f}")
    print(f"   cluster-perm diff={obs:+.1f} p={p:.4f}")

# ---------- anti-tautology control: same action verb ----------
print("\n[K3 control] restricted to a single action verb (removes 'commits are just clicks')")
for arm in ('T3','T0'):
    for verb in ('click','fill'):
        R=[r for r in rows if r['arm']==arm and r['verb']==verb]
        C=[r for r in R if r['commits']]; NC=[r for r in R if not r['commits']]
        if len(C)<3 or len(NC)<3: 
            print(f"   {arm}/{verb}: n_commit={len(C)} n_non={len(NC)} (too few)"); continue
        obs,p=perm_diff(R)
        res[f'K3ctl_{arm}_{verb}']=dict(n_commit=len(C),n_non=len(NC),
            med_commit=st.median([r['out_tok'] for r in C]),med_non=st.median([r['out_tok'] for r in NC]),
            perm_diff=obs,perm_p=p)
        print(f"   {arm}/{verb}: commit n={len(C)} med={st.median([r['out_tok'] for r in C]):.0f} | "
              f"non n={len(NC)} med={st.median([r['out_tok'] for r in NC]):.0f} | diff={obs:+.1f} p={p:.4f}")

# ---------- K4 orthogonality ----------
print("\n[K4 orthogonality] consequence vs difficulty/uncertainty proxies (T3 arm)")
R=[r for r in rows if r['arm']=='T3']
cons=[1.0 if r['commits'] else 0.0 for r in R]
tier=[float(r['max_tier']) if r['max_tier'] is not None else 0.0 for r in R]
g=[r['dir'] for r in R]
for name,proxy in [('in_tok (a11y tree size)',[r['in_tok'] for r in R]),
                   ('out_tok (revealed difficulty)',[r['out_tok'] for r in R]),
                   ('step index (progress)',[r['i'] for r in R]),
                   ('last_action_error (retry)',[1.0 if r['err'] else 0.0 for r in R])]:
    rho,p=perm_rho(cons,proxy,g)
    res[f'K4_{name}']=dict(rho=rho,p=p)
    print(f"   commits vs {name:32s} rho={rho:+.3f}  p={p:.4f}")
rho,p=perm_rho(tier,[r['out_tok'] for r in R],g)
res['K4_tier_vs_outtok']=dict(rho=rho,p=p)
print(f"   max_tier vs out_tok                       rho={rho:+.3f}  p={p:.4f}")

json.dump(res,open(OUT/f'k3_instrument{TAG}.json','w'),indent=1)
print("\nwrote out/k3_instrument.json")
