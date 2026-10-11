"""CAN WE SEE KALSHI'S FULL MARKET STRUCTURE? (2026-10-11)

Decides whether the best idea on the table is buildable. OpticOdds carries Kalshi's SPORTS
moneylines, but the edge I want is in Kalshi's structured markets -- strike ladders (CPI above
X, Fed funds ranges, temperature buckets) and exhaustive multi-outcome groups (who wins the
division, who is the nominee).

Those have ARITHMETIC constraints that do not require forecasting anything:
  * an exhaustive, mutually exclusive bucket set must sum to 100c
  * a strike ladder ("above X") must be monotone decreasing in X
  * nested events must be ordered (wins division <= makes playoffs)
When a venue violates one, the profit is known AT ENTRY. That is a different animal from a
predictive edge, and it is the only thing here that deserves the word "reliable".

This checks what Kalshi's PUBLIC market-data API exposes without authentication: whether
markets come grouped by event (needed for sum-to-100), whether bid/ask AND DEPTH are visible
(needed to know a violation is actually takeable, the phantom-fill trap), and how many markets
are live. Read-only, unauthenticated, no orders.
"""
import json
import urllib.error
import urllib.request
from collections import defaultdict

BASE = "https://api.elections.kalshi.com/trade-api/v2"


def get(path, params=None):
    url = BASE + path
    if params:
        url += "?" + "&".join("%s=%s" % (k, v) for k, v in params.items())
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "research/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %s %s" % (e.code, e.read().decode("utf-8", "replace")[:200])
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, str(e)[:160])


print("=" * 100)
print("1. IS THE PUBLIC API OPEN?")
print("=" * 100)
d, err = get("/markets", {"limit": 200, "status": "open"})
if err:
    print("   /markets FAILED  %s" % err)
    raise SystemExit
mk = d.get("markets") or []
print("   /markets OK -- %d markets in one page (cursor=%s)"
      % (len(mk), bool(d.get("cursor"))))
if mk:
    print("   fields: %s" % sorted(mk[0].keys()))

print("\n" + "=" * 100)
print("2. DO WE GET PRICES AND DEPTH? (depth decides the phantom-fill problem)")
print("=" * 100)
m0 = mk[0]
for k in ("ticker", "event_ticker", "title", "yes_bid", "yes_ask", "no_bid", "no_ask",
          "last_price", "volume", "open_interest", "liquidity", "expiration_time"):
    if k in m0:
        print("   %-18s %s" % (k, str(m0[k])[:70]))
ob, err = get("/markets/%s/orderbook" % m0.get("ticker"), {"depth": 5})
if err:
    print("   orderbook FAILED  %s" % err)
else:
    o = (ob or {}).get("orderbook") or {}
    print("   orderbook OK -- keys %s" % list(o.keys()))
    for side in ("yes", "no"):
        lv = o.get(side)
        if lv:
            print("      %s levels (price, size): %s" % (side, lv[:5]))

print("\n" + "=" * 100)
print("3. ARE MARKETS GROUPED INTO EVENTS? (needed for sum-to-100 and ladders)")
print("=" * 100)
ev = defaultdict(list)
for m in mk:
    ev[m.get("event_ticker")].append(m)
multi = {k: v for k, v in ev.items() if len(v) > 1}
print("   %d markets -> %d events, %d of them multi-market"
      % (len(mk), len(ev), len(multi)))
shown = 0
for k, v in sorted(multi.items(), key=lambda kv: -len(kv[1])):
    print("\n   event %s  (%d markets)" % (k, len(v)))
    tot_ask = tot_bid = 0
    for m in v[:8]:
        ya, yb = m.get("yes_ask"), m.get("yes_bid")
        print("      %-44s yes_bid %3s  yes_ask %3s  vol %-7s oi %s"
              % (str(m.get("title") or m.get("ticker"))[:44], yb, ya,
                 m.get("volume"), m.get("open_interest")))
        if isinstance(ya, (int, float)):
            tot_ask += ya
        if isinstance(yb, (int, float)):
            tot_bid += yb
    if len(v) <= 8:
        print("      -> sum of yes_ask %dc  |  sum of yes_bid %dc   (exhaustive set should "
              "straddle 100c; <100 ask = BUY-ALL arb, >100 bid = SELL-ALL arb)"
              % (tot_ask, tot_bid))
    shown += 1
    if shown >= 4:
        break

print("\n" + "=" * 100)
print("4. HOW BIG IS THE UNIVERSE? (one page is 200; count the series)")
print("=" * 100)
d2, err = get("/events", {"limit": 200, "status": "open"})
if err:
    print("   /events FAILED %s" % err)
else:
    evs = d2.get("events") or []
    cats = defaultdict(int)
    for e in evs:
        cats[str(e.get("category") or e.get("series_ticker") or "?")] += 1
    print("   %d open events in one page; top categories:" % len(evs))
    for c, n in sorted(cats.items(), key=lambda kv: -kv[1])[:14]:
        print("      %-34s %d" % (c[:34], n))
