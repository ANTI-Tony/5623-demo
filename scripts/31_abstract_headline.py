"""Reproduce every number in the abstract's lead sentence and in Table 4.

The paper claims every number it reports is produced by a script over shipped
intermediate data. That was not true of the statistic the title rests on: the
neighbourhood token share (19.4% of steps receiving 9.1% of reasoning output)
appeared in no script and in no out/*.json. 08b_analyze.py computes the
commit-step MEAN DIFFERENCE, which is a different statistic from the SHARE the
table reports. This script closes that gap.

It also asserts against the published values, so it doubles as a regression test
on the paper: if the source data and the printed numbers ever diverge, this
fails loudly rather than silently shipping a claim nothing computes.

FINDING (2026-09-02). Every DESCRIPTIVE value in the abstract and Table 4
reproduces exactly. The neighbourhood p-values do not, and the reason is a
mismatch between the procedure Table 4's caption states and the procedure that
produces the printed number:

  NULL-A  shuffle COMMIT labels within episode, preserving per-episode commit
          counts, then RECOMPUTE the neighbourhood.  -> p = 0.035 (episode)
          This is what the caption describes, and it is the correct null for the
          claim: it compares the observed neighbourhood against other
          commit-anchored adjacent pairs, so it preserves the confound that
          commits are clicks and clicks are short to emit.

  NULL-B  shuffle NEIGHBOURHOOD membership directly, preserving its per-episode
          count.                                     -> p = 0.0004 (episode)
          This reproduces the printed 0.0006, but it treats neighbourhood
          membership as exchangeable across steps, which discards the structural
          fact that a neighbourhood IS a commit plus its predecessor. It answers
          a weaker question than the one the paper asks.

Under NULL-A the commit-step unit survives (episode p = 0.0007, task p = 0.0034,
both matching the paper) and the neighbourhood unit weakens sharply (episode
p = 0.035, task p = 0.17, not significant). The defensible claim is therefore the
commit step, with the neighbourhood reported as the widened unit where the effect
attenuates -- which is consistent with the predecessor-matched control the paper
already reports at p = 0.78.

  input : out/k3_steps_pooled.json   (743 steps, 80 episodes, 2 seeds)
  output: out/k3_headline.json
No API calls, no environment, seconds to run.
"""
import json, random, statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / 'out'
RNG = random.Random(0)                       # fixed, as the paper states
DRAWS = 10_000

rows = json.loads((OUT / 'k3_steps_pooled.json').read_text())

# ---------------------------------------------------------------- the sets
def neighbourhood(R, lab):
    """The committing step and the one before it, within an episode.

    'Before' is by step index inside the same episode, so the predecessor of the
    first step of an episode does not exist and no label leaks across episodes."""
    idx = {}
    for k, r in enumerate(R):
        idx.setdefault(r['dir'], []).append(k)
    nb = [False] * len(R)
    for ks in idx.values():
        ks.sort(key=lambda k: R[k]['i'])
        for pos, k in enumerate(ks):
            if lab[k]:
                nb[k] = True
                if pos > 0:
                    nb[ks[pos - 1]] = True
    return nb

def share(R, sel, key='out_tok'):
    tot = sum(r[key] for r in R)
    return (sum(R[k][key] for k in range(len(R)) if sel[k]) / tot * 100) if tot else 0.0

def pct_steps(sel):
    return sum(sel) / len(sel) * 100

def medians(R, sel, key='out_tok'):
    a = [R[k][key] for k in range(len(R)) if sel[k]]
    b = [R[k][key] for k in range(len(R)) if not sel[k]]
    return (st.median(a) if a else None), (st.median(b) if b else None)

# ------------------------------------------------------------- permutation
def permute(R, cluster, unit, draws=DRAWS, null='A'):
    """Permutation test on the output-token share received by `unit`.

    null='A'  shuffle COMMIT labels within `cluster`, preserving each cluster's
              commit count, then recompute the unit. The caption's procedure.
    null='B'  shuffle the UNIT's membership directly, preserving its per-cluster
              count. Weaker: it forgets that a neighbourhood is an adjacent pair.

    Both SHARE (what Table 4 prints) and MEAN DIFF (what 08b_analyze.py computed)
    are returned, so a divergence between them stays visible."""
    byc = {}
    for k, r in enumerate(R):
        byc.setdefault(r[cluster], []).append(k)

    def sel_of(lab):
        return neighbourhood(R, lab) if unit == 'neighbourhood' else lab

    def stats(lab):
        s = sel_of(lab)
        a = [R[k]['out_tok'] for k in range(len(R)) if s[k]]
        b = [R[k]['out_tok'] for k in range(len(R)) if not s[k]]
        md = (st.mean(a) - st.mean(b)) if a and b else 0.0
        return share(R, s), md

    obs_lab = [r['commits'] for r in R]
    obs_sel = sel_of(obs_lab)
    obs_share, obs_md = stats(obs_lab)
    hit_share = hit_md = 0
    for _ in range(draws):
        lab = [False] * len(R)
        src = (lambda k: R[k]['commits']) if null == 'A' else (lambda k: obs_sel[k])
        for ks in byc.values():
            m = sum(1 for k in ks if src(k))
            for k in RNG.sample(ks, m):
                lab[k] = True
        # under NULL-B the shuffled labels ARE the unit; do not re-expand them
        s_, m_ = (stats(lab) if null == 'A' else
                  (share(R, lab), (lambda a, b: (st.mean(a) - st.mean(b)) if a and b else 0.0)(
                      [R[k]['out_tok'] for k in range(len(R)) if lab[k]],
                      [R[k]['out_tok'] for k in range(len(R)) if not lab[k]])))
        # one-sided in the direction claimed: the set receives LESS than its share
        if s_ <= obs_share + 1e-12: hit_share += 1
        if abs(m_) >= abs(obs_md) - 1e-12: hit_md += 1
    return ((hit_share + 1) / (draws + 1), (hit_md + 1) / (draws + 1))

# ------------------------------------------------------------------ report
def block(R, tag):
    lab = [r['commits'] for r in R]
    nb = neighbourhood(R, lab)
    ps, pm = permute(R, 'dir', 'commit')
    ns, nm = permute(R, 'dir', 'neighbourhood')
    nsB, _ = permute(R, 'dir', 'neighbourhood', null='B')
    mc, mnc = medians(R, lab)
    mn, mnn = medians(R, nb)
    return dict(tag=tag, steps=len(R), episodes=len({r['dir'] for r in R}),
                commit_steps=sum(lab),
                pct_steps_commit=round(pct_steps(lab), 1),
                pct_tokens_commit=round(share(R, lab), 1),
                median_commit=mc, median_noncommit=mnc,
                perm_p_commit_share=round(ps, 4), perm_p_commit_meandiff=round(pm, 4),
                pct_steps_nbhd=round(pct_steps(nb), 1),
                pct_tokens_nbhd=round(share(R, nb), 1),
                median_nbhd=mn, median_non_nbhd=mnn,
                perm_p_nbhd_share=round(ns, 4), perm_p_nbhd_meandiff=round(nm, 4),
                perm_p_nbhd_share_nullB=round(nsB, 4))

res = {'pooled': block(rows, 'pooled')}
for arm in ('T0', 'T3'):
    res[arm] = block([r for r in rows if r['arm'] == arm], arm)
# the task-clustered p the abstract also quotes
res['pooled']['perm_p_nbhd_share_by_task'] = round(
    permute(rows, 'task', 'neighbourhood')[0], 4)
res['pooled']['perm_p_commit_meandiff_by_task'] = round(
    permute(rows, 'task', 'commit')[1], 4)

(OUT / 'k3_headline.json').write_text(json.dumps(res, indent=1))

p = res['pooled']
print(f"corpus: {p['steps']} steps, {p['episodes']} episodes, {p['commit_steps']} commit steps\n")
print(f"{'':<26}{'pooled':>10}{'T0':>10}{'T3':>10}")
for lbl, key in (('% steps that commit', 'pct_steps_commit'),
                 ('% output tokens', 'pct_tokens_commit'),
                 ('median commit', 'median_commit'),
                 ('median non-commit', 'median_noncommit'),
                 ('perm p (share)', 'perm_p_commit_share'),
                 ('perm p (mean diff)', 'perm_p_commit_meandiff'),
                 ('% steps in nbhd', 'pct_steps_nbhd'),
                 ('% output tokens (nbhd)', 'pct_tokens_nbhd'),
                 ('median nbhd', 'median_nbhd'),
                 ('median non-nbhd', 'median_non_nbhd'),
                 ('perm p nbhd A (share)', 'perm_p_nbhd_share'),
                 ('perm p nbhd A (mean diff)', 'perm_p_nbhd_meandiff'),
                 ('perm p nbhd B (share)', 'perm_p_nbhd_share_nullB')):
    print(f"{lbl:<26}{str(res['pooled'][key]):>10}{str(res['T0'][key]):>10}{str(res['T3'][key]):>10}")
print(f"\nneighbourhood, clustered by task (NULL-A): p = {p['perm_p_nbhd_share_by_task']}")
print(f"commit mean-diff, clustered by task:      p = {p['perm_p_commit_meandiff_by_task']}")

# ------------------------------------------------- assert against the paper
PUBLISHED = {   # abstract + Table 4 + Sec 5.5, as compiled
    'steps': 743, 'episodes': 80, 'commit_steps': 72,
    'pct_steps_commit': 9.7, 'pct_tokens_commit': 3.3,
    'median_commit': 6, 'median_noncommit': 42,
    'pct_steps_nbhd': 19.4, 'pct_tokens_nbhd': 9.1,
    'median_nbhd': 7, 'median_non_nbhd': 46,
}
print(f"\n{'-'*58}\nagreement with the compiled paper (descriptive values)")
bad = 0
for k, want in PUBLISHED.items():
    got = res['pooled'][k]
    ok = (abs(got - want) < 0.06) if isinstance(want, float) else (got == want)
    bad += (not ok)
    print(f"  {'OK ' if ok else 'MISMATCH'} {k:<22} script={got!s:<8} paper={want}")
print(f"{'-'*58}")
print("all descriptive values reproduce" if not bad else
      f"!! {bad} descriptive value(s) do not reproduce")

# The paper reports NULL-A throughout and names NULL-B's value as the
# non-conservative alternative. These are the values it prints today; this block
# fails if the paper and the data ever diverge again.
PRINTED_P = {
    'perm_p_commit_share':          (0.0007, 'commit, by episode'),
    'perm_p_commit_meandiff_by_task': (0.0042, 'commit, clustered by task'),
    'perm_p_nbhd_share':            (0.030,  'neighbourhood, by episode (NULL-A)'),
    'perm_p_nbhd_share_by_task':    (0.17,   'neighbourhood, clustered by task'),
    'perm_p_nbhd_share_nullB':      (0.0006, 'neighbourhood, NULL-B, named as the figure we do NOT report'),
}
print(f"\n{'-'*58}\np-values against what the paper prints")
for k, (want, label) in PRINTED_P.items():
    got = p[k]
    # permutation noise: allow the printed rounding plus a draw's worth of slack
    ok = abs(got - want) <= max(0.0015, 0.15 * want)
    bad += (not ok)
    print(f"  {'OK ' if ok else 'MISMATCH'} {label:<52} script={got:<8} paper={want}")
print(f"{'-'*58}")
print("all values reproduce" if not bad else
      f"!! {bad} value(s) diverge -- the paper or this script is out of date")
raise SystemExit(1 if bad else 0)
