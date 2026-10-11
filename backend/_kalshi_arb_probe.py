"""DO KALSHI'S BUCKET SETS ACTUALLY MISPRICE? (2026-10-11)

Second pass. The first probe used the old field names (`yes_bid`) -- the live schema is
`yes_bid_dollars` / `yes_ask_dollars` with `*_size_fp` for depth -- and it happened to page into
multi-leg parlay markets, which carry no prices. This one asks the real question.

THE TEST, and why it needs no forecasting: inside one Kalshi event the markets are usually an
exhaustive, mutually exclusive bucket set (CPI in each range, who wins the division, the high
temperature band). Exactly one resolves YES. So:

    sum of all yes_ASK  < 100c  ->  buy every bucket, guaranteed 100c back, profit known AT ENTRY
    sum of all yes_BID  > 100c  ->  sell every bucket, same thing in reverse

Nothing here predicts anything; it is arithmetic on the order book. The catch is depth, so this
also pulls `yes_ask_size` -- a 3c "arb" on 5 contracts is not a strategy, and ignoring size is
the phantom-fill trap that makes scanners look profitable when they are not.

Read-only and unauthenticated. No orders are placed.
"""
import json
import urllib.error
import urllib.request

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


def num(v):
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def cents(m, which):
    """price in cents, tolerating both the _dollars schema and the legacy one"""
    v = num(m.get("%s_dollars" % which))
    if v is not None:
        return v * 100.0
    return num(m.get(which))


def size(m, which):
    v = num(m.get("%s_size_fp" % which))
    if v is None:
        v = num(m.get("%s_size" % which))
    if v is None:
        return None
    # _fp fields are fixed-point; large values are scaled
    return v / 1e9 if v > 1e6 else v


# pull a broad set of open events WITH their markets nested
events = []
cursor = None
for _ in range(6):
    p = {"limit": 200, "status": "open", "with_nested_markets": "true"}
    if cursor:
        p["cursor"] = cursor
    d, err = get("/events", p)
    if err:
        print("events FAILED %s" % err)
        break
    events.extend(d.get("events") or [])
    cursor = d.get("cursor")
    if not cursor:
        break
print("open events pulled: %d" % len(events))

sets = []
for e in events:
    ms = e.get("markets") or []
    if len(ms) < 3:
        continue
    asks = [(cents(m, "yes_ask"), size(m, "yes_ask"), m) for m in ms]
    bids = [(cents(m, "yes_bid"), size(m, "yes_bid"), m) for m in ms]
    if any(a[0] is None or a[0] <= 0 for a in asks):
        continue                      # need a two-sided quote on EVERY bucket to arb it
    sets.append((e, ms, asks, bids))
print("events with 3+ markets and a full ask quote on every bucket: %d\n" % len(sets))

rows = []
for e, ms, asks, bids in sets:
    sa = sum(a[0] for a in asks)
    sb = sum(b[0] for b in bids if b[0] is not None)
    # depth-limited contracts: the arb is only as big as the thinnest leg
    dep_a = min([a[1] for a in asks if a[1] is not None], default=None)
    dep_b = min([b[1] for b in bids if b[1] is not None], default=None)
    rows.append((sa, sb, len(ms), dep_a, dep_b, e))

print("=" * 108)
print("BUY-ALL candidates: sum of yes_ASK below 100c (profit = 100 - sum, per set, at entry)")
print("=" * 108)
buy = sorted([r for r in rows if r[0] < 100], key=lambda r: r[0])
if not buy:
    print("   none right now")
for sa, sb, n, da, db, e in buy[:12]:
    print("   %-52s %2d buckets  ask-sum %6.1fc  edge %+5.1fc  thinnest ask size %s"
          % (str(e.get("title"))[:52], n, sa, 100 - sa, da))
    print("      %s | closes %s" % (e.get("category"), str(e.get("strike_date") or "")[:16]))

print("\n" + "=" * 108)
print("SELL-ALL candidates: sum of yes_BID above 100c")
print("=" * 108)
sell = sorted([r for r in rows if r[1] and r[1] > 100], key=lambda r: -r[1])
if not sell:
    print("   none right now")
for sa, sb, n, da, db, e in sell[:12]:
    print("   %-52s %2d buckets  bid-sum %6.1fc  edge %+5.1fc  thinnest bid size %s"
          % (str(e.get("title"))[:52], n, sb, sb - 100, db))
    print("      %s | closes %s" % (e.get("category"), str(e.get("strike_date") or "")[:16]))

print("\n" + "=" * 108)
print("THE DISTRIBUTION -- how far from 100c do these sets sit?")
print("=" * 108)
if rows:
    sas = sorted(r[0] for r in rows)
    import statistics
    print("   ask-sum across %d sets: min %.1fc  p10 %.1fc  median %.1fc  p90 %.1fc  max %.1fc"
          % (len(sas), sas[0], sas[max(0, len(sas) // 10)], statistics.median(sas),
             sas[min(len(sas) - 1, 9 * len(sas) // 10)], sas[-1]))
    print("   sets with ask-sum < 100c: %d  | < 98c: %d  | < 95c: %d"
          % (sum(1 for x in sas if x < 100), sum(1 for x in sas if x < 98),
             sum(1 for x in sas if x < 95)))
    print("   (an efficient venue sits ABOVE 100 on the ask side -- that gap is the spread;")
    print("    anything below 100 is free money, which is why bots hunt it in the liquid names)")

print("\n" + "=" * 108)
print("DEEP-IN-THE-MONEY YIELD -- near-certain contracts trading below 100c")
print("=" * 108)
d, err = get("/markets", {"limit": 1000, "status": "open"})
mk = (d or {}).get("markets") or []
cand = []
for m in mk:
    a = cents(m, "yes_ask")
    oi = num(m.get("open_interest_fp")) or num(m.get("open_interest")) or 0
    if a is not None and 90 <= a <= 99 and oi > 0:
        cand.append((a, oi, m))
cand.sort(key=lambda t: -t[0])
print("   markets quoted 90-99c on the ask (buy, hold to settle): %d of %d scanned"
      % (len(cand), len(mk)))
for a, oi, m in cand[:10]:
    print("      %-56s ask %4.1fc  ->  %4.1f%% if it settles YES   closes %s"
          % (str(m.get("title"))[:56], a, 100 * (100 - a) / a,
             str(m.get("close_time") or "")[:16]))
