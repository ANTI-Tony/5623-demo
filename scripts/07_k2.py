"""K2 — where is the error determined: at the commit action, or upstream?
Uses the same URL matching as the collateral detector (regex search, so the
site base path prefix is handled correctly)."""
import sys, json, re, collections; sys.path.insert(0,'.')
from pathlib import Path
from cawebagent.trace.har_parse import parse_har, segment, expected_specs, _url_matches
from webarena_verified.utils import get_package_assets_path
DS={t["task_id"]:t for t in json.loads((get_package_assets_path()/'dataset/webarena-verified.json').read_text())}

def match(spec, ev):
    return ev.method.upper()==spec["method"].upper() and _url_matches(spec["url"], ev.path)

rows=[]
for d in sorted(Path("runs/batch").glob("*_T*")):
    if not (d/"score.json").exists(): continue
    s=json.loads((d/"score.json").read_text()); a=json.loads((d/"agent.json").read_text())
    task=DS[s["task_id"]]; exp=expected_specs(task)
    ev=parse_har(a["har"]); a0,a1=a["window"]
    mut=[e for e in segment(ev,a0,a1)["action"] if e.is_mutation]
    hit=[sp for sp in exp if any(match(sp,e) for e in mut)]
    unmatched=[e for e in mut if not any(match(sp,e) for sp in exp)]
    rows.append(dict(task=s["task_id"], tier=s["tier"], score=s["score"], steps=s["steps"],
                     n_exp=len(exp), n_hit=len(hit), n_mut=len(mut), n_unmatched=len(unmatched),
                     actions=[x["action"] for x in a["steps"]],
                     unmatched=[f"{e.method} {e.path}" for e in unmatched]))

fail=[r for r in rows if r["score"]!=1.0]
print("="*88); print(f"K2 — failure anatomy over {len(rows)} episodes ({len(fail)} failures)"); print("="*88)

def cat(r):
    if r["n_mut"]==0:                       return "A_no_commit"
    if r["n_hit"]==0:                       return "B_wrong_target"      # committed, but not what was asked
    if r["n_hit"] < r["n_exp"]:             return "C_partial"           # some required changes missing
    if r["n_unmatched"] > 0:                return "D_correct_plus_extra"
    return "E_all_matched_but_failed"                                     # payload/response mismatch

c=collections.Counter(cat(r) for r in fail)
LAB={"A_no_commit":"never issued a state change",
     "B_wrong_target":"committed to the wrong target",
     "C_partial":"committed some of the required changes, missed others",
     "D_correct_plus_extra":"made the required change AND an extra one",
     "E_all_matched_but_failed":"all required endpoints hit; failed on payload/response content"}
print(f"\n{'category':<26}{'n':>4}   meaning")
for k in sorted(c): print(f"  {k:<24}{c[k]:>4}   {LAB[k]}")

# --- the K2 question ---------------------------------------------------------
# For every failure that DID commit (B/C/D/E), was the error decided at the
# commit action itself, or by an earlier action?  The commit action is the last
# action before the mutation; "decided upstream" means the value that made it
# wrong (target page, filled fields, selected rows) was set by an earlier step.
COMMIT_ACT = re.compile(r"click\(")          # commits are always a click in this env
UPSTREAM   = re.compile(r"goto\(|fill\(|select_option\(")

print("\n[K2] for failures that committed something:")
committed=[r for r in fail if r["n_mut"]>0]
up=loc=0
for r in committed:
    acts=r["actions"]
    # index of last click (the commit) and whether any upstream-deciding action precedes it
    ci=max((i for i,x in enumerate(acts) if COMMIT_ACT.search(x)), default=None)
    pre=[x for x in acts[:ci] if UPSTREAM.search(x)] if ci is not None else []
    dec = "upstream" if pre else "local"
    up += dec=="upstream"; loc += dec=="local"
print(f"  committed-but-wrong episodes: {len(committed)}")
print(f"    error decided UPSTREAM (a goto/fill/select preceded the commit click): {up}")
print(f"    error decided LOCALLY  (commit click with no prior state-setting):     {loc}")
if committed:
    pct=100*up/len(committed)
    print(f"    => {pct:.1f}% upstream   (K2 gate: fails if >= 80%)")
    print(f"    {'GATE FAILS — local C(s,a) must be replaced by cost-to-go' if pct>=80 else 'gate passes — local formulation survives'}")

print("\n[detail] committed-but-wrong episodes:")
for r in committed:
    print(f"  task {r['task']} {r['tier']}: exp={r['n_exp']} hit={r['n_hit']} extra={r['n_unmatched']} [{cat(r)}]")
    for i,x in enumerate(r["actions"]): print(f"      [{i}] {x[:74]}")
    for u in r["unmatched"]: print(f"      EXTRA: {u}")
from cawebagent.guard import require
require(len(rows), 'episodes', 'runs/batch and the HTTP archives, which are not distributed')
json.dump(rows, open("out/k2.json","w"), indent=1)
