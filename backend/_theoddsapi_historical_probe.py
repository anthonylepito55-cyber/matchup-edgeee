"""HOW GOOD IS THE ODDS API'S TENNIS HISTORY? (2026-10-11)

The subscribed key unlocks `/v4/historical/...`, which is the ONE capability OpticOdds denies us
(403 on this plan). That matters more than anything else in the feed, because without history
there is no CLV measurement and no line-movement study except what our own poller has collected
since this morning.

So the question is not "does it work" -- it does -- but whether the history is good enough to
build on. Four things decide that:

  1. GRANULARITY   how far apart are consecutive snapshots? A 5-minute grid supports line
                   movement and steam; a daily one only supports open-vs-close.
  2. REACH BACK    how many seasons? Two years would let us replay the board's tour games
                   against a real closing line instead of our own frozen number.
  3. BOOK DEPTH    which books are IN the history, and is a sharp one (Pinnacle) among them?
                   A closing line built from soft European books is not a benchmark.
  4. COVERAGE      per-tournament sport keys mean history exists only inside tournament
                   windows. How much of a season is actually covered?

Costs are real but trivial here: historical calls bill 10 credits each against ~15M remaining.
Read-only.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://api.the-odds-api.com/v4"
HERE = os.path.dirname(os.path.abspath(__file__))


def load_key():
    k = os.environ.get("ODDS_API_KEY")
    if k:
        return k.strip()
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8", errors="replace"):
            if ln.strip().startswith("ODDS_API_KEY") and "=" in ln:
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return None


KEY = load_key()
HDR = {}


def get(path, params):
    p = dict(params)
    p["apiKey"] = KEY
    try:
        with urllib.request.urlopen(BASE + path + "?" + urllib.parse.urlencode(p),
                                    timeout=60) as r:
            HDR.update({k: v for k, v in r.headers.items()
                        if k.lower().startswith("x-requests")})
            return json.loads(r.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %s %s" % (e.code, e.read().decode("utf-8", "replace")[:160])
    except Exception as e:
        return None, str(e)[:120]


def snap(sport, when):
    r, err = get("/historical/sports/%s/odds" % sport,
                 {"regions": "us,us2,eu,uk", "markets": "h2h", "oddsFormat": "american",
                  "date": when})
    if err:
        return None, None, err
    data = r.get("data") if isinstance(r, dict) else r
    return (r.get("timestamp") if isinstance(r, dict) else None), (data or []), None


# a tournament that is live right now, so the grid is dense
SPORT = "tennis_atp_shanghai_masters"

print("=" * 104)
print("1. GRANULARITY -- consecutive snapshots across one live afternoon")
print("=" * 104)
base = datetime.now(timezone.utc) - timedelta(days=1)
seen = []
for mins in (0, 5, 10, 20, 40, 60):
    when = (base + timedelta(minutes=mins)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ts, data, err = snap(SPORT, when)
    if err:
        print("   requested %s -> FAILED %s" % (when[11:19], err[:70]))
        continue
    print("   requested %s -> snapshot %s   %d events" % (when[11:19], str(ts)[11:19],
                                                          len(data)))
    seen.append(ts)
uniq = [t for i, t in enumerate(seen) if t and (i == 0 or t != seen[i - 1])]
print("\n   distinct snapshots across a 60-minute span: %d" % len(set(t for t in seen if t)))
if len(set(t for t in seen if t)) > 1:
    ds = sorted(set(t for t in seen if t))
    try:
        gaps = [(datetime.fromisoformat(b.replace("Z", "+00:00"))
                 - datetime.fromisoformat(a.replace("Z", "+00:00"))).total_seconds() / 60.0
                for a, b in zip(ds, ds[1:])]
        print("   observed gaps (minutes): %s" % [round(g, 1) for g in gaps])
    except Exception:
        pass

print("\n" + "=" * 104)
print("2. REACH BACK -- how many seasons of tennis history?")
print("=" * 104)
for yrs_back, label in ((0, "this year"), (1, "last year"), (2, "2 years"),
                        (3, "3 years"), (4, "4 years")):
    when = (datetime.now(timezone.utc) - timedelta(days=365 * yrs_back + 2)).strftime(
        "%Y-%m-%dT12:00:00Z")
    ts, data, err = snap(SPORT, when)
    if err:
        print("   %-10s (%s) FAILED %s" % (label, when[:10], err[:80]))
        continue
    print("   %-10s requested %s -> snapshot %s  %d events"
          % (label, when[:10], str(ts)[:19], len(data)))

print("\n" + "=" * 104)
print("3. BOOK DEPTH in the history -- is a SHARP book in there?")
print("=" * 104)
ts, data, err = snap(SPORT, (datetime.now(timezone.utc) - timedelta(days=1)
                             ).strftime("%Y-%m-%dT12:00:00Z"))
if err:
    print("   FAILED %s" % err)
else:
    books = {}
    for ev in data:
        for b in (ev.get("bookmakers") or []):
            books[b.get("key")] = books.get(b.get("key"), 0) + 1
    print("   %d events, %d distinct books in the snapshot" % (len(data), len(books)))
    print("   books by coverage:")
    for b, c in sorted(books.items(), key=lambda kv: -kv[1]):
        print("      %-22s %d events" % (b, c))
    for want in ("pinnacle", "betfair_ex", "betonlineag", "circa", "kalshi", "polymarket"):
        hit = [b for b in books if want in b]
        print("   %-14s %s" % (want, ", ".join(hit) if hit else "-- ABSENT from history --"))

print("\n" + "=" * 104)
print("4. COVERAGE -- how much of a tennis season do the per-tournament keys cover?")
print("=" * 104)
sports, err = get("/sports", {"all": "true"})
if not err:
    tn = [s for s in sports if "tennis" in str(s.get("key", "")).lower()]
    print("   %d tennis tournament keys exist; ~%d-%d weeks of the year are Masters/Slam events"
          % (len(tn), 20, 26))
    print("   NO challenger / ITF key exists, so the board's main volume has no history here.")

print("\n   quota after this probe: %s" % {k: v for k, v in HDR.items()})
