"""THE TWO QUESTIONS GOALSERVE ACTUALLY TURNS ON (2026-10-12).

First pass established: `d-1_gamestats` carries 134 matches of real serve stats from
YESTERDAY -- 107 of them CHALLENGER, which is the level that dominates the board and the level
TennisRatio is slowest on. That alone is a win.

But ITF showed only 3 matches, and the ITF feeds carry no stat markers. So:

  Q1  WHAT EXACTLY IS IN THE STAT LINE?  enumerate every stat name, and whether raw
      won/total counts come with it (percentages alone cannot be re-aggregated into a
      52-week figure; counts can).

  Q2  DOES POINT-BY-POINT COVER ITF?  this is the one that matters. If p2p carries ITF point
      sequences, ITF serve/return stats can be DERIVED rather than ingested -- which would
      solve the 91%-no-context problem that no other source touches. If p2p is tour-only too,
      ITF stays dark and Goalserve's value is challenger speed only.

Also sweeps d-1..d-7 so ITF coverage is judged over a week rather than one quiet day.
"""
import gzip
import io as _io
import json
import os
import urllib.request
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))


def load_key():
    k = os.environ.get("GOALSERVE_KEY")
    if k:
        return k.strip()
    for ln in open(os.path.join(HERE, ".env"), encoding="utf-8", errors="replace"):
        if ln.strip().startswith("GOALSERVE_KEY") and "=" in ln:
            return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return None


BASE = "https://www.goalserve.com/getfeed/%s/tennis_scores/" % load_key()


def get(path, timeout=90):
    req = urllib.request.Request(BASE + path + "?json=1",
                                 headers={"Accept-Encoding": "gzip",
                                          "User-Agent": "research/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.GzipFile(fileobj=_io.BytesIO(raw)).read()
            return json.loads(raw.decode("utf-8", "replace")), None
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, str(e)[:80])


def L(x):
    return [] if x is None else (x if isinstance(x, list) else [x])


def level(name):
    s = str(name).lower()
    return ("ITF" if "itf" in s else "challenger" if "challenger" in s
            else "WTA" if "wta" in s else "ATP" if "atp" in s else "other")


print("=" * 108)
print("Q1 -- EVERY STAT NAME IN THE GAME-STATS FEED, and whether raw counts come with it")
print("=" * 108)
d, err = get("d-1_gamestats")
names = Counter()
withcnt = Counter()
groups = Counter()
if err:
    print("   FAILED %s" % err)
else:
    for c in L((d.get("statistics") or {}).get("category")):
        for m in L(c.get("match")):
            for p in L(m.get("player")):
                for per in L((p.get("stats") or {}).get("period")):
                    for ty in L(per.get("type")):
                        groups[str(ty.get("@name"))] += 1
                        for st in L(ty.get("stat")):
                            nm = str(st.get("@name"))
                            names[nm] += 1
                            if str(st.get("@total") or "").strip():
                                withcnt[nm] += 1
    print("   stat GROUPS: %s" % dict(groups))
    print("\n   %-34s %8s %8s" % ("stat", "seen", "w/counts"))
    for nm, cnt in names.most_common(40):
        print("   %-34s %8d %8d%s" % (nm, cnt, withcnt[nm],
                                      "  <- re-aggregatable" if withcnt[nm] else ""))

print("\n" + "=" * 108)
print("Q2 -- ITF COVERAGE over a week, in BOTH the stats feed and point-by-point")
print("=" * 108)
print("   %-8s %-34s %-34s" % ("day", "gamestats by level", "p2p by level"))
for day in ("d-1", "d-2", "d-3", "d-4", "d-5", "d-6", "d-7"):
    gs, e1 = get("%s_gamestats" % day)
    lv = Counter()
    if not e1:
        for c in L((gs.get("statistics") or {}).get("category")):
            for _m in L(c.get("match")):
                lv[level(c.get("@name"))] += 1
    pp, e2 = get("%s_p2p" % day) if day == "d-1" else (None, "skipped")
    lp = Counter()
    if pp and not e2:
        for c in L((pp.get("scores") or {}).get("category")):
            for _m in L(c.get("match")):
                lp[level(c.get("@name"))] += 1
    print("   %-8s %-34s %-34s" % (day, dict(lv) or e1, dict(lp) or e2))

print("\n" + "=" * 108)
print("DOES p2p CARRY ACTUAL POINT SEQUENCES? (if so ITF stats could be DERIVED)")
print("=" * 108)
pp, e = get("d-1_p2p")
if e:
    print("   FAILED %s" % e)
else:
    cats = L((pp.get("scores") or {}).get("category"))
    itf = [c for c in cats if level(c.get("@name")) == "ITF"]
    any_c = itf[0] if itf else (cats[0] if cats else None)
    print("   categories: %d | of which ITF: %d" % (len(cats), len(itf)))
    if any_c:
        m = L(any_c.get("match"))[0]
        print("   sample category: %s  (%s)" % (str(any_c.get("@name"))[:60],
                                                level(any_c.get("@name"))))
        print("   match keys: %s" % list(m.keys()))
        blob = json.dumps(m)
        print("   payload sample: %s" % blob[:700])
