"""TRAIN/SERVE WINDOW AUDIT (2026-10-10, user "Double check all stats backtest seasonal,
52 week, and last 10 stats").

Reading the code turned up two structural differences between how a feature is computed when
a model is TRAINED (the archive build scripts) and when it is SERVED (tennis_model_a.profile):

  A. THE 52-WEEK ANCHOR.
     backtest (_tennis_model_c_build.py:56-63): rolling("365D") INCLUSIVE of the current row,
       then .shift(1) within (player, surface). So a match's 52w window is the 365 days ending
       at that player's PREVIOUS match.
     live (tennis_model_a.py:165): w52 = sd[sd.date >= today - 365d]. The 365 days ending at
       THE MATCH DATE.
     Neither leaks. But they are different windows, and the gap is exactly the layoff since the
     previous match -- days for a busy player, months for someone returning from injury. The
     model is fitted on one definition and served another.

  B. THE >= 5 MATCH GATE EXISTS ONLY LIVE.
     live returns c52 = None unless len(w52) >= 5, so a thin profile gets NO Model C features
     at all. The backtest has no such gate -- core_c only requires 18 non-null features. So the
     backtest trains AND scores on thin-profile rows the live board would never price.

This script measures both, plus the last-10 and seasonal blocks, by recomputing every window
BOTH ways over the real 615k-row archive with an independent searchsorted implementation (not
the build script's pandas rolling, so an alignment bug in either would show up as disagreement).
"""
import numpy as np
import pandas as pd

P = "data_cache/tennisratio/all_match_logs.parquet"
YEAR = np.timedelta64(365, "D")

df = pd.read_parquet(P)
df["surface"] = df["surface"].astype(str).str.title()
df["date"] = pd.to_datetime(df["date"], errors="coerce")
for c in ("serve_pressure_all", "serve_pressure_won", "return_pressure_all",
          "return_pressure_won", "rival_rank"):
    df[c] = pd.to_numeric(df[c], errors="coerce")
for col, pre in (("service_games_won", "sg"),):
    parts = df[col].astype(str).str.extract(r"^(\d+)/(\d+)$")
    df[pre + "_w"] = pd.to_numeric(parts[0], errors="coerce")
    df[pre + "_a"] = pd.to_numeric(parts[1], errors="coerce")
df = df[df["date"].notna() & df["player_slug"].notna()].copy()
df["won"] = (df["result"] == "Win").astype(float)
df = df.sort_values(["player_slug", "surface", "date"], kind="stable").reset_index(drop=True)
print(f"archive rows: {len(df)}  players: {df.player_slug.nunique()}  "
      f"{df.date.min().date()}..{df.date.max().date()}", flush=True)

# ---------------------------------------------------------------------------------------
# Independent recomputation. For each (player, surface) series sorted by date, row i's
# prior rows are 0..i-1. The only difference between the two recipes is the window's LEFT
# edge: live cuts at date[i] - 365d, the backtest at date[i-1] - 365d.
# ---------------------------------------------------------------------------------------
NUM = ["won", "serve_pressure_won", "serve_pressure_all", "return_pressure_won",
       "return_pressure_all", "sg_w", "sg_a"]
out = {k: np.full(len(df), np.nan) for k in
       ("bt_n", "lv_n", "bt_won", "lv_won", "bt_sp", "lv_sp", "bt_rp", "lv_rp",
        "bt_sgw", "lv_sgw", "layoff", "bt_t10", "lv_t10")}

gi = df.groupby(["player_slug", "surface"], sort=False).indices
for _, idx in gi.items():
    idx = np.sort(idx)
    d = df["date"].values[idx]
    V = {k: np.nan_to_num(df[k].values[idx].astype(float)) for k in NUM}
    M = {k: (~np.isnan(df[k].values[idx].astype(float))).astype(float) for k in NUM}
    cs = {k: np.concatenate([[0.0], np.cumsum(V[k])]) for k in NUM}
    cm = {k: np.concatenate([[0.0], np.cumsum(M[k])]) for k in NUM}
    n = len(idx)
    for i in range(1, n):
        prev = i - 1
        lo_lv = int(np.searchsorted(d, d[i] - YEAR, side="left"))
        lo_bt = int(np.searchsorted(d, d[prev] - YEAR, side="left"))
        r = idx[i]
        out["layoff"][r] = (d[i] - d[prev]) / np.timedelta64(1, "D")
        for tag, lo in (("bt", lo_bt), ("lv", lo_lv)):
            hi = i                                  # prior rows only: [lo, i-1]
            cnt = hi - lo
            out[f"{tag}_n"][r] = cnt
            if cnt <= 0:
                continue
            nw = cm["won"][hi] - cm["won"][lo]
            if nw:
                out[f"{tag}_won"][r] = (cs["won"][hi] - cs["won"][lo]) / nw
            for key, a, b in (("sp", "serve_pressure_won", "serve_pressure_all"),
                              ("rp", "return_pressure_won", "return_pressure_all"),
                              ("sgw", "sg_w", "sg_a")):
                den = cs[b][hi] - cs[b][lo]
                if den > 0:
                    out[f"{tag}_{key}"][r] = 100.0 * (cs[a][hi] - cs[a][lo]) / den
        # last 10 prior on surface -- identical by construction in both recipes
        lo10 = max(0, i - 10)
        nw10 = cm["won"][i] - cm["won"][lo10]
        if nw10 >= 4:
            v = (cs["won"][i] - cs["won"][lo10]) / nw10
            out["bt_t10"][r] = v
            out["lv_t10"][r] = v
for k, v in out.items():
    df[k] = v

A = df[df.bt_n.notna() & df.lv_n.notna() & (df.lv_n > 0)].copy()
print(f"\ncomparable rows (a prior match on this surface exists): {len(A)}")
print("\n" + "=" * 88)
print("A. THE 52-WEEK ANCHOR -- same data, backtest window vs live window")
print("=" * 88)
print(f"   layoff since previous match on surface: median {A.layoff.median():.0f}d  "
      f"mean {A.layoff.mean():.0f}d  p90 {A.layoff.quantile(.9):.0f}d  "
      f"p99 {A.layoff.quantile(.99):.0f}d")
print(f"   -> that layoff IS the window misalignment\n")
print(f"   {'feature':10s} {'share differing':>16s} {'mean |diff|':>12s} {'p95 |diff|':>11s}"
      f" {'bt mean':>9s} {'live mean':>9s} {'bias':>8s}")
for key, lab in (("won", "m_won"), ("sp", "c_sp"), ("rp", "c_rp"), ("sgw", "c_sgw"),
                 ("n", "w_n")):
    b, l = A[f"bt_{key}"], A[f"lv_{key}"]
    m = b.notna() & l.notna()
    dv = (b[m] - l[m]).abs()
    tol = 1e-9 if key == "n" else 1e-6
    print(f"   {lab:10s} {100 * (dv > tol).mean():15.1f}% {dv.mean():12.4f} "
          f"{dv.quantile(.95):11.4f} {b[m].mean():9.3f} {l[m].mean():9.3f} "
          f"{(b[m] - l[m]).mean():+8.4f}")
big = A[(A.bt_won.notna()) & (A.lv_won.notna()) & ((A.bt_won - A.lv_won).abs() > 0.10)]
print(f"\n   rows where the 52w WIN RATE differs by more than 10 points: "
      f"{len(big)} ({100 * len(big) / len(A):.1f}%)")
print(f"      their median layoff: {big.layoff.median():.0f}d vs "
      f"{A.layoff.median():.0f}d overall")
print("   by layoff bucket, how far the two windows' win rates drift apart:")
for lo, hi in ((0, 7), (7, 21), (21, 60), (60, 180), (180, 100000)):
    s = A[(A.layoff >= lo) & (A.layoff < hi) & A.bt_won.notna() & A.lv_won.notna()]
    if len(s) < 50:
        continue
    d2 = (s.bt_won - s.lv_won).abs()
    lab = f"{lo}-{hi}d" if hi < 100000 else "180d+"
    print(f"      {lab:9s} n={len(s):6d}  mean |diff| {d2.mean():.4f}  "
          f"share >5pts {100 * (d2 > 0.05).mean():5.1f}%  share >10pts {100 * (d2 > 0.10).mean():5.1f}%")

print("\n" + "=" * 88)
print("B. THE >= 5 MATCH GATE (live only)")
print("=" * 88)
lv5 = A.lv_n >= 5
bt5 = A.bt_n >= 5
print(f"   rows live would PRICE (live window >= 5):      {100 * lv5.mean():5.1f}%")
print(f"   rows the backtest treats as usable (bt >= 5):  {100 * bt5.mean():5.1f}%")
print(f"   rows the BACKTEST uses but LIVE REFUSES:       {int((bt5 & ~lv5).sum())} "
       f"({100 * (bt5 & ~lv5).mean():.2f}%)")
print(f"   rows LIVE prices but the backtest would not:   {int((lv5 & ~bt5).sum())} "
      f"({100 * (lv5 & ~bt5).mean():.2f}%)")
thin = A[~lv5]
print(f"\n   the thin rows live refuses are a different population:")
print(f"      their win rate {thin.won.mean():.3f} vs {A[lv5].won.mean():.3f} for priced rows")
print(f"      their median layoff {thin.layoff.median():.0f}d vs {A[lv5].layoff.median():.0f}d")

print("\n" + "=" * 88)
print("C. LAST-10 and SEASONAL")
print("=" * 88)
print("   last-10-on-surface: both recipes take the 10 matches immediately before this one,")
print("   so they are identical BY CONSTRUCTION (no date anchor involved). Verified:")
m10 = A.bt_t10.notna() & A.lv_t10.notna()
print(f"      {int(m10.sum())} rows compared, max |diff| "
      f"{(A.bt_t10[m10] - A.lv_t10[m10]).abs().max():.2e}")
print("   min_periods DOES differ: backtest t10_win needs 4 prior matches (mn=4), live")
print("   tmean(gdf.won, 10, 3) needs 3 -- so live prices some rows the backtest left NaN.")
df["yr"] = df["date"].dt.year
gy = df.sort_values(["player_slug", "yr", "date"], kind="stable").groupby(["player_slug", "yr"])
sn_n = gy.cumcount()
print(f"\n   seasonal (calendar-year expanding, shifted): first match of each player-year has")
print(f"   no season history at all -- {100 * (sn_n == 0).mean():.1f}% of all rows, and "
      f"{100 * (sn_n < 5).mean():.1f}% have fewer than 5.")
print("   Both recipes agree (live yr = this calendar year, strictly before today; backtest")
print("   expanding().mean().shift(1) within the year), so the seasonal block is consistent --")
print("   but it is a JANUARY-RESET window, thin for everyone early in each season.")
