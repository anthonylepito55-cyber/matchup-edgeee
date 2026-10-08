"""Polymarket-direct ITF fetch (2026-10-02, user: 'Polymarket has all of them').
OpticOdds only mirrors ~1 ITF tournament; Polymarket's own Gamma API carries the full ITF
calendar (W15/W25/M15/M25... across many events) with clean 'Tournament: Player A vs
Player B' titles and live implied-probability prices. We pull the OPEN matchup markets
directly and feed them to the ITF tab so our models run on games no sportsbook prices.

Public read-only Gamma API (no auth); browser UA required (default urllib UA gets 403).
Cached in-process; the ITF endpoint is itself SWR-cached on top."""
import re
import time
import json as _json
from datetime import datetime, timezone
import requests

_BASE = "https://gamma-api.polymarket.com"
_H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
# Search terms to enumerate Polymarket's ITF matchup markets. The tier strings catch the
# titled events; the generic "tennis" + common host-city terms surface ITF events the tier
# queries miss (2026-10-02: narrow tier-only list found 28, this broader sweep finds 36 --
# the user's "every single match"). Non-ITF tennis (ATP/Challenger tour, e.g. the Japan
# Open) is filtered out below so it isn't mislabeled into the ITF tab.
_TIERS = ["ITF", "tennis", "W15", "W25", "W35", "W50", "W75", "W100", "W125",
          "M15", "M25", "M35", "M50", "M75", "M100", "W10", "M10",
          # host cities / common ITF venues the tier queries miss (2026-10-05, Kabbaj/
          # Sensano case -- a game OpticOdds mirrors with a corrupt line but Polymarket
          # prices correctly; broaden discovery so the real line reaches the board).
          "Monastir", "Sharm", "Cancun", "Antalya", "Heraklion", "Santo Domingo",
          "Tucuman", "Villena", "Reus", "Getxo", "Horb", "Telavi", "Kigali"]
_CACHE = {"at": 0.0, "data": []}
_TTL = 180  # 3 min


def _search(q):
    try:
        r = requests.get(f"{_BASE}/public-search",
                         params={"q": q, "limit_per_type": 40}, headers=_H, timeout=15)
        if r.status_code == 200:
            return r.json().get("events", [])
    except requests.exceptions.RequestException:
        pass
    return []


def _american(p):
    p = min(max(float(p), 0.01), 0.99)
    return int(round(-100 * p / (1 - p))) if p >= 0.5 else int(round(100 * (1 - p) / p))


def _tag_events():
    """FULL ITF universe via the tennis tag listing (2026-10-08, user "u should have 300
    itf matches"): the search endpoint caps at ~40 results per query, so the tier sweep
    was finding 18-44 of Polymarket's ~227 open ITF singles. The paginated tag_id=864
    listing (shared cache with polymarket_data) is the superset — slug starts with
    'itf', same title/markets shape. Window −12h..+36h so far-future days don't flood
    the tab (the models recompute daily anyway)."""
    try:
        import polymarket_data as _pmd
        evs = [e for e in _pmd._fetch_events(False) if str(e.get("slug") or "").startswith("itf")]
    except Exception:  # noqa: BLE001
        return []
    out = []
    now_utc = datetime.now(timezone.utc)
    for e in evs:
        st = e.get("startTime") or (e.get("markets") or [{}])[0].get("gameStartTime") or e.get("startDate")
        try:
            t = datetime.fromisoformat(str(st).strip().replace(" ", "T").replace("+00", "+00:00").replace("Z", "+00:00"))
            h = (t - now_utc).total_seconds() / 3600.0
            if not (-12 <= h <= 36):
                continue
        except (ValueError, TypeError):
            continue
        out.append(e)
    return out


def fetch_open_itf():
    """Open ITF singles matchups from Polymarket, as fixture dicts shaped like the board's
    (fixture_id/league/tournament/player_1/player_2/start_time_utc/status) plus american
    odds + market_p1 from the Polymarket price. Cached 3 min. Sourced from the FULL
    tag-864 listing (2026-10-08); the legacy search sweep remains as a fallback."""
    now = time.time()
    if _CACHE["data"] and now - _CACHE["at"] < _TTL:
        return _CACHE["data"]
    seen = {}
    _tagged = _tag_events()
    for e in _tagged:
        _consume_event(e, seen)
    if not seen:   # tag listing unavailable -> legacy search sweep
        for q in _TIERS:
            for e in _search(q):
                _consume_event(e, seen)
    out = list(seen.values())
    _CACHE.update({"at": now, "data": out})
    return out


def _consume_event(e, seen):
    """Parse one Gamma event into a fixture dict (shared by the tag listing and the
    legacy search sweep). Mutates `seen` keyed by slug; silently skips non-qualifying
    events (not an ITF W#/M# singles matchup with a live two-way price)."""
    title = (e.get("title") or "").strip()
    if " vs" not in title:
        return
    slug = e.get("slug")
    if not slug or slug in seen:
        return
    # prefer the explicit moneyline market (tag-listing events can carry several markets)
    mk = next((m for m in (e.get("markets") or []) if m.get("sportsMarketType") == "moneyline"),
              None) or (e.get("markets") or [{}])[0]
    if mk.get("closed"):
        return
    try:
        outs = mk.get("outcomes")
        prices = mk.get("outcomePrices")
        outs = outs if isinstance(outs, list) else _json.loads(outs or "[]")
        prices = prices if isinstance(prices, list) else _json.loads(prices or "[]")
    except (ValueError, TypeError):
        return
    if len(outs) != 2 or len(prices) != 2:
        return
    if "/" in str(outs[0]) or "/" in str(outs[1]) or "doubles" in title.lower():
        return  # doubles (PM combines the pair into one name) -- singles only
    try:
        p1 = float(prices[0])
    except (ValueError, TypeError):
        return
    if min(p1, 1 - p1) < 0.03:
        return  # degenerate/stale (one side ~0) -- not a live two-way market
    m = re.match(r"([WM])\d", title)
    if not m:
        return  # not an ITF W#/M# event (e.g. ATP Japan Open) -- main board's job
    league = "itf_women" if m.group(1) == "W" else "itf_men"
    tournament = title.split(":")[0].strip()
    # REAL match start is the event-level `startTime` (or market `gameStartTime`);
    # `startDate` is the market-creation time (clustered) -- using it put every game at
    # the wrong time (2026-10-06).
    st = e.get("startTime") or (e.get("markets") or [{}])[0].get("gameStartTime") or e.get("startDate")
    if st:
        st = str(st).strip().replace(" ", "T")
        if st.endswith("+00"):
            st = st[:-3] + "+00:00"
    status = "unplayed"
    try:
        if e.get("ended"):
            status = "completed"
        elif e.get("live") or (st and datetime.fromisoformat(st.replace("Z", "+00:00")) <= datetime.now(timezone.utc)):
            status = "live"
    except (ValueError, TypeError):
        pass
    seen[slug] = {
        "fixture_id": "pm_" + slug, "league": league, "tournament": tournament,
        "round": None, "player_1": str(outs[0]).strip(), "player_2": str(outs[1]).strip(),
        "start_time_utc": st, "status": status,
        "market_p1": round(p1, 4),
        "p1_odds": _american(p1), "p2_odds": _american(1 - p1),
        "source": "polymarket",
    }
