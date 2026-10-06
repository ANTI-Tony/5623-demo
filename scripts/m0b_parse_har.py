import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cawebagent.trace.har_parse import parse_har, collateral, expected_specs
from webarena_verified.utils import get_package_assets_path

har = sys.argv[1]
tid = int(sys.argv[2])
DS = json.loads((get_package_assets_path()/'dataset/webarena-verified.json').read_text())
task = next(t for t in DS if t['task_id'] == tid)

ev = parse_har(har)
mut = [e for e in ev if e.is_mutation]
print(f"HAR entries        {len(ev)}")
print(f"  non-GET          {len(mut)}")
print(f"  with post body   {sum(1 for e in mut if e.post_body)}")
print(f"  document reqs    {sum(1 for e in ev if e.is_document)}")
print(f"\ntask {tid}: {task['intent']}")
print("expected state-changing specs:")
for s in expected_specs(task): print("   ", s['method'], s['url'])
print("\nobserved non-GET:")
for e in mut: print(f"    {e.method} {e.path}  status={e.status}  body={(e.post_body or '')[:60]!r}")
col = collateral(mut, task)
print(f"\ncollateral (unexpected, non-benign) : {len(col)}")
for e in col: print("   ", e.method, e.path)
