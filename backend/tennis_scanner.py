"""Tennis cross-book price-edge scanner (2026-09-09).

The 2026 stat study (_tennis_2026_stat_study.py) and the serve-stats experiment
(_tennis_serve_stats_study.py) both found the same thing: every public stat is already in
the price -- our model loses its arguments with the market. What that leaves is PRICE:
the same match is priced differently across books, and a slow book lagging the sharp
consensus is edge that needs no model at all.

This module scans every ATP / WTA / ATP Challenger / ITF singles match with posted odds:
  fair price  = average de-vigged two-way probability across SHARP_BOOKS (needs >= 1)
  edge        = fair prob - implied prob (1/decimal) of a BETTABLE_BOOKS side price
  flag        = edge >= MIN_EDGE with fair prob >= MIN_FAIR_PROB (extreme longshots
                excluded: de-vig assumptions are least trustworthy there)

PRE-REGISTERED EXPERIMENT (forward, frozen, flat 1u -- same discipline as the MLB
trackers): every flagged side is logged, upserted until first serve, FROZEN after, graded
from completed fixtures, with CLV measured against the last sharp fair price seen before
the match started. Checkpoint: judge at 75 settled flags; until then the site shows the
record with an UNPROVEN banner and no bet advice. Known honest caveats, stated up front:
de-vig fair prices are an approximation; soft books limit winners; a flag at scan time
may be gone by the time a human sees it (prices move) -- CLV, not raw ROI, is the primary
health metric because it is robust to that.
"""
import json
import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from data_collection import CACHE_DIR, todays_date_et
from odds_fetcher import OPTICODDS_API_KEY, OPTICODDS_BASE_URL

SCAN_LEAGUES = ["atp", "wta", "atp_challenger", "itf_men", "itf_women"]
SHARP_BOOKS = ["Pinnacle", "Circa Sports"]
BETTABLE_BOOKS = ["FanDuel", "DraftKings", "BetMGM", "Caesars", "BetRivers", "bet365"]

MIN_EDGE = 0.02        # flag when a book's price implies >= 2pts less than the sharp fair prob
MIN_FAIR_PROB = 0.25   # no extreme-longshot flags -- de-vig error concentrates there
MAX_FIXTURES = 150     # per-scan cap, main tours first
FIXTURE_BATCH = 5
CHECKPOINT_N = 75      # settled flags before the record earns a verdict

LOG_PATH = os.path.join(CACHE_DIR, "tennis_scanner_log.parquet")

COLUMNS = ["date", "fixture_id", "league", "tournament", "player_1", "player_2",
           "start_time_utc", "side", "side_player", "book", "price", "decimal", "implied",
           "fair_prob", "edge", "n_sharp", "first_seen_at", "first_seen_price",
           "first_seen_fair", "close_fair", "logged_at", "settled", "side_won"]

_SCAN_CACHE = {}  # date -> (ts, result)
_SCAN_CACHE_TTL = 600


def _read_log() -> pd.DataFrame:
    if os.path.exists(LOG_PATH):
        df = pd.read_parquet(LOG_PATH)
        for c in COLUMNS:
            if c not in df.columns:
                df[c] = None
        return df
    return pd.DataFrame(columns=COLUMNS)


def _write_log(df: pd.DataFrame):
    tmp = LOG_PATH + ".tmp"
    df.to_parquet(tmp)
    os.replace(tmp, LOG_PATH)


def _started(start_time_utc) -> bool:
    try:
        st = pd.Timestamp(start_time_utc)
        if st.tzinfo is None:
            st = st.tz_localize("UTC")
        return datetime.now(timezone.utc) >= st
    except Exception:
        return False


def _decimal(am) -> float | None:
    try:
        am = float(am)
    except (TypeError, ValueError):
        return None
    if am == 0:
        return None
    return 1 + am / 100 if am > 0 else 1 + 100 / abs(am)


def _fetch_fixtures(date: str) -> list[dict]:
    """Unplayed singles fixtures across all scan leagues, main tours first."""
    headers = {"X-Api-Key": OPTICODDS_API_KEY}
    end = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    out = []
    for league in SCAN_LEAGUES:
        try:
            resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures/active", params={
                "league": league, "start_date_after": date, "start_date_before": end,
            }, headers=headers, timeout=15)
            resp.raise_for_status()
            fixtures = resp.json().get("data", [])
        except requests.exceptions.RequestException:
            continue
        for f in fixtures:
            home, away = f.get("home_competitors") or [], f.get("away_competitors") or []
            if f.get("status") != "unplayed" or len(home) != 1 or len(away) != 1:
                continue
            out.append({
                "fixture_id": f.get("id"), "league": league,
                "tournament": (f.get("tournament") or {}).get("name"),
                "player_1": home[0].get("name"), "player_2": away[0].get("name"),
                "start_time_utc": f.get("start_date"),
            })
        if len(out) >= MAX_FIXTURES:
            break
    return out[:MAX_FIXTURES]


def _fetch_prices(fixture_ids: list[str]) -> dict:
    """{fixture_id: {book: {player_name: american_price}}} for moneyline across all
    sharp + bettable books. The odds endpoint caps at 5 sportsbooks per request, so
    books are chunked; results merge per fixture."""
    headers = {"X-Api-Key": OPTICODDS_API_KEY}
    all_books = SHARP_BOOKS + BETTABLE_BOOKS
    book_chunks = [all_books[i:i + 5] for i in range(0, len(all_books), 5)]
    prices: dict = {}
    for i in range(0, len(fixture_ids), FIXTURE_BATCH):
        batch = fixture_ids[i:i + FIXTURE_BATCH]
        for books in book_chunks:
            try:
                resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures/odds", params={
                    "league": SCAN_LEAGUES, "market": "moneyline", "sportsbook": books,
                    "is_main": "true", "fixture_id": batch,
                }, headers=headers, timeout=25)
                resp.raise_for_status()
                fixtures = resp.json().get("data", [])
            except requests.exceptions.RequestException:
                continue
            for fixture in fixtures:
                by_book = prices.setdefault(fixture.get("id"), {})
                for o in fixture.get("odds") or []:
                    if o.get("market_id") != "moneyline":
                        continue
                    by_book.setdefault(o.get("sportsbook"), {})[o.get("name")] = o.get("price")
    return prices


def _fair_prob_p1(by_book: dict, p1: str, p2: str) -> tuple[float | None, int]:
    """Average de-vigged P(player_1) across sharp books quoting both sides."""
    probs = []
    for book in SHARP_BOOKS:
        q = by_book.get(book, {})
        d1, d2 = _decimal(q.get(p1)), _decimal(q.get(p2))
        if d1 is None or d2 is None:
            continue
        i1, i2 = 1 / d1, 1 / d2
        probs.append(i1 / (i1 + i2))
    return (sum(probs) / len(probs) if probs else None), len(probs)


def scan(date: str = None, force_refresh: bool = False) -> dict:
    """Run (or serve cached) scan for the date; logs flags and updates close_fair."""
    date = date or todays_date_et()
    cached = _SCAN_CACHE.get(date)
    if not force_refresh and cached and (time.time() - cached[0]) < _SCAN_CACHE_TTL:
        return cached[1]
    if not OPTICODDS_API_KEY:
        return {"date": date, "edges": [], "scanned": 0, "priced": 0}

    fixtures = _fetch_fixtures(date)
    prices = _fetch_prices([f["fixture_id"] for f in fixtures])

    edges = []
    fair_by_fixture = {}
    priced = 0
    for f in fixtures:
        by_book = prices.get(f["fixture_id"])
        if not by_book:
            continue
        fair1, n_sharp = _fair_prob_p1(by_book, f["player_1"], f["player_2"])
        if fair1 is None:
            continue
        priced += 1
        fair_by_fixture[f["fixture_id"]] = fair1
        for side, player, fair in ((1, f["player_1"], fair1), (2, f["player_2"], 1 - fair1)):
            if fair < MIN_FAIR_PROB:
                continue
            best = None
            for book in BETTABLE_BOOKS:
                d = _decimal(by_book.get(book, {}).get(player))
                if d is None:
                    continue
                implied = 1 / d
                if best is None or implied < best["implied"]:
                    best = {"book": book, "price": by_book[book][player], "decimal": round(d, 3),
                            "implied": implied}
            if best is None:
                continue
            edge = fair - best["implied"]
            if edge >= MIN_EDGE:
                edges.append({
                    **{k: f[k] for k in ("fixture_id", "league", "tournament", "player_1",
                                         "player_2", "start_time_utc")},
                    "side": side, "side_player": player, "book": best["book"],
                    "price": best["price"], "decimal": best["decimal"],
                    "implied": round(best["implied"], 4), "fair_prob": round(fair, 4),
                    "edge": round(edge, 4), "n_sharp": n_sharp,
                })
    edges.sort(key=lambda e: -e["edge"])
    _log_edges(edges, date)
    _update_close_fair(fair_by_fixture)
    edges = _attach_line_moves(edges)
    result = {"date": date, "edges": edges, "scanned": len(fixtures), "priced": priced,
              "min_edge": MIN_EDGE, "sharp_books": SHARP_BOOKS, "leagues": SCAN_LEAGUES}
    _SCAN_CACHE[date] = (time.time(), result)
    return result


def _log_edges(edges: list[dict], date: str):
    """Upsert flags: a (fixture, side) row updates until first serve, frozen after.
    first_seen_* survives every update -- that is the opening-line capture."""
    if not edges:
        return
    log = _read_log()
    now = datetime.now(timezone.utc).isoformat()
    frozen = set()
    if not log.empty:
        started_mask = (log["settled"] == True) | log["start_time_utc"].apply(_started)  # noqa: E712
        frozen = set(zip(log.loc[started_mask, "fixture_id"], log.loc[started_mask, "side"]))
    existing_first = {}
    if not log.empty:
        for _, r in log.iterrows():
            existing_first[(r["fixture_id"], r["side"])] = (
                r["first_seen_at"], r["first_seen_price"], r["first_seen_fair"])
    rows = []
    for e in edges:
        key = (e["fixture_id"], e["side"])
        if key in frozen:
            continue
        fs = existing_first.get(key, (now, e["price"], e["fair_prob"]))
        rows.append({
            "date": date, "fixture_id": e["fixture_id"], "league": e["league"],
            "tournament": e["tournament"], "player_1": e["player_1"], "player_2": e["player_2"],
            "start_time_utc": e["start_time_utc"], "side": e["side"],
            "side_player": e["side_player"], "book": e["book"], "price": e["price"],
            "decimal": e["decimal"], "implied": e["implied"], "fair_prob": e["fair_prob"],
            "edge": e["edge"], "n_sharp": e["n_sharp"], "first_seen_at": fs[0],
            "first_seen_price": fs[1], "first_seen_fair": fs[2], "close_fair": e["fair_prob"],
            "logged_at": now, "settled": False, "side_won": None,
        })
    if not rows:
        return
    new = pd.DataFrame(rows)
    if log.empty:
        _write_log(new)
        return
    new_keys = set(zip(new["fixture_id"], new["side"]))
    keep = log[[k not in new_keys for k in zip(log["fixture_id"], log["side"])]]
    _write_log(pd.concat([keep, new], ignore_index=True))


def _update_close_fair(fair_by_fixture: dict):
    """Refresh close_fair on every unfrozen logged flag whose fixture was re-priced this
    scan -- the last write before first serve is the closing sharp fair, the CLV anchor.
    (A flag whose edge later drops below MIN_EDGE stops upserting via _log_edges, but its
    close_fair keeps tracking here.)"""
    if not fair_by_fixture:
        return
    log = _read_log()
    if log.empty:
        return
    open_mask = (log["settled"] != True) & ~log["start_time_utc"].apply(_started)  # noqa: E712
    changed = False
    for i in log.index[open_mask]:
        fid, side = log.at[i, "fixture_id"], log.at[i, "side"]
        if fid in fair_by_fixture:
            fair1 = fair_by_fixture[fid]
            log.at[i, "close_fair"] = round(fair1 if side == 1 else 1 - fair1, 4)
            changed = True
    if changed:
        _write_log(log)


def _attach_line_moves(edges: list[dict]) -> list[dict]:
    log = _read_log()
    if log.empty:
        return edges
    ix = {(r["fixture_id"], r["side"]): r for _, r in log.iterrows()}
    out = []
    for e in edges:
        r = ix.get((e["fixture_id"], e["side"]))
        if r is not None and pd.notna(r["first_seen_fair"]):
            e = {**e, "first_seen_fair": float(r["first_seen_fair"]),
                 "first_seen_price": r["first_seen_price"], "first_seen_at": r["first_seen_at"],
                 "fair_move": round(e["fair_prob"] - float(r["first_seen_fair"]), 4)}
        out.append(e)
    return out


def settle(max_dates: int = 10):
    """Grade frozen flags from completed fixtures (sets won, home = player_1)."""
    if not OPTICODDS_API_KEY:
        return
    log = _read_log()
    if log.empty:
        return
    todo = log[(log["settled"] != True) & log["start_time_utc"].apply(_started)]  # noqa: E712
    if todo.empty:
        return
    changed = False
    for date in sorted(todo["date"].unique())[-max_dates:]:
        try:
            end = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            resp = requests.get(f"{OPTICODDS_BASE_URL}/fixtures", params={
                "league": SCAN_LEAGUES, "start_date_after": date, "start_date_before": end,
            }, headers={"X-Api-Key": OPTICODDS_API_KEY}, timeout=25)
            resp.raise_for_status()
            fixtures = resp.json().get("data", [])
        except requests.exceptions.RequestException:
            continue
        for f in fixtures:
            if f.get("status") != "completed":
                continue
            scores = ((f.get("result") or {}).get("scores") or {})
            h = ((scores.get("home") or {}).get("total"))
            a = ((scores.get("away") or {}).get("total"))
            if h is None or a is None or h == a:
                continue
            m = (log["fixture_id"] == f.get("id")) & (log["settled"] != True)  # noqa: E712
            if m.any():
                p1_won = bool(h > a)
                for i in log.index[m]:
                    log.at[i, "side_won"] = p1_won if log.at[i, "side"] == 1 else not p1_won
                    log.at[i, "settled"] = True
                changed = True
    if changed:
        _write_log(log)


def get_scanner_track_record() -> dict:
    """Forward record of every frozen flag: flat-1u ROI at the flagged price, win rate vs
    the fair prob the flags promised, and CLV vs the closing sharp fair -- overall and by
    league and book. UNPROVEN until CHECKPOINT_N settled."""
    log = _read_log()
    out = {"total_flagged": int(len(log)), "settled": 0, "checkpoint_n": CHECKPOINT_N,
           "min_edge": MIN_EDGE, "since": str(log["date"].min()) if len(log) else None}
    if log.empty:
        return out
    s = log[(log["settled"] == True) & log["side_won"].notna()].copy()  # noqa: E712
    out["settled"] = int(len(s))
    out["pending"] = int((log["settled"] != True).sum())  # noqa: E712
    if s.empty:
        return out
    s["flat"] = [(d - 1.0) if w else -1.0 for d, w in zip(s["decimal"].astype(float), s["side_won"])]
    s["clv"] = s["close_fair"].astype(float) - s["implied"].astype(float)

    def block(g):
        return {"n": int(len(g)), "wins": int(g["side_won"].sum()),
                "win_rate": round(float(g["side_won"].mean()), 4),
                "avg_fair_promised": round(float(g["fair_prob"].astype(float).mean()), 4),
                "flat_roi_pct": round(100 * float(g["flat"].mean()), 2),
                "avg_edge_pt": round(100 * float(g["edge"].astype(float).mean()), 2),
                "avg_clv_pt": round(100 * float(g["clv"].mean()), 2),
                "beat_close_pct": round(100 * float((g["clv"] > 0).mean()), 1)}

    out["overall"] = block(s)
    out["by_league"] = {lg: block(g) for lg, g in s.groupby("league")}
    out["by_book"] = {bk: block(g) for bk, g in s.groupby("book")}
    out["proven"] = bool(len(s) >= CHECKPOINT_N)
    return out


if __name__ == "__main__":
    res = scan(force_refresh=True)
    print(f"scanned {res['scanned']} fixtures, {res['priced']} with sharp fair prices, "
          f"{len(res['edges'])} flags >= {MIN_EDGE:.0%}")
    print(json.dumps(res["edges"][:10], indent=1, default=str))
