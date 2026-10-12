"""WHAT DOES GOALSERVE ACTUALLY GIVE US? (2026-10-12, user: "i got a test key to goalserve how
can i use it")

Probed against the two gaps nothing else has filled, rather than as a general tour of the feed:

  GAP 1 -- ITF STATS.  91% of ITF players have no serve/return context at all
           (project_itf_stats_audit), and the UE source audit found ITF stats exist nowhere.
           TennisRatio has no ITF stat lines, OpticOdds serves ITF odds but empty stats, and
           The Odds API has no ITF at all.

  GAP 2 -- STAT SPEED.  TennisRatio delivers RESULTS same-day but its STAT LINES lag to 37-55%
           on the freshest three days (reference_result_source_latency), which is why L5/L3
           windows are often statless on a live card.

So the questions are: does `d-1_gamestats` carry real serve/return numbers, does it reach below
tour level, and is YESTERDAY already populated? Point-by-point matters too -- from a point
sequence, pressure points and break points can be derived exactly rather than ingested.

Read-only. Key read from backend/.env, never printed.
"""
import json
import os
import urllib.error
import urllib.request
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))


def load_key():
    k = os.environ.get("GOALSERVE_KEY")
    if k:
        return k.strip()
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8", errors="replace"):
            if ln.strip().startswith("GOALSERVE_KEY") and "=" in ln:
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return None


KEY = load_key()
if not KEY:
    raise SystemExit("no GOALSERVE_KEY")
BASE = "https://www.goalserve.com/getfeed/%s/tennis_scores/" % KEY


def get(path, timeout=60):
    url = BASE + path + ("&json=1" if "?" in path else "?json=1")
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "research/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw.decode("utf-8", "replace")), len(raw), None
    except urllib.error.HTTPError as e:
        return None, 0, "HTTP %s" % e.code
    except Exception as e:
        return None, 0, "%s: %s" % (type(e).__name__, str(e)[:120])


def walk_keys(o, depth=0, out=None, prefix=""):
    """collect the leaf key names so the payload shape is visible without dumping it"""
    if out is None:
        out = Counter()
    if depth > 4:
        return out
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, (dict, list)):
                walk_keys(v, depth + 1, out, prefix + k + ".")
            else:
                out[prefix + k] += 1
    elif isinstance(o, list):
        for v in o[:3]:
            walk_keys(v, depth + 1, out, prefix)
    return out


print("=" * 104)
print("0. DOES THE KEY WORK?")
print("=" * 104)
d, nb, err = get("leagues")
print("   leagues      %s  (%d bytes)" % (err or "OK", nb))
if err:
    raise SystemExit("key appears dead")

print("\n" + "=" * 104)
print("GAP 2 -- STAT SPEED: is YESTERDAY already populated with game stats?")
print("=" * 104)
for feed in ("home_gamestats", "d-1_gamestats"):
    d, nb, err = get(feed)
    if err:
        print("   %-16s FAILED %s" % (feed, err))
        continue
    ks = walk_keys(d)
    stat_like = [k for k in ks if any(t in k.lower() for t in
                                      ("ace", "double", "serve", "break", "point", "winner",
                                       "unforced", "error", "fault"))]
    print("   %-16s OK  %6d bytes  | stat-ish fields: %d" % (feed, nb, len(stat_like)))
    for k in sorted(stat_like)[:16]:
        print("        %s" % k)
    if not stat_like:
        print("        top-level shape: %s" % list(d.keys())[:8])

print("\n" + "=" * 104)
print("GAP 1 -- ITF: does it reach below tour, and with stats?")
print("=" * 104)
for feed in ("itf_today", "itf", "itf_shedule", "itf_men_singles_shedule"):
    d, nb, err = get(feed)
    if err:
        print("   %-26s FAILED %s" % (feed, err))
        continue
    blob = json.dumps(d).lower()
    ks = walk_keys(d)
    has_stat = any(t in blob for t in ("ace", "double_fault", "first_serve", "breakpoint",
                                       "break_point"))
    print("   %-26s OK  %7d bytes  | carries stats: %s | fields: %s"
          % (feed, nb, "YES" if has_stat else "no", sorted(ks)[:8]))

print("\n" + "=" * 104)
print("POINT BY POINT -- can pressure points be derived exactly?")
print("=" * 104)
for feed in ("home_p2p", "d-1_p2p"):
    d, nb, err = get(feed)
    if err:
        print("   %-12s FAILED %s" % (feed, err))
        continue
    ks = walk_keys(d)
    print("   %-12s OK  %7d bytes  | fields: %s" % (feed, nb, sorted(ks)[:14]))

print("\n" + "=" * 104)
print("OTHER FEEDS WORTH KNOWING")
print("=" * 104)
for feed in ("home", "d-1", "atp", "wta", "challenger_shedule",
             "itf_women_singles_shedule", "profile?id=2010"):
    d, nb, err = get(feed)
    print("   %-28s %s  (%d bytes)" % (feed, err or "OK", nb))
