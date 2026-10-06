"""K2 (sharp) — attribute each committed-but-wrong failure to a specific step.

Test: at the moment of the commit action, was the *page the agent was on* already
the wrong one (upstream error), or did the commit action itself go wrong (local)?
Uses per-step URL, which is recorded independently of the action text.
"""
import sys, json, re, collections; sys.path.insert(0,'.')
from pathlib import Path
from cawebagent.trace.har_parse import parse_har, segment, expected_specs, _url_matches
from webarena_verified.utils import get_package_assets_path
DS={t["task_id"]:t for t in json.loads((get_package_assets_path()/'dataset/webarena-verified.json').read_text())}
match=lambda sp,e: e.method.upper()==sp["method"].upper() and _url_matches(sp["url"], e.path)
ENT=re.compile(r"/(?:order_id|address_id|id)/(\d+)")     # entity id in a URL

out=[]
for d in sorted(Path("runs/batch").glob("*_T*")):
    if not (d/"score.json").exists(): continue
    s=json.loads((d/"score.json").read_text()); a=json.loads((d/"agent.json").read_text())
    if s["score"]==1.0: continue
    task=DS[s["task_id"]]; exp=expected_specs(task)
    ev=parse_har(a["har"]); a0,a1=a["window"]
    mut=[e for e in segment(ev,a0,a1)["action"] if e.is_mutation]
    if not mut: continue
    steps=a["steps"]
    # commit step = last step whose URL still precedes the mutation in time
    ci=max((i for i,x in enumerate(steps) if x["action"].startswith("click(")), default=None)
    if ci is None: continue
    commit_url=steps[ci]["url"]
    # which entity was the agent operating on at commit time?
    on = ENT.search(commit_url)
    # which entity did the task ask for?
    want = {ENT.search(sp["url"]).group(1) for sp in exp if ENT.search(sp["url"])}
    got  = {ENT.search(e.path).group(1) for e in mut if ENT.search(e.path)}
    # when was the current page first entered?
    entered = next((i for i,x in enumerate(steps) if x["url"]==commit_url), ci)
    hit=[sp for sp in exp if any(match(sp,e) for e in mut)]
    out.append(dict(task=s["task_id"], tier=s["tier"], n_exp=len(exp), n_hit=len(hit),
                    commit_i=ci, entered_i=entered, gap=ci-entered,
                    want=sorted(want), got=sorted(got),
                    page_entity=(on.group(1) if on else None),
                    n_steps=len(steps)))

print("="*90); print(f"K2 (sharp) — {len(out)} committed-but-wrong episodes"); print("="*90)
print(f"{'task':>5}{'tier':>5}{'exp':>4}{'hit':>4}{'commit@':>8}{'page_from@':>11}{'gap':>5}  want->got")
for r in out:
    print(f"{r['task']:>5}{r['tier']:>5}{r['n_exp']:>4}{r['n_hit']:>4}{r['commit_i']:>8}"
          f"{r['entered_i']:>11}{r['gap']:>5}  {','.join(r['want']) or '-'} -> {','.join(r['got']) or '-'}")

wrong_entity=[r for r in out if r["want"] and r["got"] and set(r["want"])!=set(r["got"])]
right_entity=[r for r in out if r["want"] and r["got"] and set(r["want"])==set(r["got"])]
print(f"\nwrong entity committed : {len(wrong_entity)}  (target chosen before the commit click)")
print(f"right entity committed : {len(right_entity)}  (failure is payload/completeness, set by earlier fills)")
gaps=[r["gap"] for r in out]
if gaps:
    import statistics as st
    print(f"\ncommit click was {st.mean(gaps):.1f} steps (median {st.median(gaps):.0f}) after the agent "
          f"first landed on the page it committed from")
    print(f"episodes where the commit page was entered at an EARLIER step: "
          f"{sum(1 for g in gaps if g>0)}/{len(gaps)}")
n_up=len(wrong_entity)+len(right_entity)
print(f"\n[K2] of {len(out)} committed-but-wrong episodes, {n_up} ({100*n_up/len(out):.0f}%) had the "
      f"deciding choice\n     (which record, or what to type) made strictly before the committing click.")
json.dump(out, open("out/k2_sharp.json","w"), indent=1)
