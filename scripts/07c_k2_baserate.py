"""K2 base rate: run the SAME positional statistic on successful episodes.
Without this control, '80% of commits fired from a page entered earlier' cannot be
distinguished from how the interface is laid out. Uses cached out/k3_events.json."""
import json, re, statistics as st, random, collections
from pathlib import Path
from math import comb
ROOT=Path(__file__).resolve().parents[1]
ENT=re.compile(r"/(?:order_id|address_id|id)/(\d+)")
ev=json.loads((ROOT/'out/k3_events.json').read_text())
byd=collections.defaultdict(list)
for e in ev:
    if e['a0']<=e['t']<=e['a1'] and not e['benign'] and e['method'].upper()!='GET':
        byd[e['dir']].append(e)

rows=[]
for d in sorted((ROOT/'runs/batch').glob('*_T*')):
    if not (d/'score.json').exists(): continue
    s=json.loads((d/'score.json').read_text()); a=json.loads((d/'agent.json').read_text())
    if not byd.get(d.name): continue                  # no state change emitted
    steps=a['steps']
    ci=max((i for i,x in enumerate(steps) if x['action'].startswith('click(')), default=None)
    if ci is None: continue
    curl=steps[ci]['url']
    entered=next((i for i,x in enumerate(steps) if x['url']==curl), ci)
    rows.append(dict(dir=d.name, task=s['task_id'], tier=s['tier'],
                     score=float(s.get('score') or 0), commit_i=ci, entered_i=entered,
                     gap=ci-entered, n_steps=len(steps)))
F=[r for r in rows if r['score']<1.0]; S=[r for r in rows if r['score']>=1.0]
print(f"commit-emitting episodes: {len(rows)}  (failed {len(F)}, successful {len(S)})")
def summ(n,R):
    g=[r['gap'] for r in R]
    if not g: print(f"  {n}: none"); return []
    print(f"  {n:<9} n={len(g):<3} gap>0 {sum(1 for v in g if v>0)}/{len(g)} "
          f"({100*sum(1 for v in g if v>0)/len(g):.0f}%)  median={st.median(g):.1f} mean={st.mean(g):.1f}")
    return g
gf=summ('FAILED',F); gs=summ('SUCCESS',S)
res=dict(n_failed=len(F), n_success=len(S))
if gf and gs:
    obs=st.median(gf)-st.median(gs); pool=gf+gs; R=random.Random(0); N=20000; c=0
    for _ in range(N):
        R.shuffle(pool)
        if abs(st.median(pool[:len(gf)])-st.median(pool[len(gf):]))>=abs(obs)-1e-12: c+=1
    p=(c+1)/(N+1)
    a=sum(1 for v in gf if v>0); b=len(gf)-a; cc=sum(1 for v in gs if v>0); e=len(gs)-cc
    def fisher(a,b,c,d):
        n=a+b+c+d
        def pr(x):
            b_=a+b-x;c_=a+c-x;d_=d-(x-a)
            if min(b_,c_,d_)<0: return 0.0
            return comb(a+b,x)*comb(c+d,c_)/comb(n,a+c)
        p0=pr(a); return sum(pr(x) for x in range(max(0,a+c-(c+d)),min(a+b,a+c)+1) if pr(x)<=p0+1e-12)
    pf=fisher(a,b,cc,e)
    res.update(median_gap_failed=st.median(gf), median_gap_success=st.median(gs),
               perm_p=p, prop_failed=[a,len(gf)], prop_success=[cc,len(gs)], fisher_p=pf)
    print(f"\n  median gap diff (failed - successful) = {obs:+.1f} steps, permutation p={p:.4f}")
    print(f"  gap>0 proportion: failed {a}/{len(gf)} vs successful {cc}/{len(gs)}, Fisher p={pf:.4f}")
    print(f"\n  VERDICT: the positional statistic {'DISCRIMINATES' if min(p,pf)<0.05 else 'does NOT discriminate'} "
          f"failures from successes.")
json.dump(res, open(ROOT/'out/k2_baserate.json','w'), indent=1)
