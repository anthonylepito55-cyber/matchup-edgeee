"""Polymarket MLB moneyline fallback (2026-10-08, user "pull the polymarket mlb prices
for the mlb tab"): same situation as tennis — OpticOdds key dead → the MLB tab lost its
market odds. Polymarket's PUBLIC Gamma API (tag_id=100381) carries every MLB game as an
event with teams[{name, ordering}] (full MLB-convention names) and a "moneyline" market
whose outcomes are the team names with contract prices (price IS the probability).

Returns the SAME shape as odds_fetcher.get_moneyline_odds, keyed
(game_time_utc, away_name, home_name) — keys are taken from MLB Stats API's own schedule
(matched by team pair) so they're guaranteed to equal main.py's lookup tuples. Verified
2026-10-07: PM startTime == statsapi gameDate exactly for all 4 playoff games.

"books" stays EMPTY on purpose: Model E's best-price shop must never treat a prediction
market as a sportsbook (same rule as the OpticOdds panel-3 comment) — PM prices go in the
"polymarket" panel only. Auto-reverts: odds_fetcher only calls this when OpticOdds
yields nothing.
"""
import time
from datetime import datetime, timedelta

import requests

GAMMA = "https://gamma-api.polymarket.com"
MLB_TAG = 100381
_cache = {}      # date -> (ts, map)
_TTL = 120


def _american_from_prob(p):
    try:
        p = float(p)
    except (TypeError, ValueError):
        return None
    p = min(max(p, 0.001), 0.999)
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def _as_list(v):
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            import json
            return json.loads(v)
        except Exception:  # noqa: BLE001
            return []
    return []


def _schedule_keys(date):
    """{(away_name, home_name): game_time_utc} from MLB Stats API for date and date+1
    (late UTC starts land on the next calendar day)."""
    out = {}
    try:
        d2 = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        r = requests.get("https://statsapi.mlb.com/api/v1/schedule",
                         params={"sportId": 1, "startDate": date, "endDate": d2}, timeout=15)
        r.raise_for_status()
        for day in r.json().get("dates", []):
            for g in day.get("games", []):
                aw = g["teams"]["away"]["team"]["name"]
                hm = g["teams"]["home"]["team"]["name"]
                # first (earliest) game of a pair wins; doubleheaders get the right one by
                # falling back to the PM startTime key for the second (see caller).
                out.setdefault((aw, hm), g.get("gameDate"))
    except Exception:  # noqa: BLE001
        pass
    return out


def pm_mlb_moneyline(date):
    """Same shape as get_moneyline_odds: {(game_time_utc, away, home): {home, away,
    bookmaker, books, kalshi, polymarket}} from Polymarket's vig-light contract prices."""
    hit = _cache.get(date)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    out = {}
    try:
        evs = requests.get(f"{GAMMA}/events", params={
            "tag_id": MLB_TAG, "closed": "false", "limit": 100,
            "order": "startDate", "ascending": "false"}, timeout=20).json() or []
    except Exception:  # noqa: BLE001
        evs = []
    sched = _schedule_keys(date)
    for ev in evs:
        teams = ev.get("teams") or []
        if len(teams) != 2 or ev.get("ended"):
            continue
        ml = next((m for m in (ev.get("markets") or [])
                   if m.get("sportsMarketType") == "moneyline"), None)
        if not ml:
            continue
        t = {x.get("ordering"): x.get("name") for x in teams}
        away, home = t.get("away"), t.get("home")
        if not away or not home:
            continue
        outs = _as_list(ml.get("outcomes"))
        prices = _as_list(ml.get("outcomePrices"))
        if len(outs) != 2 or len(prices) != 2:
            continue
        try:
            pr = {outs[0]: float(prices[0]), outs[1]: float(prices[1])}
            hp, ap = pr.get(home), pr.get(away)
        except (TypeError, ValueError):
            continue
        if hp is None or ap is None or min(hp, ap) < 0.03 or hp == ap:
            continue   # resolved/degenerate/corrupt — same guards as the tennis fallback
        if not (0.90 <= hp + ap <= 1.12):
            continue
        key_time = sched.get((away, home)) or ev.get("startTime")
        if not key_time:
            continue
        out[(key_time, away, home)] = {
            "home": _american_from_prob(hp),
            "away": _american_from_prob(ap),
            "bookmaker": "Polymarket",
            "books": {},          # NEVER a sportsbook for the best-price shop
            "kalshi": None,
            "polymarket": {"home_prob": round(hp, 4), "away_prob": round(ap, 4),
                           "home_cents": int(round(hp * 100)),
                           "away_cents": int(round(ap * 100))},
        }
    _cache[date] = (time.time(), out)
    return out


if __name__ == "__main__":
    from datetime import timezone
    d = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    m = pm_mlb_moneyline(d)
    print(f"{d}: {len(m)} games priced")
    for k, v in m.items():
        print(f"  {k[1]} @ {k[2]} | {k[0]} | away {v['away']} / home {v['home']}")
