import sys, json; sys.path.insert(0,'.')
from pathlib import Path
from cawebagent.trace.har_parse import parse_har, segment, collateral, expected_specs
from webarena_verified.utils import get_package_assets_path
from webarena_verified.api import WebArenaVerified
from webarena_verified.types.config import WebArenaVerifiedConfig, EnvironmentConfig
from webarena_verified.types.task import WebArenaSite

DS = json.loads((get_package_assets_path()/'dataset/webarena-verified.json').read_text())
task = next(t for t in DS if t['task_id']==470)
import os; T4 = os.environ.get('T4_OUT', 'runs/t4_demo'); arms = json.load(open(T4 + '/arms.json'))

cfg = WebArenaVerifiedConfig(environments={
    WebArenaSite.SHOPPING_ADMIN: EnvironmentConfig(urls=["http://localhost:7780/admin"])})
wa = WebArenaVerified(config=cfg)

RESP = json.dumps({"task_type":"mutate","status":"SUCCESS","retrieved_data":None,"error_details":None})
print("="*80); print("T4 — collateral detection vs official score"); print("="*80)
print(f"task 470: {task['intent']}")
print("expected:", [f"{s['method']} {s['url']}" for s in expected_specs(task)])

rows=[]
for arm, m in arms.items():
    ev = parse_har(m['har'])
    a0, a1 = m['window']
    seg = segment(ev, a0, a1)
    mut_all = [e for e in ev if e.is_mutation]
    mut_act = [e for e in seg['action'] if e.is_mutation]
    col = collateral(mut_act, task)
    try:
        r = wa.evaluate_task(task_id=470, agent_response=RESP, network_trace=Path(m['har']))
        score, status = r.score, r.status.value
    except Exception as e:
        score, status = None, f"ERR:{type(e).__name__}"
    print(f"\n--- {arm} ---")
    print(f"  HAR entries {len(ev)}   setup {len(seg['setup'])} / action {len(seg['action'])} / validate {len(seg['validate'])}")
    print(f"  non-GET total {len(mut_all)}  in action phase {len(mut_act)}")
    for e in mut_act: print(f"      {e.method} {e.path}  -> {e.status}")
    print(f"  COLLATERAL detected: {len(col)}")
    for e in col: print(f"      *** {e.method} {e.path}")
    print(f"  OFFICIAL SCORE: {score}  status={status}")
    rows.append(dict(arm=arm, entries=len(ev), mut_action=len(mut_act),
                     collateral=len(col), score=score, status=status))

json.dump(rows, open(T4 + '/t4_result.json','w'), indent=1)
print("\n" + "="*80)
a = next(r for r in rows if r['arm']=='A_clean'); b = next(r for r in rows if r['arm']=='B_collateral')
print(f"A_clean      : official={a['score']}  collateral={a['collateral']}")
print(f"B_collateral : official={b['score']}  collateral={b['collateral']}")
if a['score'] == b['score'] and b['collateral'] > a['collateral']:
    print("\n>>> DEMONSTRATED: identical official score, different real-world damage.")
    print(">>> The benchmark cannot distinguish them; our detector can.")
