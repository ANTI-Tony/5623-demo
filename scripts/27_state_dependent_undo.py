"""FR7 as revised: reversibility is a property of (action, object state), not of
the verb. Folding both into one 'cancel' row hides the thing that matters in
deployment -- an order can usually be cancelled while pending and not once it has
shipped.

This drives the same order through two states and records, at each, which actions
the interface offers and which of those have an inverse. No model in the loop.
"""
import sys, json, re, time; sys.path.insert(0, '.')
from pathlib import Path
from cawebagent.trace.runner import set_env, run_episode, click_button
from cawebagent.trace.reset import hard_reset
set_env(WA_SHOPPING_ADMIN="http://localhost:7780/admin")
from browsergym.utils.obs import flatten_axtree_to_str

ADMIN="http://localhost:7780/admin"
OUT=Path('runs/state_undo'); OUT.mkdir(parents=True, exist_ok=True)
BUTTON=re.compile(r"\[(\d+)\] button '([^']*)'")
INVERSE=('unhold','reopen','restore','undo','undelete','uncancel','revert','void','unship')

def snap(store, label):
    def _f(obs):
        ax=flatten_axtree_to_str(obs['axtree_object'])
        st=re.search(r"rowheader 'Order Status'.*?gridcell '([^']*)'", ax, re.S)
        store[label]=dict(status=(st.group(1) if st else None),
                          buttons=sorted({n for _,n in BUTTON.findall(ax) if n.strip()}))
        return None
    return _f

ORDER=304                      # pending at snapshot time
url=f"{ADMIN}/sales/order/view/order_id/{ORDER}/"
st={}
print(f"hard reset ...", flush=True); t=time.time(); hard_reset("shopping_admin")
print(f"  {time.time()-t:.0f}s", flush=True)
acts=[f"goto('{url}')", snap(st,'pending'),
      click_button('Ship', nth=0), click_button('Submit Shipment'),
      f"goto('{url}')", snap(st,'after_shipment'),
      # does Cancel still WORK once shipped, or is it offered but refused?
      click_button('Cancel', nth=0), click_button('OK'),
      f"goto('{url}')", snap(st,'after_cancel_attempt')]
log=run_episode("webarena_verified.284.499.2", acts, OUT/'order_state')
for s in log.steps:
    print(f"  [{s.i}] {str(s.action)[:44]:<44} err={s.last_action_error[:32]!r}", flush=True)

res={}
for k,v in st.items():
    inv=[b for b in v['buttons'] if any(w in b.lower() for w in INVERSE)]
    res[k]=dict(status=v['status'], buttons=v['buttons'], inverse=inv)
    print(f"\n{k}: status={v['status']}")
    print(f"   offers: {v['buttons']}")
    print(f"   inverse controls: {inv or 'none'}")
if 'pending' in res and 'after_shipment' in res:
    lost=sorted(set(res['pending']['buttons'])-set(res['after_shipment']['buttons']))
    print(f"\nactions withdrawn once the order shipped: {lost}")
    res['withdrawn']=lost
json.dump(res, open('out/k14_state_undo.json','w'), indent=1)
print("\nwrote out/k14_state_undo.json")
