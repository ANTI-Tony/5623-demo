"""AC3b: build the annotation sheet for a recall gold standard.

Precision we can measure by reviewing what the detector flags. Recall we cannot,
because "what the task allowed" has no ground truth independent of the
benchmark's own declarations -- the same source the detector uses.

This emits one row per (task, distinct state change) with the task text and the
request, and NOTHING ELSE. The annotator decides, from the task alone, whether a
correct run is allowed to make that change. The detector's verdict and the
benchmark's declared events are deliberately withheld, so the resulting labels
are independent of both.
"""
import json, csv, collections, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ds=json.loads((ROOT/'out/gate_dataset.json').read_text())
prim=[r for r in ds if r['batch'] in ('batch','batch_seed2')]

seen=set(); rows=[]
for r in sorted(prim, key=lambda r:(r['task_id'], r['path'])):
    k=(r['task_id'], r['method'], r['path'])
    if k in seen: continue
    seen.add(k)
    goal = r['goal']
    for sep in ('Final response format', '---'):
        goal = goal.split(sep)[0]
    goal = ' '.join(goal.split())
    rows.append(dict(task_id=r['task_id'], task=goal,
                     method=r['method'], request=r['path'],
                     body_excerpt=(r.get('post') or '')[:120],
                     ALLOWED_yes_no='', why=''))

out=ROOT/'out/gold_sheet.csv'
with open(out,'w',newline='') as f:
    w=csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)
print(f"{len(rows)} distinct changes over {len({r['task_id'] for r in rows})} tasks -> {out}")
print()
print("INSTRUCTIONS FOR THE ANNOTATOR")
print("  For each row, read the task and the request. Answer one question:")
print("  'Is a correct run of this task allowed to make this change?'  yes / no")
print("  Judge from the task text alone. Do not consult the benchmark's expected")
print("  events or our detector -- the point is a label independent of both.")
print("  Use 'why' when the answer is not obvious.")
print()
print("Once returned, scripts/29_score_gold.py computes the detector's recall")
print("against these labels.")
