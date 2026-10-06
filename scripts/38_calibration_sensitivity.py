r"""What kappa is, under every defensible reading of "the application warned".

Section 5.3 reports one coefficient. Four reviewers of a mock review objected on
four different grounds and arrived at four different numbers, which is the real
finding: "does the application warn?" is not one variable. The confirmation the
paper counts is rendered TEXT in the modal frame. But `Ship` and `Invoice` do not
post directly either -- clicking them opens a New Shipment / New Invoice form and
a second, separate click commits -- and the review status verbs commit through a
form save. Whether those count as confirmation is a judgement, and the sign of
the result depends on it.

  C1  rendered warning text                     (what the paper counts)
  C2  C1 + a commit that requires a second click on a separate form page
  C3  C2 + a commit that requires a form save in the page

Reported at the cell unit (n = 18) and at the verb unit (n = 8), since both rated
variables are constant within verb -- which is the paper's own state-invariance
result, so the cells are not independent.

  out: out/k18_calibration_sensitivity.json
"""
import json, sys, itertools
from pathlib import Path
from cawebagent.guard import require

ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / 'out'

# How each verb's write actually commits, read off the two grid scripts' seq
# tables. 'text' is set from the measured gate_warn, not asserted here.
COMMIT = {
    'hold':      'direct',      # single click, posts immediately
    'cancel':    'modal',       # JS confirm() then OK
    'ship':      'form_page',   # New Shipment page, then Submit Shipment
    'invoice':   'form_page',   # New Invoice page, then Submit Invoice
    'delete':    'modal',       # confirm then OK
    'approve':   'form_save',   # status field then Save Review
    'reject':    'form_save',
    'unpublish': 'form_save',
}
CODINGS = {
    'C1 rendered warning text':        lambda v, w: w,
    'C2 + separate form page':         lambda v, w: w or COMMIT[v] == 'form_page',
    'C3 + in-page form save':          lambda v, w: w or COMMIT[v] in ('form_page', 'form_save'),
}

rows = []
for fam, fn in (('order', 'e1_grid.json'), ('review', 'e1_grid_reviews.json')):
    f = OUT / fn
    if not f.exists(): continue
    for r in json.loads(f.read_text()):
        if r.get('cell_role') != 'POSITIVE_CONTROL' and r.get('outcome') == 'MEASURED':
            r.setdefault('family', fam); rows.append(r)
require(len(rows), 'measured grid cells', 'out/e1_grid*.json')
assert set(r['verb'] for r in rows) <= set(COMMIT), \
    f"unclassified verb: {set(r['verb'] for r in rows) - set(COMMIT)}"

def kappa(a, b):
    n = len(a); po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return (po - pe) / (1 - pe) if pe < 1 else float('nan')

def table(w, i):
    c = lambda x, y: sum(1 for a, b in zip(w, i) if a == x and b == y)
    return dict(warn_irrev=c(1, 1), warn_rev=c(1, 0),
                silent_irrev=c(0, 1), silent_rev=c(0, 0))

irr = [r['reversible'] is False for r in rows]
res = {'n_cells': len(rows), 'n_verbs': len(set(r['verb'] for r in rows)), 'codings': {}}
print(f"{len(rows)} measured cells over {res['n_verbs']} verbs\n")
print(f"{'coding':<30} {'cell kappa':>11} {'verb kappa':>11}   2x2 at the verb unit")
print('-' * 84)
for name, f in CODINGS.items():
    w = [bool(f(r['verb'], bool(r.get('gate_warn')))) for r in rows]
    kc = kappa(w, irr)
    # collapse to verbs; both variables are constant within verb, so this is exact
    seen, wv, iv = {}, [], []
    for r, ww, ii in zip(rows, w, irr):
        seen.setdefault(r['verb'], (ww, ii))
    for v in sorted(seen):
        wv.append(seen[v][0]); iv.append(seen[v][1])
    kv, tv = kappa(wv, iv), table(wv, iv)
    res['codings'][name] = dict(kappa_cell=round(kc, 4), kappa_verb=round(kv, 4),
                                table_verb=tv,
                                warned_verbs=sorted(v for v in seen if seen[v][0]))
    print(f"{name:<30} {kc:>11.3f} {kv:>11.3f}   "
          f"warn/irrev {tv['warn_irrev']}  warn/rev {tv['warn_rev']}  "
          f"silent/irrev {tv['silent_irrev']}  silent/rev {tv['silent_rev']}")
print('-' * 84)
lo = min(v['kappa_cell'] for v in res['codings'].values())
hi = max(v['kappa_cell'] for v in res['codings'].values())
res['range_cell'] = [lo, hi]
print(f"\nrange over codings, cell unit: [{lo:.2f}, {hi:.2f}]")
print("the DIRECTION is coding-dependent: C2 makes the application exhaustive,")
print("C3 makes it over-warn on the reversible review verbs.")
(OUT / 'k18_calibration_sensitivity.json').write_text(json.dumps(res, indent=1))

PRINTED = {'n_cells': 18, 'n_verbs': 8}
bad = sum(res[k] != v for k, v in PRINTED.items())
for k, v in PRINTED.items():
    print(f"  {'OK ' if res[k]==v else 'MISMATCH'} {k:<12} script={res[k]} paper={v}")
print('reproduces' if not bad else f'!! {bad} diverge')

# ------------------------------------------------- the second application
# Postmill gets its own commit table: its `delete` is a single direct POST
# (delete_own), unlike Magento's modal-gated review delete, so the Magento map
# keyed on the verb name alone would mis-code it. `edit` is the separate-page
# pattern (GET /-/comment/N/edit, then Save POSTs), which is exactly what C2
# counts -- so Postmill is NOT signal-free under C2 and C3, only under C1.
COMMIT_PM = {'upvote': 'direct', 'downvote': 'direct', 'delete': 'direct',
             'edit': 'form_page'}
CODINGS_PM = {
    'C1 rendered warning text': lambda v, w: w,
    'C2 + separate form page':  lambda v, w: w or COMMIT_PM[v] == 'form_page',
    'C3 + in-page form save':   lambda v, w: w or COMMIT_PM[v] in ('form_page', 'form_save'),
}
pm = []
fpm = OUT / 'e2_grid_postmill.json'
if fpm.exists():
    pm = [r for r in json.loads(fpm.read_text())
          if r.get('cell_role') != 'POSITIVE_CONTROL' and r.get('outcome') == 'MEASURED']
assert set(r['verb'] for r in pm) <= set(COMMIT_PM), 'unclassified Postmill verb'
pm_irr = [r['reversible'] is False for r in pm]
res['postmill'] = {'n_cells': len(pm), 'codings': {}}
print(f"\nPostmill: {len(pm)} measured cells")
for name, f in CODINGS_PM.items():
    w = [bool(f(r['verb'], bool(r.get('gate_warn')))) for r in pm]
    t = table(w, pm_irr)
    k = kappa(w, pm_irr) if len(set(w)) > 1 else None     # constant rater: undefined
    res['postmill']['codings'][name] = dict(kappa_cell=(round(k, 4) if k is not None else None),
                                            table=t)
    print(f"  {name:<28} kappa {('%.3f' % k) if k is not None else 'undefined (no variance)':<26}"
          f" warn/irrev {t['warn_irrev']} warn/rev {t['warn_rev']} "
          f"silent/irrev {t['silent_irrev']} silent/rev {t['silent_rev']}")

# ------------------------------------------------------- the table the paper prints
# One table, both applications. The verb 2x2 columns are dropped: the body never
# cites them, and the Postmill column needs the width.
LAB = {'C1 rendered warning text': (r'C1', r'warning text'),
       'C2 + separate form page':  (r'C2', r'{}+{} separate page'),
       'C3 + in-page form save':   (r'C3', r'{}+{} in-page save')}
VERDICT = {'C1 rendered warning text': 'incomplete',
           'C2 + separate form page':  'exhaustive',
           'C3 + in-page form save':   'over-warns'}
fmt = lambda k: ('%.2f' % k) if k is not None else '--'
lines = []
for name, d in res['codings'].items():
    tag, desc = LAB[name]
    pmk = res['postmill']['codings'][name]['kappa_cell']
    lines.append(f"{tag} & {desc} & {d['kappa_cell']:.2f} & {d['kappa_verb']:.2f} & "
                 f"{fmt(pmk)} & \\emph{{{VERDICT[name]}}} \\\\")
tex = r"""% Generated by scripts/38_calibration_sensitivity.py -- do not hand-edit.
\begin{table}[htbp]
\caption{Cohen's $\kappa$ between confirmation signal and measured
reversibility, by what counts as a confirmation. --: undefined (no warning text).}
\label{tab:calib}
\small
\setlength{\tabcolsep}{4pt}
\begin{tabular}{@{}ll rr r l@{}}
\toprule
& counts as & \multicolumn{2}{c}{Magento} & Postmill & Magento \\
\cmidrule(lr){3-4}
& a warning & cell & verb & cell & reads as \\
\midrule
""" + "\n".join(lines) + r"""
\bottomrule
\end{tabular}
\end{table}
"""
(ROOT / 'tab_calib.tex').write_text(tex)
# the numbers the paper prints for the second application
assert res['postmill']['codings']['C1 rendered warning text']['kappa_cell'] is None, 'Postmill C1 now has variance'
assert abs(res['postmill']['codings']['C2 + separate form page']['kappa_cell'] - 0.2759) < 5e-4, 'Postmill C2 moved'
print('wrote tab_calib.tex')
sys.exit(1 if bad else 0)
