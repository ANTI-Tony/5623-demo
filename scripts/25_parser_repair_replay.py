"""Replay the parser repair against the run it would have saved.

The second model emitted the observation's display form of an element id
(click('[156]')) instead of the bare id on 95 of 96 steps, and 87 steps failed to
parse. This checks, offline against the recorded raw outputs, how many the repair
recovers. (The two counts differ: not every bracketed step is a parse failure.)
"""
import re, json, glob, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cawebagent.agent.policy import _normalise, ACT

BATCH = sys.argv[1] if len(sys.argv) > 1 else 'runs/batch_sonnet46'
VALID = re.compile(r"^[a-z_]+\('[^']*'(, '[^']*')?\)$|^(go_back|noop)\(\)$|^goto\('.*'\)$")

tot = rep = errs = fixed = 0
for fp in sorted(glob.glob(f'{BATCH}/*_T3max/agent.json')):
    for s in json.load(open(fp))['steps']:
        raw = (s.get('raw') or '').strip()
        if not raw: continue
        tot += 1
        line = next((l.strip().strip('`') for l in raw.splitlines() if ACT.search(l)), '')
        if not line: continue
        out, r = _normalise(line)
        rep += r
        if (s.get('err') or '').strip():
            errs += 1
            if r and VALID.match(out): fixed += 1
print(f"raw outputs replayed        {tot}")
print(f"steps that errored          {errs}")
print(f"steps the repair rewrites   {rep}")
print(f"errored steps now valid     {fixed}  ({100*fixed/max(errs,1):.0f}% recovered)")
