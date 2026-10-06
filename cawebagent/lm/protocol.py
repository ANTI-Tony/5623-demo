"""Budget-controlled LM layer. Effort tiers ARE the compute knob:
Sonnet 5 removed budget_tokens, so output_config.effort is the only lever."""
from __future__ import annotations
import os, json, time
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass(frozen=True)
class Tier:
    name: str; effort: str; thinking: str; order: int   # thinking: adaptive|disabled

TIERS = {
    "T0": Tier("T0", "low",    "disabled", 0),
    "T1": Tier("T1", "medium", "adaptive", 1),
    "T2": Tier("T2", "high",   "adaptive", 2),
    "T3": Tier("T3", "xhigh",  "adaptive", 3),
    # highest level exposed by models that do not implement xhigh (e.g. Sonnet 4.6)
    "T3max": Tier("T3max", "max", "adaptive", 3),
}

PRICE = {"claude-sonnet-5":  (2.00, 10.00),   # $/MTok in/out (intro thru 2026-08-31)
         "claude-haiku-4-5": (1.00,  5.00),
         "claude-sonnet-4-6": (3.00, 15.00)}

@dataclass
class Call:
    tier: str; input_tokens: int; output_tokens: int
    cache_read: int; cache_write: int
    thinking_chars: int; latency_ms: int; usd: float
    stop_reason: str | None = None
    truncated: bool = False

class Budget:
    """Hard spend cap; raises before a call that would exceed it."""
    def __init__(self, cap_usd: float, ledger: Path):
        self.cap = cap_usd; self.ledger = Path(ledger)
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        self.spent = self._replay()
    def _replay(self) -> float:
        if not self.ledger.exists(): return 0.0
        return sum(json.loads(l)["usd"] for l in self.ledger.read_text().splitlines() if l.strip())
    def check(self, est: float = 0.05):
        if self.spent + est > self.cap:
            raise RuntimeError(f"BUDGET STOP: ${self.spent:.2f} + est ${est:.2f} > cap ${self.cap:.2f}")
    def add(self, c: Call):
        self.spent += c.usd
        with self.ledger.open("a") as f: f.write(json.dumps(asdict(c)) + "\n")
    def __repr__(self): return f"<Budget ${self.spent:.3f}/${self.cap:.2f}>"

class SonnetLM:
    MODEL = os.environ.get("CAWE_MODEL", "claude-sonnet-5")
    def __init__(self, budget: Budget):
        import anthropic
        self.c = anthropic.Anthropic(); self.budget = budget; self.calls: list[Call] = []

    def generate(self, system_stable: str, user: str, tier: Tier, max_tokens: int = 1500):
        self.budget.check()
        t0 = time.time()
        kw = dict(
            model=self.MODEL, max_tokens=max_tokens,
            system=[{"type": "text", "text": system_stable,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"effort": tier.effort},
            thinking={"type": "adaptive"} if tier.thinking == "adaptive" else {"type": "disabled"},
        )
        r = self.c.messages.create(**kw)
        u = r.usage
        pin, pout = PRICE[self.MODEL]
        cr = getattr(u, "cache_read_input_tokens", 0) or 0
        cw = getattr(u, "cache_creation_input_tokens", 0) or 0
        usd = (u.input_tokens*pin + cw*pin*1.25 + cr*pin*0.1)/1e6 + (u.output_tokens*pout)/1e6
        call = Call(tier=tier.name, input_tokens=u.input_tokens, output_tokens=u.output_tokens,
                    cache_read=cr, cache_write=cw,
                    thinking_chars=sum(len(b.thinking or "") for b in r.content if b.type=="thinking"),
                    latency_ms=int((time.time()-t0)*1000), usd=usd,
                    stop_reason=r.stop_reason, truncated=(r.stop_reason=="max_tokens"))
        self.budget.add(call); self.calls.append(call)
        return "".join(b.text for b in r.content if b.type=="text"), call
