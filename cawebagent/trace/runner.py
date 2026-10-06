"""Instrumented episode runner: HAR capture + phase timestamps + step log."""
from __future__ import annotations
import os, json, time
from dataclasses import dataclass, field, asdict
from pathlib import Path

SITES = dict(WA_SHOPPING_ADMIN=None, WA_SHOPPING=None, WA_REDDIT=None,
             WA_GITLAB=None, WA_WIKIPEDIA=None, WA_MAP=None, WA_HOMEPAGE=None)
DEAD = "http://localhost:1"

def set_env(**live):
    """All seven vars are asserted by browsergym; point dead ones at a closed port."""
    env = {k: DEAD for k in SITES}
    env.update(live)
    os.environ.update(env)

@dataclass
class StepLog:
    i: int; action: str
    action_exec_start: float; action_exec_stop: float
    page_load_stop: float; validation_stop: float
    url: str; last_action_error: str
    reward: float; terminated: bool; truncated: bool

@dataclass
class EpisodeLog:
    task: str; task_id: int; har: str
    goal: str = ""
    steps: list = field(default_factory=list)
    reset_wall: float = 0.0
    close_wall: float = 0.0
    final_response: str | None = None
    @property
    def action_window(self):
        if not self.steps: return (self.reset_wall, self.close_wall)
        return (self.steps[0].action_exec_start, self.steps[-1].validation_stop)
    def save(self, p):
        d = asdict(self); d["action_window"] = self.action_window
        Path(p).write_text(json.dumps(d, indent=1)); return p

def run_episode(task: str, actions, outdir: Path, headless=True, timeout=30000,
                accept_dialogs: bool = True) -> EpisodeLog:
    import gymnasium
    import browsergym.webarena_verified  # noqa: F401
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    tag = task.replace(".", "_")
    har = outdir / f"{tag}.har"
    if har.exists(): har.unlink()

    env = gymnasium.make(f"browsergym/{task}", headless=headless, timeout=timeout)
    env.unwrapped.pw_context_kwargs.update({
        "record_har_path": str(har),
        "record_har_content": "embed",     # required: post bodies feed 447 evaluators
        "record_har_mode": "full",
    })
    log = EpisodeLog(task=task, task_id=int(task.split(".")[2]), har=str(har))
    try:
        log.reset_wall = time.time()
        obs, info = env.reset()
        if accept_dialogs:
            # Magento gates destructive actions behind window.confirm; Playwright
            # auto-DISMISSES dialogs by default, which silently cancels the POST.
            def _accept(d):
                try: d.accept()
                except Exception: pass
            env.unwrapped.context.on("dialog", _accept)
            env.unwrapped.page.on("dialog", _accept)
        log.goal = "".join(p["text"] for p in obs["goal_object"] if p["type"] == "text")
        for i, act in enumerate(actions):
            if callable(act):                    # dynamic action: obs -> action str
                act = act(obs)
                if act is None: continue
            obs, r, term, trunc, info = env.step(act)
            log.steps.append(StepLog(
                i=i, action=act,
                action_exec_start=float(info.get("action_exec_start", 0)),
                action_exec_stop=float(info.get("action_exec_stop", 0)),
                page_load_stop=float(info.get("wait_for_page_loading_stop", 0)),
                validation_stop=float(info.get("validation_stop", 0)),
                url=obs["url"], last_action_error=obs["last_action_error"][:200],
                reward=float(r), terminated=bool(term), truncated=bool(trunc)))
            if term or trunc: break
    finally:
        env.close()                     # HAR flushed HERE
        log.close_wall = time.time()
    log.save(outdir / f"{tag}.episode.json")
    return log


def click_button(name: str, nth: int = -1):
    """Return a dynamic action that clicks the button whose a11y name == `name`.
    nth=-1 picks the LAST match (modals are appended late in the tree)."""
    import re
    from browsergym.utils.obs import flatten_axtree_to_str
    def _f(obs):
        txt = flatten_axtree_to_str(obs["axtree_object"])
        bids = re.findall(r"\[(\d+)\] button '" + re.escape(name) + r"'", txt)
        if not bids:
            raise RuntimeError(f"button {name!r} not found")
        return f"click('{bids[nth]}')"
    return _f
