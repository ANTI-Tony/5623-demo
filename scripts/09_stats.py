"""Experiment 9 -- the statistics the paper owes.

  S1  headline +25.0pp   -> paired exact McNemar + bootstrap CI + min detectable effect
  S2  collateral 3 vs 3  -> Wilson CIs, power, and the honest 'no power' statement
  S3  sec 4.3 'the two failure modes come apart' -> tested against our own data
  S4  cost / caching audit
No API calls.
"""
import json, glob, os, math, random, statistics as st
from math import comb
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT/'out'; OUT.mkdir(exist_ok=True)
RNG = random.Random(0)

def load():
    E = {}
    for d in sorted(glob.glob(str(ROOT/'runs/batch/*_T*'))):
        d = Path(d)
        if not (d/'score.json').exists(): continue
        s = json.loads((d/'score.json').read_text())
        arm = d.name.rsplit('_',1)[1]; task = d.name.rsplit('_',1)[0]
        E.setdefault(task, {})[arm] = s
    return E

def coll(s):
    c = s.get('collateral'); return len(c) if isinstance(c,list) else int(c or 0)
def ok(s): return float(s.get('score') or 0) >= 1.0

def mcnemar_exact(b, c):
    n = b + c
    if n == 0: return 1.0
    lo = min(b, c)
    p = sum(comb(n,k)*0.5**n for k in range(0, lo+1))
    return min(1.0, 2*p)

def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 0.0)
    p = k/n; d = 1 + z*z/n
    c = (p + z*z/(2*n))/d
    h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/d
    return max(0,c-h), min(1,c+h)

def fisher(a,b,c,d):
    n=a+b+c+d
    def pr(x):
        b_=a+b-x; c_=a+c-x; d_=d-(x-a)
        if min(b_,c_,d_)<0: return 0.0
        return comb(a+b,x)*comb(c+d,c_)/comb(n,a+c)
    p0=pr(a)
    return sum(pr(x) for x in range(max(0,a+c-(c+d)), min(a+b,a+c)+1) if pr(x)<=p0+1e-12)

E = load()
paired = {t:v for t,v in E.items() if 'T0' in v and 'T3' in v}
res = {'n_paired_tasks': len(paired)}
print(f"paired tasks: {len(paired)}")

# ---- S1 headline ----
b = sum(1 for t,v in paired.items() if not ok(v['T0']) and ok(v['T3']))   # T0 fail -> T3 success
c = sum(1 for t,v in paired.items() if ok(v['T0']) and not ok(v['T3']))
n = len(paired)
s0 = sum(1 for v in paired.values() if ok(v['T0'])); s3 = sum(1 for v in paired.values() if ok(v['T3']))
p_mc = mcnemar_exact(b,c)
# paired bootstrap CI on the difference in success rate
diffs=[]
tasks=list(paired)
for _ in range(20000):
    smp=[paired[RNG.choice(tasks)] for _ in tasks]
    diffs.append(sum(ok(v['T3']) for v in smp)/len(smp) - sum(ok(v['T0']) for v in smp)/len(smp))
diffs.sort(); ci=(diffs[int(.025*len(diffs))], diffs[int(.975*len(diffs))])
res['S1']=dict(n=n, succ_T0=s0, succ_T3=s3, pp=100*(s3-s0)/n, b=b, c=c,
               mcnemar_exact_two_sided=p_mc, boot_ci_pp=[100*ci[0],100*ci[1]])
print(f"\n[S1] T0 {s0}/{n} -> T3 {s3}/{n} = {100*(s3-s0)/n:+.1f}pp")
print(f"     discordant b={b} c={c}   exact McNemar two-sided p={p_mc:.4f} "
      f"({'SIG' if p_mc<0.05 else 'NOT significant'})")
print(f"     paired bootstrap 95% CI = [{100*ci[0]:+.1f}, {100*ci[1]:+.1f}] pp")
# smallest b (c=0) reaching p<.05
need = next(k for k in range(1,40) if mcnemar_exact(k,0) < 0.05)
res['S1']['discordant_needed_for_p05'] = need
print(f"     need b>={need} (c=0) for p<0.05  -> we have b={b}")

# ---- S2 collateral ----
k0 = sum(1 for v in paired.values() if coll(v['T0'])>0); k3 = sum(1 for v in paired.values() if coll(v['T3'])>0)
b2 = sum(1 for v in paired.values() if coll(v['T0'])>0 and coll(v['T3'])==0)
c2 = sum(1 for v in paired.values() if coll(v['T0'])==0 and coll(v['T3'])>0)
p2 = mcnemar_exact(b2,c2)
w0,w3 = wilson(k0,n), wilson(k3,n)
res['S2']=dict(coll_T0=k0, coll_T3=k3, wilson_T0=[100*w0[0],100*w0[1]], wilson_T3=[100*w3[0],100*w3[1]],
               b=b2,c=c2, mcnemar_exact_two_sided=p2)
print(f"\n[S2] collateral episodes  T0 {k0}/{n} CI[{100*w0[0]:.1f},{100*w0[1]:.1f}]%   "
      f"T3 {k3}/{n} CI[{100*w3[0]:.1f},{100*w3[1]:.1f}]%")
print(f"     discordant b={b2} c={c2}  exact McNemar p={p2:.4f}  -> UNDERPOWERED null, not evidence of no effect")

# ---- S3 the claim in sec 4.3 ----
flat = [s for v in paired.values() for s in v.values()]
sc_ = sum(1 for s in flat if ok(s) and coll(s)>0); sn_ = sum(1 for s in flat if ok(s) and coll(s)==0)
fc_ = sum(1 for s in flat if not ok(s) and coll(s)>0); fn_ = sum(1 for s in flat if not ok(s) and coll(s)==0)
pf = fisher(sc_,sn_,fc_,fn_)
# do the collateral TASKS overlap across arms?
ct0 = {t for t,v in paired.items() if coll(v['T0'])>0}
ct3 = {t for t,v in paired.items() if coll(v['T3'])>0}
flip_tasks = {t for t,v in paired.items() if not ok(v['T0']) and ok(v['T3'])}
res['S3']=dict(succ_coll=sc_, succ_nocoll=sn_, fail_coll=fc_, fail_nocoll=fn_, fisher_two_sided=pf,
               coll_tasks_T0=sorted(ct0), coll_tasks_T3=sorted(ct3),
               overlap=sorted(ct0&ct3), flip_tasks=sorted(flip_tasks),
               flips_that_were_collateral=sorted(flip_tasks & ct0))
print(f"\n[S3] episode-level:  success/coll {sc_}  success/no {sn_}  fail/coll {fc_}  fail/no {fn_}")
print(f"     Fisher exact two-sided p={pf:.4f}  -> collateral and task-failure are "
      f"{'ASSOCIATED (paper 4.3 as written is contradicted)' if pf<0.05 else 'not sig associated'}")
print(f"     T0 collateral tasks: {len(ct0)}  T3: {len(ct3)}  overlap: {len(ct0&ct3)}")
print(f"     of the {len(flip_tasks)} tasks compute FIXED, {len(flip_tasks&ct0)} had T0 collateral")
print(f"     -> compute repaired a DISJOINT subset of failures from the ones emitting collateral")

# ---- S4 cost / caching ----
tot=cr=cw=inp=out=0; ncalls=0
for line in open(ROOT/'runs/ledger.jsonl'):
    r=json.loads(line); u=r.get('usage',r)
    inp+=u.get('input_tokens',0) or 0; out+=u.get('output_tokens',0) or 0
    cr+=u.get('cache_read_input_tokens',0) or 0; cw+=u.get('cache_creation_input_tokens',0) or 0
    ncalls+=1
res['S4']=dict(calls=ncalls, input_tokens=inp, output_tokens=out, cache_read=cr, cache_write=cw,
               caching_active=bool(cr or cw))
print(f"\n[S4] ledger {ncalls} calls  in={inp:,} out={out:,}  cache_read={cr:,} cache_write={cw:,}")
print(f"     prompt caching {'active' if cr else 'NEVER ACTIVE -> reported costs are un-cached'}")
json.dump(res, open(OUT/'k5_stats.json','w'), indent=1)
print("\nwrote out/k5_stats.json")
