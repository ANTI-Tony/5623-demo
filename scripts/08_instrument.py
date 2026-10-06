"""Experiment 8 -- the instrument the title promises.

Joins, per agent step:
  (a) the step's wall-clock window   [action_exec_start, page_load_stop]   (episode.json)
  (b) the state-changing HTTP requests emitted inside that window          (HAR)
  (c) the compute spent deciding that step: output tokens / usd            (agent.json)

Produces:
  K3  misalignment  -- is test-time compute allocated where consequence lands?
  K4  orthogonality -- is consequence redundant with difficulty/uncertainty proxies?

No API calls. Pure re-analysis of runs/batch/.
"""
import json, glob, os, re, random, statistics as st
from pathlib import Path
from cawebagent.trace import har_parse as hp

ROOT = Path(__file__).resolve().parents[1]
OUT  = ROOT / 'out'; OUT.mkdir(exist_ok=True)
RNG  = random.Random(0)

# tier rules: reuse exp1's table verbatim
import importlib.util
spec = importlib.util.spec_from_file_location('exp1', ROOT/'scripts/exp1_consequence_taxonomy.py')

RULES_SRC = (ROOT/'scripts/exp1_consequence_taxonomy.py').read_text()
_m = re.search(r'^RULES = \[(.*?)^\]', RULES_SRC, re.S | re.M)
RULES = eval('[' + _m.group(1) + ']')

def classify(u):
    for rx, cls, tier, flags, d, i, o in RULES:
        if re.search(rx, u): return cls, tier
    return 'UNCLASSIFIED', None

def load_episodes():
    eps = []
    for d in sorted(glob.glob(str(ROOT/'runs/batch/*_T*'))):
        d = Path(d)
        ep_f = list(d.glob('*.episode.json'))
        if not ep_f or not (d/'agent.json').exists(): continue
        ep  = json.loads(ep_f[0].read_text())
        ag  = json.loads((d/'agent.json').read_text())
        sc  = json.loads((d/'score.json').read_text()) if (d/'score.json').exists() else {}
        har = d / Path(ep['har']).name
        if not har.exists(): continue
        eps.append(dict(dir=d.name, ep=ep, ag=ag, sc=sc, har=har,
                        tier_arm=ag['tier'], task=ep['task']))
    return eps

def per_step_rows(e):
    """One row per agent step."""
    events = hp.parse_har(e['har'])
    a0, a1 = e['ep']['action_window']
    agent_phase = hp.segment(events, float(a0), float(a1))['action']
    # state-changing = non-GET, non-benign, classifiable
    sc_events = []
    for ev in agent_phase:
        if ev.method.upper() == 'GET': continue
        if hp._benign(ev): continue
        cls, tier = classify(ev.url)
        if tier is None: continue
        sc_events.append((ev, cls, tier))

    ag_steps = {int(s['i']): s for s in e['ag']['steps']}
    rows = []
    for s in e['ep']['steps']:
        i = int(s['i'])
        t0 = float(s['action_exec_start'])
        t1 = float(s.get('page_load_stop') or s.get('action_exec_stop') or t0)
        t1 = max(t1, float(s['action_exec_stop']))
        hits = [(ev, cls, tr) for ev, cls, tr in sc_events if t0 <= ev.started_s <= t1]
        a = ag_steps.get(i, {})
        act = (s['action'] or '').strip()
        verb = re.match(r'^([a-z_]+)\s*\(', act)
        rows.append(dict(
            dir=e['dir'], task=e['task'], arm=e['tier_arm'], i=i,
            verb=verb.group(1) if verb else 'other',
            commits=len(hits) > 0,
            max_tier=max([tr for _, _, tr in hits], default=None),
            classes=sorted({cls for _, cls, _ in hits}),
            out_tok=int(a.get('output_tokens') or 0),
            in_tok=int(a.get('input_tokens') or 0),
            usd=float(a.get('usd') or 0.0),
            err=bool((a.get('err') or s.get('last_action_error') or '').strip()),
        ))
    return rows

def perm_test(rows, key='out_tok', n=4000):
    """Cluster-preserving permutation: shuffle commit labels within each episode."""
    byep = {}
    for r in rows: byep.setdefault(r['dir'], []).append(r)
    def stat(labels):
        c = [r[key] for r, l in zip(rows, labels) if l]
        nc = [r[key] for r, l in zip(rows, labels) if not l]
        if not c or not nc: return 0.0
        return st.mean(c) - st.mean(nc)
    obs_labels = [r['commits'] for r in rows]
    obs = stat(obs_labels)
    idx = {id(r): k for k, r in enumerate(rows)}
    cnt = 0
    for _ in range(n):
        lab = [False]*len(rows)
        for d, rs in byep.items():
            ks = [idx[id(r)] for r in rs]
            m = sum(1 for r in rs if r['commits'])
            for k in RNG.sample(ks, m): lab[k] = True
        if abs(stat(lab)) >= abs(obs) - 1e-12: cnt += 1
    return obs, (cnt + 1) / (n + 1)

def spearman(x, y):
    def rank(v):
        o = sorted(range(len(v)), key=lambda k: v[k]); r = [0.0]*len(v); k = 0
        while k < len(o):
            j = k
            while j+1 < len(o) and v[o[j+1]] == v[o[k]]: j += 1
            avg = (k + j) / 2 + 1
            for t in range(k, j+1): r[o[t]] = avg
            k = j + 1
        return r
    rx, ry = rank(x), rank(y); n = len(x)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a-mx)*(b-my) for a, b in zip(rx, ry))
    den = (sum((a-mx)**2 for a in rx) * sum((b-my)**2 for b in ry)) ** .5
    return num/den if den else 0.0

def perm_rho(x, y, groups, n=4000):
    obs = spearman(x, y)
    byg = {}
    for k, g in enumerate(groups): byg.setdefault(g, []).append(k)
    cnt = 0
    for _ in range(n):
        yy = list(y)
        for g, ks in byg.items():
            vals = [y[k] for k in ks]; RNG.shuffle(vals)
            for k, v in zip(ks, vals): yy[k] = v
        if abs(spearman(x, yy)) >= abs(obs) - 1e-12: cnt += 1
    return obs, (cnt+1)/(n+1)

if __name__ == '__main__':
    eps = load_episodes()
    rows = [r for e in eps for r in per_step_rows(e)]
    print(f"episodes={len(eps)}  steps={len(rows)}")
    json.dump(rows, open(OUT/'k3_steps.json','w'), indent=1)

    res = {'n_episodes': len(eps), 'n_steps': len(rows)}

    for arm in ('T3','T0','ALL'):
        R = [r for r in rows if arm=='ALL' or r['arm']==arm]
        C  = [r for r in R if r['commits']]
        NC = [r for r in R if not r['commits']]
        if not C: continue
        tot = sum(r['out_tok'] for r in R) or 1
        d = dict(
            steps=len(R), commit_steps=len(C),
            pct_steps_commit=100*len(C)/len(R),
            pct_outtok_on_commit=100*sum(r['out_tok'] for r in C)/tot,
            median_out_commit=st.median([r['out_tok'] for r in C]),
            median_out_noncommit=st.median([r['out_tok'] for r in NC]),
            mean_out_commit=st.mean([r['out_tok'] for r in C]),
            mean_out_noncommit=st.mean([r['out_tok'] for r in NC]),
        )
        obs,p = perm_test(R)
        d['perm_mean_diff'], d['perm_p'] = obs, p
        res[f'K3_{arm}'] = d
        print(f"\n[K3 {arm}] steps={d['steps']} commit={d['commit_steps']} "
              f"({d['pct_steps_commit']:.1f}% of steps) get {d['pct_outtok_on_commit']:.1f}% of output tokens")
        print(f"   median out_tok  commit={d['median_out_commit']:.0f}  non-commit={d['median_out_noncommit']:.0f}")
        print(f"   mean            commit={d['mean_out_commit']:.1f}  non-commit={d['mean_out_noncommit']:.1f}")
        print(f"   cluster-permutation  diff={obs:+.1f}  p={p:.4f}")
    json.dump(res, open(OUT/'k3_instrument.json','w'), indent=1)
    print("\nwrote out/k3_instrument.json, out/k3_steps.json")
