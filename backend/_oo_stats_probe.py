"""THE TWO THINGS THAT MATTER NOW THE OPTICODDS KEY IS ALIVE (2026-10-10).

  1. Does /fixtures/results carry a real STAT LINE for a TOUR match? The payload has a `stats`
     and a `market_stats` field. If those populate, OpticOdds is the same-day stat source we
     concluded did not exist -- and it covers ITF Men/Women too.
  2. Is the board still on the Polymarket fallback? Memory says the fallback auto-reverts when
     the OpticOdds key comes back. The Brengle card was priced "Polymarket (USA)", so it may
     not have reverted -- which would mean pricing off one venue while 240 books are available.
"""
import json
import os
import urllib.parse
import urllib.request

BASE = "https://api.opticodds.com/api/v3"
HERE = "/home/ec2-user/mlb-predictor/backend"


def load_key():
    k = os.environ.get("OPTICODDS_API_KEY")
    if k:
        return k.strip()
    with open(os.path.join(HERE, ".env"), encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            if ln.strip().startswith("OPTICODDS_API_KEY") and "=" in ln:
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return None


KEY = load_key()


def get(path, params=None):
    q = ("?" + urllib.parse.urlencode(params, doseq=True)) if params else ""
    req = urllib.request.Request(f"{BASE}{path}{q}",
                                 headers={"X-Api-Key": KEY, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            b = r.read().decode("utf-8", "replace")
            return json.loads(b) if b.strip().startswith(("{", "[")) else None
    except Exception as e:  # noqa: BLE001
        print(f"   ERR {path}: {type(e).__name__} {e}")
        return None


def items(d):
    v = d.get("data") if isinstance(d, dict) else d
    return v if isinstance(v, list) else ([v] if v else [])


print("=" * 86)
print("1. DOES A TOUR MATCH CARRY A STAT LINE?")
print("=" * 86)
for league in ("ATP", "WTA", "ITF Women"):
    fx = get("/fixtures", {"sport": "tennis", "league": league, "status": "completed"})
    fi = items(fx)
    if not fi:
        print(f"   {league}: no completed fixtures returned")
        continue
    f0 = fi[0]
    print(f"\n   {league}: {f0.get('home_team_display')} vs {f0.get('away_team_display')} "
          f"({f0.get('start_date')})  id={f0.get('id')}")
    rs = items(get("/fixtures/results", {"fixture_id": f0.get("id")}))
    if not rs:
        print("      no results row")
        continue
    r0 = rs[0]
    for fld in ("stats", "market_stats", "scores", "sub_scores", "retirement_info"):
        v = r0.get(fld)
        s = json.dumps(v) if v is not None else "null"
        print(f"      {fld:16s} {'EMPTY' if s in ('null', '{}', '[]') else s[:260]}")
    low = json.dumps(r0).lower()
    print("      stat keywords: " + ", ".join(
        f"{w}={'Y' if w in low else '-'}" for w in
        ("ace", "fault", "first_serve", "break", "unforced", "winner", "point")))

print("\n" + "=" * 86)
print("2. IS THE BOARD STILL ON THE POLYMARKET FALLBACK?")
print("=" * 86)
import pandas as pd
L = pd.read_parquet(os.path.join(HERE, "data_cache", "tennis_prediction_log.parquet"),
                    columns=["date", "bookmaker"])
L["date"] = pd.to_datetime(L["date"], errors="coerce")
rec = L[L.date >= L.date.max() - pd.Timedelta(days=6)]
print("   bookmaker on the last 7 days of logged cards:")
for b, n in rec.bookmaker.astype(str).value_counts().head(8).items():
    print(f"      {b:34s} {n}")
print("\n   and what OpticOdds would offer for a live tennis fixture right now:")
fx = get("/fixtures", {"sport": "tennis", "status": "unplayed"})
fi = items(fx)
if fi:
    fid = fi[0].get("id")
    od = get("/fixtures/odds", {"fixture_id": fid, "sportsbook": ["Pinnacle", "Kalshi",
                                                                  "Polymarket", "FanDuel"],
                                "market": "Moneyline"})
    oi = items(od)
    print(f"      fixture {fid}: {fi[0].get('home_team_display')} vs "
          f"{fi[0].get('away_team_display')}")
    seen = {}
    for o in oi:
        for q in (o.get("odds") or []) if isinstance(o, dict) else []:
            seen.setdefault(str(q.get("sportsbook")), []).append(
                f"{q.get('name')} {q.get('price')}")
    if not seen and oi:
        print(f"      raw: {json.dumps(oi[0])[:400]}")
    for bk, qs in seen.items():
        print(f"      {bk:14s} {qs[:2]}")
