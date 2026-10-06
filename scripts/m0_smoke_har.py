"""M0 smoke — validate the HAR instrumentation chain end to end, with NO LLM.
Opens a real WebArena-Verified task, performs a few scripted actions, closes the
context, and verifies the HAR was flushed WITH request bodies.
"""
import os, sys, json, time
from pathlib import Path

SA = "http://localhost:7780"
DEAD = "http://localhost:1"          # unavailable sites must still be set (asserted)
os.environ.update(
    WA_SHOPPING_ADMIN=f"{SA}/admin", WA_SHOPPING=DEAD, WA_REDDIT=DEAD,
    WA_GITLAB=DEAD, WA_WIKIPEDIA=DEAD, WA_MAP=DEAD, WA_HOMEPAGE=DEAD,
)

import gymnasium
import browsergym.webarena_verified  # noqa: F401

TASK = sys.argv[1] if len(sys.argv) > 1 else "webarena_verified.257.470.2"
OUT = Path("runs/m0"); OUT.mkdir(parents=True, exist_ok=True)
har = OUT / f"{TASK.replace('.','_')}.har"          # plain .har — NEVER .zip
if har.exists(): har.unlink()

env = gymnasium.make(f"browsergym/{TASK}", headless=True, timeout=30000)

# --- the injection point: pw_context_kwargs is read INSIDE reset() -----------
u = env.unwrapped
print("pw_context_kwargs before:", u.pw_context_kwargs)
u.pw_context_kwargs.update({
    "record_har_path": str(har),
    "record_har_content": "embed",   # MUST be embed: post_data/response bodies
    "record_har_mode": "full",
})

t0 = time.time()
obs, info = env.reset()
print(f"reset in {time.time()-t0:.1f}s")
goal = "".join(p["text"] for p in obs["goal_object"] if p["type"] == "text")
print(f"goal: {goal[:160]}...")
print(f"url : {obs['url']}")
print(f"obs keys: {sorted(obs.keys())}")

# a few harmless read-only steps to generate traffic
for act in ["noop()", "noop()"]:
    obs, r, term, trunc, info = env.step(act)
    print(f"  step {act} -> reward={r} term={term} trunc={trunc} err={obs['last_action_error'][:60]!r}")

env.close()                                   # <- HAR is flushed here
print(f"\nHAR exists: {har.exists()}  size={har.stat().st_size/1e6:.2f} MB" if har.exists() else "HAR MISSING")

if har.exists():
    d = json.load(open(har))
    ents = d["log"]["entries"]
    nonget = [e for e in ents if e["request"]["method"] != "GET"]
    withbody = [e for e in nonget if e["request"].get("postData", {}).get("text")]
    print(f"entries={len(ents)}  non-GET={len(nonget)}  non-GET with body={len(withbody)}")
    hdrs = {h["name"] for e in ents[:3] for h in e["request"]["headers"]}
    print("sample header names:", sorted(n for n in hdrs if n.lower().startswith("sec-fetch"))[:5])
