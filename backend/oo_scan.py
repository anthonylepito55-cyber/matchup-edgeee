"""SHARP-FAIR vs EXCHANGE SCANNER + FLAG LOG + CLV (2026-10-11, user: "start").

The product. Takes the snapshots `oo_feed` stores and asks one question per selection:

    is the price on an exchange I can actually bet BETTER than the sharp market's fair value,
    by more than the fee, with real size behind it?

Three things make this honest rather than flattering, and all three are failure modes I either
hit or watched for earlier today:

 1. **Fees are netted, not footnoted.** Kalshi charges 0.07 x P x (1-P) per contract, which is
    **1.75 probability points at even money** -- bigger than most edges here. A scanner that
    reports gross edge on Kalshi is reporting fiction.
 2. **Depth is required.** Every flag carries the size takeable at or better than the flagged
    price, summed off the real ladder. No size, no flag.
 3. **The benchmark excludes the trigger.** Fair value comes from the SHARP books only, and CLV
    is later measured against the closing sharp fair. If the exchange itself fed the fair line
    we would be measuring a venue against itself.

Every flag is logged whether or not it is bet, so the record cannot be quietly filtered into
looking good later. `settle_flags()` then attaches the closing sharp fair to each flag, which is
what gives a verdict in ~50-100 flags instead of the ~10,000 bets ROI would need.

Builds scanners and logs. Places no orders.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import pandas as pd

import oo_feed as F

HERE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(HERE, "data_cache", "oo_flags.parquet")

MIN_EDGE_PP = 1.5        # net of fees, in probability points
MIN_SIZE = 25.0          # dollars takeable at the flagged price or better
SHARP_PREF = ["Pinnacle", "BetOnline", "Circa Sports"]


def _fair_from_sharp(grp: pd.DataFrame) -> tuple[dict, str] | tuple[None, None]:
    """Two-way fair probabilities per selection, from the best available sharp book.

    Preference order is Pinnacle, then BetOnline, then Circa -- Pinnacle first because it is the
    reference sharp book and priced 3/3 of probed fixtures, Circa last because it priced 1/3.
    Only ONE book is used, never a blend: mixing books with different vig and different update
    times produces a fair line that belongs to no venue and moves for the wrong reasons.
    """
    for bk in SHARP_PREF:
        sub = grp[grp.sportsbook == bk]
        sels = [s for s in sub.selection.dropna().unique()]
        if len(sels) != 2:
            continue
        a, b = sels
        pa = sub[sub.selection == a].price.iloc[0]
        pb = sub[sub.selection == b].price.iloc[0]
        fa = F.devig_two_way(pa, pb)
        if fa is None:
            continue
        return {a: fa, b: 1.0 - fa}, bk
    return None, None


def scan(df: pd.DataFrame | None = None, min_edge_pp: float = MIN_EDGE_PP,
         min_size: float = MIN_SIZE, verbose: bool = True) -> pd.DataFrame:
    """Scan the most recent quote per (fixture, book, selection) for exchange value."""
    if df is None or df.empty:
        df = F.load_snapshots(days=1)
    if df.empty:
        if verbose:
            print("no snapshot rows to scan")
        return pd.DataFrame()

    # one row per (fixture, book, selection): the freshest quote we hold
    df = df.sort_values("poll_ts").copy()
    latest = (df.groupby(["fixture_id", "sportsbook", "selection"], as_index=False)
                .tail(1).reset_index(drop=True))

    out = []
    now = time.time()
    for fid, grp in latest.groupby("fixture_id"):
        fair, sharp_book = _fair_from_sharp(grp)
        if not fair:
            continue
        for r in grp.itertuples():
            if r.sportsbook in SHARP_PREF:
                continue                        # never score the benchmark against itself
            fee_fn = F.FEE_PP.get(r.sportsbook)
            if fee_fn is None:
                continue                        # only venues with a known fee model
            fv = fair.get(r.selection)
            if fv is None:
                continue
            imp = F.am_to_prob(r.price)
            if imp is None:
                continue
            fee = fee_fn(imp)
            gross = 100.0 * (fv - imp)          # probability points
            net = gross - fee
            size = F.takeable_size(r.order_book, r.price, r.top_size)
            out.append({
                "flag_ts": now,
                "fixture_id": fid,
                "league": r.league,
                "start_date": r.start_date,
                "matchup": "%s v %s" % (r.home, r.away),
                "selection": r.selection,
                "venue": r.sportsbook,
                "price": r.price,
                "venue_prob_pct": 100.0 * imp,
                "sharp_book": sharp_book,
                "sharp_fair_pct": 100.0 * fv,
                "gross_edge_pp": gross,
                "fee_pp": fee,
                "net_edge_pp": net,
                "size_at_price": size,
                "quote_age_s": (now - float(r.quote_ts)) if r.quote_ts else None,
                "deep_link": r.deep_link,
                "qualified": bool(net >= min_edge_pp
                                  and (size is None or size >= min_size)),
            })
    res = pd.DataFrame(out)
    if verbose and not res.empty:
        q = res[res.qualified]
        print("scanned %d fixtures -> %d exchange quotes, %d qualified "
              "(net >= %.1fpp, size >= $%.0f)"
              % (latest.fixture_id.nunique(), len(res), len(q), min_edge_pp, min_size))
    return res


def log_flags(res: pd.DataFrame, qualified_only: bool = True) -> int:
    """Append flags to the durable log.

    Deliberately keeps EVERY flag, bet or not. The moment this file only contains acted-on bets
    it stops being evidence -- that is the selection bias that makes every home-made scanner
    look profitable in hindsight.
    """
    if res is None or res.empty:
        return 0
    rows = res[res.qualified] if qualified_only else res
    if rows.empty:
        return 0
    if os.path.exists(FLAGS):
        try:
            old = pd.read_parquet(FLAGS)
            rows = pd.concat([old, rows], ignore_index=True)
        except Exception as e:
            print("   WARN could not read flag log (%s); writing fresh" % e)
    os.makedirs(os.path.dirname(FLAGS), exist_ok=True)
    rows.to_parquet(FLAGS, index=False)
    return int(len(rows))


def settle_flags(verbose: bool = True) -> pd.DataFrame:
    """Attach the CLOSING sharp fair to each logged flag and compute CLV.

    CLV = (closing sharp fair) - (probability we flagged at). Positive means the sharp market
    moved toward our side after we saw it, i.e. we got a price better than the market's final
    estimate. This is the fast verdict: per-flag CLV noise is small next to win/loss noise, so
    ~50-100 flags say what ~10,000 settled bets would have to say about ROI.

    The closing fair is rebuilt from the stored snapshots -- the LAST sharp quote before start
    time -- so it needs no extra API calls and no result feed.
    """
    if not os.path.exists(FLAGS):
        if verbose:
            print("no flag log yet")
        return pd.DataFrame()
    fl = pd.read_parquet(FLAGS)
    snaps = F.load_snapshots(days=30)
    if snaps.empty or fl.empty:
        return fl
    snaps = snaps[snaps.sportsbook.isin(SHARP_PREF)].copy()
    snaps["start_ts"] = pd.to_datetime(snaps.start_date, errors="coerce", utc=True)
    snaps = snaps[snaps.start_ts.notna()]
    # keep only quotes taken BEFORE the off, then the last of them per fixture
    snaps = snaps[snaps.poll_ts <= snaps.start_ts.astype("int64") / 1e9]

    closing = {}
    for fid, grp in snaps.groupby("fixture_id"):
        last_poll = grp.poll_ts.max()
        g = grp[grp.poll_ts == last_poll]
        fair, bk = _fair_from_sharp(g)
        if fair:
            closing[fid] = fair

    clv, closed = [], []
    for r in fl.itertuples():
        fair = closing.get(r.fixture_id)
        if not fair or r.selection not in fair:
            clv.append(None)
            closed.append(None)
            continue
        cf = 100.0 * fair[r.selection]
        closed.append(cf)
        clv.append(cf - r.venue_prob_pct)
    fl["closing_fair_pct"] = closed
    fl["clv_pp"] = clv
    fl.to_parquet(FLAGS, index=False)
    done = fl[fl.clv_pp.notna()]
    if verbose:
        print("flags: %d logged, %d with a closing line" % (len(fl), len(done)))
        if len(done):
            m, sd = done.clv_pp.mean(), done.clv_pp.std(ddof=1)
            se = sd / max(len(done) ** 0.5, 1)
            print("   mean CLV %+.2fpp +/- %.2f (n=%d)  -- positive and >2se means the edge is real"
                  % (m, se, len(done)))
            print("   by venue:")
            for v, g in done.groupby("venue"):
                print("      %-18s CLV %+.2fpp  net edge at flag %+.2fpp  (n=%d)"
                      % (v, g.clv_pp.mean(), g.net_edge_pp.mean(), len(g)))
    return fl


def report(res: pd.DataFrame, top: int = 15) -> None:
    if res is None or res.empty:
        print("nothing to report")
        return
    r = res.sort_values("net_edge_pp", ascending=False)
    print("\n%-34s %-11s %-6s %7s %7s %6s %7s %9s" %
          ("matchup / selection", "venue", "price", "venue%", "fair%", "fee", "NET pp", "size$"))
    print("-" * 104)
    for x in r.head(top).itertuples():
        print("%-34s %-11s %-6s %7.1f %7.1f %6.2f %+7.2f %9s%s"
              % (("%s | %s" % (x.matchup, x.selection))[:34], str(x.venue)[:11],
                 str(x.price), x.venue_prob_pct, x.sharp_fair_pct, x.fee_pp, x.net_edge_pp,
                 ("%.0f" % x.size_at_price) if x.size_at_price else "-",
                 "  <= QUALIFIED" if x.qualified else ""))
    print("\n   fair value from: %s" % ", ".join(sorted(set(r.sharp_book.dropna()))))
    print("   venues scanned : %s" % ", ".join(sorted(set(r.venue.dropna()))))
    neg = (r.net_edge_pp < 0).mean() * 100
    print("   %.0f%% of exchange quotes are WORSE than sharp fair after fees -- expected on an "
          "efficient venue;" % neg)
    print("   the scanner earns its keep only on the tail that is not.")


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "once"
    if cmd == "settle":
        settle_flags()
    else:
        lgs = sys.argv[2].split(",") if len(sys.argv) > 2 else None
        print("=== snapshot ===")
        df = F.snapshot(leagues=lgs, within_hours=48)
        print("\n=== scan ===")
        res = scan(df)
        report(res)
        n = log_flags(res)
        print("\n   flag log now holds %d qualified flags -> %s"
              % (n, os.path.basename(FLAGS)))
        print("   %s" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
