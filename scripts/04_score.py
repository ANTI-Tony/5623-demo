"""Score an agent episode: official evaluator + collateral detection."""
import sys, json, argparse; sys.path.insert(0,'.')
from pathlib import Path
from cawebagent.trace.har_parse import parse_har, segment, collateral, expected_specs
from webarena_verified.utils import get_package_assets_path
from webarena_verified.api import WebArenaVerified
from webarena_verified.types.config import WebArenaVerifiedConfig, EnvironmentConfig
from webarena_verified.types.task import WebArenaSite

ap = argparse.ArgumentParser(); ap.add_argument("rundir"); a = ap.parse_args()
d = Path(a.rundir); rec = json.loads((d/"agent.json").read_text())
DS = json.loads((get_package_assets_path()/'dataset/webarena-verified.json').read_text())
tid = int(rec["task"].split(".")[2]); task = next(t for t in DS if t["task_id"]==tid)

cfg = WebArenaVerifiedConfig(environments={
    WebArenaSite.SHOPPING_ADMIN: EnvironmentConfig(urls=["http://localhost:7780/admin"])})
wa = WebArenaVerified(config=cfg)
final = next((s["action"] for s in reversed(rec["steps"]) if "send_msg_to_user" in s["action"]), "")
import re
m = re.search(r"send_msg_to_user\(\s*['\"](.+)['\"]\s*\)\s*$", final, re.S)
resp = m.group(1) if m else "{}"

ev = parse_har(rec["har"]); a0,a1 = rec["window"]
seg = segment(ev, a0, a1)
mut = [e for e in seg["action"] if e.is_mutation]
col = collateral(mut, task)
try:
    r = wa.evaluate_task(task_id=tid, agent_response=resp, network_trace=Path(rec["har"]))
    score, status = r.score, r.status.value
except Exception as e:
    score, status = None, f"ERR:{type(e).__name__}: {str(e)[:80]}"

print(f"task {tid} [{rec['tier']}]  {task['intent']}")
print(f"  steps={len(rec['steps'])}  cost=${rec['usd']:.4f}")
print(f"  action-phase state changes: {len(mut)}")
for e in mut: print(f"      {e.method} {e.path} -> {e.status}")
print(f"  collateral: {len(col)}")
print(f"  OFFICIAL SCORE: {score}   status={status}")
out = dict(task_id=tid, tier=rec["tier"], steps=len(rec["steps"]), usd=rec["usd"],
           mutations=len(mut), collateral=len(col), score=score, status=status)
(d/"score.json").write_text(json.dumps(out, indent=1)); print("wrote", d/"score.json")
