"""Run the LLM agent on one task at one tier, with HAR capture + budget cap."""
import sys, json, argparse, time; sys.path.insert(0, '.')
from pathlib import Path
from cawebagent.trace.runner import set_env, run_episode
from cawebagent.trace.reset import hard_reset
from cawebagent.lm.protocol import Budget, SonnetLM, TIERS
from cawebagent.agent.policy import Agent

p = argparse.ArgumentParser()
p.add_argument("--task", required=True)          # e.g. webarena_verified.257.470.2
p.add_argument("--tier", default="T0")
p.add_argument("--steps", type=int, default=12)
p.add_argument("--cap", type=float, default=14.0)
p.add_argument("--out", default="runs/agent")
p.add_argument("--no-reset", action="store_true")
a = p.parse_args()

set_env(WA_SHOPPING_ADMIN="http://localhost:7780/admin")
if not a.no_reset:
    t0=time.time(); hard_reset("shopping_admin"); print(f"reset {time.time()-t0:.0f}s", flush=True)

budget = Budget(a.cap, Path("runs/ledger.jsonl"))
lm = SonnetLM(budget)
agent = Agent(lm, TIERS[a.tier], a.steps)
print(f"budget before: {budget}", flush=True)

goal_box = {}
def dynamic(obs):
    if not goal_box:
        goal_box["g"] = "".join(x["text"] for x in obs["goal_object"] if x["type"]=="text")
    act = agent.act(obs, goal_box["g"])
    print(f"  [{len(agent.steps)-1}] {act[:80]:<80} ${budget.spent:.3f}", flush=True)
    return act

outdir = Path(a.out) / f"{a.task.replace('.','_')}_{a.tier}"
log = run_episode(a.task, [dynamic]*a.steps, outdir)
rec = dict(task=a.task, tier=a.tier, har=log.har, window=list(log.action_window),
           steps=[s.__dict__ for s in agent.steps],
           usd=sum(s.usd for s in agent.steps),
           budget_after=budget.spent)
(outdir/"agent.json").write_text(json.dumps(rec, indent=1))
print(f"\nepisode cost ${rec['usd']:.4f}   {budget}")
print("wrote", outdir/"agent.json")
