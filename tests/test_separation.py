"""NFR3 / AC10: the change detector must not depend on the risk-rating rules.

If detection could see the tier table, then changing which endpoints we call
consequential would silently change what counts as a detected change, and the
collateral counts would be partly a function of our own risk judgements. This
test fails the build if that dependency ever appears.
"""
import ast, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# the detection path: capture, segmentation, collateral
DETECTION = ["cawebagent/trace/har_parse.py", "cawebagent/trace/runner.py"]
# anything that encodes a consequence judgement
RISK_MARKERS = ("exp1_consequence_taxonomy", "tier", "RULES", "consequence")

def imports_of(path):
    tree = ast.parse(Path(path).read_text())
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            out.append(n.module or "")
    return out

def failures():
    bad = []
    for rel in DETECTION:
        p = ROOT / rel
        if not p.exists():
            bad.append(f"{rel}: missing"); continue
        for mod in imports_of(p):
            if any(m.lower() in mod.lower() for m in RISK_MARKERS):
                bad.append(f"{rel}: imports risk-rating module {mod!r}")
        src = p.read_text()
        # a literal tier table inside the detector is the same violation by another route
        if "RULES = [" in src or "tier_of" in src:
            bad.append(f"{rel}: defines a tier table inline")
    return bad

if __name__ == "__main__":
    bad = failures()
    for b in bad:
        print("FAIL:", b)
    if bad:
        sys.exit(1)
    print(f"OK: {len(DETECTION)} detection modules carry no dependency on the risk rules")
