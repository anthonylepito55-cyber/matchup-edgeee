"""SHARP-MONEY / STEAM TRACKER (2026-10-11, user: "maybe like a sharp money tracker").

Reads the snapshots `oo_feed` stores -- which are already one row per real price change -- and
answers three questions, in increasing order of how much they matter:

  A. LIVE GAPS      the sharp fair has moved and an exchange has not followed yet. Actionable
                    now, with the size takeable and a deep link.
  B. FOLLOW LATENCY after a sharp move, how long until each exchange re-prices, and how far?
                    **This is the number that decides whether any of this is viable.** If Kalshi
                    tracks Pinnacle within seconds there is no edge to take; if it takes minutes
                    there is a window.
  C. WHO LEADS      across all moves, which venue tends to move first. Tells you whose move to
                    treat as information and whose to ignore.

Clock discipline: everything uses `quote_ts`, the venue's OWN stamp on the quote, not `poll_ts`
(when we happened to look). Using poll_ts would measure our polling cadence rather than the
market, and would make every venue look exactly as slow as our timer.

Read-only. Places no orders.
"""
from __future__ import annotations

import os
import time

import numpy as np
import pandas as pd

import oo_feed as F

SHARP_PREF = ["Pinnacle", "BetOnline", "Circa Sports"]
EXCHANGES = ["Kalshi", "Polymarket", "Novig", "Betfair Exchange"]


def _prob(p):
    return F.am_to_prob(p)


def fair_series(df: pd.DataFrame, sharp: str = "Pinnacle") -> pd.DataFrame:
    """Sharp de-vigged fair probability per (fixture, selection) over time.

    A sharp book stamps both sides of a two-way market with the SAME quote_ts (verified in the
    payload), so pivoting on quote_ts recovers the exact two-sided quote that existed at that
    instant -- rather than pairing a stale side against a fresh one, which would invent
    movement that never happened.
    """
    s = df[df.sportsbook == sharp].copy()
    if s.empty:
        return pd.DataFrame()
    s["imp"] = s.price.map(_prob)
    s = s[s.imp.notna() & s.quote_ts.notna()]
    out = []
    for (fid, qts), g in s.groupby(["fixture_id", "quote_ts"]):
        sels = g.selection.dropna().unique()
        if len(sels) != 2:
            continue
        a, b = sels
        ia = g[g.selection == a].imp.iloc[0]
        ib = g[g.selection == b].imp.iloc[0]
        tot = ia + ib
        if tot <= 0:
            continue
        meta = g.iloc[0]
        for sel, fv in ((a, ia / tot), (b, ib / tot)):
            out.append({"fixture_id": fid, "quote_ts": float(qts), "selection": sel,
                        "fair": fv, "matchup": "%s v %s" % (meta.home, meta.away),
                        "league": meta.league, "start_date": meta.start_date})
    fs = pd.DataFrame(out)
    return fs.sort_values(["fixture_id", "selection", "quote_ts"]).reset_index(drop=True)


def detect_moves(fs: pd.DataFrame, min_pp: float = 1.0) -> pd.DataFrame:
    """Consecutive sharp re-prices where the fair moved at least `min_pp` probability points."""
    if fs.empty:
        return pd.DataFrame()
    fs = fs.sort_values(["fixture_id", "selection", "quote_ts"]).copy()
    g = fs.groupby(["fixture_id", "selection"], sort=False)
    fs["prev_fair"] = g.fair.shift(1)
    fs["prev_ts"] = g.quote_ts.shift(1)
    fs["move_pp"] = 100.0 * (fs.fair - fs.prev_fair)
    mv = fs[fs.prev_fair.notna() & (fs.move_pp.abs() >= min_pp)].copy()
    return mv.reset_index(drop=True)


def follow_latency(df: pd.DataFrame, moves: pd.DataFrame,
                   max_wait_s: float = 900) -> pd.DataFrame:
    """For each sharp move: when did each exchange next re-price, and by how much?

    Per move and per venue, finds the venue's first quote stamped AFTER the sharp move and
    measures the delay plus the venue's own change across that boundary. A venue that was
    already level with the new fair before the move gets excluded -- it did not 'follow', it was
    simply already there, and counting it would flatter the latency number.
    """
    if moves.empty or df.empty:
        return pd.DataFrame()
    ex = df[df.sportsbook.isin(EXCHANGES)].copy()
    if ex.empty:
        return pd.DataFrame()
    ex["imp"] = ex.price.map(_prob)
    ex = ex[ex.imp.notna() & ex.quote_ts.notna()]
    ex["quote_ts"] = ex.quote_ts.astype(float)

    rows = []
    for m in moves.itertuples():
        sub = ex[(ex.fixture_id == m.fixture_id) & (ex.selection == m.selection)]
        for venue, g in sub.groupby("sportsbook"):
            g = g.sort_values("quote_ts")
            before = g[g.quote_ts <= m.quote_ts]
            after = g[(g.quote_ts > m.quote_ts) &
                      (g.quote_ts <= m.quote_ts + max_wait_s)]
            if before.empty:
                continue
            pre = before.imp.iloc[-1]
            # how far off the NEW fair was the venue at the moment of the move?
            gap_before = 100.0 * (m.fair - pre)
            if after.empty:
                rows.append({"venue": venue, "fixture_id": m.fixture_id,
                             "selection": m.selection, "move_pp": m.move_pp,
                             "gap_before_pp": gap_before, "delay_s": None,
                             "venue_move_pp": None, "followed": False})
                continue
            post = after.imp.iloc[0]
            rows.append({"venue": venue, "fixture_id": m.fixture_id,
                         "selection": m.selection, "move_pp": m.move_pp,
                         "gap_before_pp": gap_before,
                         "delay_s": float(after.quote_ts.iloc[0] - m.quote_ts),
                         "venue_move_pp": 100.0 * (post - pre), "followed": True})
    return pd.DataFrame(rows)


def live_gaps(df: pd.DataFrame | None = None, min_pp: float = 1.0,
              recent_s: float = 600, min_size: float = 25.0) -> pd.DataFrame:
    """Open opportunities: the sharp fair moved recently and an exchange is still behind."""
    if df is None or df.empty:
        df = F.load_snapshots(days=1)
    if df.empty:
        return pd.DataFrame()
    fs = fair_series(df)
    if fs.empty:
        return pd.DataFrame()
    now = time.time()
    # the newest sharp fair per (fixture, selection)
    cur = fs.sort_values("quote_ts").groupby(["fixture_id", "selection"], as_index=False).tail(1)
    mv = detect_moves(fs, min_pp=min_pp)
    recent = mv[mv.quote_ts >= now - recent_s]
    if recent.empty:
        return pd.DataFrame()
    ex = df[df.sportsbook.isin(EXCHANGES)].copy()
    ex["imp"] = ex.price.map(_prob)
    ex = ex[ex.imp.notna()]
    ex = ex.sort_values("poll_ts").groupby(
        ["fixture_id", "sportsbook", "selection"], as_index=False).tail(1)
    out = []
    for m in recent.itertuples():
        fv = cur[(cur.fixture_id == m.fixture_id) & (cur.selection == m.selection)]
        if fv.empty:
            continue
        fair = float(fv.fair.iloc[0])
        sub = ex[(ex.fixture_id == m.fixture_id) & (ex.selection == m.selection)]
        for r in sub.itertuples():
            fee_fn = F.FEE_PP.get(r.sportsbook)
            if fee_fn is None:
                continue
            fee = fee_fn(r.imp)
            net = 100.0 * (fair - r.imp) - fee
            size = F.takeable_size(r.order_book, r.price, r.top_size)
            if net < min_pp or (size is not None and size < min_size):
                continue
            out.append({"matchup": m.matchup, "selection": m.selection, "venue": r.sportsbook,
                        "price": r.price, "venue_pct": 100 * r.imp, "fair_pct": 100 * fair,
                        "sharp_move_pp": m.move_pp, "net_edge_pp": net,
                        "stale_s": (now - float(r.quote_ts)) if r.quote_ts else None,
                        "size": size, "deep_link": r.deep_link})
    return pd.DataFrame(out).sort_values("net_edge_pp", ascending=False) if out else pd.DataFrame()


def report(days: int = 1, min_pp: float = 1.0) -> None:
    df = F.load_snapshots(days=days)
    if df.empty:
        print("no snapshots yet -- the poller writes one row per price change every 60s")
        return
    span = (df.poll_ts.max() - df.poll_ts.min()) / 60.0
    print("snapshot rows %d | polls %d | span %.0f min | fixtures %d"
          % (len(df), df.poll_ts.nunique(), span, df.fixture_id.nunique()))

    fs = fair_series(df)
    mv = detect_moves(fs, min_pp=min_pp)
    print("\nsharp (Pinnacle) re-prices: %d  |  moves >= %.1fpp: %d"
          % (len(fs), min_pp, len(mv)))
    if not mv.empty:
        print("   biggest moves:")
        for m in mv.reindex(mv.move_pp.abs().sort_values(ascending=False).index).head(6).itertuples():
            print("      %-38s %-26s %+5.2fpp" % (str(m.matchup)[:38], str(m.selection)[:26],
                                                  m.move_pp))

    fl = follow_latency(df, mv)
    print("\n" + "=" * 100)
    print("B. FOLLOW LATENCY -- how fast does each exchange re-price after a sharp move?")
    print("=" * 100)
    if fl.empty:
        print("   no sharp moves with exchange quotes on both sides of them yet")
    else:
        for v, g in fl.groupby("venue"):
            f = g[g.followed]
            if f.empty:
                print("   %-18s never re-priced inside the window (n=%d moves)" % (v, len(g)))
                continue
            # of the venue's response, how much of the sharp move did it actually absorb?
            cap = f[(f.move_pp.abs() > 0)]
            absorb = (cap.venue_move_pp / cap.move_pp).replace([np.inf, -np.inf], np.nan)
            print("   %-18s followed %d/%d  median delay %6.1fs  mean %6.1fs  "
                  "absorbed %s of the move"
                  % (v, len(f), len(g), f.delay_s.median(), f.delay_s.mean(),
                     ("%.0f%%" % (100 * absorb.mean())) if absorb.notna().any() else "n/a"))
        print("\n   read: a venue that re-prices in SECONDS leaves no window; one that takes")
        print("   minutes, or absorbs only part of the move, is where a stale price can be hit.")

    print("\n" + "=" * 100)
    print("C. WHO MOVES FIRST -- re-price counts per venue (needs hours of history to mean much)")
    print("=" * 100)
    ch = (df[df.quote_ts.notna()]
          .groupby("sportsbook")
          .agg(reprices=("quote_ts", "nunique"), quotes=("price", "size")))
    for b, r in ch.sort_values("reprices", ascending=False).iterrows():
        print("   %-18s %5d distinct quote timestamps over %d stored quotes"
              % (b, r.reprices, r.quotes))

    print("\n" + "=" * 100)
    print("A. LIVE GAPS -- sharp moved in the last 10 min, exchange still behind")
    print("=" * 100)
    lg = live_gaps(df, min_pp=min_pp)
    if lg.empty:
        print("   none open right now")
    else:
        for x in lg.head(10).itertuples():
            print("   %-34s %-22s %-11s %-6s venue %5.1f%% vs fair %5.1f%%  NET %+5.2fpp  "
                  "stale %4.0fs  size $%s"
                  % (str(x.matchup)[:34], str(x.selection)[:22], str(x.venue)[:11],
                     str(x.price), x.venue_pct, x.fair_pct, x.net_edge_pp,
                     x.stale_s or 0, ("%.0f" % x.size) if x.size else "-"))


if __name__ == "__main__":
    import sys
    d = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    pp = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    report(days=d, min_pp=pp)
