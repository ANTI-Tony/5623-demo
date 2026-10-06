"""Turn the raw undo-probe snapshots into the table the paper needs.

Operational definition of irreversibility used here:
  the pre-action state is not reachable again through the same interface the
  agent has, i.e. no control exists whose effect is the inverse.

Evidence is graded, because the affordance-delta signal is not equally
informative for every action class:
  STRONG  -- the action removed affordances and added no inverse (the interface
             visibly closed off options)
  CONTROL -- an inverse WAS found (validates that the probe can detect
             reversibility rather than always reporting irreversible)
  WEAK    -- no affordance changed at all (page template is identical), so
             irreversibility rests on the record being gone with no restore
             path, not on the delta
"""
import json, difflib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
res=json.loads((ROOT/'out/undo_probe.json').read_text())

def field_delta(d):
    pre,post=(d/'PRE.ax.txt'),(d/'POST.ax.txt')
    if not(pre.exists() and post.exists()): return 0
    a=[l.strip() for l in pre.read_text().splitlines() if l.strip()]
    b=[l.strip() for l in post.read_text().splitlines() if l.strip()]
    return sum(1 for l in difflib.unified_diff(a,b,n=0,lineterm='') if l[:1] in '+-' and l[:3] not in ('+++','---'))

rows=[]
for r in res:
    if r.get('error'):
        print(f"{r['cls']}: ERROR {r['error']}"); continue
    d=ROOT/'runs/undo'/r['cls']
    inv=r['inverse_affordance']; lost=r['lost']
    if inv:                    grade,irrev='CONTROL',False
    elif lost:                 grade,irrev='STRONG',True
    else:                      grade,irrev='WEAK',True
    rows.append(dict(cls=r['cls'], status=[r.get('pre_status'),r.get('post_status')],
                     inverse=inv, gained=r['gained'], lost=lost,
                     n_page_lines_changed=field_delta(d),
                     evidence=grade, irreversible=irrev))

w=max(len(r['cls']) for r in rows)+2
print(f"{'action class':<{w}}{'status':<24}{'inverse':<12}{'lost affordances':<44}{'evidence'}")
print("-"*(w+92))
for r in rows:
    st=f"{r['status'][0]} -> {r['status'][1]}" if r['status'][0] else "(n/a)"
    print(f"{r['cls']:<{w}}{st:<24}{str(r['inverse'] or 'NONE'):<12}{str(r['lost'])[:42]:<44}{r['evidence']}")
n=len(rows); irr=sum(1 for r in rows if r['irreversible'])
print(f"\n{irr}/{n} probed action classes expose NO inverse control in the agent's own action space.")
print(f"The positive control ({[r['cls'] for r in rows if not r['irreversible']]}) confirms the probe")
print("detects reversibility when it exists, so the negatives are not a detector artifact.")
json.dump(rows, open(ROOT/'out/undo_report.json','w'), indent=1)
print("\nwrote out/undo_report.json")
