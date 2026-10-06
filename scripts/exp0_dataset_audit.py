"""Experiment 0 — offline dataset audit. No environment required.
Produces: out/exp0_*.json + console tables. Source of Figure 1."""
import json, collections, re, sys
from pathlib import Path
from webarena_verified.utils import get_package_assets_path

A = get_package_assets_path()
DS = json.loads((A/'dataset/webarena-verified.json').read_text())
OUT = Path(__file__).resolve().parents[1]/'out'; OUT.mkdir(exist_ok=True)

def task_type(t):
    for e in t['eval']:
        if e['evaluator'] == 'AgentResponseEvaluator':
            return e['expected'].get('task_type')
    return None

rows = []
for t in DS:
    nev = [e for e in t['eval'] if e['evaluator'] == 'NetworkEventEvaluator']
    rows.append(dict(task_id=t['task_id'], tpl=t['intent_template_id'],
                     sites=tuple(t['sites']), tt=task_type(t),
                     n_net=len(nev), revision=t['revision'], intent=t['intent']))

print(f"N tasks = {len(DS)}   N templates = {len({r['tpl'] for r in rows})}")
print("\n[task_type]"); 
for k,v in collections.Counter(r['tt'] for r in rows).most_common(): print(f"  {k:10} {v:4d}")
print("\n[sites]")
for k,v in collections.Counter('+'.join(r['sites']) for r in rows).most_common(): print(f"  {k:28} {v:4d}")
print(f"\n[tasks with >=1 NetworkEventEvaluator] {sum(1 for r in rows if r['n_net'])}")

# ---- the核心: enumerate every EXPECTED network event, split GET vs state-changing
evs = []
for t in DS:
    tt = task_type(t)
    for e in t['eval']:
        if e['evaluator'] != 'NetworkEventEvaluator': continue
        x = e['expected']
        urls = x['url'] if isinstance(x['url'], list) else [x['url']]
        for u in urls:
            evs.append(dict(task_id=t['task_id'], tpl=t['intent_template_id'],
                            sites=tuple(t['sites']), tt=tt,
                            method=(x.get('http_method') or 'GET').upper(),
                            url=u, status=x.get('response_status'),
                            has_post=bool(x.get('post_data')),
                            has_qp=bool(x.get('query_params')),
                            has_rc=bool(x.get('response_content')),
                            should_not_exist=e.get('should_not_exist', False)))

print(f"\n[expected network events] total={len(evs)}")
for k,v in collections.Counter(e['method'] for e in evs).most_common(): print(f"  {k:8} {v:4d}")
print(f"  with post_data       {sum(e['has_post'] for e in evs)}")
print(f"  with query_params    {sum(e['has_qp'] for e in evs)}")
print(f"  with response_content{sum(e['has_rc'] for e in evs)}")
print(f"  should_not_exist     {sum(e['should_not_exist'] for e in evs)}")

MUT = [e for e in evs if e['method'] != 'GET']
print(f"\n[STATE-CHANGING expected events] {len(MUT)}  over "
      f"{len({e['task_id'] for e in MUT})} tasks / {len({e['tpl'] for e in MUT})} templates")

def endpoint(u):
    u = re.sub(r'^\^?__[A-Z_]+__', '', u)
    u = re.sub(r'\?.*$', '', u); u = re.sub(r'\$$', '', u)
    u = re.sub(r'/\d+(?=/|$)', '/{id}', u)
    u = re.sub(r'/key/[^/]+', '/key/{k}', u)
    return u or '/'

print("\n[state-changing endpoints]")
cnt = collections.Counter((e['sites'][0] if e['sites'] else '?', e['method'], endpoint(e['url'])) for e in MUT)
for (site, m, ep), n in cnt.most_common():
    print(f"  {n:3d}  {site:16} {m:5} {ep[:88]}")

json.dump(dict(n_tasks=len(DS), rows=rows), open(OUT/'exp0_tasks.json','w'))
json.dump([{**e, 'endpoint': endpoint(e['url'])} for e in evs], open(OUT/'exp0_events.json','w'))
print(f"\nwrote {OUT}/exp0_tasks.json, exp0_events.json")
