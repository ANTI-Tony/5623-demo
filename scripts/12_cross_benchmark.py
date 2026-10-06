"""Cross-benchmark audit: is the evaluator blindness a property of one release,
or of the WebArena lineage? Compares original WebArena against WebArena-Verified.
Pure offline script -- no environment, no API."""
import json, collections, re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'out'
import webarena_verified.utils as wvu

WV = Path(wvu.__file__).resolve().parent            # .../site-packages/webarena_verified
SITE = WV.parent                                     # .../site-packages
RAW = SITE/'webarena'/'test.raw.json'                # original WebArena, 812 tasks
VER = WV/'assets/dataset/webarena-verified.json'     # WebArena-Verified

raw=json.loads(RAW.read_text()); ver=json.loads(VER.read_text())
res={'original_tasks':len(raw), 'verified_tasks':len(ver)}
print(f"original WebArena : {len(raw)} tasks\nWebArena-Verified : {len(ver)} tasks\n")

# ---------- 1. original WebArena assertion vocabulary ----------
vocab=collections.Counter(); et=collections.Counter(); n_ph=0
for t in raw:
    e=t.get('eval') or {}
    for x in e.get('eval_types') or []: et[x]+=1
    for p in e.get('program_html') or []:
        n_ph+=1
        for k in (p.get('required_contents') or {}): vocab[f'program_html.{k}']+=1
    for k in (e.get('reference_answers') or {}): vocab[f'reference_answers.{k}']+=1
NEG=re.compile(r'exclude|not_include|must_not|absent|forbid|should_not', re.I)
neg_orig={k:v for k,v in vocab.items() if NEG.search(k)}
res['original']=dict(eval_types=dict(et), assertion_vocabulary=dict(vocab),
                     program_html_entries=n_ph, negative_terms=neg_orig,
                     network_evaluators=0)
print("original WebArena eval_types:"); [print(f"   {k}: {v}") for k,v in et.most_common()]
print("original WebArena assertion vocabulary:"); [print(f"   {k}: {v}") for k,v in vocab.most_common()]
print(f"   negative-assertion terms: {neg_orig or 'NONE'}")
print(f"   network-level evaluators: 0 (the schema has no request-level evaluator)\n")

# ---------- 2. WebArena-Verified network evaluators (same logic as exp0b) ----------
nev=0; negs=[]; methods=collections.Counter()
for t in ver:
    for e in t['eval']:
        if e.get('evaluator')!='NetworkEventEvaluator': continue
        nev+=1
        methods[(e['expected'].get('http_method') or 'GET').upper()]+=1
        if e.get('should_not_exist'):
            negs.append((t['task_id'], e['expected'].get('url')))
res['verified']=dict(network_evaluators=nev, methods=dict(methods),
                     negative_assertions=len(negs),
                     pct_negative=100*len(negs)/max(nev,1))
print(f"WebArena-Verified network-level evaluators: {nev}")
for k,v in methods.most_common(): print(f"   {k}: {v}")
print(f"   asserting a NEGATIVE (should_not_exist): {len(negs)} "
      f"= {100*len(negs)/max(nev,1):.2f}%")
tgt=collections.Counter(u for _,u in negs if u)
for u,c in tgt.most_common(3): print(f"     {u}  x{c}")
res['verified']['negative_targets']=tgt.most_common(5)
res['verified']['distinct_negative_endpoints']=len(tgt)

print("\n" + "="*74)
print("The original benchmark cannot express 'X should not happen' AT ALL:")
print("its assertion vocabulary is must_include / exact_match / fuzzy_match only.")
print("WebArena-Verified introduced request-level evaluators and with them the")
print("first ability to assert a negative -- used in a small fraction of them.")
print("The blindness is a property of the lineage, not of one release.")
print("="*74)
json.dump(res, open(OUT/'k6_cross_benchmark.json','w'), indent=1)
print("\nwrote out/k6_cross_benchmark.json")
