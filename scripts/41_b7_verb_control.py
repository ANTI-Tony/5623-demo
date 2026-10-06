r"""B.7 under the controls a reviewer asked for.

The submitted analysis correlated the commit indicator against three proxies over
all 373 high-effort steps. Two objections: commits are almost all clicks, so a
correlation over mixed verbs may be reading the verb; and `err` on the same step
is not an ex-ante signal -- the stall the allocator could actually condition on
is the PREVIOUS step's error. This recomputes all three within click steps only,
with the retry proxy taken from the predecessor, permutation clustered by episode.

  in : out/k3_steps_pooled.json
  out: out/k19_b7_verb_control.json
"""
import json, random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / 'out'
RNG = random.Random(0); DRAWS = 10_000

S = json.loads((OUT / 'k3_steps_pooled.json').read_text())
t3 = [r for r in S if r['arm'] == 'T3']
# predecessor error within the same episode, by step index
by_ep = {}
for r in t3: by_ep.setdefault(r['dir'], []).append(r)
for ep in by_ep.values():
    ep.sort(key=lambda r: r['i'])
    for k, r in enumerate(ep):
        r['_prev_err'] = bool(ep[k-1].get('err')) if k else False
clicks = [r for r in t3 if r['verb'] == 'click']
print(f"T3 steps {len(t3)}, click steps {len(clicks)}, "
      f"commits among clicks {sum(1 for r in clicks if r['commits'])}")

def rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i]); rk = [0.0]*len(xs); i = 0
    while i < len(order):
        j = i
        while j+1 < len(order) and xs[order[j+1]] == xs[order[i]]: j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j+1): rk[order[k]] = avg
        i = j + 1
    return rk

def spearman(a, b):
    ra, rb = rank(a), rank(b); n = len(a)
    ma, mb = sum(ra)/n, sum(rb)/n
    num = sum((x-ma)*(y-mb) for x, y in zip(ra, rb))
    da = sum((x-ma)**2 for x in ra) ** .5; db = sum((y-mb)**2 for y in rb) ** .5
    return num / (da*db) if da and db else float('nan')

def perm_p(rows, proxy):
    y = [1 if r['commits'] else 0 for r in rows]
    x = [proxy(r) for r in rows]
    obs = spearman(x, y)
    eps = {}
    for k, r in enumerate(rows): eps.setdefault(r['dir'], []).append(k)
    hits = 0
    for _ in range(DRAWS):
        yy = y[:]
        for idx in eps.values():               # shuffle commit labels within episode
            vals = [yy[k] for k in idx]; RNG.shuffle(vals)
            for k, v in zip(idx, vals): yy[k] = v
        if abs(spearman(x, yy)) >= abs(obs) - 1e-12: hits += 1
    return obs, max(hits, 1) / DRAWS

res = {}
for name, proxy, pop in [
    ('obs_size_clicks',   lambda r: r['in_tok'],           clicks),
    ('step_index_clicks', lambda r: r['i'],                clicks),
    ('prev_error_clicks', lambda r: 1 if r['_prev_err'] else 0, clicks),
    ('prev_error_all_t3', lambda r: 1 if r['_prev_err'] else 0, t3),
]:
    rho, p = perm_p(pop, proxy)
    res[name] = dict(rho=round(rho, 4), p=round(p, 4), n=len(pop))
    print(f"  {name:<20} rho={rho:+.3f}  p={p:.4f}  n={len(pop)}")
(OUT / 'k19_b7_verb_control.json').write_text(json.dumps(res, indent=1))
print('wrote out/k19_b7_verb_control.json')

PRINTED = {'prev_error_clicks': (-0.214, 0.0024), 'obs_size_clicks': (-0.012, None),
           'step_index_clicks': (0.189, 0.094), 'prev_error_all_t3': (-0.161, 0.0015)}
bad = 0
for k, (want_r, want_p) in PRINTED.items():
    ok = abs(res[k]['rho'] - want_r) < 5e-4 and (want_p is None or abs(res[k]['p'] - want_p) < 5e-4)
    bad += (not ok)
    print(f"  {'OK ' if ok else 'MISMATCH'} {k:<20} rho={res[k]['rho']} p={res[k]['p']}")
print('reproduces' if not bad else f'!! {bad} diverge')
sys.exit(1 if bad else 0)
