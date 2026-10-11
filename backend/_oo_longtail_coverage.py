"""IS THERE A LONG TAIL WE CAN ACTUALLY BET? (2026-10-11)

The US-major test failed on two counts: the exchanges re-price in 3-6s, and Kalshi/Polymarket
sit BELOW sharp fair anyway. The remaining hope is the long tail -- thinner leagues among the
1,577 active, where re-pricing should be slower and pricing looser.

But a loose market is only useful if we can bet it. So the question is not "where is the market
soft", it is the intersection:

    leagues where a SHARP book prices the game  (so fair value is computable)
      AND an EXCHANGE the user actually uses prices it too  (Kalshi / Polymarket)

If that intersection is just the US majors, the long tail is dead for this account regardless
of how inefficient it is, and we should stop looking there.

Samples broadly rather than exhaustively: a few leagues per sport, a few fixtures per league.
Cheap, because the rate cap resets per minute.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

BASE = "https://api.opticodds.com/api/v3"
HERE = os.path.dirname(os.path.abspath(__file__))

SHARP = ["Pinnacle", "BetOnline"]
MINE = ["Kalshi", "Polymarket", "Polymarket (USA)"]      # the venues the user actually bets
OTHER_EX = ["Novig", "Betfair Exchange"]
LEAGUES_PER_SPORT = 6
FIXTURES_PER_LEAGUE = 3


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
CALLS = [0]


def get(path, params=None):
    q = ("?" + urllib.parse.urlencode(params, doseq=True)) if params else ""
    req = urllib.request.Request(BASE + path + q,
                                 headers={"X-Api-Key": KEY, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            CALLS[0] += 1
            return json.loads(r.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %s" % e.code
    except Exception as e:
        return None, str(e)[:80]


d, err = get("/leagues", {"is_active": "true"})
if err:
    raise SystemExit("leagues failed: %s" % err)
leagues = d.get("data") or []
bysport = defaultdict(list)
for L in leagues:
    sp = L.get("sport")
    sid = sp.get("id") if isinstance(sp, dict) else str(sp)
    bysport[sid].append(L)
print("active leagues: %d across %d sports\n" % (len(leagues), len(bysport)))

results = []
for sport, ls in sorted(bysport.items(), key=lambda kv: -len(kv[1])):
    probed = 0
    for L in ls:
        if probed >= LEAGUES_PER_SPORT:
            break
        lid = L.get("id")
        if not lid:
            continue
        fd, e = get("/fixtures/active", {"league": lid})
        if e or not fd:
            continue
        fx = [f for f in (fd.get("data") or [])
              if f.get("id") and not f.get("is_live")
              and str(f.get("status") or "unplayed") == "unplayed"]
        if not fx:
            continue
        probed += 1
        ids = [f["id"] for f in fx[:FIXTURES_PER_LEAGUE]]
        seen = defaultdict(set)
        for grp in (SHARP + MINE[:3], OTHER_EX):
            if not grp:
                continue
            od, e2 = get("/fixtures/odds", {"fixture_id": ids, "sportsbook": grp[:5],
                                            "market": "moneyline"})
            if e2 or not od:
                continue
            for f in (od.get("data") or []):
                for o in (f.get("odds") or []):
                    if o.get("price") is not None and o.get("sportsbook"):
                        seen[o["sportsbook"]].add(f.get("id"))
        n_sharp = len(set().union(*[seen[b] for b in SHARP if b in seen]) if
                      any(b in seen for b in SHARP) else set())
        n_mine = len(set().union(*[seen[b] for b in MINE if b in seen]) if
                     any(b in seen for b in MINE) else set())
        n_other = len(set().union(*[seen[b] for b in OTHER_EX if b in seen]) if
                      any(b in seen for b in OTHER_EX) else set())
        results.append({"sport": sport, "league": lid, "name": L.get("name"),
                        "fixtures": len(fx), "probed": len(ids),
                        "sharp": n_sharp, "mine": n_mine, "other_ex": n_other,
                        "books": sorted(seen.keys())})

print("=" * 108)
print("LEAGUES WHERE BOTH A SHARP BOOK **AND** KALSHI/POLYMARKET PRICE THE GAME")
print("=" * 108)
both = [r for r in results if r["sharp"] > 0 and r["mine"] > 0]
if not both:
    print("   NONE in the sample")
for r in sorted(both, key=lambda x: -x["fixtures"]):
    print("   %-11s %-34s %3d fixtures  sharp %d/%d  MINE %d/%d   %s"
          % (r["sport"], str(r["name"])[:34], r["fixtures"], r["sharp"], r["probed"],
             r["mine"], r["probed"], ",".join(b for b in r["books"] if b in MINE)))

print("\n" + "=" * 108)
print("SHARP BUT NO KALSHI/POLYMARKET -- soft markets we cannot act on")
print("=" * 108)
sharp_only = [r for r in results if r["sharp"] > 0 and r["mine"] == 0]
print("   %d leagues sampled" % len(sharp_only))
for r in sorted(sharp_only, key=lambda x: -x["fixtures"])[:18]:
    print("   %-11s %-36s %3d fixtures  sharp %d/%d  other-exch %d"
          % (r["sport"], str(r["name"])[:36], r["fixtures"], r["sharp"], r["probed"],
             r["other_ex"]))

print("\n" + "=" * 108)
print("SUMMARY BY SPORT")
print("=" * 108)
agg = defaultdict(lambda: [0, 0, 0])
for r in results:
    a = agg[r["sport"]]
    a[0] += 1
    a[1] += 1 if r["sharp"] > 0 else 0
    a[2] += 1 if (r["sharp"] > 0 and r["mine"] > 0) else 0
print("   %-16s %8s %8s %10s" % ("sport", "sampled", "w/sharp", "w/sharp+MINE"))
for sp, (n, s, b) in sorted(agg.items(), key=lambda kv: -kv[1][2]):
    print("   %-16s %8d %8d %10d" % (sp, n, s, b))
print("\n   leagues sampled %d | with a sharp price %d | ALSO on Kalshi/Polymarket %d"
      % (len(results), sum(1 for r in results if r["sharp"] > 0), len(both)))
print("   API calls used: %d" % CALLS[0])
