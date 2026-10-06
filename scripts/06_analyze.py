"""K1/K2 analysis over a batch: does more compute help, and what does it cost?"""
import sys, json, collections; sys.path.insert(0,'.')
from pathlib import Path
import statistics as st

root = Path(sys.argv[1] if len(sys.argv)>1 else "runs/batch")
rows=[]
for d in sorted(root.glob("*_T*")):
    sf, af = d/"score.json", d/"agent.json"
    if not sf.exists(): continue
    s=json.loads(sf.read_text()); a=json.loads(af.read_text())
    s["steps_detail"]=a["steps"]
    s["in_tok"]=sum(x["input_tokens"] for x in a["steps"])
    s["out_tok"]=sum(x["output_tokens"] for x in a["steps"])
    rows.append(s)
if not rows: print("no results yet"); raise SystemExit

print("="*86); print(f"BATCH ANALYSIS — {len(rows)} episodes"); print("="*86)
by=collections.defaultdict(list)
for r in rows: by[r["tier"]].append(r)

print(f"{'tier':<6}{'n':>4}{'success':>9}{'succ%':>7}{'collat':>8}{'steps':>7}{'out_tok':>9}{'$/ep':>9}")
for t in sorted(by):
    g=by[t]; n=len(g); succ=sum(1 for x in g if x["score"]==1.0)
    print(f"{t:<6}{n:>4}{succ:>9}{100*succ/n:>6.1f}%{sum(x['collateral'] for x in g):>8}"
          f"{st.mean(x['steps'] for x in g):>7.1f}{st.mean(x['out_tok'] for x in g):>9.0f}"
          f"{st.mean(x['usd'] for x in g):>9.4f}")

# K1: paired comparison on tasks that have both tiers
pair=collections.defaultdict(dict)
for r in rows: pair[r["task_id"]][r["tier"]]=r
both=[v for v in pair.values() if "T0" in v and "T3" in v]
print(f"\n[K1] paired tasks with both T0 and T3: {len(both)}")
if both:
    t0s=sum(1 for v in both if v["T0"]["score"]==1.0); t3s=sum(1 for v in both if v["T3"]["score"]==1.0)
    flips_up=[k for k,v in pair.items() if v.get("T0",{}).get("score")==0.0 and v.get("T3",{}).get("score")==1.0]
    flips_dn=[k for k,v in pair.items() if v.get("T0",{}).get("score")==1.0 and v.get("T3",{}).get("score")==0.0]
    d_out=st.mean(v["T3"]["out_tok"]-v["T0"]["out_tok"] for v in both)
    d_usd=st.mean(v["T3"]["usd"]-v["T0"]["usd"] for v in both)
    print(f"  T0 success {t0s}/{len(both)} ({100*t0s/len(both):.1f}%)")
    print(f"  T3 success {t3s}/{len(both)} ({100*t3s/len(both):.1f}%)")
    print(f"  DELTA = {100*(t3s-t0s)/len(both):+.1f} pp   (K1 gate: >= +5pp)")
    print(f"  flips 0->1: {flips_up}   flips 1->0: {flips_dn}")
    print(f"  extra output tokens at T3: {d_out:+.0f}/episode   extra cost: ${d_usd:+.4f}")
    if abs(d_out) < 50:
        print("  !! T3 barely spends more compute than T0 — the effort dial is not moving spend,")
        print("     so a null K1 result would be uninformative about compute, only about effort.")

print("\n[collateral] episodes with unexpected state changes:")
c=[r for r in rows if r["collateral"]>0]
print(f"  {len(c)}/{len(rows)} episodes, {sum(r['collateral'] for r in c)} total")
for r in c: print(f"    task {r['task_id']} {r['tier']}: {r['collateral']}")

tot=sum(r["usd"] for r in rows)
print(f"\ntotal spend on scored episodes: ${tot:.3f}   mean ${tot/len(rows):.4f}/episode")
json.dump(rows, open(root/"analysis.json","w"), indent=1)
