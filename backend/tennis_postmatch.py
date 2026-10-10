"""POST-MATCH STAT CAPTURE (2026-10-10, user: "How do we start logging unforced errors a game").

Until now the log kept only `settled`, `p1_won` and `score` once a match finished. `ue_set5_diff_p1`
is the PRE-match profile diff, not what happened in the game, so we had no record of the actual
errors in any match we bet. This fills that in, nightly, from two sources with different reach:

  TIER 1 -- REAL unforced errors, from the Match Charting Project (tennis_ue):
      ue_p1 / ue_p2        total unforced errors
      ue_fh_p1 / ue_fh_p2  forehand share of them
      win_p1 / win_p2      winners (so winners-per-UE is available)
      ue_sets              sets played, for the per-set figure
    Reach is small and always will be: charting is volunteer work, lags ~5 days, and covered
    1.8% of our logged matches when measured on 2026-10-10 (ATP 5.6%, WTA 1.6%, challenger and
    ITF 0%). Logging it anyway means the number grows on its own and is never recomputed.

  TIER 2 -- DOUBLE FAULTS and the serve line, from the TennisRatio archive:
      df_p1 / df_p2        double faults -- the ONLY unforced error recorded for every match
      sgames_p1/_p2        service games played, so DF per service game is derivable
      aces_p1 / aces_p2
    Reach is ~100% of matches INCLUDING ITF and challengers, but the archive lags ~10 days.

Both tiers are retried every night until filled or the row is older than MAX_AGE days, because
both sources arrive days after the match. Values are never overwritten once set, and a row that
is already filled is skipped, so this is cheap to run repeatedly.

Run as a subprocess from daily_retrain (step 0.9) so its archive read is handed back; never run
it under sudo -- that leaves the parquet root-owned and the service (ec2-user) cannot write it.
"""
import os
import sys

import numpy as np
import pandas as pd

import tennis_log
import tennis_ue as U

MAX_AGE = 35          # stop retrying a row this many days after it was played
ARCH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "data_cache", "tennisratio", "all_match_logs.parquet")
COLS = ["ue_p1", "ue_p2", "ue_fh_p1", "ue_fh_p2", "win_p1", "win_p2", "ue_sets",
        "df_p1", "df_p2", "sgames_p1", "sgames_p2", "aces_p1", "aces_p2", "pm_src"]


def _frac_played(s):
    """'13/15' -> games played (15)."""
    out = np.full(len(s), np.nan)
    for i, v in enumerate(s.astype(str).values):
        if "/" in v:
            a, _, b = v.partition("/")
            if b.strip().isdigit():
                out[i] = int(b)
    return out


def _mcp_index():
    """(date, player key, opponent key) -> that player's charted line for the match."""
    C = U.load()
    idx = {}
    for r in C.itertuples():
        idx[(r.date.normalize(), r.key, r.okey)] = r
    return idx


def _archive_index():
    """(date, player key, opponent key) -> double faults / service games / aces."""
    if not os.path.exists(ARCH):
        return {}
    A = pd.read_parquet(ARCH, columns=["date", "player_slug", "rival_slugname",
                                       "double_faults", "service_games_won", "aces"])
    A["d"] = pd.to_datetime(A["date"]).dt.normalize()
    A["k"] = A["player_slug"].astype(str).map(U.norm)
    A["ok"] = A["rival_slugname"].astype(str).map(U.norm)
    A["sg"] = _frac_played(A["service_games_won"])
    idx = {}
    for d, k, ok, df, sg, ac in zip(A.d, A.k, A.ok, A.double_faults, A.sg, A.aces):
        idx[(d, k, ok)] = (df, sg, ac)
    return idx


def _lookup(idx, d, a, b):
    """Try the match date and +/-1 day -- our slate date and the archive's match date can
    differ by one when a match runs past midnight UTC."""
    for off in (0, -1, 1):
        hit = idx.get((d + pd.Timedelta(days=off), a, b))
        if hit is not None:
            return hit
    return None


def backfill(max_age_days=MAX_AGE, verbose=True):
    log = tennis_log._read_log()
    if log.empty:
        return {"rows": 0}
    for c in COLS:
        if c not in log.columns:
            log[c] = None
    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    dates = pd.to_datetime(log["date"].astype(str).str[:10], errors="coerce")
    # settled, recent enough to still be arriving, and not already complete
    need_ue = log["ue_p1"].isna()
    need_df = log["df_p1"].isna()
    todo = log[(log["settled"] == True) & (dates >= today - pd.Timedelta(days=max_age_days))  # noqa: E712
               & (need_ue | need_df)]
    if todo.empty:
        if verbose:
            print("[postmatch] nothing to fill")
        return {"rows": 0}
    mcp, arch = _mcp_index(), _archive_index()
    n_ue = n_df = 0
    for i, r in todo.iterrows():
        d = pd.Timestamp(str(r["date"])[:10])
        k1, k2 = U.norm(r["player_1"]), U.norm(r["player_2"])
        if pd.isna(r["ue_p1"]):
            a, b = _lookup(mcp, d, k1, k2), _lookup(mcp, d, k2, k1)
            if a is not None and b is not None:
                log.at[i, "ue_p1"], log.at[i, "ue_p2"] = float(a.unforced), float(b.unforced)
                for side, row in (("p1", a), ("p2", b)):
                    fh, bh = row.unforced_fh, row.unforced_bh
                    tot = (fh + bh) if (pd.notna(fh) and pd.notna(bh)) else None
                    log.at[i, f"ue_fh_{side}"] = (float(fh) / tot) if tot else None
                    log.at[i, f"win_{side}"] = (float(row.winners) if pd.notna(row.winners) else None)
                log.at[i, "ue_sets"] = float(a.sets) if pd.notna(a.sets) else None
                n_ue += 1
        if pd.isna(r["df_p1"]):
            a, b = _lookup(arch, d, k1, k2), _lookup(arch, d, k2, k1)
            if a is not None and b is not None:
                for side, v in (("p1", a), ("p2", b)):
                    log.at[i, f"df_{side}"] = (float(v[0]) if pd.notna(v[0]) else None)
                    log.at[i, f"sgames_{side}"] = (float(v[1]) if pd.notna(v[1]) else None)
                    log.at[i, f"aces_{side}"] = (float(v[2]) if pd.notna(v[2]) else None)
                n_df += 1
        src = []
        if pd.notna(log.at[i, "ue_p1"]):
            src.append("mcp")
        if pd.notna(log.at[i, "df_p1"]):
            src.append("archive")
        if src:
            log.at[i, "pm_src"] = "+".join(src)
    tennis_log._write_log(log)
    out = {"checked": int(len(todo)), "ue_filled": n_ue, "df_filled": n_df,
           "ue_total": int(log["ue_p1"].notna().sum()), "df_total": int(log["df_p1"].notna().sum()),
           "settled": int((log["settled"] == True).sum())}  # noqa: E712
    if verbose:
        print(f"[postmatch] {out}")
    return out


if __name__ == "__main__":
    print(backfill())
    sys.stdout.flush()
