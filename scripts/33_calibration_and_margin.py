r"""Two numbers the paper prints that no script produced.

  - Cohen's kappa between the application's own confirmation signal and measured
    reversibility, with a bootstrap interval (Section 5.3).
  - The margin between each classified state-changing event and the nearest
    phase boundary, which is what licenses the wall-clock segmentation
    (Appendix, detector validation).

Both recompute from shipped intermediate data with no environment and no model
calls, and both are asserted against what the paper prints, so this file fails
loudly if the two ever diverge. The kappa half also reports the verb-clustered
interval, which is the one the paper leans on: both rated variables are constant
within every verb, so the 18 cells are 8 independent observations.

  in : out/e1_grid.json, out/k3_events.json
  out: out/k16_calibration.json
"""
from __future__ import annotations
import json, random, sys
from pathlib import Path
from cawebagent.guard import require

ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / 'out'
RNG = random.Random(0)
DRAWS = 20_000

# --------------------------------------------------------------- kappa
def kappa(a, b):
    """Cohen's kappa for two binary raters over the same items."""
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return (po - pe) / (1 - pe) if pe < 1 else float('nan')

FAMILIES = [('order', 'e1_grid.json'), ('review', 'e1_grid_reviews.json')]
rows = []
for fam, fn in FAMILIES:
    f = OUT / fn
    if not f.exists(): continue
    for r in json.loads(f.read_text()):
        if r.get('cell_role') != 'POSITIVE_CONTROL':
            r.setdefault('family', fam); rows.append(r)
meas = [r for r in rows if r.get('outcome') == 'MEASURED']
require(len(meas), 'measured grid cells', 'out/e1_grid*.json')

warn = [bool(r.get('gate_warn')) for r in meas]          # what the app rendered
irr = [r['reversible'] is False for r in meas]           # what we measured
k = kappa(warn, irr)

boot = []
for _ in range(DRAWS):
    idx = [RNG.randrange(len(meas)) for _ in range(len(meas))]
    v = kappa([warn[i] for i in idx], [irr[i] for i in idx])
    if v == v:                                            # drop degenerate draws
        boot.append(v)
boot.sort()
lo, hi = boot[int(.025 * len(boot))], boot[int(.975 * len(boot))]

cell = lambda w, i: sum(1 for x, y in zip(warn, irr) if x == w and y == i)
tab = {'warn_irreversible': cell(True, True), 'warn_reversible': cell(True, False),
       'silent_irreversible': cell(False, True), 'silent_reversible': cell(False, False)}

# ------------------------------------------------- phase-boundary margin
ev = json.loads((OUT / 'k3_events.json').read_text())
cls = [e for e in ev if e.get('cls') and e['cls'] != 'UNCLASSIFIED']
require(len(cls), 'classified events', 'out/k3_events.json')
# distance to the nearer of the two action-window boundaries
margins = [min(abs(e['t'] - e['a0']), abs(e['t'] - e['a1'])) for e in cls]
worst = min(margins)

# per-family kappa, and the leave-one-verb-out sensitivity the paper reports
byfam_k = {}
for fam in sorted({r['family'] for r in meas}):
    sel = [i for i, r in enumerate(meas) if r['family'] == fam]
    byfam_k[fam] = round(kappa([warn[i] for i in sel], [irr[i] for i in sel]), 4)
nodel = [i for i, r in enumerate(meas) if r['verb'] != 'delete']
k_nodel = kappa([warn[i] for i in nodel], [irr[i] for i in nodel])

# both rated variables are constant within verb, so the i.i.d. interval above
# overstates n threefold; resample clusters of verbs instead.
verbs = sorted({r['verb'] for r in meas})
by_verb = {v: [(warn[i], irr[i]) for i, r in enumerate(meas) if r['verb'] == v]
           for v in verbs}
CRNG = random.Random(0); cboot = []
for _ in range(DRAWS):
    draw = [x for _ in verbs for x in by_verb[verbs[CRNG.randrange(len(verbs))]]]
    v = kappa([x[0] for x in draw], [x[1] for x in draw])
    if v == v: cboot.append(v)
cboot.sort()
clo, chi = cboot[int(.025 * len(cboot))], cboot[int(.975 * len(cboot))]
share_le0 = round(100 * sum(1 for v in cboot if v <= 0) / len(cboot), 1)

res = dict(kappa=round(k, 4), ci=[round(lo, 3), round(hi, 3)], n=len(meas),
           table=tab, draws=DRAWS,
           n_verbs=len(verbs),
           ci_verb_clustered=[round(clo, 3), round(chi, 3)],
           clustered_share_at_or_below_zero=share_le0,
           kappa_excl_review_delete=round(k_nodel, 4),
           by_family=byfam_k,
           classified_events=len(cls), min_margin_s=round(worst, 2),
           within_5s=sum(1 for m in margins if m < 5))
(OUT / 'k16_calibration.json').write_text(json.dumps(res, indent=1))

import collections
byfam = collections.Counter(r['family'] for r in meas)
print(f"calibration, n = {len(meas)} measured cells over {len(byfam)} object families "
      f"({', '.join(f'{k} {v}' for k, v in sorted(byfam.items()))})")
print(f"           irrev  rev")
print(f"  warned     {tab['warn_irreversible']}     {tab['warn_reversible']}")
print(f"  silent     {tab['silent_irreversible']}     {tab['silent_reversible']}")
print(f"  Cohen's kappa = {k:.3f}   bootstrap 95% CI [{lo:.2f}, {hi:.2f}]  ({DRAWS} draws)\n")
print(f"phase margin over {len(cls)} classified events")
print(f"  nearest boundary  {worst:.2f} s      within 5 s: {res['within_5s']}\n")

PRINTED = {'classified_events': (34, 0), 'within_5s': (0, 0),
           'kappa': (0.5556, 0.0005), 'n': (18, 0), 'n_verbs': (8, 0),
           'kappa_excl_review_delete': (0.375, 0.0005)}
bad = 0
print('-' * 52)
for key, (want, tol) in PRINTED.items():
    got = res[key]
    ok = abs(got - want) <= tol
    bad += (not ok)
    print(f"  {'OK ' if ok else 'MISMATCH'} {key:<20} script={got!s:<8} paper={want}")
print(f"  --  {'ci (i.i.d.)':<20} script={res['ci']}")
print(f"  --  {'ci (verb-clustered)':<20} script={res['ci_verb_clustered']}  "
      f"{res['clustered_share_at_or_below_zero']}% of draws <= 0")
print(f"  --  {'by family':<20} script={res['by_family']}")
print('-' * 52)
print('reproduces' if not bad else f'!! {bad} value(s) diverge')
sys.exit(1 if bad else 0)
