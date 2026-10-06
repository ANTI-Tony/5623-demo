"""Operational irreversibility probe (no LLM, no API cost).

For each tier-2 action class on shopping_admin:
  1. snapshot the entity's PRE state (affordances + key fields + history)
  2. execute the action, scripted
  3. snapshot POST
  4. enumerate the affordance delta and look for an inverse control
  5. if one plausibly exists, attempt recovery and snapshot FINAL
  6. report: recoverable? how many steps? what residue persists?

This replaces our *asserted* consequence tiers with an *observed* property.
Irreversibility is defined operationally as: the PRE state is not reachable
again through the same interface the agent has.
"""
import sys, json, re, time, argparse; sys.path.insert(0,'.')
from pathlib import Path
from cawebagent.trace.runner import set_env, run_episode, click_button
from cawebagent.trace.reset import hard_reset
set_env(WA_SHOPPING_ADMIN="http://localhost:7780/admin")
from browsergym.utils.obs import flatten_axtree_to_str

ADMIN="http://localhost:7780/admin"
OUT=Path('runs/undo'); OUT.mkdir(parents=True,exist_ok=True)

BUTTON=re.compile(r"\[(\d+)\] button '([^']*)'")
LINK  =re.compile(r"\[(\d+)\] link '([^']*)'")
TEXTBOX=re.compile(r"\[(\d+)\] textbox '([^']*)'[^\n]*?value='([^']*)'")

# words that would indicate the interface offers an inverse of a destructive act
INVERSE_LEXICON = ('unhold','reopen','restore','undo','undelete','uncancel',
                   'revert','void','unship','unsubscribe','recover')

def snapshot(obs):
    ax = flatten_axtree_to_str(obs['axtree_object'])
    st=re.search(r"rowheader 'Order Status'.*?gridcell '([^']*)'", ax, re.S)
    return dict(url=obs['url'], status=(st.group(1) if st else None),
                buttons=sorted({n for _,n in BUTTON.findall(ax) if n.strip()}),
                links=sorted({n for _,n in LINK.findall(ax) if n.strip()}),
                fields={n:v for _,n,v in TEXTBOX.findall(ax)},
                ax_len=len(ax), ax=ax)

def probe(store,label):
    def _f(obs):
        store[label]=snapshot(obs); return None      # returning None skips env.step
    return _f

def goto(u): return f"goto('{u}')"

# ---------------------------------------------------------------- action classes
def classes():
    """Each entry: an action we execute, then we look for an inverse control.
    order_hold is a POSITIVE CONTROL -- Magento does expose 'Unhold', so a probe
    that reports everything irreversible would be shown to be broken."""
    return {
    'order_hold': dict(
        task="webarena_verified.257.470.2", entity=f"{ADMIN}/sales/order/view/order_id/302/",
        do=[click_button('Hold',nth=0)],
        undo=[click_button('Unhold',nth=0)],
        note="POSITIVE CONTROL: Magento hold an order, then actually take the inverse"),
    'order_cancel': dict(
        task="webarena_verified.257.471.2", entity=f"{ADMIN}/sales/order/view/order_id/307/",
        do=[click_button('Cancel',nth=0), click_button('OK')],
        note="Magento: cancel an order"),
    'shipment_create': dict(
        task="webarena_verified.284.499.2", entity=f"{ADMIN}/sales/order/view/order_id/304/",
        do=[click_button('Ship',nth=0), click_button('Submit Shipment')],
        note="Magento: create a shipment"),
    'review_delete': dict(
        task="webarena_verified.246.774.2", entity=f"{ADMIN}/review/product/edit/id/353/",
        do=[click_button('Delete Review',nth=0), click_button('OK')],
        note="Magento: delete a product review"),
    }

def fill_named(label,value):
    def _f(obs):
        ax=flatten_axtree_to_str(obs['axtree_object'])
        m=re.search(r"\[(\d+)\] textbox '"+re.escape(label)+r"'",ax)
        if not m: raise RuntimeError(f"textbox {label!r} not found")
        return f"fill('{m.group(1)}', '{value}')"
    return _f

def expand(do):
    out=[]
    for a in do:
        if isinstance(a,tuple) and a[0]=='fill_first_named': out.append(fill_named(a[1],a[2]))
        else: out.append(a)
    return out

def run_one(name,cfg,do_reset=True):
    st={}
    if do_reset:
        t=time.time(); hard_reset("shopping_admin"); print(f"  reset {time.time()-t:.0f}s",flush=True)
    acts=[goto(cfg['entity']), probe(st,'PRE')] + expand(cfg['do']) + \
         [goto(cfg['entity']), probe(st,'POST')]
    if cfg.get('undo'):                      # positive control: actually take the inverse
        acts += expand(cfg['undo']) + [goto(cfg['entity']), probe(st,'AFTER_UNDO')]
    d=OUT/name
    try:
        log=run_episode(cfg['task'], acts, d)
    except Exception as e:
        print(f"  !! {name}: {e}",flush=True); return dict(cls=name,error=str(e))
    for s in log.steps:
        print(f"    [{s.i}] {str(s.action)[:44]:<44} err={s.last_action_error[:40]!r}",flush=True)
    und=st.get('AFTER_UNDO')
    pre,post=st.get('PRE'),st.get('POST')
    if not pre or not post: return dict(cls=name,error='probe missing')
    gained=sorted(set(post['buttons'])-set(pre['buttons']))
    lost  =sorted(set(pre['buttons'])-set(post['buttons']))
    inverse=[b for b in gained if any(w in b.lower() for w in INVERSE_LEXICON)]
    res=dict(cls=name, note=cfg['note'], url=cfg['entity'],
             pre_status=pre.get('status'), post_status=post.get('status'),
             pre_buttons=pre['buttons'], post_buttons=post['buttons'],
             gained=gained, lost=lost, inverse_affordance=inverse,
             undo_status=(und.get('status') if und else None),
             undo_restored=(bool(und) and und.get('status')==pre.get('status')),
             field_changes={k:[pre['fields'].get(k),post['fields'].get(k)]
                            for k in set(pre['fields'])|set(post['fields'])
                            if pre['fields'].get(k)!=post['fields'].get(k)})
    (d/'snapshots.json').write_text(json.dumps({k:{kk:vv for kk,vv in v.items() if kk!='ax'}
                                                for k,v in st.items()},indent=1))
    for k,v in st.items(): (d/f'{k}.ax.txt').write_text(v['ax'])
    print(f"  status: {pre.get('status')} -> {post.get('status')}"
          + (f" -> {und.get('status')} (after taking the inverse)" if und else ""),flush=True)
    print(f"  gained={gained}\n  lost={lost}\n  INVERSE AFFORDANCE={inverse or 'NONE'}",flush=True)
    return res

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--only'); ap.add_argument('--no-reset',action='store_true')
    a=ap.parse_args()
    C=classes(); out=[]
    for name,cfg in C.items():
        if a.only and name!=a.only: continue
        print(f"\n=== {name} ===",flush=True)
        out.append(run_one(name,cfg,do_reset=not a.no_reset))
        Path('out/undo_probe.json').write_text(json.dumps(out,indent=1))
    print("\nwrote out/undo_probe.json")
