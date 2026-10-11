"""EXACT SHAPE OF AN /fixtures/odds ROW (2026-10-11).

Needed before writing the poller: the field names for sportsbook/selection/price, whether a
TIMESTAMP comes with each quote (so stored snapshots can be dated per quote rather than per
poll), and above all whether any SIZE or LIMIT field exists -- because without size the scanner
cannot tell a takeable gap from a phantom one, which is the failure mode that makes these tools
look profitable when they are not.
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
        for ln in open(p, encoding="utf-8", errors="replace"):
            if ln.strip().startswith("OPTICODDS_API_KEY") and "=" in ln:
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return None


KEY = load_key()


def get(path, params):
    q = "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(BASE + path + q,
                                 headers={"X-Api-Key": KEY, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as h:
            return json.loads(h.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %s %s" % (e.code, e.read().decode("utf-8", "replace")[:200])


d, err = get("/fixtures/active", {"league": "nba"})
fx = [f for f in d["data"] if f.get("id")][:3]
print("fixture top-level fields: %s\n" % sorted(fx[0].keys()))
print("start_date sample: %s | status %s | is_live %s\n"
      % (fx[0].get("start_date"), fx[0].get("status"), fx[0].get("is_live")))

d2, err = get("/fixtures/odds", {"fixture_id": [f["id"] for f in fx],
                                 "sportsbook": ["Pinnacle", "Kalshi", "Polymarket", "Novig"],
                                 "market": "moneyline"})
rows = d2["data"]
print("fixtures returned: %d" % len(rows))
o = (rows[0].get("odds") or [])
print("odds rows on fixture 1: %d" % len(o))
if o:
    print("\nODDS ROW FIELDS: %s\n" % sorted(o[0].keys()))
    print("full first row:")
    print(json.dumps(o[0], indent=2)[:1200])
    print("\nany size/limit-ish field anywhere in the payload?")
    blob = json.dumps(rows[0])
    for probe in ("size", "limit", "max_", "stake", "liquidity", "depth", "timestamp",
                  "updated", "deep_link"):
        print("   %-12s %s" % (probe, "YES" if probe in blob.lower() else "no"))
    print("\none quote per venue for fixture 1 (%s v %s):"
          % (rows[0].get("home_team_display"), rows[0].get("away_team_display")))
    for q in o:
        print("   %-18s %-28s price %-8s  %s"
              % (q.get("sportsbook"), str(q.get("selection"))[:28], q.get("price"),
                 {k: v for k, v in q.items()
                  if k not in ("sportsbook", "selection", "price", "id", "market",
                               "market_id", "name", "selection_line")}))
