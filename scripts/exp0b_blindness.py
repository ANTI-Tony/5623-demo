"""Experiment 0b — quantify the benchmark's blindness to collateral state change.
This is the paper's motivating measurement. No environment required."""
import json, collections
from pathlib import Path
from webarena_verified.utils import get_package_assets_path

DS = json.loads((get_package_assets_path()/'dataset/webarena-verified.json').read_text())
OUT = Path(__file__).resolve().parents[1]/'out'

def tt(t):
    for e in t['eval']:
        if e['evaluator']=='AgentResponseEvaluator': return e['expected'].get('task_type')

n_are = n_nee = 0
snx = []                      # should_not_exist assertions
mut_tasks, mut_tpls = set(), set()
per_task_mut = collections.Counter()
for t in DS:
    for e in t['eval']:
        if e['evaluator']=='AgentResponseEvaluator': n_are += 1
        elif e['evaluator']=='NetworkEventEvaluator':
            n_nee += 1
            if e.get('should_not_exist'):
                snx.append((t['task_id'], tt(t), t['sites'], e['expected'].get('http_method','GET'), e['expected']['url']))
            m = (e['expected'].get('http_method') or 'GET').upper()
            if m != 'GET':
                mut_tasks.add(t['task_id']); mut_tpls.add(t['intent_template_id'])
                per_task_mut[t['task_id']] += 1

mutate_tasks = {t['task_id'] for t in DS if tt(t)=='mutate'}
print("="*72)
print("EXP-0b  Benchmark blindness to collateral state change")
print("="*72)
print(f"tasks                                    {len(DS)}")
print(f"templates                                {len({t['intent_template_id'] for t in DS})}")
print(f"AgentResponseEvaluator instances         {n_are}")
print(f"NetworkEventEvaluator instances          {n_nee}")
print(f"tasks declared task_type=mutate          {len(mutate_tasks)}")
print(f"tasks with >=1 state-changing expectation{len(mut_tasks)}  ({len(mut_tpls)} templates)")
print()
print(f"NEGATIVE assertions (should_not_exist)   {len(snx)}   "
      f"= {100*len(snx)/max(n_nee,1):.2f}% of network evaluators")
for s in snx: print("   ", s)
print()
# mutate tasks with NO network verification at all
no_net = [t['task_id'] for t in DS if tt(t)=='mutate' and not any(e['evaluator']=='NetworkEventEvaluator' for e in t['eval'])]
print(f"mutate tasks with NO NetworkEventEvaluator {len(no_net)}  "
      f"({100*len(no_net)/len(mutate_tasks):.1f}% of mutate tasks)")
print(f"  -> these are scored on the agent's own textual answer only")
print()
print("[expected state-changing events per task]")
for k,v in sorted(collections.Counter(per_task_mut.values()).items()): print(f"  {k} event(s): {v} tasks")
json.dump(dict(n_tasks=len(DS), n_are=n_are, n_nee=n_nee,
               n_mutate=len(mutate_tasks), n_statechanging_tasks=len(mut_tasks),
               n_statechanging_templates=len(mut_tpls), n_should_not_exist=len(snx),
               should_not_exist=snx, mutate_without_network_eval=no_net),
          open(OUT/'exp0b_blindness.json','w'), indent=1)
print(f"\nwrote {OUT}/exp0b_blindness.json")
