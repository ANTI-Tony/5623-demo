"""Aggressive AXTree pruning. Raw WebArena grids reach ~95k tokens/step, which is
unaffordable; this keeps what an agent can actually act on."""
from __future__ import annotations
import re

# roles the agent can act on (bid-addressable)
ACTIONABLE = re.compile(
    r"\b(button|link|textbox|searchbox|combobox|checkbox|radio|menuitem|menuitemcheckbox|"
    r"tab|option|spinbutton|slider|switch|listbox|textarea)\b", re.I)
# structural context worth keeping
CONTEXT = re.compile(r"\b(heading|alert|status|dialog|rowheader|columnheader|main|form)\b", re.I)
BID = re.compile(r"^\s*\[(\d+)\]")

def prune_axtree(txt: str, max_chars: int = 14000, keep_static_near: int = 1) -> str:
    """Keep actionable + context lines; keep StaticText only adjacent to kept lines.
    Deduplicate repeated gridcell text. Hard-cap the result."""
    lines = txt.split("\n")
    keep = [False] * len(lines)
    for i, l in enumerate(lines):
        if ACTIONABLE.search(l) or CONTEXT.search(l):
            keep[i] = True
            for j in range(max(0, i - keep_static_near), min(len(lines), i + keep_static_near + 1)):
                if "StaticText" in lines[j]:
                    keep[j] = True
    out, seen, dropped = [], set(), 0
    for i, l in enumerate(lines):
        if not keep[i]:
            dropped += 1; continue
        s = l.strip()
        key = re.sub(r"^\[\d+\]\s*", "", s)          # dedupe ignoring bid
        if key in seen and "StaticText" in s:
            dropped += 1; continue
        seen.add(key)
        out.append(l)
    res = "\n".join(out)
    if dropped:
        res += f"\n... [{dropped} non-actionable/duplicate lines omitted]"
    if len(res) > max_chars:
        head = res[: int(max_chars * 0.7)]
        tail = res[-int(max_chars * 0.3):]
        res = head + f"\n... [TRUNCATED {len(res)-max_chars} chars] ...\n" + tail
    return res
