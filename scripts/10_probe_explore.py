"""Exploration for the undo probe: dump the a11y tree of an order page so we can
see which affordances exist before/after a tier-2 action. No LLM."""
import sys, json; sys.path.insert(0,'.')
from pathlib import Path
from cawebagent.trace.runner import set_env, run_episode
set_env(WA_SHOPPING_ADMIN="http://localhost:7780/admin")
from browsergym.utils.obs import flatten_axtree_to_str

print('imports done',flush=True)
OUT=Path('runs/probe'); OUT.mkdir(parents=True,exist_ok=True)
print('outdir ready',flush=True)
cap={}
def dump(label,url=None):
    def _f(obs):
        cap[label]=dict(url=obs['url'], ax=flatten_axtree_to_str(obs['axtree_object']))
        return None
    return _f
acts=[ "goto('http://localhost:7780/admin/sales/order/view/order_id/302/')",
       dump('order302'),
       "goto('http://localhost:7780/admin/review/product/index/')",
       dump('reviews') ]
print('calling run_episode (env.reset can take ~1-2 min) ...',flush=True)
run_episode("webarena_verified.257.470.2", acts, OUT/'explore')
print('episode done',flush=True)
for k,v in cap.items():
    (OUT/f'{k}.txt').write_text(v['ax'])
    print(f"=== {k} :: {v['url']}  ({len(v['ax'])} chars)")
print("saved to runs/probe/")
