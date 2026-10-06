"""Batch: run N tasks x tiers with hard reset between episodes. Budget-capped, resumable."""
import sys, json, time, argparse, subprocess; sys.path.insert(0,'.')
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--tasks", required=True, help="comma task_ids or @file")
ap.add_argument("--tiers", default="T0,T3")
ap.add_argument("--steps", type=int, default=12)
ap.add_argument("--cap", type=float, default=12.0)
ap.add_argument("--out", default="runs/batch")
a = ap.parse_args()

import os
# .venv312 inside the repo was evicted by iCloud; use the env outside the sync scope
PY = os.environ.get("CAWE_PYTHON", os.path.expanduser("~/.venvs/cawe312/bin/python"))

from webarena_verified.utils import get_package_assets_path
DS = json.loads((get_package_assets_path()/'dataset/webarena-verified.json').read_text())
gym_id = {t["task_id"]: f"webarena_verified.{t['intent_template_id']}.{t['task_id']}.{t['revision']}" for t in DS}

ids = json.loads(Path(a.tasks[1:]).read_text()) if a.tasks.startswith("@") else [int(x) for x in a.tasks.split(",")]
tiers = a.tiers.split(",")
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
plan = [(t, ti) for t in ids for ti in tiers]
print(f"plan: {len(plan)} episodes ({len(ids)} tasks x {len(tiers)} tiers)", flush=True)

done = 0
for k, (tid, tier) in enumerate(plan):
    d = out / f"{gym_id[tid].replace('.','_')}_{tier}"
    if (d/"score.json").exists():
        print(f"[{k+1}/{len(plan)}] task {tid} {tier} SKIP (done)", flush=True); done += 1; continue
    print(f"[{k+1}/{len(plan)}] task {tid} {tier} ...", flush=True)
    try:
        r = subprocess.run([PY,"scripts/03_run_agent.py","--task",gym_id[tid],
                            "--tier",tier,"--steps",str(a.steps),"--cap",str(a.cap),"--out",str(out)],
                           capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        print(f"   TIMEOUT after 900s — skipping (episode left unscored)", flush=True)
        continue
    if "BUDGET STOP" in (r.stdout + r.stderr):
        print("!! BUDGET CAP REACHED — stopping batch", flush=True); break
    if r.returncode != 0:
        print(f"   FAIL rc={r.returncode}: {r.stderr.strip().splitlines()[-1][:160] if r.stderr.strip() else ''}", flush=True)
        continue
    s = subprocess.run([PY,"scripts/04_score.py",str(d)], capture_output=True, text=True)
    for l in s.stdout.strip().splitlines()[-4:]: print("   " + l, flush=True)
    done += 1
print(f"\nbatch finished: {done}/{len(plan)} episodes", flush=True)
