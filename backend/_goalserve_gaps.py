"""DOES GOALSERVE FILL OUR TWO GAPS? (2026-10-12)

Probe focused on the only two things nothing else supplies:

  GAP 1  ITF STATS   -- 91% of ITF players have no serve/return context. TennisRatio has no ITF
                        stat lines, OpticOdds serves ITF odds with empty stats, The Odds API
                        has no ITF at all.
  GAP 2  STAT SPEED  -- TennisRatio's stat lines lag to 37-55% on the freshest three days, so
                        L5/L3 windows are often statless on a live card.

`d-1_gamestats` returned 106KB, so the question is what is IN it: which stat fields, which
tournament levels, and whether yesterday is already complete. Also checks point-by-point, from
which pressure points and break points could be derived exactly rather than ingested.

The `leagues` endpoint times out; everything else responds, so it is skipped rather than
treated as a failure.
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
    for ln in open(p, encoding="utf-8", errors="replace"):
        if ln.strip().startswith("GOALSERVE_KEY") and "=" in ln:
            return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return None


KEY = load_key()
BASE = "https://www.goalserve.com/getfeed/%s/tennis_scores/" % KEY


def get(path, timeout=60):
    url = BASE + path + ("&json=1" if "?" in path else "?json=1")
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "Accept-Encoding": "gzip",
                                               "User-Agent": "research/1.0"})
    try:
        import gzip
        import io as _io
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.GzipFile(fileobj=_io.BytesIO(raw)).read()
            return json.loads(raw.decode("utf-8", "replace")), len(raw), None
    except Exception as e:
        return None, 0, "%s: %s" % (type(e).__name__, str(e)[:90])


def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


print("=" * 108)
print("GAP 2 -- d-1_gamestats : what stats, and is yesterday already populated?")
print("=" * 108)
d, nb, err = get("d-1_gamestats")
if err:
    raise SystemExit("   FAILED %s" % err)
cats = as_list((d.get("statistics") or {}).get("category"))
print("   %d bytes | %d categories (tournaments)" % (nb, len(cats)))

lvl = Counter()
statfields = Counter()
nmatch = 0
example = None
for c in cats:
    name = str(c.get("@name") or "")
    low = name.lower()
    tag = ("ITF" if "itf" in low else "challenger" if "challenger" in low
           else "WTA" if "wta" in low else "ATP" if "atp" in low else "other")
    for m in as_list(c.get("match")):
        nmatch += 1
        lvl[tag] += 1
        for p in as_list(m.get("player")):
            for k in p.keys():
                statfields[k] += 1
        if example is None and as_list(m.get("player")):
            example = (name, m)
print("   matches with stats: %d" % nmatch)
print("   by level: %s" % dict(lvl))
print("\n   PER-PLAYER STAT FIELDS available:")
for k, v in statfields.most_common(40):
    print("      %-34s on %d players" % (k, v))

if example:
    nm, m = example
    print("\n   EXAMPLE -- %s" % nm[:70])
    print("      %s" % str({k: v for k, v in m.items() if not isinstance(v, (dict, list))})[:220])
    for p in as_list(m.get("player"))[:2]:
        print("      %s" % json.dumps(p)[:460])

print("\n" + "=" * 108)
print("GAP 1 -- ITF: is there an ITF feed, and does it carry stats?")
print("=" * 108)
for feed in ("itf_today", "itf", "itf_men_singles_shedule"):
    dd, nb2, e2 = get(feed)
    if e2:
        print("   %-26s FAILED %s" % (feed, e2))
        continue
    blob = json.dumps(dd).lower()
    marks = [t for t in ("aces", "double_faults", "first_serve", "break_point",
                         "breakpoint", "service", "winner") if t in blob]
    root = list(dd.keys())
    print("   %-26s OK %7d bytes | root=%s | stat markers: %s"
          % (feed, nb2, root, marks or "NONE"))

print("\n" + "=" * 108)
print("POINT BY POINT -- could pressure points be derived exactly?")
print("=" * 108)
for feed in ("home_p2p", "d-1_p2p"):
    dd, nb2, e2 = get(feed)
    if e2:
        print("   %-12s FAILED %s" % (feed, e2))
        continue
    root = list(dd.keys())
    s = json.dumps(dd)
    print("   %-12s OK %7d bytes | root=%s" % (feed, nb2, root))
    print("      sample: %s" % s[:300])

print("\n" + "=" * 108)
print("PLAYER PROFILE + H2H")
print("=" * 108)
for feed in ("profile?id=2010", "h2h_1998-1426"):
    dd, nb2, e2 = get(feed)
    if e2:
        print("   %-18s FAILED %s" % (feed, e2))
        continue
    print("   %-18s OK %6d bytes | %s" % (feed, nb2, json.dumps(dd)[:260]))
