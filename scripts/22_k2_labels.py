"""Ship the per-episode labels behind the upstream-attribution table, and
reconcile them with the shipped classifier. The area chair flagged this table as
the only one with no artifact behind it.

Categories (as in the paper):
  A  committed to the wrong record
  B  committed nothing matching the target
  C  right record, missed some required changes
  D  right record and count, wrong content
"""
import json, re, collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'out'
k2=json.loads((OUT/'k2_sharp.json').read_text())

def classify(r):
    want,got=set(r['want']),set(r['got'])
    if want and got and want!=got:            return 'A'   # wrong record
    if r['n_hit']==0:                         return 'B'   # nothing matching
    if r['n_hit'] < r['n_exp']:               return 'C'   # incomplete
    return 'D'                                             # right target, wrong content

rows=[]
for r in k2:
    rows.append(dict(task=r['task'], tier=r['tier'], category=classify(r),
                     n_expected=r['n_exp'], n_hit=r['n_hit'],
                     wanted_entities=r['want'], committed_entities=r['got'],
                     commit_step=r['commit_i'], page_entered_step=r['entered_i'],
                     dwell=r['gap'], n_steps=r['n_steps']))
c=collections.Counter(x['category'] for x in rows)
print(f"{len(rows)} committed-but-wrong episodes")
print(f"  A wrong record            {c['A']}")
print(f"  B nothing matching        {c['B']}")
print(f"  C right record, incomplete{c['C']:>2}")
print(f"  D right record, wrong content {c['D']}")
print(f"  paper's Table 8 states 6 / 2 / 0 / 7")
match = (c['A'],c['B'],c['C'],c['D'])==(6,2,0,7)
print(f"  -> {'MATCHES' if match else 'DOES NOT MATCH -- fix the table or the rule'}")
print()
print(f"{'task':>5}{'tier':>7}{'cat':>5}{'exp':>5}{'hit':>5}{'dwell':>7}  want -> got")
for x in rows:
    print(f"{x['task']:>5}{x['tier']:>7}{x['category']:>5}{x['n_expected']:>5}{x['n_hit']:>5}"
          f"{x['dwell']:>7}  {','.join(x['wanted_entities']) or '-'} -> {','.join(x['committed_entities']) or '-'}")
(OUT/'k2_labels.json').write_text(json.dumps(rows, indent=1))
print(f"\nwrote out/k2_labels.json  ({len(rows)} labelled episodes, coding rule in this file's classify())")
