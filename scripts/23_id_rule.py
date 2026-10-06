"""The method, as a rule rather than a model.

Interrupt an outgoing state-changing request unless every entity identifier in
its path also appears in the task text. Two lines. Compared here against the
deterministic read-only gate and against the model-based pre-commit check.
"""
import json, re, collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'out'
ID=re.compile(r'/(?:order_id|address_id|id|shipment_id|track_id)/(\d+)')

def interrupt(goal, path):
    ids=ID.findall(path)
    if not ids: return True                       # nothing to verify -> ask
    named=set(re.findall(r'\d+', goal))
    return not all(i in named for i in ids)       # ask unless the task named them all

if __name__=='__main__':
    chk=json.loads((OUT/'gate_check.json').read_text())
    INT={'BLOCK','ESCALATE','UNPARSED'}
    def report(items, unit, label_of, preds):
        C=[x for x in items if label_of(x)=='collateral']
        print(f"\n{unit}  (n={len(items)}, collateral={len(C)})")
        for name,p in preds:
            inter=[x for x in items if p(x)]
            got=[x for x in inter if label_of(x)=='collateral']
            print(f"   {name:<26} interruptions {len(inter):>4}  "
                  f"recall {100*len(got)/len(C):>5.1f}%  precision {100*len(got)/max(len(inter),1):>5.1f}%")
    rule_req=lambda r: interrupt(r['goal'], r['path'])
    report(chk,"PER REQUEST",lambda r:r['label'],
           [("read-only gate",lambda r:True),
            ("model-based check",lambda r:r['verdict'] in INT),
            ("two-line id rule",rule_req)])
    g=collections.defaultdict(list)
    for r in chk: g[(r['dir'],r['method'],r['path'])].append(r)
    items=list(g.values())
    report(items,"PER DISTINCT CHANGE",lambda v:v[0]['label'],
           [("read-only gate",lambda v:True),
            ("model-based check",lambda v:any(x['verdict'] in INT for x in v)),
            ("two-line id rule",lambda v:any(rule_req(x) for x in v))])
    agree=sum(1 for r in chk if (r['verdict'] in INT)==rule_req(r))
    print(f"\nmodel and rule agree on {agree}/{len(chk)} = {100*agree/len(chk):.1f}% of requests")
    shape=lambda p: re.sub(r'/\d+','/N',p)
    t=collections.defaultdict(collections.Counter)
    for r in chk: t[shape(r['path'])][r['verdict']]+=1
    maj=sum(max(c.values()) for c in t.values())
    print(f"an {len(t)}-row endpoint lookup reproduces {maj}/{len(chk)} = {100*maj/len(chk):.1f}% of the model's verdicts")
