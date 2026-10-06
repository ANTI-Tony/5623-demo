r"""The two evaluator-field counts the paper uses to justify HAR content capture.

Section 5.1 says embedding response bodies is not optional because 447 of the
benchmark's evaluators read request `post_data` and 31 read response bodies.
Both are counted over NetworkEventEvaluator *instances* in the released task
specification -- not over expected events, which is a different denominator
(out/exp0_events.json gives 506 and 36 at the event level).

Needs the webarena_verified package, so it is one of the analyses that cannot be
re-run from out/ alone.

  out: out/k17_evaluator_fields.json
"""
import json, collections, sys
from pathlib import Path
from webarena_verified.utils import get_package_assets_path

ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / 'out'
D = json.loads((Path(get_package_assets_path()) / 'dataset/webarena-verified.json').read_text())

def keys(o):
    """Every key name anywhere in the evaluator's nested expectation."""
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from keys(v)

net = [e for t in D for e in t['eval'] if e['evaluator'] == 'NetworkEventEvaluator']
resp = [e for t in D for e in t['eval'] if e['evaluator'] == 'AgentResponseEvaluator']
has = lambda field: sum(1 for e in net if field in set(keys(e)))

res = dict(tasks=len(D),
           network_event_evaluators=len(net),
           agent_response_evaluators=len(resp),
           reading_post_data=has('post_data'),
           reading_response_content=has('response_content'),
           reading_http_method=has('http_method'),
           reading_response_status=has('response_status'))
OUT.mkdir(exist_ok=True)
(OUT / 'k17_evaluator_fields.json').write_text(json.dumps(res, indent=1))

for k, v in res.items():
    print(f"  {k:<28} {v}")

PRINTED = {'tasks': 812, 'network_event_evaluators': 663,
           'agent_response_evaluators': 812,
           'reading_post_data': 447, 'reading_response_content': 31}
print('-' * 52)
bad = 0
for k, want in PRINTED.items():
    ok = res[k] == want
    bad += (not ok)
    print(f"  {'OK ' if ok else 'MISMATCH'} {k:<28} script={res[k]:<6} paper={want}")
print('-' * 52)
print('reproduces' if not bad else f'!! {bad} value(s) diverge')
sys.exit(1 if bad else 0)
