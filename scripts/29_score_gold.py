"""AC3b: score the detector against the hand-labelled gold standard.

Reads out/gold_sheet.csv once the ALLOWED_yes_no column is filled in, and
compares the annotator's judgement to what the detector actually flagged.

  annotator says NOT allowed + detector flagged      -> true positive
  annotator says NOT allowed + detector stayed quiet -> MISS (what recall measures)
  annotator says allowed     + detector flagged      -> false positive
"""
import csv, json, collections, sys
from math import comb
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sheet=ROOT/'out/gold_sheet.csv'
rows=list(csv.DictReader(open(sheet)))
filled=[r for r in rows if r['ALLOWED_yes_no'].strip().lower() in ('yes','no','y','n')]
if not filled:
    print(f"{sheet} has no judgements yet.")
    print(f"Fill the ALLOWED_yes_no column ({len(rows)} rows) and re-run.")
    sys.exit(0)
print(f"annotated {len(filled)}/{len(rows)} rows")

det={}
for r in json.loads((ROOT/'out/gold_dataset.json').read_text()) if False else \
        json.loads((ROOT/'out/gate_dataset.json').read_text()):
    det[(r['task_id'], r['method'], r['path'])] = r['label']

tp=miss=fp=tn=0; misses=[]
for r in filled:
    allowed = r['ALLOWED_yes_no'].strip().lower().startswith('y')
    flagged = det.get((int(r['task_id']), r['method'], r['request'])) == 'collateral'
    if not allowed and flagged: tp+=1
    elif not allowed and not flagged: miss+=1; misses.append(r)
    elif allowed and flagged: fp+=1
    else: tn+=1
print(f"\n              detector flagged   detector quiet")
print(f"  not allowed {tp:>14}   {miss:>15}")
print(f"  allowed     {fp:>14}   {tn:>15}")
if tp+miss:
    print(f"\n  RECALL    {100*tp/(tp+miss):.1f}%   ({tp} of {tp+miss} disallowed changes caught)")
if tp+fp:
    print(f"  precision {100*tp/(tp+fp):.1f}%")
if misses:
    print(f"\n  the {len(misses)} the detector missed:")
    for m in misses: print(f"    task {m['task_id']}: {m['request'][:62]}  ({m['why'][:40]})")
json.dump(dict(annotated=len(filled), tp=tp, miss=miss, fp=fp, tn=tn,
               recall=(tp/(tp+miss) if tp+miss else None)),
          open(ROOT/'out/k15_gold_recall.json','w'), indent=1)
print(f"\nwrote out/k15_gold_recall.json")
