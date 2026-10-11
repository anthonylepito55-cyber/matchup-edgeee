"""HOW BAD IS THE ONE-SIDED BACKFILL, AND DOES IT REACH THE LIVE PROFILES? (2026-10-10)

Corrected second pass. The first pass made two mistakes worth recording:
  * it mixed two populations. Among rows WITH ODDS ON BOTH SIDES -- the betting universe every
    study uses -- the archive is 98.5% mirrored. Across ALL rows it is only ~75% mirrored,
    because the archive is scraped per tracked player (1,760 of them) and a tracked player's
    match against an UNTRACKED opponent legitimately appears once. That is design, not a bug.
  * it estimated "missing losses" per player by counting one-sided rows naming them as the
    rival across the ENTIRE 20-year archive, then divided by a 35-day match count. Nonsense
    (JJ Wolf: 3 wins / 5 matches "corrected" with 142 missing rows). Both windows must match.

So there are two separate things, and only one of them is a defect:
  STRUCTURAL one-sidedness -- untracked opponents, ~25% of all rows, stable for years. Models
    are trained and served on the same thing, so it is consistent.
  INGESTION LAG -- the loser's row for a RECENT match has not been scraped yet. This is the
    defect: it is winner-biased, it inflates recent-form features on today's board, and it
    self-heals as the scraper catches up.
"""
import numpy as np
import pandas as pd

AR = "data_cache/tennisratio/all_match_logs.parquet"
K = ["date", "player_slug", "rival_slugname"]

A = pd.read_parquet(AR, columns=K + ["result", "player_odd", "rival_odd"])
A["date"] = pd.to_datetime(A["date"], errors="coerce")
for c in ("player_slug", "rival_slugname"):
    A[c] = A[c].astype(str)
for c in ("player_odd", "rival_odd"):
    A[c] = pd.to_numeric(A[c], errors="coerce")
A = A[A.date.notna() & A.player_slug.ne("nan") & A.rival_slugname.ne("nan")].copy()
A["won"] = A["result"].eq("Win")
A = A.drop_duplicates(K)
mir = A[K].rename(columns={"player_slug": "rival_slugname", "rival_slugname": "player_slug"})
mir["has_mirror"] = True
A = A.merge(mir, on=K, how="left")
A["has_mirror"] = A["has_mirror"].fillna(False)
A["priced"] = A.player_odd.gt(1.005) & A.rival_odd.gt(1.005)
TODAY = A.date.max()
A["age"] = (TODAY - A.date).dt.days
print(f"archive: {len(A)} unique match-sides, latest {TODAY.date()}")

print("\n" + "=" * 88)
print("1. TWO DIFFERENT POPULATIONS -- only one is the betting universe")
print("=" * 88)
for lab, s in (("ALL rows", A), ("rows PRICED on both sides", A[A.priced])):
    print(f"   {lab:26s} n={len(s):7d}  mirrored {100 * s.has_mirror.mean():5.1f}%  "
          f"win rate {s.won.mean():.4f}")
    print(f"      {'mirrored only':23s} win rate {s[s.has_mirror].won.mean():.4f} "
          f"(a fully mirrored set must be exactly 0.5000)")
    o = s[~s.has_mirror]
    if len(o) > 20:
        print(f"      {'one-sided only':23s} win rate {o.won.mean():.4f}  (n={len(o)})")
print("   -> the ~25% one-sided share of ALL rows is STRUCTURAL: a tracked player versus an")
print("      untracked one yields a single row, and tracked players win those. Stable for")
print("      years, so training and serving see the same thing.")

print("\n" + "=" * 88)
print("2. THE DEFECT: ingestion lag. One-sidedness in the BETTING universe, by month")
print("=" * 88)
P = A[A.priced].copy()
P["ym"] = P.date.dt.to_period("M")
rec = P[P.date >= TODAY - pd.Timedelta(days=430)]
for ym, r in rec.groupby("ym").agg(n=("won", "size"),
                                   one=("has_mirror", lambda s: 100 * (~s).mean()),
                                   wr=("won", "mean")).iterrows():
    flag = "  <-- LAG" if r.one > 5 else ""
    print(f"   {ym}  n={int(r.n):6d}  one-sided {r.one:5.1f}%  win rate {r.wr:.4f}"
          f"  {'#' * int(round(r.one))}{flag}")
print("\n   and by age, which is what shows it heals:")
for lo, hi in ((0, 7), (7, 14), (14, 35), (35, 90), (90, 365), (365, 10 ** 6)):
    s = P[(P.age >= lo) & (P.age < hi)]
    if len(s) < 50:
        continue
    o = s[~s.has_mirror]
    lab = f"{lo}-{hi}d" if hi < 10 ** 6 else "over 1y"
    wr = f"{o.won.mean():.3f}" if len(o) >= 20 else "  n/a"
    print(f"      {lab:9s} n={len(s):6d}  one-sided {100 * (~s.has_mirror).mean():5.1f}%  "
          f"their win rate {wr}  (n={len(o)})")

print("\n" + "=" * 88)
print("3. DOES THE LAG INFLATE RECENT FORM? (window-matched this time)")
print("=" * 88)
for W in (14, 35):
    R = A[A.age <= W]
    # a player's missing rows = one-sided rows IN THIS SAME WINDOW that name them as the rival
    one = R[~R.has_mirror]
    miss = one.groupby("rival_slugname").size().rename("miss")
    own = R.groupby("player_slug").agg(n=("won", "size"), w=("won", "sum")).join(miss, how="left")
    own["miss"] = own["miss"].fillna(0)
    own = own[own.n >= 4]
    own["logged"] = own.w / own.n
    own["corrected"] = own.w / (own.n + own.miss)
    own["infl"] = own.logged - own.corrected
    print(f"\n   last {W} days -- players with 4+ logged matches: {len(own)}")
    print(f"      with at least one missing row: {100 * (own.miss > 0).mean():.1f}%")
    print(f"      win-rate inflation: mean {own.infl.mean():+.4f}  median {own.infl.median():+.4f}"
          f"  p90 {own.infl.quantile(.9):+.4f}  max {own.infl.max():+.4f}")
    print(f"      overstated by more than 5 points: {int((own.infl > 0.05).sum())} players "
          f"({100 * (own.infl > 0.05).mean():.1f}%)")
    bad = own[own.infl > 0.05].sort_values("infl", ascending=False)
    for slug, r in bad.head(6).iterrows():
        print(f"         {slug:26s} logged {r.logged:.3f} ({int(r.w)}/{int(r.n)}) -> "
              f"{r.corrected:.3f} with {int(r.miss)} missing  ({r.infl:+.3f})")
print("\n   NOTE: a missing row is only assumed to be a loss because one-sided rows in the")
print("   betting universe are winner-biased. Treat these as an upper bound on the inflation.")
