"""SANITY CHECK: can the existing harness produce a NEW (verb, object-state) cell?

Cell under test: Hold x Processing-shipped.
Existing data has Hold x Pending only (the positive control).
Question: once an order has shipped, is Hold still offered, does it execute,
and is Unhold still the inverse -- i.e. does the reversibility class hold
across object states, or flip?
"""
import sys, json, re, time; sys.path.insert(0, '.')
from pathlib import Path
from cawebagent.trace.runner import set_env, run_episode, click_button
from cawebagent.trace.reset import hard_reset
set_env(WA_SHOPPING_ADMIN="http://localhost:7780/admin")
from browsergym.utils.obs import flatten_axtree_to_str

ADMIN = "http://localhost:7780/admin"
BUTTON = re.compile(r"\[(\d+)\] button '([^']*)'")
INVERSE = ('unhold','reopen','restore','undo','undelete','uncancel','revert','void','unship')
ORDER = 304
url = f"{ADMIN}/sales/order/view/order_id/{ORDER}/"
st = {}

def snap(label):
    def _f(obs):
        ax = flatten_axtree_to_str(obs['axtree_object'])
        m = re.search(r"rowheader 'Order Status'.*?gridcell '([^']*)'", ax, re.S)
        st[label] = dict(status=(m.group(1) if m else None),
                         buttons=sorted({n for _, n in BUTTON.findall(ax) if n.strip()}))
        return None
    return _f

T0 = time.time()
print("hard reset ...", flush=True); t = time.time(); hard_reset("shopping_admin")
RESET = time.time() - t; print(f"  reset {RESET:.0f}s", flush=True)

acts = [f"goto('{url}')", snap('s0_pending'),
        # manufacture the object state: ship it
        click_button('Ship', nth=0), click_button('Submit Shipment'),
        f"goto('{url}')", snap('s1_shipped'),
        # the cell under test: Hold on a SHIPPED order
        click_button('Hold', nth=0),
        f"goto('{url}')", snap('s2_after_hold'),
        # attempt the inverse
        click_button('Unhold', nth=0),
        f"goto('{url}')", snap('s3_after_unhold')]

t = time.time()
log = run_episode("webarena_verified.284.499.2", acts, Path('runs/sanity_cell'))
EPISODE = time.time() - t
for s in log.steps:
    print(f"  [{s.i}] {str(s.action)[:40]:<40} err={s.last_action_error[:40]!r}", flush=True)

print(f"\n--- CELL: Hold x Processing-shipped ---")
for k in ['s0_pending','s1_shipped','s2_after_hold','s3_after_unhold']:
    v = st.get(k)
    if not v: print(f"{k}: MISSING"); continue
    inv = [b for b in v['buttons'] if any(w in b.lower() for w in INVERSE)]
    print(f"{k:<16} status={str(v['status']):<12} inverse_offered={inv or 'NONE'}")
    print(f"                 buttons={v['buttons']}")

ok = (st.get('s1_shipped',{}).get('status'), st.get('s2_after_hold',{}).get('status'),
      st.get('s3_after_unhold',{}).get('status'))
restored = st.get('s3_after_unhold',{}).get('status') == st.get('s1_shipped',{}).get('status')
print(f"\nstatus chain: {ok}")
print(f"REVERSIBLE (returned to the pre-Hold state)? {restored}")
print(f"\nTIMING: reset {RESET:.0f}s + episode {EPISODE:.0f}s = {time.time()-T0:.0f}s for ONE cell")
json.dump(dict(cell="Hold x Processing-shipped", snapshots=st, restored=restored,
               reset_s=round(RESET,1), episode_s=round(EPISODE,1)),
          open('out/sanity_new_cell.json','w'), indent=1)
print("wrote out/sanity_new_cell.json")
