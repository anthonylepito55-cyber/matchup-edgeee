"""WHAT CAN THE OPTICODDS KEY DO ACROSS ALL SPORTS? (2026-10-11, user: "what my optic odds api
is there anything i can make to help me beat the market just in general not on tennis but maybe
like a sharp money tracker")

The tennis probe answered a tennis question. This asks the general one, because what is worth
BUILDING depends entirely on which of these the key actually serves:

  1. breadth      -- which sports/leagues are active right now
  2. book list    -- are the SHARP books there (Pinnacle, Circa, BetOnline) and are the
                     EXCHANGES there (Kalshi, Polymarket)? A sharp-money tracker needs both:
                     sharps to define fair, exchanges because that is where the user bets
  3. line history -- can we see a line MOVE, or only its current value? Without history there
                     is no steam detection and no CLV measurement; this is the make-or-break one
  4. openers      -- is there an opening line, so opener->close drift is computable
  5. granularity  -- how often does history tick, and does it carry per-book timestamps
  6. markets      -- moneyline only, or spreads/totals/props too

Read-only. Keys are loaded from the environment or backend/.env and never printed.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.opticodds.com/api/v3"
HERE = os.path.dirname(os.path.abspath(__file__))


def load_key():
    k = os.environ.get("OPTICODDS_API_KEY")
    if k:
        return k.strip()
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        with open(p, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                if ln.strip().startswith("OPTICODDS_API_KEY") and "=" in ln:
                    return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return None


KEY = load_key()
print("key loaded: %s\n" % bool(KEY))
if not KEY:
    raise SystemExit("no OPTICODDS_API_KEY in env or backend/.env")


def get(path, params=None):
    q = ("?" + urllib.parse.urlencode(params, doseq=True)) if params else ""
    req = urllib.request.Request(BASE + path + q,
                                 headers={"X-Api-Key": KEY, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %s %s" % (e.code, e.read().decode("utf-8", "replace")[:160])
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, str(e)[:160])


def show(label, path, params=None, n=0, keys=False):
    d, err = get(path, params)
    if err:
        print("   %-34s FAILED  %s" % (label, err))
        return None
    items = d.get("data") if isinstance(d, dict) else d
    cnt = len(items) if isinstance(items, list) else "-"
    print("   %-34s OK  %s items" % (label, cnt))
    if isinstance(items, list) and items and keys:
        print("      fields: %s" % sorted(items[0].keys())[:18])
    if isinstance(items, list) and n:
        for it in items[:n]:
            if isinstance(it, dict):
                nm = it.get("name") or it.get("id") or it.get("league") or ""
                print("      - %s" % str(nm)[:70])
    return items


print("=" * 100)
print("1. BREADTH -- sports and active leagues")
print("=" * 100)
sports = show("/sports", "/sports", n=0)
if sports:
    names = [s.get("name") or s.get("id") for s in sports if isinstance(s, dict)]
    print("      sports: %s" % ", ".join(str(x) for x in names[:30]))
leagues = show("/leagues (active)", "/leagues", {"is_active": "true"})
if leagues:
    bysport = {}
    for L in leagues:
        bysport.setdefault(str(L.get("sport") or L.get("sport_id") or "?"), []).append(
            str(L.get("name") or L.get("id")))
    for sp, ls in sorted(bysport.items(), key=lambda kv: -len(kv[1]))[:12]:
        print("      %-16s %2d leagues: %s" % (sp, len(ls), ", ".join(ls[:6])))

print("\n" + "=" * 100)
print("2. BOOKS -- are the sharps and the exchanges in the feed?")
print("=" * 100)
books = show("/sportsbooks", "/sportsbooks")
if books:
    names = sorted(str(b.get("name") or b.get("id")) for b in books if isinstance(b, dict))
    print("      total books: %d" % len(names))
    want = ["pinnacle", "circa", "betonline", "bookmaker", "kalshi", "polymarket", "prophetx",
            "novig", "betfair", "fanduel", "draftkings", "bet365", "espn", "fliff"]
    low = [n.lower() for n in names]
    for w in want:
        hit = [n for n, l in zip(names, low) if w in l]
        print("      %-12s %s" % (w, (", ".join(hit) if hit else "-- NOT IN FEED --")))

print("\n" + "=" * 100)
print("3. LINE HISTORY -- the make-or-break capability")
print("=" * 100)
fx = None
for lg in ("nfl", "nba", "mlb", "nhl", "ncaaf"):
    items, err = get("/fixtures/active", {"league": lg})
    if err:
        print("   /fixtures/active %-6s FAILED %s" % (lg, err))
        continue
    data = items.get("data") if isinstance(items, dict) else items
    print("   /fixtures/active %-6s %s fixtures" % (lg, len(data) if data else 0))
    if data and fx is None:
        fx = (lg, data[0])
if fx:
    lg, f = fx
    fid = f.get("id") or f.get("fixture_id")
    print("\n   probing league=%s fixture=%s" % (lg, str(fid)[:40]))
    print("      %s" % str(f.get("home_team_display") or f.get("home_team") or "")[:40]
          + " vs " + str(f.get("away_team_display") or f.get("away_team") or "")[:40])
    for label, path, params in (
        ("/fixtures/odds", "/fixtures/odds",
         {"fixture_id": fid, "sportsbook": ["Pinnacle", "FanDuel"], "market": "moneyline"}),
        ("/fixtures/odds/historical", "/fixtures/odds/historical",
         {"fixture_id": fid, "sportsbook": "Pinnacle", "market": "moneyline"}),
        ("/fixtures/odds (openers?)", "/fixtures/odds",
         {"fixture_id": fid, "sportsbook": "Pinnacle", "market": "moneyline",
          "include_opening_odds": "true"}),
        ("/markets", "/markets", {"league": lg}),
    ):
        d, err = get(path, params)
        if err:
            print("      %-30s FAILED  %s" % (label, err))
            continue
        data = d.get("data") if isinstance(d, dict) else d
        cnt = len(data) if isinstance(data, list) else "-"
        print("      %-30s OK  %s items" % (label, cnt))
        if isinstance(data, list) and data and isinstance(data[0], dict):
            k = sorted(data[0].keys())
            print("         fields: %s" % k[:16])
            # does any payload carry a timestamp or an opener? that is what decides the build
            blob = json.dumps(data[0])[:600]
            for probe in ("timestamp", "opening", "open_", "updated", "history"):
                if probe in blob.lower():
                    print("         carries '%s' -> %s" % (probe, blob[:200]))
                    break
