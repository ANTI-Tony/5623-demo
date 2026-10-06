"""Minimal, budget-aware web agent. One LM call per step."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from cawebagent.agent.prune import prune_axtree
from cawebagent.lm.protocol import SonnetLM, Tier

SYSTEM = """You are a web agent operating a Magento admin site through an accessibility tree.

Each turn you receive the GOAL, the current URL, recent actions, and a pruned
accessibility tree in which actionable elements carry a numeric id in brackets,
e.g. `[736] button 'Cancel'`.

Reply with EXACTLY ONE action on a single line, no prose, no code fences.
Available actions:
  click('<bid>')                      - click the element with that bracket id
  fill('<bid>', '<text>')             - type text into a field
  select_option('<bid>', '<label>')   - choose an option
  goto('<url>')                       - navigate directly
  go_back()                           - browser back
  send_msg_to_user('<json>')          - FINISH the task (see below)

Destructive operations open a confirmation modal; after clicking the primary
button you must also click the modal's 'OK' button to commit the change.

To finish, call send_msg_to_user with a JSON string exactly of this form:
{"task_type": "mutate"|"retrieve"|"navigate", "status": "SUCCESS", "retrieved_data": <list or null>, "error_details": null}

Act directly. Do not explain. Output only the action line."""

ACT = re.compile(r"\b(click|fill|select_option|goto|go_back|send_msg_to_user|noop)\s*\(")

# Models sometimes echo the observation's display form of an element id instead of
# the bare id: click('[156]') or click('[226] link '...''). Both are the model
# copying what it was shown. Recover the bid rather than failing the step, and
# record that we did so.
BID_ARG = re.compile(r"^(click|fill|select_option)\(\s*'(?P<arg>[^']*)'")
BRACKETED = re.compile(r"^\s*\[(\d+)\]")

def _normalise(line: str) -> tuple[str, bool]:
    """Recover a bare bid from the observation's display form.

    click('[156]')                  -> click('156')
    click('[226] link 'MARKETING'') -> click('226')
    fill('[748]', 'text')           -> fill('748', 'text')
    Anything without a leading [digits] is returned untouched.
    """
    m = BID_ARG.match(line)
    if not m:
        return line, False
    b = BRACKETED.match(m.group("arg"))
    if not b:
        return line, False
    verb = m.group(1)
    rest = line[m.end():]                      # what follows the first quoted arg
    if verb == "click":
        return f"click('{b.group(1)}')", True  # a click takes exactly one argument
    return f"{verb}('{b.group(1)}'" + rest, True

@dataclass
class Step:
    i: int; action: str; raw: str; tier: str; usd: float
    input_tokens: int; output_tokens: int; cache_read: int; url: str; err: str

class Agent:
    def __init__(self, lm: SonnetLM, tier: Tier, max_steps: int = 12):
        self.lm, self.tier, self.max_steps = lm, tier, max_steps
        self.history: list[str] = []
        self.steps: list[Step] = []

    def _prompt(self, obs, goal):
        from browsergym.utils.obs import flatten_axtree_to_str
        ax = prune_axtree(flatten_axtree_to_str(obs["axtree_object"]))
        hist = "\n".join(f"  {i}. {a}" for i, a in enumerate(self.history[-5:])) or "  (none)"
        err = obs.get("last_action_error") or ""
        return (f"GOAL:\n{goal}\n\nURL: {obs['url']}\n"
                f"RECENT ACTIONS:\n{hist}\n"
                + (f"\nLAST ACTION ERROR: {err[:300]}\n" if err else "")
                + f"\nPAGE (pruned accessibility tree):\n{ax}\n\nYour action:")

    def act(self, obs, goal) -> str:
        text, call = self.lm.generate(SYSTEM, self._prompt(obs, goal), self.tier)
        line = ""
        for l in text.strip().splitlines():
            l = l.strip().strip("`")
            if ACT.search(l): line = l; break
        line, repaired = _normalise(line)
        if not line:
            line, repaired = "noop()", False
        self.history.append(line)
        self.steps.append(Step(i=len(self.steps), action=line, raw=text[:300],
                               tier=self.tier.name, usd=call.usd,
                               input_tokens=call.input_tokens, output_tokens=call.output_tokens,
                               cache_read=call.cache_read, url=obs["url"],
                               err=(obs.get("last_action_error") or "")[:120]))
        return line
