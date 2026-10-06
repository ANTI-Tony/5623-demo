r"""E2: the (write-verb x object-state) grid on a SECOND application.

Postmill (the WebArena `reddit` image), so the reversibility claims can be read
against an application that is not Magento. Deliberately NOT pooled with E1: the
two applications are the contrast, and pooling would wash it out.

WHAT THIS DESIGN RESTS ON (probed on this machine before it was written):

1. Postmill names its own inverse. After an upvote the control relabels itself
   `Retract upvote`, exactly as Magento relabels Hold -> Unhold. Taking it
   restores the score exactly (3085 -> 3086 -> 3085, verified end to end). That
   is the positive control.

2. The object state IS the control label. There is no status string to read, so
   the predicate is the vote control's own name plus the integer score.

3. A submission page carries TWO vote widgets for the same object, and a comment
   carries a third. Every locator here is anchored to the comment's own text and
   takes the FIRST control after it; a naive by-name click lands on the wrong
   widget, which is how the first probe "upvoted twice" instead of retracting.

4. Deletion is one click with NO confirmation of any kind -- no modal, no
   interstitial page. That is the finding the second application is here to
   produce, so the gate frame is captured anyway and recorded as empty.

  in : the reddit container on :9999
  out: out/e2_grid_postmill.json
"""
from __future__ import annotations
import sys, json, re, time, argparse
sys.path.insert(0, '.')
from pathlib import Path
from cawebagent.trace.runner import set_env, run_episode
from cawebagent.trace.reset import hard_reset
set_env(WA_REDDIT="http://localhost:9999")
from browsergym.utils.obs import flatten_axtree_to_str

BASE = "http://localhost:9999"
TASK = "webarena_verified.33.27.2"          # any reddit task; we drive by URL
SUBMISSION = f"{BASE}/f/books/81371"
OUT = Path('out'); OUT.mkdir(exist_ok=True)
RUNS = Path('runs/e2_grid'); RUNS.mkdir(parents=True, exist_ok=True)
GRID_F = OUT / 'e2_grid_postmill.json'

# Postmill's own words for undoing something, plus the generic ones E1 used.
INVERSE_LEXICON = ('retract', 'undo', 'undelete', 'restore', 'unhide',
                   'unsave', 'unsubscribe', 'revert')
WARN = re.compile(r"are you sure|cannot be undone|permanently|will be (?:deleted|removed)", re.I)

# `commit` names the control that actually posts, for verbs whose first click
# only opens a form. Postmill's Edit navigates to /-/comment/N/edit and does
# nothing until Save is pressed; clicking Edit and navigating away records the
# object as unchanged, which reads as OFFERED_BUT_REFUSED and is indistinguishable
# from a real refusal. A verb declaring `commit` whose commit control never
# appears is SEQUENCE_INCOMPLETE, not a measurement.
VERBS = {
    'upvote':   dict(control='Upvote'),
    'downvote': dict(control='Downvote'),
    'delete':   dict(control='Delete'),
    'edit':     dict(control='Edit', commit='Save', edits_text=True),
}
# A comment I authored starts UPVOTED: Postmill auto-votes your own content.
STATES = {
    'upvoted':    dict(recipe=[],                    predicate='Retract upvote'),
    'none':       dict(recipe=['retract'],           predicate='Upvote'),
    'downvoted':  dict(recipe=['retract','downvote'],predicate='Retract downvote'),
}
CONTROL_CELL = ('upvote', 'none')       # must come back REVERSIBLE or the batch is void
RETRY = (None, 'HARNESS_ERROR', 'DRIVER_FAILED', 'BAD_OBSERVATION', 'SEQUENCE_INCOMPLETE')

# ---------------------------------------------------------------- observation
def _after(ax: str, marker: str):
    """Controls belonging to OUR comment, and to nothing else.

    The window runs from our comment's text to the start of the NEXT comment.
    Postmill wraps each comment in an `article`, so that boundary is exact.
    Taking everything after the marker instead -- which the first version did --
    reaches other users' comments further down the page, and the probe then
    clicks a stranger's vote button and records our own object as unchanged.
    That reads as OFFERED_BUT_REFUSED and is indistinguishable from a real
    refusal, which is why the boundary is enforced rather than assumed."""
    i = ax.find(marker)
    if i < 0:
        return ''
    tail = ax[i:]
    m = re.search(r"\n\s*\[\d+\] article ''", tail)
    return tail[:m.start()] if m else tail

def _snapshot(obs, marker: str) -> dict:
    ax = flatten_axtree_to_str(obs['axtree_object'])
    tail = _after(ax, marker)
    btn = [n for _, n in re.findall(r"\[(\d+)\] button '([^']*)'", tail)]
    lnk = [n for _, n in re.findall(r"\[(\d+)\] link '([^']*)'", tail)]
    m = re.search(r"button '(?:Upvote|Retract upvote|Downvote|Retract downvote)'\n\s*StaticText '(-?\d+)'", tail)
    # The vote state is which retraction is on offer, not which button appears
    # first: in the downvoted state the pair is (Upvote, Retract downvote) and
    # Upvote appears first, so a first-in-order read misreports the state and
    # fails every downvoted-column cell as unreached.
    vote = ('Retract upvote' if 'Retract upvote' in btn else
            'Retract downvote' if 'Retract downvote' in btn else
            'Upvote' if 'Upvote' in btn else None)
    # the comment's own text, up to its navigation row. An edit changes only
    # this: presence, vote label and score are all untouched by one, so a
    # predicate without it records a completed edit as "no observable change".
    # `tail` begins AT the marker text, i.e. inside StaticText '...', so the
    # body runs to that string's closing quote. Matching StaticText here finds
    # nothing, because its opening quote was already consumed.
    body = tail.split("'")[0].strip() if tail else ''
    return dict(url=obs['url'], present=marker in ax, vote=vote, body=body,
                score=(int(m.group(1)) if m else None),
                buttons=sorted(set(btn[:14])), links=sorted(set(lnk[:14])),
                warn=sorted({l.strip() for l in ax.splitlines() if WARN.search(l)}))

def snap(store, label, marker):
    def _f(obs):
        store[label] = _snapshot(obs, marker); return None
    return _f

def click_in_comment(name, store, marker, key=None, optional=False):
    """Click the first control with this name AFTER our comment's text."""
    def _f(obs):
        ax = flatten_axtree_to_str(obs['axtree_object'])
        tail = _after(ax, marker)
        ids = re.findall(r"\[(\d+)\] (?:button|link) '" + re.escape(name) + r"'", tail)
        store.setdefault('_found', {})[key or name] = len(ids)
        if not ids:
            if optional: return None
            raise RuntimeError(f"{name!r} not offered on our comment")
        return f"click('{ids[0]}')"
    return _f

def take_inverse(store, pre_key, post_key, marker):
    """Take whichever newly-offered control could serve as an inverse, and record
    what the lexicon rejected -- without that, an empty candidate list cannot be
    told apart from a lexicon that is too narrow."""
    def _f(obs):
        a, b = store.get(pre_key), store.get(post_key)
        if not a or not b: return None
        ctrl = lambda s: set(s.get('buttons') or []) | set(s.get('links') or [])
        gained = ctrl(b) - ctrl(a)
        cand = [x for x in sorted(gained) if any(w in x.lower() for w in INVERSE_LEXICON)]
        store['_inverse_candidates'] = cand
        store['_gained_unmatched'] = [x for x in sorted(gained) if x not in cand]
        store['_inverse_present_not_gained'] = [
            x for x in sorted(ctrl(b) - gained)
            if any(w in x.lower() for w in INVERSE_LEXICON)]
        if not cand: return None
        ax = flatten_axtree_to_str(obs['axtree_object'])
        ids = re.findall(r"\[(\d+)\] (?:button|link) '" + re.escape(cand[0]) + r"'",
                         _after(ax, marker))
        if not ids: return None
        store['_inverse_taken'] = cand[0]
        store['_inverse_committed'] = True     # Postmill votes post directly, no form
        return f"click('{ids[0]}')"
    return _f

# ------------------------------------------------------------------- one cell
def run_cell(verb: str, state: str, tag_suffix: str = '') -> dict:
    """Post a fresh comment (a distinct object, so no cell sees another's writes),
    drive it into `state`, execute `verb`, then look for and TAKE an inverse."""
    st: dict = {}
    marker = f"undoatlas {verb} {state}{tag_suffix} {int(time.time()*1000)%10**7}"
    rec = dict(verb=verb, state=state, marker=marker, family='comment')

    acts = [f"goto('{SUBMISSION}')"]
    # create the object
    acts += [_fill_comment(marker), _click_plain('Post', st, 'create')]
    acts += [f"goto('{SUBMISSION}')", snap(st, 'S0', marker)]
    # manufacture the state
    for prep in STATES[state]['recipe']:
        ctrl = {'retract': 'Retract upvote', 'downvote': 'Downvote'}[prep]
        acts += [click_in_comment(ctrl, st, marker, key=f'prep:{prep}'),
                 f"goto('{SUBMISSION}')"]
    acts += [snap(st, 'PRE', marker)]
    # the measured action, with the frame between clicks captured for a warning
    acts += [click_in_comment(VERBS[verb]['control'], st, marker, key=verb,
                              optional=True),
             snap(st, 'GATE', marker)]
    spec = VERBS[verb]
    if spec.get('commit'):
        if spec.get('edits_text'):
            acts += [_fill_comment(marker + ' EDITED')]
        acts += [_click_plain(spec['commit'], st, 'commit')]
    acts += [f"goto('{SUBMISSION}')", snap(st, 'POST', marker)]
    # and the inverse
    acts += [take_inverse(st, 'PRE', 'POST', marker),
             f"goto('{SUBMISSION}')", snap(st, 'UNDO', marker)]

    d = RUNS / f"{verb}__{state}{tag_suffix}"
    t = time.time()
    try:
        run_episode(TASK, acts, d)
    except Exception as e:
        rec.update(outcome='DRIVER_FAILED', executed=None, reversible=None,
                   note=str(e)[:200], secs=round(time.time()-t, 1))
        return rec
    rec['secs'] = round(time.time()-t, 1)

    g = lambda s, k: (st.get(s) or {}).get(k)
    rec.update(pre_body=g('PRE','body'), post_body=g('POST','body'),
               undo_body=g('UNDO','body'),
               pre_state=g('PRE','vote'), pre_score=g('PRE','score'),
               post_state=g('POST','vote'), post_score=g('POST','score'),
               undo_state=g('UNDO','vote'), undo_score=g('UNDO','score'),
               pre_present=g('PRE','present'), post_present=g('POST','present'),
               undo_present=g('UNDO','present'),
               gate_warn=g('GATE','warn'), seq_found=st.get('_found'),
               inverse_candidates=st.get('_inverse_candidates'),
               gained_unmatched=st.get('_gained_unmatched'),
               inverse_present_not_gained=st.get('_inverse_present_not_gained'),
               inverse_taken=st.get('_inverse_taken'))

    # --- 1. did the object get created and reach the state under test?
    if not g('S0','present'):
        rec.update(outcome='HARNESS_ERROR', executed=None, reversible=None,
                   note='the comment we posted is not on the page'); return rec
    want = STATES[state]['predicate']
    if g('PRE','vote') != want:
        rec.update(outcome='HARNESS_ERROR', executed=None, reversible=None,
                   note=f"state not reached: wanted {want!r}, page says {g('PRE','vote')!r}")
        return rec

    # --- 2. was the verb offered at all?  A withdrawn verb is the R1 signal.
    if not (st.get('_found') or {}).get(verb):
        rec.update(outcome='NOT_OFFERED', executed=False, reversible=None,
                   note='verb absent from the affordance set in this state'); return rec

    # --- 2b. a verb that opens a form is not executed until the form is posted
    spec = VERBS[verb]
    if spec.get('commit') and not (st.get('_found') or {}).get('commit'):
        rec.update(outcome='SEQUENCE_INCOMPLETE', executed=None, reversible=None,
                   note=f"{verb!r} opened a form but {spec['commit']!r} never appeared")
        return rec

    # --- 3. did anything change?  Deletion changes presence; votes change the
    #        control label and the score.  Neither is inferred from the click.
    changed = (g('PRE','present') != g('POST','present')
               or g('PRE','vote') != g('POST','vote')
               or g('PRE','score') != g('POST','score')
               or g('PRE','body') != g('POST','body'))
    rec['executed'] = changed
    if not changed:
        rec.update(outcome='OFFERED_BUT_REFUSED', reversible=None,
                   note='control present, no observable state change'); return rec

    # --- 4. reversible ONLY if an inverse was taken and the prior state returned
    took = bool(st.get('_inverse_taken'))
    restored = (took and g('UNDO','present') == g('PRE','present')
                and g('UNDO','vote') == g('PRE','vote')
                and g('UNDO','score') == g('PRE','score')
                and g('UNDO','body') == g('PRE','body'))
    rec.update(outcome='MEASURED', inverse_offered=bool(st.get('_inverse_candidates')),
               reversible=restored,
               note=('restored via ' + str(st.get('_inverse_taken'))) if restored
                    else ('no inverse control was taken' if not took
                          else 'the inverse was taken and did not restore'))
    return rec

def _fill_comment(text):
    def _f(obs):
        ax = flatten_axtree_to_str(obs['axtree_object'])
        b = re.findall(r"\[(\d+)\] textbox 'Comment'", ax)
        return f"fill('{b[0]}', '{text}')" if b else None
    return _f

def _click_plain(name, store, key):
    def _f(obs):
        ax = flatten_axtree_to_str(obs['axtree_object'])
        b = re.findall(r"\[(\d+)\] button '" + re.escape(name) + r"'", ax)
        store.setdefault('_found', {})[key] = len(b)
        return f"click('{b[0]}')" if b else None
    return _f

# ----------------------------------------------------------------- the sweep
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verbs', default=','.join(VERBS))
    ap.add_argument('--states', default=','.join(STATES))
    ap.add_argument('--batch', type=int, default=6, help='cells per container reset')
    ap.add_argument('--fresh', action='store_true')
    a = ap.parse_args()

    prev = [] if a.fresh or not GRID_F.exists() else json.loads(GRID_F.read_text())
    done = {(r['verb'], r['state']): r for r in prev
            if r.get('cell_role') != 'POSITIVE_CONTROL'
               and r.get('outcome') not in RETRY}
    # every batch's control belongs in the record: a run resumed across sessions
    # must still be able to show that the probe could see an inverse each time
    controls = [r for r in prev if r.get('cell_role') == 'POSITIVE_CONTROL']
    cells = [(v, s) for v in a.verbs.split(',') for s in a.states.split(',')
             if (v, s) not in done]
    print(f"{len(cells)} cells to run ({len(done)} already done)", flush=True)

    rows = controls + list(done.values())
    since_reset, batch = 10**9, len(controls)
    for i, (v, s) in enumerate(cells, 1):
        if since_reset >= a.batch:
            batch += 1; print(f"\n--- hard reset (batch {batch}) ---", flush=True)
            hard_reset('reddit', timeout=420); since_reset = 0
            # the control re-runs every batch: without it, "nothing is reversible
            # here" cannot be told apart from a probe that cannot see an inverse
            c = run_cell(*CONTROL_CELL, tag_suffix=f'__ctl{batch}')
            c.update(cell_role='POSITIVE_CONTROL', batch=batch)
            ok = c.get('reversible') is True
            print(f"  [control b{batch}] {CONTROL_CELL[0]} x {CONTROL_CELL[1]}"
                  f" -> reversible={c.get('reversible')} {'OK' if ok else 'VOID'}", flush=True)
            rows.append(c); since_reset += 1
            if not ok:
                print("  !! control failed; the batch that follows is not evidence", flush=True)
        r = run_cell(v, s); r['batch'] = batch; since_reset += 1
        rows.append(r)
        print(f"[{i}/{len(cells)}] {v} x {s} -> {r['outcome']:<20} "
              f"{r.get('pre_state')} -> {r.get('post_state')} | "
              f"exec={r.get('executed')} rev={r.get('reversible')} "
              f"warn={bool(r.get('gate_warn'))} | {r.get('secs')}s", flush=True)
        GRID_F.write_text(json.dumps(rows, indent=1))

    meas = [r for r in rows if r.get('cell_role') != 'POSITIVE_CONTROL'
            and r.get('outcome') == 'MEASURED']
    print(f"\n{'='*72}\n{len(rows)} rows, {len(meas)} MEASURED\n{'='*72}")
    for r in sorted(rows, key=lambda x: (x['verb'], x['state'])):
        if r.get('cell_role') == 'POSITIVE_CONTROL': continue
        print(f"  {r['verb']:<10} {r['state']:<12} {r['outcome']:<20} "
              f"rev={str(r.get('reversible')):<6} warn={bool(r.get('gate_warn'))}")
    warned_irr = [r for r in meas if r['reversible'] is False and r.get('gate_warn')]
    silent_irr = [r for r in meas if r['reversible'] is False and not r.get('gate_warn')]
    warned_rev = [r for r in meas if r['reversible'] is True and r.get('gate_warn')]
    print(f"\n-- does the application warn about what it cannot undo? --")
    print(f"  irreversible: {len(warned_irr)} warned, {len(silent_irr)} silent")
    print(f"  reversible  : {len(warned_rev)} warned (false alarms)")
    print(f"\nwrote {GRID_F}")

if __name__ == '__main__':
    main()
