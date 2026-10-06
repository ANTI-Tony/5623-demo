"""Refuse to overwrite recorded evidence with an empty result.

Every analysis script here reads a run directory and writes a JSON summary. When
the run directory is absent -- most often because the HTTP archives it needs are
3.3 GB and are deliberately not distributed -- the loops simply iterate zero
times, the counters stay at zero, and the script writes a well-formed file full
of zeros and exits 0. Doing that on a clean clone silently replaces the shipped
evidence with nothing, and the next reader sees numbers that contradict the paper
with no indication anything went wrong.

`require` turns that into a loud failure before anything is written.
"""
from __future__ import annotations
import sys


class EmptyInput(RuntimeError):
    pass


def require(n: int, what: str, needs: str = "") -> None:
    """Stop before writing if nothing was processed.

    n     -- how many inputs were actually consumed
    what  -- what they were, for the message
    needs -- what is probably missing, if we can guess
    """
    if n > 0:
        return
    msg = [f"refusing to write: processed 0 {what}."]
    if needs:
        msg.append(f"This analysis needs {needs}.")
    msg.append("Writing now would replace recorded results with zeros, so nothing "
               "was written and the existing output is unchanged.")
    print("\n!! " + " ".join(msg), file=sys.stderr)
    raise EmptyInput(" ".join(msg))
