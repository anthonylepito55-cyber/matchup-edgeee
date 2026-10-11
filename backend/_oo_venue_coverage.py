"""DO THE SHARPS AND THE EXCHANGES ACTUALLY RETURN PRICES? (2026-10-11)

Being in /sportsbooks only means OpticOdds KNOWS the book. The question that decides whether a
sharp-vs-exchange scanner is buildable is whether real prices come back for the venues that
matter:

  SHARP (defines fair):     Pinnacle, Circa Sports, BetOnline, BookMaker
  EXCHANGE (where we bet):  Kalshi, Polymarket, Novig, Betfair Exchange
  RETAIL (reference):       FanDuel, DraftKings, bet365

Checked across several leagues, because coverage is usually deep on NFL/NBA and thin elsewhere,
and the whole plan changes if the exchanges only show up for US majors.

Also measures the two practical limits: how many fixtures one call returns prices for, and
whether a de-vigged sharp price and an exchange price can be put side by side right now -- which
is the actual product.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

BASE = "https://api.opticodds.com/api/v3"
HERE = os.path.dirname(os.path.abspath(__file__))

SHARP = ["Pinnacle", "Circa Sports", "BetOnline", "BookMaker"]
EXCH = ["Kalshi", "Polymarket", "Novig", "Betfair Exchange"]
RETAIL = ["FanDuel", "DraftKings", "bet365"]
LEAGUES = ["nfl", "nba", "nhl", "ncaaf", "mlb", "atp", "epl"]


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
if not KEY:
    raise SystemExit("no key")


def get(path, params=None):
    q = ("?" + urllib.parse.urlencode(params, doseq=True)) if params else ""
    req = urllib.request.Request(BASE + path + q,
                                 headers={"X-Api-Key": KEY, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode("utf-8", "replace")), r.headers, None
    except urllib.error.HTTPError as e:
        return None, e.headers, "HTTP %s" % e.code
    except Exception as e:
        return None, None, str(e)[:120]


def devig(p1, p2):
    """two-way de-vig by normalising implied probabilities"""
    if not p1 or not p2:
        return None
    i1, i2 = 1.0 / p1, 1.0 / p2
    return i1 / (i1 + i2)


def am_to_dec(a):
    a = float(a)
    return 1 + a / 100.0 if a > 0 else 1 + 100.0 / abs(a)


print("=" * 104)
print("VENUE COVERAGE BY LEAGUE -- fixtures with a moneyline price from each venue")
print("=" * 104)
BOOKS = SHARP + EXCH + RETAIL
for lg in LEAGUES:
    d, hdr, err = get("/fixtures/active", {"league": lg})
    if err:
        print("   %-7s fixtures FAILED %s" % (lg, err))
        continue
    fixtures = (d.get("data") if isinstance(d, dict) else d) or []
    if not fixtures:
        print("   %-7s no active fixtures" % lg)
        continue
    ids = [f.get("id") for f in fixtures[:12] if f.get("id")]
    d2, hdr2, err2 = get("/fixtures/odds", {"fixture_id": ids, "sportsbook": BOOKS,
                                            "market": "moneyline"})
    if err2:
        print("   %-7s odds FAILED %s" % (lg, err2))
        continue
    rows = (d2.get("data") if isinstance(d2, dict) else d2) or []
    seen = defaultdict(set)
    for fx in rows:
        for o in (fx.get("odds") or []):
            sb = o.get("sportsbook")
            if sb:
                seen[sb].add(fx.get("id"))
    print("   %-7s %d active, probed %d:" % (lg, len(fixtures), len(ids)))
    for grp, lab in ((SHARP, "sharp "), (EXCH, "exch  "), (RETAIL, "retail")):
        bits = []
        for b in grp:
            hits = [k for k in seen if k.lower() == b.lower() or b.lower() in k.lower()]
            n = len(set().union(*[seen[h] for h in hits])) if hits else 0
            bits.append("%s %d/%d" % (b.split()[0], n, len(ids)))
        print("      %s %s" % (lab, " | ".join(bits)))

print("\n" + "=" * 104)
print("THE ACTUAL PRODUCT -- sharp de-vigged fair vs what the exchange shows, right now")
print("=" * 104)
for lg in ("nfl", "nba", "nhl"):
    d, _h, err = get("/fixtures/active", {"league": lg})
    if err:
        continue
    fixtures = (d.get("data") if isinstance(d, dict) else d) or []
    ids = [f.get("id") for f in fixtures[:25] if f.get("id")]
    if not ids:
        continue
    d2, _h2, err2 = get("/fixtures/odds", {"fixture_id": ids,
                                           "sportsbook": ["Pinnacle", "Kalshi", "Polymarket",
                                                          "Novig", "Circa Sports"],
                                           "market": "moneyline"})
    if err2:
        continue
    rows = (d2.get("data") if isinstance(d2, dict) else d2) or []
    print("\n   %s" % lg.upper())
    shown = 0
    for fx in rows:
        by = defaultdict(dict)
        for o in (fx.get("odds") or []):
            sb, nm, pr = o.get("sportsbook"), o.get("selection"), o.get("price")
            if sb and nm and pr is not None:
                by[sb][nm] = pr
        pin = by.get("Pinnacle") or by.get("Circa Sports")
        if not pin or len(pin) < 2:
            continue
        names = list(pin.keys())[:2]
        fair = devig(am_to_dec(pin[names[0]]), am_to_dec(pin[names[1]]))
        if fair is None:
            continue
        line = "      %-42s sharp fair %5.1f%%" % (
            (str(fx.get("home_team_display"))[:19] + " v " + str(fx.get("away_team_display"))[:19]),
            100 * fair)
        for ex in ("Kalshi", "Polymarket", "Polymarket (USA)", "Novig"):
            e = by.get(ex)
            if e and names[0] in e:
                try:
                    ip = 1.0 / am_to_dec(e[names[0]])
                except Exception:
                    continue
                line += "  | %s %5.1f%% (%+.1fpt)" % (ex[:4], 100 * ip, 100 * (fair - ip))
        if "|" in line:
            print(line)
            shown += 1
        if shown >= 6:
            break
    if not shown:
        print("      no fixture had BOTH a sharp and an exchange price in this snapshot")

print("\n" + "=" * 104)
print("LIMITS -- rate-limit headers on the last call")
print("=" * 104)
d, hdr, err = get("/fixtures/active", {"league": "nba"})
if hdr:
    found = False
    for k in hdr.keys():
        if any(t in k.lower() for t in ("ratelimit", "rate-limit", "quota", "remaining")):
            print("   %s: %s" % (k, hdr[k]))
            found = True
    if not found:
        print("   no rate-limit headers returned (limits undocumented in the response)")
