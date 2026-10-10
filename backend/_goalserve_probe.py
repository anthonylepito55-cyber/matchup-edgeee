"""DOES GOALSERVE POPULATE UNFORCED ERRORS? (2026-10-10, user: "do that")

Why Goalserve is the lead worth testing: the level split (`_ue_edge_by_level.py`) showed the
women's unforced-error dog edge is a **WTA-TOUR** edge -- +10.8% (n=276), positive 2024/25/26,
against -0.4% for every charted dog in the same band and level. Tour level is exactly where
official stats crews record unforced errors. We currently have both players charted on only 47%
of WTA-tour + slam women's dogs at +100..+250, so full tour coverage roughly doubles the lane
(~19 picks a month instead of ~9). Goalserve is what dropshotft.com licenses, and Dropshot
visibly shows unforced errors for tour matches our model is blank on.

What is NOT yet known: whether Goalserve's own feed exposes the field. Their public pages list
"in-game player statistics" without naming fields, and the public live-score sample carries only
scores -- no stats at all. So this must be verified on their free 30-day trial before paying
($150/month, $1,200/year).

USAGE: put the trial token in backend/.goalserve_key (gitignored, same pattern as the RapidAPI
key -- never pasted into a command or a chat), then:
    cd backend && venv/Scripts/python.exe _goalserve_probe.py

It walks a set of candidate feed paths, dumps every field name it finds, and reports whether
anything resembling unforced errors / winners appears, and at which tournament levels. Goalserve's
exact stats path is not publicly documented, so the path list is a starting point -- if their
reply names the right one, add it to PATHS and re-run.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter

BASE = "http://www.goalserve.com/getfeed"
# Goalserve's documented shape is /getfeed/{token}/{feed}/{resource}. The stats resource is not
# named on their public pages; these are the plausible candidates to try first.
PATHS = [
    "tennis_scores/home?json=1",
    "tennis_scores/stats?json=1",
    "tennis_scores/livescore?json=1",
    "tennis/home?json=1",
    "tennis_scores/d1?json=1",
]
UE_WORDS = ("unforced", "winner", "error")


def token():
    f = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".goalserve_key")
    try:
        with open(f, encoding="utf-8-sig") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def walk(obj, trail="", depth=0):
    """Every leaf field name in a nested JSON payload, with a sample value."""
    out = []
    if depth > 7:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{trail}.{k}" if trail else k
            if isinstance(v, (dict, list)):
                out += walk(v, p, depth + 1)
            else:
                out.append((p, v))
    elif isinstance(obj, list):
        for v in obj[:2]:
            out += walk(v, trail + "[]", depth + 1)
    return out


def main():
    t = token()
    if not t:
        print("No token found.\n"
              "Ask Goalserve for the free 30-day tennis trial, then put the token in\n"
              "  backend/.goalserve_key\n"
              "(gitignored; nothing else needed) and run this again.")
        return
    print(f"probing {len(PATHS)} candidate Goalserve feeds\n")
    found_any = False
    for p in PATHS:
        url = f"{BASE}/{t}/{p}"
        shown = url.replace(t, "<TOKEN>")
        try:
            with urllib.request.urlopen(url, timeout=40) as r:
                raw = r.read().decode("utf-8", "replace")
                st = r.status
        except urllib.error.HTTPError as e:
            print(f"  {e.code}  {shown}")
            continue
        except Exception as e:  # noqa: BLE001
            print(f"  ERR  {shown}  {str(e)[:80]}")
            continue
        try:
            body = json.loads(raw)
            fields = walk(body)
            names = Counter(re.sub(r"\[\]", "", n.split(".")[-1]) for n, _ in fields)
        except ValueError:
            # XML fallback: just pull attribute names
            names = Counter(re.findall(r'(\w+)=', raw))
            fields = []
        print(f"  {st}  {shown}  ({len(raw)} bytes, {len(names)} distinct field names)")
        hits = [n for n in names if any(w in n.lower() for w in UE_WORDS)]
        if hits:
            found_any = True
            print(f"       *** error/winner-like fields: {hits}")
            for n, v in fields:
                if any(w in n.lower() for w in UE_WORDS):
                    print(f"           {n} = {v!r}")
        else:
            top = ", ".join(sorted(names)[:22])
            print(f"       fields: {top}{' …' if len(names) > 22 else ''}")
    print()
    if found_any:
        print("VERDICT: an unforced-errors-like field EXISTS. Next: confirm it is POPULATED (not\n"
              "null) on WTA-tour matches, then wire the ingest -- it merges into tennis_ue the\n"
              "same way manual_ue.csv does, so the 🧤 lane widens with no model change.")
    else:
        print("VERDICT: no error/winner field in any feed reached. Either the stats resource is a\n"
              "different path (ask them for the exact one and add it to PATHS), or the feed does\n"
              "not carry unforced errors -- in which case do not buy it. The field existing in a\n"
              "schema is not evidence; the RapidAPI feed documented it and returned null on 21 of\n"
              "21 matches at every level.")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
