"""WHAT DOES THE ODDS API GIVE FOR TENNIS, AND IS IT BETTER THAN OPTICODDS? (2026-10-11,
user: "i got an sub to the odds api i want you to see if it has more better tennis info")

The comparison that matters, because OpticOdds already covers a lot
(reference_opticodds_general_capability): 240 books, 15 tennis leagues INCLUDING ATP Challenger
and ITF, tour stat lines, Kalshi + Polymarket in the same feed -- but **/fixtures/odds/historical
is 403 on our plan**, so we have no line history except what our own poller has collected since
this morning.

So this probe is organised around what would actually be an upgrade:

  1. HISTORICAL ODDS -- the one real gap. The Odds API documents
     /v4/historical/sports/{sport}/odds?date=... on paid plans. If that works, it is worth more
     than anything else here: it would give instant CLV and line-movement history instead of
     waiting weeks for our poller to accumulate it.
  2. TENNIS DEPTH -- which tours? ATP/WTA only, or challenger and ITF too? OpticOdds has
     challenger (92 fixtures today) and ITF, which is most of the board.
  3. BOOKS -- does it carry Pinnacle (fair value) and Kalshi/Polymarket (where the user bets)?
  4. MARKETS -- h2h only, or spreads/totals/sets as well?
  5. SCORES -- is there a results feed we could settle from?
  6. QUOTA -- the response headers state usage; a per-request cost model changes how any
     poller would be designed.

Read-only. Keys are read from the environment or backend/.env and never printed.
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
print("key loaded: %s\n" % bool(KEY))
if not KEY:
    raise SystemExit("no ODDS_API_KEY")

LAST = {}


def get(path, params=None):
    p = dict(params or {})
    p["apiKey"] = KEY
    url = BASE + path + "?" + urllib.parse.urlencode(p)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            for h in ("x-requests-remaining", "x-requests-used", "x-requests-last"):
                if r.headers.get(h):
                    LAST[h] = r.headers.get(h)
            return json.loads(r.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:220]
        for h in ("x-requests-remaining", "x-requests-used"):
            if e.headers and e.headers.get(h):
                LAST[h] = e.headers.get(h)
        return None, "HTTP %s %s" % (e.code, body)
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, str(e)[:140])


print("=" * 104)
print("2. TENNIS DEPTH -- which tennis competitions exist?")
print("=" * 104)
sports, err = get("/sports", {"all": "true"})
if err:
    print("   /sports FAILED %s" % err)
    raise SystemExit
tennis = [s for s in sports if "tennis" in str(s.get("key", "")).lower()
          or str(s.get("group", "")).lower() == "tennis"]
print("   total sports on the plan: %d   | tennis entries: %d" % (len(sports), len(tennis)))
active = [s for s in tennis if s.get("active")]
print("   tennis ACTIVE now: %d" % len(active))
for s in tennis:
    print("      %-34s active=%-5s  %s" % (s.get("key"), s.get("active"),
                                           str(s.get("title"))[:40]))
low = " ".join(str(s.get("key", "")) + " " + str(s.get("title", "")) for s in tennis).lower()
print("\n   does it reach below tour level?")
for tag in ("challenger", "itf", "futures", "atp", "wta", "doubles"):
    print("      %-12s %s" % (tag, "YES" if tag in low else "-- absent --"))

if not active:
    print("\n   no active tennis competition right now -- the rest of the probe needs one.")

print("\n" + "=" * 104)
print("3+4. BOOKS AND MARKETS on a live tennis competition")
print("=" * 104)
WANT = ["pinnacle", "kalshi", "polymarket", "novig", "betfair", "betonline", "circa",
        "fanduel", "draftkings", "betmgm"]
for s in active[:3]:
    k = s["key"]
    od, err = get("/sports/%s/odds" % k,
                  {"regions": "us,us2,eu,uk", "markets": "h2h", "oddsFormat": "american"})
    if err:
        print("   %-30s odds FAILED %s" % (k, err))
        continue
    books = {}
    for ev in (od or []):
        for b in (ev.get("bookmakers") or []):
            books.setdefault(b.get("key"), set()).add(ev.get("id"))
    print("   %-30s %d events, %d books" % (k, len(od or []), len(books)))
    if books:
        print("      books: %s" % ", ".join(sorted(books)[:18]))
        for w in WANT:
            hit = [b for b in books if w in b.lower()]
            print("         %-11s %s" % (w, (", ".join(hit) if hit else "-- no --")))
    # which markets does this competition support?
    for mk in ("h2h", "spreads", "totals", "outrights", "h2h_h2h", "sets"):
        t, e2 = get("/sports/%s/odds" % k,
                    {"regions": "us,eu", "markets": mk, "oddsFormat": "american"})
        nb = sum(len(ev.get("bookmakers") or []) for ev in (t or [])) if t else 0
        print("      market %-10s %s" % (mk, ("OK, %d book-quotes" % nb) if not e2
                                         else e2.split(" ")[1] + " " + e2[:60]))
    break

print("\n" + "=" * 104)
print("1. HISTORICAL ODDS -- the one thing OpticOdds will not give us (403)")
print("=" * 104)
probe_sport = active[0]["key"] if active else "tennis_atp_us_open"
for days_back in (2, 30, 200):
    when = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime(
        "%Y-%m-%dT12:00:00Z")
    h, err = get("/historical/sports/%s/odds" % probe_sport,
                 {"regions": "us,eu", "markets": "h2h", "oddsFormat": "american",
                  "date": when})
    if err:
        print("   %-4sd ago (%s)  FAILED  %s" % (days_back, when[:10], err))
        continue
    data = h.get("data") if isinstance(h, dict) else h
    snap = h.get("timestamp") if isinstance(h, dict) else None
    nb = sum(len(ev.get("bookmakers") or []) for ev in (data or []))
    print("   %-4sd ago (%s)  OK  snapshot=%s  %d events, %d book-quotes"
          % (days_back, when[:10], str(snap)[:19], len(data or []), nb))
    if data:
        ev = data[0]
        print("      sample: %s v %s, %d books"
              % (ev.get("home_team"), ev.get("away_team"), len(ev.get("bookmakers") or [])))

print("\n" + "=" * 104)
print("5. SCORES / RESULTS FEED")
print("=" * 104)
if active:
    sc, err = get("/sports/%s/scores" % active[0]["key"], {"daysFrom": 3})
    if err:
        print("   scores FAILED %s" % err)
    else:
        done = [x for x in (sc or []) if x.get("completed")]
        print("   %d events returned, %d completed" % (len(sc or []), len(done)))
        for x in done[:4]:
            print("      %-44s %s" % (("%s v %s" % (x.get("home_team"), x.get("away_team")))[:44],
                                      x.get("scores")))

print("\n" + "=" * 104)
print("6. QUOTA")
print("=" * 104)
for k, v in LAST.items():
    print("   %-26s %s" % (k, v))
print("\n   note: this API bills PER REQUEST x regions x markets, unlike OpticOdds whose")
print("   8,000 cap resets every minute -- that difference drives any poller design.")
