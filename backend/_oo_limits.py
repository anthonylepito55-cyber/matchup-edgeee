"""WHAT ARE THE /fixtures/odds PARAMETER LIMITS? (2026-10-11)

The coverage probe got a bare HTTP 400 batching 12 fixtures x 11 sportsbooks. A poller has to
know the real batch ceiling, because that number sets the whole cost model: fixtures-per-call
and books-per-call decide how many requests a full snapshot of a league costs, and therefore how
often we can afford to snapshot. Prints the server's own error text, which the earlier probe
swallowed.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.opticodds.com/api/v3"
HERE = os.path.dirname(os.path.abspath(__file__))
ALL_BOOKS = ["Pinnacle", "Kalshi", "Polymarket", "Novig", "Circa Sports", "FanDuel",
             "DraftKings", "BetOnline", "bet365", "Betfair Exchange", "BookMaker", "Fliff"]


def load_key():
    k = os.environ.get("OPTICODDS_API_KEY")
    if k:
        return k.strip()
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8", errors="replace"):
            if ln.strip().startswith("OPTICODDS_API_KEY") and "=" in ln:
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return None


KEY = load_key()
if not KEY:
    raise SystemExit("no key")


def get(path, params):
    q = "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(BASE + path + q,
                                 headers={"X-Api-Key": KEY, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as h:
            return json.loads(h.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %s %s" % (e.code, e.read().decode("utf-8", "replace")[:240])
    except Exception as e:
        return None, str(e)[:160]


d, err = get("/fixtures/active", {"league": "nba"})
if err:
    raise SystemExit(err)
ids = [f["id"] for f in d["data"][:15] if f.get("id")]
print("nba active fixture ids pulled: %d\n" % len(ids))

print("batching ceiling (fixtures x sportsbooks):")
for nf in (1, 2, 3, 5, 10):
    for nb in (1, 3, 5, 8, 12):
        r, e = get("/fixtures/odds", {"fixture_id": ids[:nf],
                                      "sportsbook": ALL_BOOKS[:nb], "market": "moneyline"})
        if e:
            print("   fixtures=%-2d books=%-2d -> %s" % (nf, nb, e))
            break
        rows = r.get("data") or []
        tot = sum(len(x.get("odds") or []) for x in rows)
        print("   fixtures=%-2d books=%-2d -> OK  %d fixtures, %d odds rows"
              % (nf, nb, len(rows), tot))

print("\nwhich of these venues actually price NBA right now (1 fixture, 1 book per call):")
for b in ALL_BOOKS:
    r, e = get("/fixtures/odds", {"fixture_id": ids[:3], "sportsbook": b, "market": "moneyline"})
    if e:
        print("   %-18s %s" % (b, e))
        continue
    rows = r.get("data") or []
    tot = sum(len(x.get("odds") or []) for x in rows)
    withp = sum(1 for x in rows if x.get("odds"))
    print("   %-18s %d/%d fixtures priced, %d selections" % (b, withp, len(rows), tot))
