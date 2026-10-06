"""E1: the (write-verb x object-state) reversibility grid.

One row per cell: was the verb offered, did it execute, what did the application
warn, was an inverse offered, was it TAKEN, did the prior status return.

Two claims are read off this table:
  R2 (primary)   does the application's own warning signal track measured
                 irreversibility?  -> Cohen's kappa over (gate_warn, reversible)
  R1 (secondary) does the reversibility class flip across object states?
                 -> flip rate vs the verb's modal class, NOT_OFFERED included

MEASURED FACTS THIS DESIGN RESTS ON (verified on this machine, 2026-08-31):

1. Every Magento click reports `TimeoutError: Locator.click: Timeout 500` because
   the click triggers a navigation that destroys the execution context. The click
   still lands. `last_action_error` is therefore NEVER read; every outcome is
   decided by a state predicate read back from the page.

2. The application's warning signal lives in an injected modal and in inline JS
   (`post-wrapper.js`: #order-view-cancel-button is gated by confirm(); the hold
   and unhold buttons post directly). It never reaches the accessibility tree of
   the settled page. The ONLY observation that contains it is the frame between
   the two clicks of a two-click verb -- captured here as GATE. It exists for
   about one second per cell and is not reconstructible afterwards.

3. `snap()` returns None, so runner.py `continue`s without stepping the env: GATE
   costs zero extra actions and the following click sees the identical obs.

4. hard_reset measured at 16 s warm / 175 s cold; a cell is 20-60 s. Reset is not
   the cost driver it was thought to be, but cells are still batched (one reset,
   many cells, each on a DISTINCT order) with the control re-run every batch.

5. A snapshot whose status is unparsed is NOT data: Magento redirects a
   non-resolving order id to the grid, where status is None. Treating None as
   "a different status" would fabricate both `executed` and `reversible`.
"""
from __future__ import annotations
import sys, json, re, time, argparse
sys.path.insert(0, '.')
from pathlib import Path
from cawebagent.trace.runner import set_env, run_episode
from cawebagent.trace.reset import hard_reset
set_env(WA_SHOPPING_ADMIN="http://localhost:7780/admin")
from browsergym.utils.obs import flatten_axtree_to_str

ADMIN = "http://localhost:7780/admin"
TASK = "webarena_verified.284.499.2"          # any order-scoped task; we drive by URL
OUT = Path('out'); OUT.mkdir(exist_ok=True)
RUNS = Path('runs/e1_grid'); RUNS.mkdir(parents=True, exist_ok=True)
GRID_F = OUT / 'e1_grid.json'
POOL_F = OUT / 'e1_order_pool.json'

BUTTON = re.compile(r"\[(\d+)\] button '([^']*)'")
LINK   = re.compile(r"\[(\d+)\] link '([^']*)'")
STATUS = re.compile(r"rowheader 'Order Status'.*?gridcell '([^']*)'", re.S)
# The rendered warning. Matched against the GATE frame, where the modal lives.
WARN   = re.compile(r"are you sure|cannot be undone|permanently|"
                    r"will be (?:deleted|canceled|cancelled|removed|refunded)", re.I)

# Widened beyond scripts/11_undo_probe.py: on Magento the compensating action for
# an invoice is a Credit Memo, which the original eleven words would reject.
INVERSE_LEXICON = ('unhold', 'reopen', 'restore', 'undo', 'undelete', 'uncancel',
                   'revert', 'void', 'unship', 'unsubscribe', 'recover',
                   'credit memo', 'refund', 'return', 'cancel shipment')

# An inverse that OPENS a form is not taken until the form is submitted. The
# first version of this script clicked the entry control and navigated away, and
# then recorded 'the inverse was taken and did not restore the status' for a
# credit memo that was never created -- the same asymmetry the forward verbs are
# already protected against by their second click. Registered here, and any
# inverse that leaves us on a form page without a registered commit control is
# SEQUENCE_INCOMPLETE rather than a measurement.
INVERSE_COMMIT = {
    'credit memo': 'Refund Offline',      # POSTs to sales/order_creditmemo/save
}
FORM_URL = re.compile(r'/(?:new|start|edit)/')

def order_url(oid: int) -> str:
    return f"{ADMIN}/sales/order/view/order_id/{oid}/"

# --------------------------------------------------------------------- verbs
# `observable=False` marks verbs whose consequence leaves the page entirely, so
# the status predicate cannot decide them. Sending a customer email mutates the
# world and changes nothing in the order view; calling that "the application
# refused" would attribute our blind spot to the application.
VERBS = {
    'hold':       dict(seq=[('Hold', 0)]),
    'cancel':     dict(seq=[('Cancel', 0), ('OK', -1)]),
    'ship':       dict(seq=[('Ship', 0), ('Submit Shipment', -1)]),
    'invoice':    dict(seq=[('Invoice', 0), ('Submit Invoice', -1)]),
    'send_email': dict(seq=[('Send Email', 0), ('OK', -1)], observable=False),
    'reorder':    dict(seq=[('Reorder', 0)],                observable=False),
}

# recipe = verbs applied to a Pending order to manufacture the state.
# predicate = the Order Status the page must report before the cell is measured.
# Preparation writes happen BEFORE the measured action and are never counted.
# NOTE: Magento decides availability by canCancel()/canShip()/canInvoice(), which
# read the shipment and invoice records rather than the status string -- hence
# two distinct Processings, both kept.
STATES = {
    'pending':              dict(recipe=[],                  predicate='Pending'),
    'processing_shipped':   dict(recipe=['ship'],            predicate='Processing'),
    'processing_invoiced':  dict(recipe=['invoice'],         predicate='Processing'),
    'on_hold':              dict(recipe=['hold'],            predicate='On Hold'),
    'complete':             dict(recipe=['ship', 'invoice'], predicate='Complete'),
    'canceled':             dict(recipe=['cancel'],          predicate='Canceled'),
}

CONTROL_CELL = ('hold', 'pending')   # must return REVERSIBLE or the batch is void
# A probe that cannot recognise an undo cannot evidence its absence, and a cell
# whose harness state is ambiguous must be re-run rather than frozen.
RETRY_OUTCOMES = (None, 'HARNESS_ERROR', 'DRIVER_FAILED', 'STALE_ORDER',
                  'BAD_OBSERVATION', 'SEQUENCE_INCOMPLETE')

# ------------------------------------------------------------------ snapshots
def _snapshot(obs) -> dict:
    ax = flatten_axtree_to_str(obs['axtree_object'])
    m = STATUS.search(ax)
    return dict(url=obs['url'],
                status=(m.group(1) if m else None),
                buttons=sorted({n for _, n in BUTTON.findall(ax) if n.strip()}),
                links=sorted({n for _, n in LINK.findall(ax) if n.strip()}),
                warn=sorted({l.strip() for l in ax.splitlines() if WARN.search(l)}),
                ax_lines=ax.count('\n'), ax=ax)

def snap(store: dict, label: str):
    def _f(obs):
        store[label] = _snapshot(obs)
        return None                     # returning None skips env.step
    return _f

def click(name: str, nth: int = 0, optional: bool = False, store: dict | None = None):
    """click_button, but a missing button is data (not offered), not a crash.
    Records how many controls matched, so 'offered' can mean the commit control
    and not merely the entry control that opens a form."""
    def _f(obs):
        ax = flatten_axtree_to_str(obs['axtree_object'])
        bids = re.findall(r"\[(\d+)\] button '" + re.escape(name) + r"'", ax)
        if store is not None:
            store.setdefault('_found', {})[name] = len(bids)
        if not bids:
            if optional:
                return None
            raise RuntimeError(f"button {name!r} not offered")
        return f"click('{bids[nth]}')"
    return _f

def click_inverse(store: dict, pre: str, post: str):
    """Take whichever newly-offered control looks like an inverse.

    The candidate is not known until the verb has executed, so it cannot be
    written into the action list ahead of time. This is the step that turns a
    lexicon match into a measurement: we do not report that an inverse exists,
    we take it and read the status back.

    Everything the lexicon REJECTED is recorded too. Without that, an empty
    candidate list cannot be distinguished from 'no gained control matched my
    fifteen words', and 'no inverse exists' is unfalsifiable."""
    def _f(obs):
        a, b = store.get(pre), store.get(post)
        if not a or not b:
            return None
        controls = lambda s: set(s.get('buttons') or []) | set(s.get('links') or [])
        gained = controls(b) - controls(a)
        cand = [x for x in sorted(gained) if any(w in x.lower() for w in INVERSE_LEXICON)]
        store['_inverse_candidates'] = cand
        store['_gained_unmatched'] = [x for x in sorted(gained) if x not in cand]
        # an inverse that was already present is invisible to a set difference;
        # record it rather than let set arithmetic make the decision silently
        store['_inverse_present_not_gained'] = [
            x for x in sorted(controls(b) - gained)
            if any(w in x.lower() for w in INVERSE_LEXICON)]
        if not cand:
            return None
        ax = flatten_axtree_to_str(obs['axtree_object'])
        bids = re.findall(r"\[(\d+)\] button '" + re.escape(cand[0]) + r"'", ax)
        if not bids:                      # a link candidate: not clickable here
            return None
        store['_inverse_taken'] = cand[0]
        return f"click('{bids[0]}')"
    return _f

def inverse_commit(store: dict):
    """Submit a form-driven inverse. The mirror of the forward verbs' second
    click, and the step whose absence made 'we take it' false for the credit
    memo. Records enough to tell 'committed' from 'opened and abandoned'."""
    def _f(obs):
        taken = store.get('_inverse_taken')
        if not taken:
            return None
        on_form = bool(FORM_URL.search(obs.get('url') or ''))
        want = INVERSE_COMMIT.get(taken.lower())
        if want is None:
            # A direct-post inverse (Unhold) has already committed. If we are
            # sitting on a form, the click only opened something and this cell
            # must not be scored.
            if on_form:
                store['_inverse_commit_missing'] = (
                    f"{taken} opened a form ({obs.get('url')}) and no commit "
                    f"control is registered for it")
            else:
                store['_inverse_committed'] = True
            return None
        ax = flatten_axtree_to_str(obs['axtree_object'])
        bids = re.findall(r"\[(\d+)\] button '" + re.escape(want) + r"'", ax)
        if not bids:
            store['_inverse_commit_missing'] = f"{taken} -> {want!r} not offered"
            return None
        store['_inverse_committed'] = True
        store['_inverse_commit_control'] = want
        return f"click('{bids[0]}')"
    return _f

def _seq(verb: str, optional_first: bool = False, store: dict | None = None):
    """optional_first=True makes the WHOLE sequence optional: a withdrawn verb is
    the R1 signal, not a harness error. GATE is snapped after the first click --
    the only frame that contains the application's rendered warning."""
    out = []
    for i, (name, nth) in enumerate(VERBS[verb]['seq']):
        out.append(click(name, nth, optional=optional_first or name == 'OK', store=store))
        if i == 0 and store is not None:
            out.append(snap(store, 'GATE'))
    return out

# ------------------------------------------------------------- order discovery
def discover_pool(lo: int, hi: int, refresh: bool = False) -> dict:
    """Map order_id -> status at the image baseline. Deterministic across hard
    resets, so this is done once and cached -- with the range stamped in, because
    a cache built over a narrower range silently starves a wider run."""
    if POOL_F.exists() and not refresh:
        d = json.loads(POOL_F.read_text())
        if d.get('_range') == [lo, hi]:
            return {int(k): v for k, v in d.items() if k != '_range'}
        print(f"pool cache covers {d.get('_range')}, need [{lo}, {hi}] -- rediscovering",
              flush=True)
    print(f"discovering order pool {lo}..{hi} (cached to {POOL_F})", flush=True)
    st, acts = {}, []
    for oid in range(lo, hi + 1):
        acts += [f"goto('{order_url(oid)}')", snap(st, str(oid))]
    run_episode(TASK, acts, RUNS / 'pool')
    pool = {int(k): v['status'] for k, v in st.items() if v.get('status')}
    POOL_F.write_text(json.dumps({**{str(k): v for k, v in pool.items()},
                                  '_range': [lo, hi]}, indent=1, sort_keys=True))
    print(f"  found {len(pool)} orders; "
          f"pending={sum(1 for v in pool.values() if v == 'Pending')}", flush=True)
    return pool

# ------------------------------------------------------------------- one cell
def run_cell(verb: str, state: str, oid: int, baseline: str | None = None,
             tag_suffix: str = '') -> dict:
    """Manufacture `state` on order `oid`, execute `verb`, look for and TAKE an
    inverse, and report. Every judgement comes from a state predicate."""
    st: dict = {}
    url = order_url(oid)
    recipe = STATES[state]['recipe']
    want = STATES[state]['predicate']
    prep_buttons = {n for p in recipe for n, _ in VERBS[p]['seq']}

    acts = [f"goto('{url}')", snap(st, 'S0')]
    for prep in recipe:                                   # manufacture the state
        acts += _seq(prep) + [f"goto('{url}')"]           # not optional: must raise
    acts += [snap(st, 'PRE')]                             # the state under test
    acts += _seq(verb, optional_first=True, store=st)     # the measured action
    acts += [f"goto('{url}')", snap(st, 'POST')]
    acts += [click_inverse(st, 'PRE', 'POST'),
             inverse_commit(st),                          # submit a form-driven inverse
             click('OK', -1, optional=True, store=st),    # in case the inverse is gated
             f"goto('{url}')", snap(st, 'UNDO')]

    tag = f"{verb}__{state}__o{oid}{tag_suffix}"
    d = RUNS / tag
    t = time.time()
    try:
        log = run_episode(TASK, acts, d)
        nsteps = len(log.steps)
    except Exception as e:
        # A prep control that is absent means the state could not be manufactured
        # -- a driver failure, not a dead harness. The two must not share a bucket.
        msg = str(e)
        kind = 'DRIVER_FAILED' if any(f"'{b}'" in msg for b in prep_buttons) \
               else 'HARNESS_ERROR'
        return dict(verb=verb, state=state, order=oid, recipe=recipe,
                    outcome=kind, error=msg[:300], secs=round(time.time() - t, 1))

    # persist the full trees before they are dropped: any stronger reversibility
    # predicate (residue, field diffs, history entries) must be applicable
    # retrospectively, because re-running a cell costs minutes and a campaign hours
    d.mkdir(parents=True, exist_ok=True)
    for k, v in st.items():
        if isinstance(v, dict) and v.get('ax'):
            (d / f'{k}.ax.txt').write_text(v.pop('ax'))

    s0, pre, post, undo, gate = (st.get(k) for k in ('S0', 'PRE', 'POST', 'UNDO', 'GATE'))
    g = lambda s, k: (s or {}).get(k)
    rec = dict(verb=verb, state=state, order=oid, recipe=recipe,
               secs=round(time.time() - t, 1), steps=nsteps,
               baseline_status=g(s0, 'status'), pre_status=g(pre, 'status'),
               post_status=g(post, 'status'), undo_status=g(undo, 'status'),
               pre_buttons=g(pre, 'buttons'), post_buttons=g(post, 'buttons'),
               undo_buttons=g(undo, 'buttons'),
               gate_url=g(gate, 'url'), gate_buttons=g(gate, 'buttons'),
               gate_warn=g(gate, 'warn'),          # <- the R2 predictor
               pre_warn=g(pre, 'warn'),
               inverse_candidates=st.get('_inverse_candidates'),
               inverse_taken=st.get('_inverse_taken'),
               gained_unmatched=st.get('_gained_unmatched'),
               inverse_present_not_gained=st.get('_inverse_present_not_gained'),
               seq_found=st.get('_found'),
               urls={k: g(st.get(k), 'url') for k in ('S0', 'PRE', 'POST', 'UNDO')},
               residue_buttons=sorted(set(g(undo, 'buttons') or [])
                                      ^ set(g(pre, 'buttons') or [])))

    # --- 0. was the order at the baseline the pool recorded?  The only check
    #        that can catch cross-cell contamination or a half-warm reset.
    if baseline and g(s0, 'status') != baseline:
        rec.update(outcome='STALE_ORDER', executed=None, reversible=None,
                   note=f"baseline {g(s0,'status')!r} != pooled {baseline!r}")
        return rec

    # --- 1. did the state driver reach the state under test?
    if not pre or g(pre, 'status') != want:
        rec.update(outcome='DRIVER_FAILED', executed=None, reversible=None,
                   note=f"wanted {want}, page said {g(pre,'status')!r}")
        return rec

    rec['offered'] = VERBS[verb]['seq'][0][0] in (g(pre, 'buttons') or [])

    # --- 2. was the verb offered?  Withdrawal is the strongest form of state
    #        dependence, so this is a measurement, never a skip.
    if not rec['offered']:
        rec.update(outcome='NOT_OFFERED', executed=False, reversible=None,
                   note='verb absent from the affordance set')
        return rec

    # --- 3. did the committing control appear?  'Ship' only opens the New
    #        Shipment form; 'Submit Shipment' is what commits.
    found = rec['seq_found'] or {}
    missing = [nm for nm, _ in VERBS[verb]['seq'][1:] if nm != 'OK' and not found.get(nm)]
    if missing:
        rec.update(outcome='SEQUENCE_INCOMPLETE', executed=None, reversible=None,
                   note=f"verb offered but {missing} never appeared")
        return rec

    # --- 4. are POST and UNDO parsed views of THIS order?  An unparsed snapshot
    #        scored as data fabricates both `executed` and `reversible`.
    for lbl, s in (('POST', post), ('UNDO', undo)):
        if not s or not s.get('status') or f"/order_id/{oid}/" not in (s.get('url') or ''):
            rec.update(outcome='BAD_OBSERVATION', executed=None, reversible=None,
                       note=f"{lbl} is not a parsed view of order {oid} "
                            f"(url={g(s,'url')!r}, status={g(s,'status')!r})")
            return rec

    ctrl = lambda s: set(g(s, 'buttons') or []) | set(g(s, 'links') or [])
    gained = sorted(ctrl(post) - ctrl(pre))
    lost = sorted(ctrl(pre) - ctrl(post))
    changed = g(post, 'status') != g(pre, 'status')
    rec.update(gained=gained, lost=lost, executed=changed or bool(gained or lost))

    # --- 5. verbs whose consequence leaves the page cannot be decided here.
    if not VERBS[verb].get('observable', True):
        rec.update(outcome='OFF_PAGE_EFFECT', reversible=None,
                   note='consequence is not observable in the order view; the '
                        'status predicate cannot decide this verb')
        return rec

    if not rec['executed']:
        rec.update(outcome='OFFERED_BUT_REFUSED', reversible=None,
                   note='control present, no observable state or affordance change')
        return rec

    # --- 6. reversible ONLY if an inverse was actually taken, the verb had moved
    #        the status, and the status came back.  Without the first two
    #        conjuncts a status that never moved reports itself REVERSIBLE --
    #        the direction that would move R1 off zero and destroy R2's kappa.
    took = bool(st.get('_inverse_taken'))
    committed = bool(st.get('_inverse_committed'))
    if took and st.get('_inverse_commit_missing'):
        rec.update(outcome='SEQUENCE_INCOMPLETE', executed=True, reversible=None,
                   inverse_offered=True, inverse_taken=st.get('_inverse_taken'),
                   note='inverse entry control clicked but not committed: '
                        + str(st['_inverse_commit_missing']))
        return rec
    restored = (took and committed and bool(undo) and changed
                and g(undo, 'status') == g(pre, 'status'))
    rec.update(outcome='MEASURED',
               inverse_offered=bool(st.get('_inverse_candidates')),
               inverse_clicks_tried=(1 if took else 0),
               inverse_committed=committed,
               inverse_commit_control=st.get('_inverse_commit_control'),
               reversible=restored,
               note=('restored via ' + str(st.get('_inverse_taken'))) if restored
                    else ('no inverse control was taken' if not took
                          else 'the inverse was taken, committed, and did not '
                               'restore the status'))
    return rec

# ----------------------------------------------------------------- the sweep
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repeat', type=int, default=1,
                    help='re-run each cell on a DIFFERENT order (bounds harness '
                         'flake; the measurement itself is deterministic)')
    ap.add_argument('--batch', type=int, default=10, help='cells per container reset')
    ap.add_argument('--isolate', action='store_true', help='one hard reset per cell')
    ap.add_argument('--verbs', default=','.join(VERBS))
    ap.add_argument('--states', default=','.join(STATES))
    ap.add_argument('--pool-range', default='300,340')
    ap.add_argument('--refresh-pool', action='store_true')
    ap.add_argument('--retry-refused', action='store_true',
                    help='also re-run OFFERED_BUT_REFUSED (a dismissed modal looks identical)')
    ap.add_argument('--fresh', action='store_true')
    a = ap.parse_args()

    verbs = [v for v in a.verbs.split(',') if v in VERBS]
    states = [s for s in a.states.split(',') if s in STATES]
    batch = 1 if a.isolate else max(1, a.batch)

    done = [] if a.fresh or not GRID_F.exists() else json.loads(GRID_F.read_text())
    seen = {(r['verb'], r['state'], r.get('rep', 0)) for r in done
            if r.get('cell_role') != 'POSITIVE_CONTROL'
            and r.get('outcome') not in RETRY_OUTCOMES
            and not (a.retry_refused and r.get('outcome') == 'OFFERED_BUT_REFUSED')}

    print("hard reset (initial) ...", flush=True)
    t = time.time(); hard_reset("shopping_admin"); print(f"  {time.time()-t:.0f}s", flush=True)
    lo, hi = (int(x) for x in a.pool_range.split(','))
    pool = discover_pool(lo, hi, refresh=a.refresh_pool)
    pending = sorted(o for o, s in pool.items() if s == 'Pending')
    if len(pending) < 2:
        print(f"!! need >=2 Pending orders (control + cell), have {len(pending)}"); return
    batch = min(batch, len(pending) - 1)
    print(f"pool: {len(pending)} Pending orders; batch={batch}", flush=True)

    todo = [(v, s, r) for r in range(a.repeat) for s in states for v in verbs
            if (v, s, r) not in seen]
    print(f"{len(todo)} cells to run ({len(verbs)}v x {len(states)}s x {a.repeat}r; "
          f"{len(seen)} already done)", flush=True)

    # start the loop already "due" so the FIRST batch is validated too: without
    # this the first `batch` cells run with no positive control and are recorded
    # indistinguishably from validated ones.
    i_since_reset, oi, T0 = batch, 0, time.time()
    bidx, batch_ok = 0, None
    for n, (verb, state, rep) in enumerate(todo, 1):
        if i_since_reset >= batch or oi >= len(pending):
            if n > 1:
                print(f"\n--- hard reset ({i_since_reset} cells since last) ---", flush=True)
                t = time.time(); hard_reset("shopping_admin")
                print(f"  {time.time()-t:.0f}s", flush=True)
            i_since_reset, oi, bidx = 0, 0, bidx + 1
            ctl = run_cell(*CONTROL_CELL, pending[oi], pool.get(pending[oi]),
                           f"__ctl{bidx}"); oi += 1; i_since_reset += 1
            batch_ok = ctl.get('reversible') is True
            ctl.update(cell_role='POSITIVE_CONTROL', batch=bidx, batch_ok=batch_ok)
            done.append(ctl); GRID_F.write_text(json.dumps(done, indent=1))
            print(f"  [control b{bidx}] hold x pending -> reversible={ctl.get('reversible')}"
                  f"  {'OK' if batch_ok else '!! BATCH INVALID - probe cannot see an undo'}",
                  flush=True)

        oid = pending[(oi + rep) % len(pending)]; oi += 1; i_since_reset += 1
        print(f"\n[{n}/{len(todo)}] {verb} x {state} (order {oid}, rep {rep}, b{bidx})",
              flush=True)
        rec = run_cell(verb, state, oid, pool.get(oid), f"__r{rep}")
        rec.update(rep=rep, batch=bidx, batch_ok=batch_ok)
        done.append(rec); GRID_F.write_text(json.dumps(done, indent=1))
        print(f"  -> {rec['outcome']:<20} {rec.get('pre_status')} -> {rec.get('post_status')}"
              f" | offered={rec.get('offered')} exec={rec.get('executed')}"
              f" rev={rec.get('reversible')} warn={bool(rec.get('gate_warn'))}"
              f" | {rec['secs']}s", flush=True)

    # -------------------------------------------------------------- summary
    valid = [r for r in done if r.get('cell_role') != 'POSITIVE_CONTROL'
             and r.get('batch_ok') is not False]
    meas = [r for r in valid if r.get('outcome') == 'MEASURED']
    print(f"\n{'='*76}\n{len(done)} rows, {len(meas)} MEASURED, "
          f"{(time.time()-T0)/60:.0f} min\n{'='*76}")
    print(f"{'verb':<11}{'state':<21}{'outcome':<21}{'rev':<7}{'warn':<6}inverse")
    for r in sorted(valid, key=lambda r: (r['verb'], r['state'])):
        print(f"{r['verb']:<11}{r['state']:<21}{str(r.get('outcome')):<21}"
              f"{str(r.get('reversible')):<7}{str(bool(r.get('gate_warn'))):<6}"
              f"{r.get('inverse_taken') or (r.get('inverse_candidates') or '-')}")

    # R1 -- flip rate against each verb's modal class, with NOT_OFFERED counted:
    # affordance withdrawal is the strongest form of state dependence, and
    # excluding it biases the flip rate toward zero.
    print(f"\n-- R1 flip rate (reversibility class across object states) --")
    flips = tot = 0
    for v in sorted({r['verb'] for r in valid}):
        by_state = {}
        for r in valid:
            if r['verb'] == v and r.get('outcome') in ('MEASURED', 'NOT_OFFERED'):
                by_state.setdefault(r['state'], []).append(
                    'NOT_OFFERED' if r['outcome'] == 'NOT_OFFERED' else r['reversible'])
        cls = [c[0] for c in by_state.values() if len(set(c)) == 1]
        if len(cls) < 2:
            continue
        top = max(set(cls), key=cls.count)
        if sum(1 for c in set(cls) if cls.count(c) == cls.count(top)) > 1:
            print(f"  {v:<11} modal=TIE          states={len(cls)} flips=undefined")
            continue
        f = sum(1 for c in cls if c != top)
        flips += f; tot += len(cls)
        print(f"  {v:<11} modal={str(top):<12} states={len(cls)} flips={f}")
    print(f"  TOTAL {flips}/{tot}" + (f" = {100*flips/tot:.1f}%" if tot else ""))

    # R2 -- the predictor is the warning the app rendered at the GATE frame,
    # not any hand-typed prior of ours.
    rev = [r for r in meas if r.get('reversible') is True]
    irr = [r for r in meas if r.get('reversible') is False]
    print(f"\n-- R2 (does the app's own warning track measured irreversibility?) --")
    print(f"  warned  -- irreversible {sum(1 for r in irr if r.get('gate_warn'))}/{len(irr)}"
          f"   reversible {sum(1 for r in rev if r.get('gate_warn'))}/{len(rev)}")
    print(f"  gained an inverse-looking control -- "
          f"irreversible {sum(1 for r in irr if r.get('inverse_offered'))}/{len(irr)}"
          f"   reversible {sum(1 for r in rev if r.get('inverse_offered'))}/{len(rev)}")
    unmatched = sum(1 for r in irr if r.get('gained_unmatched'))
    print(f"  irreversible cells that gained SOME control the lexicon rejected: "
          f"{unmatched}/{len(irr)}  <- the falsification evidence for 'no inverse exists'")
    for o in ('NOT_OFFERED', 'OFF_PAGE_EFFECT', 'OFFERED_BUT_REFUSED',
              'SEQUENCE_INCOMPLETE', 'DRIVER_FAILED', 'STALE_ORDER',
              'BAD_OBSERVATION', 'HARNESS_ERROR'):
        c = sum(1 for r in done if r.get('outcome') == o)
        if c: print(f"  {o:<21} {c}")
    print(f"\nwrote {GRID_F}")

if __name__ == '__main__':
    main()
