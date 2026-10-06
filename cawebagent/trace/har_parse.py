"""HAR -> MutationEvent extraction + phase segmentation + collateral detection."""
from __future__ import annotations
import json, re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

@dataclass
class NetEvent:
    idx: int; method: str; url: str; path: str
    status: int; started_s: float
    post_body: str | None
    sec_fetch_dest: str | None
    resource_type: str | None
    @property
    def is_mutation(self) -> bool: return self.method.upper() != "GET"
    @property
    def is_document(self) -> bool: return (self.sec_fetch_dest or "").lower() == "document"

def _hdr(headers, name):
    n = name.lower()
    for h in headers or []:
        if h.get("name", "").lower() == n:      # HAR uses Title-Case; must fold
            return h.get("value")
    return None

def _ts(s):
    """Return UNIX SECONDS (same clock as browsergym's info timestamps)."""
    try: return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception: return 0.0

def parse_har(path: str | Path) -> list[NetEvent]:
    d = json.loads(Path(path).read_text())
    out = []
    for i, e in enumerate(d["log"]["entries"]):
        req, res = e["request"], e.get("response", {})
        out.append(NetEvent(
            idx=i, method=req["method"], url=req["url"],
            path=re.sub(r"^https?://[^/]+", "", req["url"]).split("?")[0],
            status=res.get("status", 0), started_s=_ts(e.get("startedDateTime", "")),
            post_body=(req.get("postData") or {}).get("text"),
            sec_fetch_dest=_hdr(req.get("headers"), "sec-fetch-dest"),
            resource_type=e.get("_resourceType"),
        ))
    return out

# --- phase segmentation ------------------------------------------------------
def segment(events: list[NetEvent], action_start_s: float, action_end_s: float):
    """Split into setup / action / validate using runner wall-clock marks."""
    setup  = [e for e in events if e.started_s and e.started_s <  action_start_s]
    action = [e for e in events if e.started_s and action_start_s <= e.started_s <= action_end_s]
    valid  = [e for e in events if e.started_s and e.started_s >  action_end_s]
    return dict(setup=setup, action=action, validate=valid)

# --- collateral detection ----------------------------------------------------
BENIGN = (
    r"/admin/mui/index/render",        # grid re-render (read-only UI)
    r"/admin/security/session/",       # session keepalive
    r"/customer/section/load",
    r"/admin/admin/dashboard",
    r"\.(js|css|png|jpg|svg|woff2?|ico)$",
)
def _benign(e: NetEvent) -> bool:
    return any(re.search(p, e.url) for p in BENIGN)

def expected_specs(task) -> list[dict]:
    """Expected state-changing events declared by the task config."""
    out = []
    for ev in task["eval"]:
        if ev["evaluator"] != "NetworkEventEvaluator": continue
        x = ev["expected"]
        m = (x.get("http_method") or "GET").upper()
        if m == "GET": continue
        urls = x["url"] if isinstance(x["url"], list) else [x["url"]]
        for u in urls: out.append(dict(method=m, url=u))
    return out

def _url_matches(spec_url: str, actual_path: str) -> bool:
    pat = re.sub(r"^\^?__[A-Z_]+__", "", spec_url).rstrip("$")
    try: return re.search(pat, actual_path) is not None
    except re.error: return pat in actual_path

def collateral(action_events: list[NetEvent], task) -> list[NetEvent]:
    """Non-GET agent-phase requests that match no expected spec and are not benign."""
    specs = expected_specs(task)
    out = []
    for e in action_events:
        if not e.is_mutation or _benign(e): continue
        if any(e.method.upper() == s["method"] and _url_matches(s["url"], e.path) for s in specs):
            continue
        out.append(e)
    return out
