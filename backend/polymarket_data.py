"""Polymarket data source (2026-10-06): tennis slate + prices + per-set scores + settlement
from Polymarket's PUBLIC Gamma API (no API key needed for reads). Built as a FALLBACK for
when OpticOdds is down/invalid — tennis_data uses it only when the OpticOdds fetch returns
nothing, so it auto-reverts the moment the OpticOdds key is restored.

Each tennis match is a Gamma EVENT (tag_id=864) with:
  teams: [{name, ordering:"home"/"away"}, ...]      -> the two players
  a "moneyline" market: outcomes=[p1name,p2name], outcomePrices=[p,1-p] (vig-free),
                        bestBid/bestAsk/lastTradePrice
  startDate, live, ended, period, score ("6-3, 1-6, 6-4" — FULL per-set line), umaResolutionStatus

This module exposes the SAME shapes as tennis_data.get_tennis_today_matches /
get_tennis_moneyline_odds, plus pm_results() for tennis_log.settle.
"""
import time
from datetime import datetime, timezone

import requests

GAMMA = "https://gamma-api.polymarket.com"
TENNIS_TAG = 864
_cache = {}          # key -> (ts, value)
_TTL = 120           # seconds


def _get(url, params):
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def _fetch_events(closed):
    """All current tennis events for closed=<bool>, newest startDate first, paginated."""
    ck = f"ev_{closed}"
    hit = _cache.get(ck)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    out, offset = [], 0
    while True:
        try:
            data = _get(f"{GAMMA}/events", {
                "tag_id": TENNIS_TAG, "closed": "true" if closed else "false",
                "limit": 100, "offset": offset, "order": "startDate", "ascending": "false"})
        except Exception:  # noqa: BLE001
            break
        if not data:
            break
        out += data
        offset += 100
        if len(data) < 100 or offset >= 1500:
            break
    _cache[ck] = (time.time(), out)
    return out


def _moneyline_market(ev):
    """The head-to-head moneyline market whose two outcomes are the player names."""
    for m in ev.get("markets") or []:
        if m.get("sportsMarketType") == "moneyline":
            return m
    # fallback: a market with exactly two non-Yes/No outcomes
    for m in ev.get("markets") or []:
        outs = _as_list(m.get("outcomes"))
        if len(outs) == 2 and set(o.lower() for o in outs) != {"yes", "no"}:
            return m
    return None


def _as_list(v):
    """Gamma returns some arrays as JSON strings — normalize to a list."""
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            import json
            return json.loads(v)
        except Exception:  # noqa: BLE001
            return []
    return []


def _norm_ts(s):
    """Normalize PM timestamps to ISO: 'gameStartTime' comes as '2026-10-07 11:00:00+00'."""
    if not s:
        return None
    s = str(s).strip().replace(" ", "T")
    if s.endswith("+00"):
        s = s[:-3] + "+00:00"
    return s


def _start_time(ev):
    """The REAL scheduled match start. PM's event `startDate` is the market-creation time
    (clustered per batch) — the actual start is the event-level `startTime` (clean ISO), or
    the market-level `gameStartTime`. Fall back to startDate only if neither exists."""
    t = ev.get("startTime")
    if not t:
        for m in (ev.get("markets") or []):
            if m.get("gameStartTime"):
                t = m.get("gameStartTime")
                break
    return _norm_ts(t or ev.get("startDate"))


def _players(ev):
    teams = ev.get("teams") or []
    home = next((t.get("name") for t in teams if t.get("ordering") == "home"), None)
    away = next((t.get("name") for t in teams if t.get("ordering") == "away"), None)
    if home and away:
        return home, away
    if len(teams) == 2:
        return teams[0].get("name"), teams[1].get("name")
    return None, None


def _is_singles(ev):
    """Singles only. PM pre-combines doubles into team names like 'Santillan/Zheng', and the
    title carries '(Doubles)' — exclude both (OpticOdds filtered by competitor count)."""
    p1, p2 = _players(ev)
    if not p1 or not p2:
        return False
    if "/" in p1 or "/" in p2:
        return False
    if "doubles" in (ev.get("title") or "").lower():
        return False
    return True


def _league(ev):
    """Map the PM slug to our league ids. PM uses 'atp-'/'wta-' prefixes (challengers included
    under 'atp'/'wta'); ITF under 'itf'. Gender is what the pipeline actually needs."""
    slug = (ev.get("slug") or "").lower()
    if slug.startswith("wta"):
        return "wta"
    if slug.startswith("atp"):
        return "atp"
    if slug.startswith("itf"):
        return "itf_women" if "women" in slug else "itf_men"
    # last resort: infer from any league/series label on the event
    lab = str((ev.get("series") or [{}])[0].get("title") if ev.get("series") else "").lower()
    if "wta" in lab:
        return "wta"
    return "atp"


def _status(ev):
    if ev.get("ended"):
        return "completed"
    if ev.get("live"):
        return "live"
    return "unplayed"


def _tournament(ev):
    t = ev.get("title") or ""
    return t.split(":")[0].strip() if ":" in t else (ev.get("seriesSlug") or None)


def _american_from_prob(p):
    try:
        p = float(p)
    except (TypeError, ValueError):
        return None
    p = min(max(p, 0.001), 0.999)
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def _fixture_id(ev):
    return "pm_" + str(ev.get("id"))   # namespaced so it never collides with OpticOdds ids


def _match_price(ev):
    """(p1_prob, p2_prob) for the two players, using mid of best bid/ask, else last trade,
    else outcomePrices. Returned in player_1/player_2 (home/away) order."""
    m = _moneyline_market(ev)
    if not m:
        return None, None
    outs = _as_list(m.get("outcomes"))
    prices = _as_list(m.get("outcomePrices"))
    if len(outs) != 2 or len(prices) != 2:
        return None, None
    p1name, _ = _players(ev)
    # outcomes order may differ from teams order; align to player_1 (home)
    try:
        idx1 = 0 if (p1name and outs[0].strip().lower() == p1name.strip().lower()) else \
            (1 if (p1name and outs[1].strip().lower() == p1name.strip().lower()) else 0)
    except Exception:  # noqa: BLE001
        idx1 = 0
    try:
        pr = [float(x) for x in prices]
    except (TypeError, ValueError):
        return None, None
    return pr[idx1], pr[1 - idx1]


def _window_ok(ev, date):
    """Keep events whose startDate sits in the board's window: from the day before `date`
    through 2 days after (UTC), matching OpticOdds' 48h+ pull. Trims far-future ITF futures."""
    sd = _start_time(ev)
    if not sd:
        return False
    try:
        t = datetime.fromisoformat(str(sd).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return True
    if date:
        try:
            base = datetime.fromisoformat(date + "T00:00:00+00:00")
        except Exception:  # noqa: BLE001
            base = datetime.now(timezone.utc)
    else:
        base = datetime.now(timezone.utc)
    days = (t - base).total_seconds() / 86400.0
    return -0.75 <= days <= 1.5


def _keep_league(lg, leagues):
    """This module serves ATP/WTA only (the main board). ITF is handled by the existing
    polymarket_tennis.fetch_open_itf() module, which parses gender (M/W) from the slug
    correctly — so we must NOT return ITF here or we'd override it (mislabeled) via the
    ITF endpoint's pair-dedup. Challengers map to atp/wta in _league, so they're included."""
    if lg in ("itf_men", "itf_women"):
        return False
    if leagues:
        return lg in leagues
    return lg in ("atp", "wta")


def pm_today_matches(date=None, leagues=None):
    """Same shape as tennis_data.get_tennis_today_matches()."""
    out = []
    for ev in _fetch_events(False):
        if len(ev.get("teams") or []) != 2 or not _window_ok(ev, date):
            continue
        if not _keep_league(_league(ev), leagues) or not _is_singles(ev):
            continue
        p1, p2 = _players(ev)
        out.append({
            "fixture_id": _fixture_id(ev), "league": _league(ev),
            "tournament": _tournament(ev), "round": ev.get("period") or None,
            "player_1": p1, "player_2": p2,
            "start_time_utc": _start_time(ev), "status": _status(ev),
        })
    return out


def pm_moneyline_odds(date=None, leagues=None):
    """Same shape as tennis_data.get_tennis_moneyline_odds()."""
    out = {}
    for ev in _fetch_events(False):
        if len(ev.get("teams") or []) != 2 or not _window_ok(ev, date):
            continue
        if not _keep_league(_league(ev), leagues) or not _is_singles(ev):
            continue
        if ev.get("ended"):
            continue   # resolved market prices are 1.00/0.00 -- never serve those as odds
        p1p, p2p = _match_price(ev)
        if p1p is None or p2p is None or min(p1p, p2p) < 0.03:
            continue   # degenerate/stale one-sided price (resolving or dead market)
        a1, a2 = _american_from_prob(p1p), _american_from_prob(p2p)
        if a1 is None or a2 is None:
            continue
        out[_fixture_id(ev)] = {"player_1": a1, "player_2": a2, "bookmaker": "Polymarket"}
    return out


def _norm_score(s):
    """PM 'score' is '6-3, 1-6, 6-4' -> our space-separated '6-3 1-6 6-4'. None if empty."""
    if not s:
        return None
    return " ".join(x.strip() for x in str(s).split(",") if x.strip())


def pm_results(date=None):
    """{fixture_id: {p1_won: bool, score: '6-3 1-6 6-4', player_1, player_2}} for finished
    matches — drives settlement. Reads both just-ended (closed=false) and resolved (closed=true)."""
    out = {}
    for closed in (False, True):
        for ev in _fetch_events(closed):
            if not ev.get("ended") or len(ev.get("teams") or []) != 2 or not _is_singles(ev):
                continue
            fid = _fixture_id(ev)
            if fid in out:
                continue
            p1, p2 = _players(ev)
            p1p, p2p = _match_price(ev)
            # winner from the resolved market price (the 1.0 side) or the score
            won = None
            if p1p is not None and p2p is not None and abs(p1p - p2p) > 0.05:
                won = p1p > p2p
            if won is None:
                continue
            res = {"p1_won": bool(won), "score": _norm_score(ev.get("score")),
                   "player_1": p1, "player_2": p2}
            out[fid] = res
            # ALSO key by slug (2026-10-08): polymarket_tennis's ITF cards use
            # "pm_"+slug fixture ids — publish the result under both keys so the
            # ledger's ITF rows settle too.
            sl = ev.get("slug")
            if sl:
                out.setdefault("pm_" + str(sl), res)
    return out


if __name__ == "__main__":
    ms = pm_today_matches()
    od = pm_moneyline_odds()
    res = pm_results()
    print(f"matches: {len(ms)} | priced: {len(od)} | finished-with-result: {len(res)}")
    import collections
    print("leagues:", dict(collections.Counter(m["league"] for m in ms)))
    print("statuses:", dict(collections.Counter(m["status"] for m in ms)))
    for m in ms[:8]:
        o = od.get(m["fixture_id"]) or {}
        print(f"  [{m['league']:8s} {m['status']:9s}] {m['player_1']} vs {m['player_2']} "
              f"| {o.get('player_1')}/{o.get('player_2')} | {m['tournament']} | {m['start_time_utc']}")
    print("sample results:")
    for fid, r in list(res.items())[:6]:
        print(f"  {r['player_1']} vs {r['player_2']} -> p1_won={r['p1_won']} score={r['score']}")
