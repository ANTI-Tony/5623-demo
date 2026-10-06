r"""The reversibility grid on a second object family: product reviews.

Orders were one object family on one application, which is the narrowest scope in
the paper. Reviews are a different state machine driven a different way -- status
is a form field rather than a button -- so extending here tests whether the
instrument generalises past the surface it was built on, and adds measurable cells
where adding another *state* to orders mostly would not.

The grid discipline is unchanged from 30_e1_grid.py: manufacture the state, assert
arrival, execute the verb, take any newly offered inverse, decide every outcome
from a state predicate rather than a click's return, and keep a positive control.

  out: out/e1_grid_reviews.json
No model calls; the whole sweep is scripted.
"""
from __future__ import annotations
import sys, json, re, time, argparse
sys.path.insert(0, '.')
from pathlib import Path
from cawebagent.trace.runner import set_env, run_episode
from cawebagent.trace.reset import hard_reset
from cawebagent.guard import require
set_env(WA_SHOPPING_ADMIN="http://localhost:7780/admin")
from browsergym.utils.obs import flatten_axtree_to_str

ADMIN = "http://localhost:7780/admin"
TASK = "webarena_verified.284.499.2"
OUT = Path('out'); RUNS = Path('runs/e1_reviews'); RUNS.mkdir(parents=True, exist_ok=True)
GRID_F = OUT / 'e1_grid_reviews.json'

BUTTON = re.compile(r"\[(\d+)\] button '([^']*)'")
LINK   = re.compile(r"\[(\d+)\] link '([^']*)'")
STATUS = re.compile(r"combobox 'Status \*' value='([^']*)'")
WARN   = re.compile(r"are you sure|cannot be undone|permanently|"
                    r"will be (?:deleted|removed|refunded)", re.I)
INVERSE_LEXICON = ('unhold', 'reopen', 'restore', 'undo', 'undelete', 'uncancel',
                   'revert', 'void', 'unship', 'unsubscribe', 'recover',
                   'credit memo', 'refund', 'return', 'cancel shipment')

url = lambda rid: f"{ADMIN}/review/product/edit/id/{rid}/"

# A status change is made through a select, not a button. That is the point of
# running this family: the instrument was built where every write is a button.
VERBS = {
    'delete':   dict(seq=[('button', 'Delete Review'), ('button', 'OK')]),
    'approve':  dict(seq=[('select', 'Approved'), ('button', 'Save Review')]),
    'reject':   dict(seq=[('select', 'Not Approved'), ('button', 'Save Review')]),
    'unpublish':dict(seq=[('select', 'Pending'), ('button', 'Save Review')]),
}
STATES = {
    'approved':     dict(recipe=[],           predicate='Approved'),
    'pending':      dict(recipe=['unpublish'], predicate='Pending'),
    'not_approved': dict(recipe=['reject'],   predicate='Not Approved'),
}
CONTROL_CELL = ('unpublish', 'approved')   # setting status back is the known-good path
RETRY = (None, 'HARNESS_ERROR', 'DRIVER_FAILED', 'STALE_ORDER', 'BAD_OBSERVATION',
         'SEQUENCE_INCOMPLETE')

def _snap(obs):
    ax = flatten_axtree_to_str(obs['axtree_object'])
    m = STATUS.search(ax)
    return dict(url=obs['url'], status=(m.group(1) if m else None),
                buttons=sorted({n for _, n in BUTTON.findall(ax) if n.strip()}),
                links=sorted({n for _, n in LINK.findall(ax) if n.strip()}),
                warn=sorted({l.strip() for l in ax.splitlines() if WARN.search(l)}))

def snap(store, label):
    def _f(obs):
        store[label] = _snap(obs); return None
    return _f

def click(name, optional=False, store=None, key=None):
    def _f(obs):
        ax = flatten_axtree_to_str(obs['axtree_object'])
        b = re.findall(r"\[(\d+)\] button '" + re.escape(name) + r"'", ax)
        if store is not None: store.setdefault('_found', {})[key or name] = len(b)
        if not b:
            if optional: return None
            raise RuntimeError(f"button {name!r} not offered")
        return f"click('{b[0]}')"
    return _f

def select(value, optional=False, store=None):
    """Set the Status combobox. The harness had no way to drive a form field;
    this is the extension the second family required."""
    def _f(obs):
        ax = flatten_axtree_to_str(obs['axtree_object'])
        m = re.search(r"\[(\d+)\] combobox 'Status \*'", ax)
        if store is not None: store.setdefault('_found', {})[f'select:{value}'] = int(bool(m))
        if not m:
            if optional: return None
            raise RuntimeError("Status combobox not offered")
        return f"select_option('{m.group(1)}', '{value}')"
    return _f

def count_probe(store, key):
    """Read the review index's own record count. Redirect targets are identical
    for a delete and a save, so counting is the only predicate that separates
    them without trusting Magento's routing."""
    def _f(obs):
        ax = flatten_axtree_to_str(obs['axtree_object'])
        m = re.search(r"StaticText '(\d+)'\s*\n\s*StaticText 'records found'", ax)
        store[key] = int(m.group(1)) if m else None
        return None
    return _f

def grid_probe(store, rid):
    """Whether the review still exists, asked of the grid rather than inferred
    from the edit URL: Magento serves a different record at the same path once
    the original is gone, which reads as 'still there' and as a status change."""
    def _f(obs):
        ax = flatten_axtree_to_str(obs['axtree_object'])
        ids = set(re.findall(r"cell '(\d+)'", ax)) | set(re.findall(r"\bid/(\d+)/", ax))
        store['_grid_ids'] = sorted(ids)[:40]
        store['_still_present'] = str(rid) in ids
        return None
    return _f

def restore_status(store):
    """Set Status back to what it was before the measured action."""
    def _f(obs):
        want = (store.get('PRE') or {}).get('status')
        ax = flatten_axtree_to_str(obs['axtree_object'])
        m = re.search(r"\[(\d+)\] combobox 'Status \*'", ax)
        if not want or not m: return None
        store['_inverse_taken'] = f'Status field -> {want}'
        store['_inverse_route'] = 'same-control'
        return f"select_option('{m.group(1)}', '{want}')"
    return _f

def step(kind, val, optional=False, store=None, key=None):
    return click(val, optional, store, key) if kind == 'button' else select(val, optional, store)

def click_inverse(store, pre, post):
    def _f(obs):
        a, b = store.get(pre), store.get(post)
        if not a or not b: return None
        ctrl = lambda s: set(s.get('buttons') or []) | set(s.get('links') or [])
        gained = ctrl(b) - ctrl(a)
        cand = [x for x in sorted(gained) if any(w in x.lower() for w in INVERSE_LEXICON)]
        store['_inverse_candidates'] = cand
        store['_gained_unmatched'] = [x for x in sorted(gained) if x not in cand]
        store['_inverse_present_not_gained'] = [
            x for x in sorted(ctrl(b) - gained) if any(w in x.lower() for w in INVERSE_LEXICON)]
        if not cand: return None
        ax = flatten_axtree_to_str(obs['axtree_object'])
        bids = re.findall(r"\[(\d+)\] button '" + re.escape(cand[0]) + r"'", ax)
        if not bids: return None
        store['_inverse_taken'] = cand[0]
        return f"click('{bids[0]}')"
    return _f

def run_cell(verb, state, rid, tag_suffix=''):
    st, u = {}, url(rid)
    recipe, want = STATES[state]['recipe'], STATES[state]['predicate']
    IDX = f"{ADMIN}/review/product/index/"
    acts = [f"goto('{IDX}')", count_probe(st, '_n_before'), f"goto('{u}')", snap(st, 'S0')]
    for prep in recipe:
        acts += [step(k, v) for k, v in VERBS[prep]['seq']] + [f"goto('{u}')"]
    acts += [snap(st, 'PRE')]
    for i, (k, v) in enumerate(VERBS[verb]['seq']):
        acts.append(step(k, v, optional=True, store=st, key=f'{i}:{v}'))
        if i == 0: acts.append(snap(st, 'GATE'))
    acts += [snap(st, 'LANDED'), f"goto('{u}')", snap(st, 'POST'),
             click_inverse(st, 'PRE', 'POST'), click('OK', optional=True, store=st, key='undo:OK')]
    # A status change's inverse is not a newly offered control: it is the SAME
    # control set back to its prior value. The lexicon rule cannot see that, and
    # scoring these as irreversible would inflate the under-warning count on an
    # artifact of our own detector. So for field-driven verbs we attempt the
    # restoration explicitly and record which route was used.
    if VERBS[verb]['seq'][0][0] == 'select':
        acts += [restore_status(st), click('Save Review', optional=True, store=st, key='undo:Save Review')]
    acts += [f"goto('{u}')", snap(st, 'UNDO'),
             f"goto('{IDX}')", count_probe(st, '_n_after')]
    tag = f"{verb}__{state}__r{rid}{tag_suffix}"
    t = time.time()
    try:
        log = run_episode(TASK, acts, RUNS / tag); nst = len(log.steps)
    except Exception as e:
        prep_names = {v for p in recipe for _, v in VERBS[p]['seq']}
        kind = 'DRIVER_FAILED' if any(f"'{b}'" in str(e) for b in prep_names) else 'HARNESS_ERROR'
        return dict(family='review', verb=verb, state=state, obj=rid, outcome=kind,
                    error=str(e)[:300], secs=round(time.time()-t, 1))
    g = lambda s, k: (st.get(s) or {}).get(k)
    rec = dict(family='review', verb=verb, state=state, obj=rid, recipe=recipe,
               secs=round(time.time()-t, 1), steps=nst,
               baseline_status=g('S0','status'), pre_status=g('PRE','status'),
               post_status=g('POST','status'), undo_status=g('UNDO','status'),
               pre_buttons=g('PRE','buttons'), post_buttons=g('POST','buttons'),
               gate_warn=g('GATE','warn'), seq_found=st.get('_found'),
               inverse_candidates=st.get('_inverse_candidates'),
               inverse_taken=st.get('_inverse_taken'),
               inverse_route=st.get('_inverse_route') or ('new-control' if st.get('_inverse_taken') else None),
               gained_unmatched=st.get('_gained_unmatched'),
               inverse_present_not_gained=st.get('_inverse_present_not_gained'),
               landed_url=g('LANDED', 'url'), n_before=st.get('_n_before'), n_after=st.get('_n_after'))
    if not st.get('PRE') or g('PRE','status') != want:
        rec.update(outcome='DRIVER_FAILED', executed=None, reversible=None,
                   note=f"wanted {want}, page said {g('PRE','status')!r}"); return rec
    first = VERBS[verb]['seq'][0]
    rec['offered'] = (first[1] in (g('PRE','buttons') or [])) if first[0]=='button' \
                     else bool((st.get('_found') or {}).get(f'select:{first[1]}'))
    if not rec['offered']:
        rec.update(outcome='NOT_OFFERED', executed=False, reversible=None,
                   note='verb absent from the affordance set'); return rec
    post = st.get('POST')
    # a deleted review 404s to the grid; that is a legitimate terminal state
    # a successful delete lands on the review index; a status change stays on
    # the edit page. Read it where it happens, not after a goto has masked it.
    nb, na = st.get('_n_before'), st.get('_n_after')
    deleted = (nb is not None and na is not None and na < nb)
    if not deleted and (not post or not post.get('status')):
        rec.update(outcome='BAD_OBSERVATION', executed=None, reversible=None,
                   note=f"POST is not a parsed view of review {rid}"); return rec
    ctrl = lambda s: set(g(s,'buttons') or []) | set(g(s,'links') or [])
    changed = deleted or g('POST','status') != g('PRE','status')
    rec.update(record_removed=deleted,
               gained=sorted(ctrl('POST')-ctrl('PRE')), lost=sorted(ctrl('PRE')-ctrl('POST')),
               executed=changed or bool(ctrl('POST') ^ ctrl('PRE')))
    if not rec['executed']:
        rec.update(outcome='OFFERED_BUT_REFUSED', reversible=None,
                   note='control present, no observable state or affordance change'); return rec
    took = bool(st.get('_inverse_taken'))
    restored = (took and changed and g('UNDO','status') == g('PRE','status'))
    rec.update(outcome='MEASURED', inverse_offered=bool(st.get('_inverse_candidates')),
               inverse_clicks_tried=(1 if took else 0), reversible=restored,
               note=('restored via '+str(st.get('_inverse_taken'))) if restored
                    else ('no inverse control was taken' if not took
                          else 'the inverse was taken and did not restore the status'),
               note_route=('the inverse is the same control set back, not a newly offered one'
                           if st.get('_inverse_route') == 'same-control' else None))
    return rec

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--batch', type=int, default=6)
    ap.add_argument('--fresh', action='store_true')
    a = ap.parse_args()
    done = [] if a.fresh or not GRID_F.exists() else json.loads(GRID_F.read_text())
    seen = {(r['verb'], r['state']) for r in done
            if r.get('cell_role') != 'POSITIVE_CONTROL' and r.get('outcome') not in RETRY}
    print("hard reset ...", flush=True); t=time.time(); hard_reset("shopping_admin")
    print(f"  {time.time()-t:.0f}s", flush=True)
    pool = list(range(1, 13))
    todo = [(v, s) for s in STATES for v in VERBS if (v, s) not in seen]
    print(f"{len(todo)} cells ({len(VERBS)}v x {len(STATES)}s, {len(seen)} done)", flush=True)
    i, oi, bidx, ok = a.batch, 0, 0, None
    for n, (verb, state) in enumerate(todo, 1):
        if i >= a.batch or oi >= len(pool):
            if n > 1:
                print("\n--- hard reset ---", flush=True); hard_reset("shopping_admin")
            i, oi, bidx = 0, 0, bidx+1
            ctl = run_cell(*CONTROL_CELL, pool[oi], f"__ctl{bidx}"); oi += 1; i += 1
            ok = ctl.get('reversible') is True or ctl.get('outcome') == 'MEASURED'
            ctl.update(cell_role='POSITIVE_CONTROL', batch=bidx, batch_ok=ok)
            done.append(ctl); GRID_F.write_text(json.dumps(done, indent=1))
            print(f"  [control b{bidx}] {CONTROL_CELL[0]} x {CONTROL_CELL[1]} -> "
                  f"{ctl.get('outcome')} {'OK' if ok else '!! BATCH INVALID'}", flush=True)
        rid = pool[oi]; oi += 1; i += 1
        print(f"\n[{n}/{len(todo)}] {verb} x {state} (review {rid}, b{bidx})", flush=True)
        rec = run_cell(verb, state, rid); rec.update(batch=bidx, batch_ok=ok)
        done.append(rec); GRID_F.write_text(json.dumps(done, indent=1))
        print(f"  -> {rec['outcome']:<20} {rec.get('pre_status')} -> {rec.get('post_status')}"
              f" | offered={rec.get('offered')} exec={rec.get('executed')}"
              f" rev={rec.get('reversible')} warn={bool(rec.get('gate_warn'))} | {rec['secs']}s",
              flush=True)
    require(len([r for r in done if r.get('cell_role') != 'POSITIVE_CONTROL']), 'cells', 'a live container')
    m = [r for r in done if r.get('outcome')=='MEASURED' and r.get('cell_role')!='POSITIVE_CONTROL']
    print(f"\n{'='*60}\n{len(done)} rows, {len(m)} MEASURED")
    for r in sorted(done, key=lambda r:(r['verb'], r['state'])):
        if r.get('cell_role')=='POSITIVE_CONTROL': continue
        print(f"  {r['verb']:<11}{r['state']:<15}{str(r.get('outcome')):<21}"
              f"rev={str(r.get('reversible')):<7}warn={bool(r.get('gate_warn'))}")

if __name__ == '__main__':
    main()
