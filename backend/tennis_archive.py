"""GUARDED ACCESS TO THE TENNISRATIO ARCHIVE (2026-10-10, user "Yes" to a mirror-row guard).

The archive is scraped per tracked player, so a match should appear TWICE -- once from each
side. When only one side is present, selecting rows by their own price silently biases a study,
because the surviving row is overwhelmingly the WINNER's. In my first pass at the favourite
investigation that produced a bogus "archive favourites +5.2% over the live window" (the real
mirrored figure was -4.1%), and one-sided favourites appeared to "hit" 86.1% for +39.5%.

TWO DIFFERENT CAUSES, and only one is a defect:

  STRUCTURAL -- a tracked player versus an UNTRACKED one yields a single row, because only
    tracked players have a page to scrape. CHRONIC and large, not a recent regression: of
    priced rows 43.4% were one-sided in 2021, 33.9% in 2023, 21.1% in 2025, 23.7% in 2026 --
    slowly improving as the tracked pool grows. Only 1.2% of one-sided rows older than a year
    have a tracked opponent, which confirms the cause. They are winner-biased anyway (tracked
    players beat untracked ones, so these rows win 65-81%), and in the favourite band they are
    36% of all rows and hit 62.7% against 58.0% for mirrored ones. Do NOT try to repair the
    data here -- require the mirror in the STUDY.

  REFRESH LAG -- the loser's row for a recent match has not been fetched yet. This IS a defect
    and it is winner-biased, not random: `tennisratio_ingest.discover_active_slugs()` refreshes
    the players in TODAY's matches, so a winner advances, reappears tomorrow and gets refreshed,
    while a loser is out of the draw, never reappears, and their loss never lands until they
    enter a new tournament. Measured 2026-10-10 on the priced universe:
        age 0-7d    78.7% one-sided, those rows 96.8% wins, 74.7% have a TRACKED opponent
        age 7-14d   43.5% one-sided, 85.0% wins, 55.3% tracked
        age 14-35d  24.0% one-sided, 19.2% tracked  (back to the structural floor)
    The chronic floor is ~24%, so only the EXCESS above it plus a high tracked-opponent share
    identifies lag rather than structure.
    In the last 14 days 45% of active players were missing at least one row, overstating their
    win rate by +0.064 on average and +0.167 at p90 -- which feeds l10, form_win, sn_win, d_m_won.

The test that separates them is whether the MISSING opponent is tracked: if they have rows of
their own elsewhere, their row for this match should exist and is merely late.

Use `load(priced_only=True, require_mirror=True)` for any study that selects rows by price, and
`assert_mirrored()` if you build the frame yourself. `health()` re-runs the diagnosis.
"""
import os

import numpy as np
import pandas as pd

_here = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.join(_here, "data_cache", "tennisratio", "all_match_logs.parquet")
KEY = ["date", "player_slug", "rival_slugname"]
#: beyond this age a one-sided row is structural, not lag (measured: tracked-opponent share
#: falls from 74.8% at 0-7d to 19.1% by 14-35d and 1.3% past a year)
LAG_DAYS = 35


class MirrorGuardError(AssertionError):
    """Raised when a frame that must be mirrored is not."""


def _norm(df):
    df = df.copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for c in ("player_slug", "rival_slugname"):
        if c in df.columns:
            df[c] = df[c].astype(str)
    return df


def attach_mirror(df, tracked=None, reference=None):
    """Add `has_mirror` (the opponent's row for this same match exists), `opp_tracked` (the
    opponent has rows of their own somewhere in this frame) and `lag_suspect` (one-sided with a
    tracked opponent -- i.e. a row that SHOULD have a mirror and is just late)."""
    df = _norm(df)
    # idempotent: a frame that already carries the flags would otherwise collide on the merge
    # and produce has_mirror_x / has_mirror_y (found by re-checking an already-guarded frame).
    df = df.drop(columns=[c for c in ("has_mirror", "opp_tracked", "lag_suspect")
                          if c in df.columns])
    # The mirror test asks "does this MATCH have two sides", so the reference pool should be
    # the whole archive, not a filtered slice. Testing within a slice raises false alarms: a
    # row kept by priced_only whose opponent's row lacks odds looks one-sided but is not, and
    # those rows are 53.4% wins -- unbiased, i.e. harmless.
    ref = _norm(reference) if reference is not None else df
    mir = ref[KEY].drop_duplicates().rename(
        columns={"player_slug": "rival_slugname", "rival_slugname": "player_slug"})
    mir["has_mirror"] = True
    df = df.merge(mir, on=KEY, how="left")
    df["has_mirror"] = df["has_mirror"].fillna(False).astype(bool)
    pool = set(tracked) if tracked is not None else set(ref["player_slug"].unique())
    df["opp_tracked"] = df["rival_slugname"].isin(pool)
    df["lag_suspect"] = (~df["has_mirror"]) & df["opp_tracked"]
    return df


def assert_mirrored(df, name="study", priced_only=True, max_one_sided=0.0, recompute=False):
    """Raise unless effectively every row has its opponent's row too.

    Call this on any frame whose rows are selected by their own price (favourite-side or
    dog-side universes), because one-sided rows are winner-biased and will manufacture an edge.
    `max_one_sided` is the tolerated share, 0.0 by default.
    """
    # trust flags that load() already computed against the full archive
    d = df if ("has_mirror" in df.columns and not recompute) else attach_mirror(
        df, reference=pd.read_parquet(ARCHIVE, columns=KEY))
    if priced_only and {"player_odd", "rival_odd"} <= set(d.columns):
        for c in ("player_odd", "rival_odd"):
            d[c] = pd.to_numeric(d[c], errors="coerce")
        d = d[d.player_odd.gt(1.005) & d.rival_odd.gt(1.005)]
    if not len(d):
        return d
    share = float((~d.has_mirror).mean())
    if share > max_one_sided:
        one = d[~d.has_mirror]
        raise MirrorGuardError(
            f"{name}: {len(one)} of {len(d)} rows ({100 * share:.2f}%) have no mirror row. "
            f"Those rows are {100 * one['result'].eq('Win').mean():.1f}% wins "
            f"(a mirrored set is exactly 50%), so selecting by price will invent an edge. "
            f"{int(one.lag_suspect.sum())} of them are refresh lag (tracked opponent) and "
            f"{int((~one.opp_tracked).sum())} are structural (untracked opponent). "
            f"Load with require_mirror=True, or pass max_one_sided if you have a reason.")
    return d


def load(columns=None, priced_only=False, require_mirror=False, drop_lag_window=False,
         with_flags=False, verbose=True):
    """Read the archive with the mirror guard applied.

    priced_only        keep only rows with a real price on BOTH sides (the betting universe)
    require_mirror     drop rows whose opponent's row is missing -- use this for any study
                       that selects rows by their own price
    drop_lag_window    also drop the trailing LAG_DAYS days, where the refresh lag lives
    with_flags         keep has_mirror / opp_tracked / lag_suspect on the result
    """
    cols = None
    if columns is not None:
        cols = sorted(set(list(columns) + KEY + ["result", "player_odd", "rival_odd"]))
    df = pd.read_parquet(ARCHIVE, columns=cols)
    df = _norm(df)
    df = df[df["date"].notna() & df["player_slug"].ne("nan")
            & df["rival_slugname"].ne("nan")].drop_duplicates(KEY)
    n0 = len(df)
    df = attach_mirror(df, reference=_norm(pd.read_parquet(ARCHIVE, columns=KEY)))
    if priced_only:
        for c in ("player_odd", "rival_odd"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df[df.player_odd.gt(1.005) & df.rival_odd.gt(1.005)]
    n1 = len(df)
    if drop_lag_window:
        df = df[df["date"] <= df["date"].max() - pd.Timedelta(days=LAG_DAYS)]
    n2 = len(df)
    if require_mirror:
        df = df[df.has_mirror]
    if verbose:
        bits = [f"{n0} rows"]
        if priced_only:
            bits.append(f"priced {n1}")
        if drop_lag_window:
            bits.append(f"outside the {LAG_DAYS}d lag window {n2}")
        bits.append(f"mirrored {len(df)}" if require_mirror
                    else f"{len(df)} kept, MIRROR NOT REQUIRED "
                         f"({100 * (1 - df.has_mirror.mean()):.1f}% one-sided)"
                    if "has_mirror" in df.columns else f"{len(df)} kept")
        print("[tennis_archive] " + " -> ".join(bits))
    if not with_flags:
        df = df.drop(columns=[c for c in ("has_mirror", "opp_tracked", "lag_suspect")
                              if c in df.columns])
    return df.reset_index(drop=True)


def stale_slugs(days=21, limit=None):
    """The players whose recent rows are MISSING -- i.e. the refresh list that fixes the lag.

    A one-sided row in the last `days` whose opponent is tracked means that opponent played
    this match and their own row has not been fetched. Returns those opponents, most recently
    affected first. `tennisratio_ingest.discover_active_slugs()` only walks TODAY's matches, so
    eliminated players never come back round; this is the set it misses.
    """
    df = pd.read_parquet(ARCHIVE, columns=KEY + ["result"])
    df = _norm(df)
    df = df[df["date"].notna()].drop_duplicates(KEY)
    df = attach_mirror(df)
    cut = df["date"].max() - pd.Timedelta(days=days)
    want = df[(df["date"] >= cut) & df.lag_suspect]
    order = want.sort_values("date", ascending=False)["rival_slugname"].drop_duplicates()
    out = list(order)
    return out[:limit] if limit else out


def health(days=430):
    """Print the mirror diagnosis. Safe to run any time; this is the check that caught it."""
    df = _norm(pd.read_parquet(ARCHIVE, columns=KEY + ["result", "player_odd", "rival_odd"]))
    # the same row filter load() applies: a row whose opponent slug is missing can NEVER have
    # a mirror, so leaving them in understates coverage badly (57.4% vs the real 98.5%).
    df = df[df["date"].notna() & df["player_slug"].ne("nan")
            & df["rival_slugname"].ne("nan")].drop_duplicates(KEY)
    for c in ("player_odd", "rival_odd"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = attach_mirror(df)
    df["priced"] = df.player_odd.gt(1.005) & df.rival_odd.gt(1.005)
    today = df["date"].max()
    df["age"] = (today - df["date"]).dt.days
    print(f"archive {ARCHIVE}\n  {len(df)} match-sides, latest {today.date()}")
    for lab, s in (("all rows", df), ("priced both sides", df[df.priced])):
        print(f"  {lab:20s} mirrored {100 * s.has_mirror.mean():5.1f}%  "
              f"win rate {s['result'].eq('Win').mean():.4f}  "
              f"(mirrored-only {s[s.has_mirror]['result'].eq('Win').mean():.4f}, must be 0.5000)")
    P = df[df.priced]
    print("  priced universe by age -- one-sided share, their win rate, tracked-opponent share:")
    for lo, hi in ((0, 7), (7, 14), (14, 35), (35, 90), (90, 365), (365, 10 ** 9)):
        s = P[(P.age >= lo) & (P.age < hi)]
        if len(s) < 50:
            continue
        o = s[~s.has_mirror]
        lab = f"{lo}-{hi}d" if hi < 10 ** 9 else "over 1y"
        wr = f"{o['result'].eq('Win').mean():.3f}" if len(o) >= 20 else " n/a"
        tk = f"{100 * o.opp_tracked.mean():4.1f}%" if len(o) else "  n/a"
        print(f"    {lab:9s} n={len(s):6d}  one-sided {100 * (~s.has_mirror).mean():5.1f}%  "
              f"wins {wr}  tracked-opp {tk}")
    n = len(stale_slugs(days=21))
    print(f"  players needing a refresh to close the lag (21d): {n}")
    return df


if __name__ == "__main__":
    health()
