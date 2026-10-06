"""Experiment 1c — what task coverage survives each deployable site subset?
Driven by measured Docker image sizes (compressed, Docker Hub API, 2026-08-19)."""
import json, collections
from pathlib import Path
OUT = Path(__file__).resolve().parents[1]/'out'
recs = json.load(open(OUT/'exp1_taxonomy.json'))

SIZE_GB = dict(shopping=5.42, shopping_admin=1.25, reddit=4.57, gitlab=22.01,
               map=1.19, wikipedia=0.05)          # compressed; on-disk ~2x
FREE_GB = 27.0

def maxtier(r):
    ts=[e['tier'] for e in r['seq'] if e['is_mut'] and e['tier'] is not None]
    return max(ts) if ts else None

def coverage(sites):
    s=set(sites); t2=t1=tot=0; tpl2=set()
    for r in recs:
        if not set(r['sites']) <= s: continue
        tot+=1; mt=maxtier(r)
        if mt==2: t2+=1; tpl2.add(r['tpl'])
        elif mt==1: t1+=1
    return tot, t1, t2, len(tpl2)

print("="*78); print("EXP-1c  Deployability vs task coverage"); print("="*78)
print(f"free disk = {FREE_GB} GB;  on-disk footprint estimated at 2x compressed size\n")
print(f"{'site':<16}{'compressed':>12}{'~on-disk':>10}")
for k,v in sorted(SIZE_GB.items(), key=lambda x:-x[1]):
    print(f"  {k:<14}{v:>10.2f}GB{v*2:>9.1f}GB")

SUBSETS = [
    ("shopping+shopping_admin",            ["shopping","shopping_admin"]),
    ("shopping+shopping_admin+reddit",     ["shopping","shopping_admin","reddit"]),
    ("+map+wikipedia",                     ["shopping","shopping_admin","reddit","map","wikipedia"]),
    ("ALL (incl. gitlab)",                 list(SIZE_GB)),
]
print(f"\n{'subset':<34}{'disk':>9}{'fits?':>7}{'tasks':>7}{'tier1':>7}{'tier2':>7}{'t2 tpl':>8}")
for name, ss in SUBSETS:
    d = sum(SIZE_GB[x] for x in ss)*2
    tot,t1,t2,tp2 = coverage(ss)
    print(f"{name:<34}{d:>7.1f}GB{'YES' if d<FREE_GB else 'NO':>7}{tot:>7}{t1:>7}{t2:>7}{tp2:>8}")

print("\n[tier-2 tasks by site]")
c=collections.Counter()
for r in recs:
    if maxtier(r)==2: c['+'.join(r['sites'])]+=1
for k,v in c.most_common(): print(f"  {k:<28}{v:>4}")

tot,t1,t2,tp2 = coverage(["shopping","shopping_admin","reddit","map","wikipedia"])
print(f"\n>>> Without gitlab: {t2} tier-2 tasks over {tp2} templates "
      f"({100*t2/65:.0f}% of the 65 available).")
print(f">>> At 3 seeds x 20% per-commit error: ~{3*t2*0.20:.0f} high-consequence error events "
      f"(gate K4 needs >=15).")
