"""Why the corpus cannot separate the identifier rule from an endpoint allowlist,
and where it could. Pure re-analysis of the benchmark's declared events.

An allowlist decides by endpoint identity alone. The identifier comparison only
earns its keep where one endpoint carries both requested and unrequested writes.
That depends on how many distinct write endpoints a site has and how many carry
an entity id -- both measurable from the declared events, with no agent runs.
"""
import json, collections, re, math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ev=json.loads((ROOT/'out/exp0_events.json').read_text())
mut=[e for e in ev if (e.get('method') or 'GET').upper()!='GET']
shape=lambda u: re.sub(r'/\d+','/N', re.sub(r'^__[A-Z_]+__','',u or '')).split('?')[0]
def site(e):
    s=e.get('sites'); return s[0] if isinstance(s,list) and s else (s or '?')

rows=[]
for st,_ in collections.Counter(site(e) for e in mut).most_common():
    R=[e for e in mut if site(e)==st]
    c=collections.Counter(shape(e['url']) for e in R)
    if len(R)<20: continue
    H=-sum((n/len(R))*math.log2(n/len(R)) for n in c.values())
    Hmax=math.log2(len(c)) if len(c)>1 else 1
    idb=[k for k in c if '/N' in k]
    rows.append(dict(site=st, events=len(R), endpoints=len(c),
                     top3=100*sum(n for _,n in c.most_common(3))/len(R),
                     norm_entropy=H/Hmax,
                     id_bearing_endpoints=len(idb),
                     id_bearing_share=100*sum(c[k] for k in idb)/len(R)))
print(f"{'site':<16}{'events':>8}{'endpts':>8}{'top3%':>8}{'H/Hmax':>9}{'id-endpts':>11}{'id-share%':>11}")
for r in rows:
    print(f"{r['site']:<16}{r['events']:>8}{r['endpoints']:>8}{r['top3']:>7.0f}%"
          f"{r['norm_entropy']:>9.2f}{r['id_bearing_endpoints']:>11}{r['id_bearing_share']:>10.0f}%")
json.dump(rows, open(ROOT/'out/k13_site_structure.json','w'), indent=1)
print("\nwrote out/k13_site_structure.json")
