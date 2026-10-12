"""EVERY PRE-MATCH STAT, ONE BY ONE AND COMBINED (2026-10-11, user: "Go through every stat one
by one and combined and see what stats to lead to wins").

The full sweep on the archive. Two different questions get answered separately, because they
have different answers and conflating them is how people talk themselves into bad bets:

    A. WHICH STAT PREDICTS THE WINNER?   does the player ahead on it win?
    B. WHICH STAT BEATS THE PRICE?       EDGE = win rate minus the NO-VIG implied probability

Then combinations, in two forms:
    C. AGREEMENT LADDER   how many of the core stats point the same way -- one pre-specified
       test, so it is the honest one
    D. OFFSET FIT         all stats at once with the market's log-odds as a fixed baseline, so
       each is credited only for what it adds ON TOP of the price. Walk-forward by year, which
       is the only version that cannot overfit its own answer.

Every feature is a 52-week-on-surface figure built from sums over the player's EARLIER matches
(`.shift(1)` before the rolling window), mirror-guarded and priced-only. One row per match,
oriented to player_1, with both genders reported separately because essentially every finding
in this app is gender-split.
"""
import numpy as np
import pandas as pd

import tennis_archive as TA

W_DAYS = 365
MINM = 8          # matches in the window before a feature is trusted


def frac(s):
    p = s.astype(str).str.extract(r"^(\d+)/(\d+)$")
    return pd.to_numeric(p[0], errors="coerce"), pd.to_numeric(p[1], errors="coerce")


COLS = ["surface", "service_games_won", "return_games_won", "double_faults", "aces",
        "first_serve_accuracy", "first_serve_points", "second_serve_points",
        "return_1st_serve_points", "return_2nd_serve_points",
        "serve_pressure_all", "serve_pressure_won",
        "return_pressure_all", "return_pressure_won",
        "breakpoints_saved_count", "breakpoints_converted_count",
        "rival_rank", "tournament_level"]
df = TA.load(columns=COLS, priced_only=True, require_mirror=True, verbose=False)
df["surf"] = df["surface"].astype(str).str.title().replace({"I.Hard": "Hard", "Carpet": "Hard"})
df["won"] = df["result"].eq("Win").astype(int)
df["sg_w"], df["sg_a"] = frac(df["service_games_won"])
df["rg_w"], df["rg_a"] = frac(df["return_games_won"])
df["bps_w"], df["bps_a"] = frac(df["breakpoints_saved_count"])
df["bpc_w"], df["bpc_a"] = frac(df["breakpoints_converted_count"])
for c in ("double_faults", "aces", "first_serve_accuracy", "first_serve_points",
          "second_serve_points", "return_1st_serve_points", "return_2nd_serve_points",
          "serve_pressure_all", "serve_pressure_won", "return_pressure_all",
          "return_pressure_won", "rival_rank"):
    df[c] = pd.to_numeric(df[c], errors="coerce")
df = df.sort_values(["player_slug", "surf", "date"], kind="stable").reset_index(drop=True)
print("priced + mirrored rows: %d" % len(df))

# ---- rolling 52-week sums on that surface, strictly BEFORE each match -------------
SUMS = ["sg_w", "sg_a", "rg_w", "rg_a", "bps_w", "bps_a", "bpc_w", "bpc_a",
        "double_faults", "aces", "serve_pressure_all", "serve_pressure_won",
        "return_pressure_all", "return_pressure_won", "won"]
MEANS = ["first_serve_accuracy", "first_serve_points", "second_serve_points",
         "return_1st_serve_points", "return_2nd_serve_points", "rival_rank"]
g = df.groupby(["player_slug", "surf"], sort=False)
idx = df.index
for c in SUMS:
    df["s_" + c] = (g[c].shift(1).groupby([df.player_slug, df.surf])
                    .rolling(40, min_periods=MINM).sum().reset_index(level=[0, 1], drop=True))
for c in MEANS:
    df["m_" + c] = (g[c].shift(1).groupby([df.player_slug, df.surf])
                    .rolling(40, min_periods=MINM).mean().reset_index(level=[0, 1], drop=True))
df["n_prev"] = (g["won"].shift(1).groupby([df.player_slug, df.surf])
                .rolling(40, min_periods=MINM).count().reset_index(level=[0, 1], drop=True))
# short-window form, which earlier work showed behaves differently from the season figure
for K, tag in ((10, "l10"), (5, "l5")):
    df["w_" + tag] = (g["won"].shift(1).groupby([df.player_slug, df.surf])
                      .rolling(K, min_periods=3).mean().reset_index(level=[0, 1], drop=True))

sg = df.s_sg_a.replace(0, np.nan)
rg = df.s_rg_a.replace(0, np.nan)
F = pd.DataFrame(index=df.index)
F["hold%"] = 100 * df.s_sg_w / sg
F["break%"] = 100 * df.s_rg_w / rg
F["holdbreak"] = F["hold%"] + F["break%"]
F["1stSvAcc"] = df.m_first_serve_accuracy
F["1stSvWon"] = df.m_first_serve_points
F["2ndSvWon"] = df.m_second_serve_points
F["retVs1st"] = df.m_return_1st_serve_points
F["retVs2nd"] = df.m_return_2nd_serve_points
F["aces/gm"] = df.s_aces / sg
F["DF/gm"] = -(df.s_double_faults / sg)                 # fewer is better -> negate
F["svPressure"] = 100 * df.s_serve_pressure_won / df.s_serve_pressure_all.replace(0, np.nan)
F["rtPressure"] = 100 * df.s_return_pressure_won / df.s_return_pressure_all.replace(0, np.nan)
F["clutch"] = 100 * (df.s_serve_pressure_won + df.s_return_pressure_won) / \
    (df.s_serve_pressure_all + df.s_return_pressure_all).replace(0, np.nan)
F["BPsaved%"] = 100 * df.s_bps_w / df.s_bps_a.replace(0, np.nan)
F["BPconv%"] = 100 * df.s_bpc_w / df.s_bpc_a.replace(0, np.nan)
F["win%52w"] = 100 * df.s_won / df.n_prev.replace(0, np.nan)
F["win%L10"] = 100 * df.w_l10
F["win%L5"] = 100 * df.w_l5
F["oppRank"] = -df.m_rival_rank                          # tougher schedule -> higher is better
FEATS = list(F.columns)
df = pd.concat([df, F], axis=1)

# sUTR, the one rating that is not a raw stat -- strictly-prior, from the build's own output
try:
    pre = pd.read_parquet("data_cache/tennis_sutr_prematch.parquet")
    pre["date"] = pd.to_datetime(pre["date"], errors="coerce")
    sut = pre[["date", "player_slug", "rival_slugname", "r1"]].rename(columns={"r1": "sUTR"})
    df = df.merge(sut, on=["date", "player_slug", "rival_slugname"], how="left")
    FEATS.append("sUTR")
    print("   sUTR merged on %d rows" % df.sUTR.notna().sum())
except Exception as e:
    print("   sUTR unavailable: %s" % e)

key = ["date", "player_slug", "rival_slugname"]
opp = df[key + FEATS].rename(columns={"player_slug": "rival_slugname",
                                      "rival_slugname": "player_slug",
                                      **{f: "o_" + f for f in FEATS}})
M = df.merge(opp, on=key, how="inner")
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
M["G"] = M.player_slug.astype(str).map(GM)
i1 = 1 / M.player_odd.where(M.player_odd > 1.005)
i2 = 1 / M.rival_odd.where(M.rival_odd > 1.005)
M["mkt"] = i1 / (i1 + i2)
M = M[M.mkt.notna()].copy()
# ONE ROW PER MATCH
M["pair"] = [tuple(sorted((a, str(b)))) for a, b in zip(M.player_slug.astype(str),
                                                        M.rival_slugname)]
M = M.drop_duplicates(["date", "pair"]).reset_index(drop=True)
M["yr"] = M.date.dt.year
print("matches (one row each): %d   %s..%s\n" % (len(M), M.date.min().date(), M.date.max().date()))

for f in FEATS:
    M["d_" + f] = M[f] - M["o_" + f]


# ---------------------------------------------------------------- A + B
def one(sel, title):
    sub = M[sel]
    print("=" * 112)
    print("%s   (n=%d matches)" % (title, len(sub)))
    print("=" * 112)
    print("   %-14s %7s %9s %9s %8s %9s" %
          ("stat", "n", "picks win", "mkt same", "EDGE", "flat ROI"))
    out = []
    for f in FEATS:
        s = sub[sub["d_" + f].notna() & (sub["d_" + f] != 0)]
        if len(s) < 500:
            continue
        p1 = s["d_" + f] > 0
        hit = (p1 == s.won.astype(bool)).mean()
        mkt = ((s.mkt > 0.5) == s.won.astype(bool)).mean()
        imp = np.where(p1, s.mkt, 1 - s.mkt).mean()
        odds = np.where(p1, s.player_odd, s.rival_odd)
        pnl = np.where(p1 == s.won.astype(bool), odds - 1, -1.0)
        out.append((hit, f, len(s), mkt, 100 * (hit - imp), 100 * pnl.mean()))
    for hit, f, n, mkt, edge, roi in sorted(out, reverse=True):
        print("   %-14s %7d %8.1f%% %8.1f%% %+7.1fpt %+8.1f%%"
              % (f, n, 100 * hit, 100 * mkt, edge, roi))
    return [o[1] for o in sorted(out, reverse=True)]


order_m = one(M.G == "M", "A+B. MEN -- every stat alone")
print()
order_w = one(M.G == "W", "A+B. WOMEN -- every stat alone")

# ---------------------------------------------------------------- C
CORE = ["hold%", "break%", "win%52w", "win%L10", "oppRank", "svPressure", "rtPressure"]
print("\n" + "=" * 112)
print("C. AGREEMENT LADDER -- how many of %d core stats point the same way" % len(CORE))
print("=" * 112)
for Gg, nm in (("M", "men"), ("W", "women")):
    sub = M[(M.G == Gg) & M[["d_" + c for c in CORE]].notna().all(axis=1)]
    if len(sub) < 500:
        continue
    pos = pd.DataFrame({c: sub["d_" + c] > 0 for c in CORE})
    cnt = pos.sum(axis=1)
    agree = np.maximum(cnt, len(CORE) - cnt)
    side = cnt >= (len(CORE) - cnt)
    print("   %s (n=%d):" % (nm, len(sub)))
    for k in range(4, len(CORE) + 1):
        s = sub[agree == k]
        if len(s) < 200:
            continue
        sp = side[agree == k]
        hit = (sp == s.won.astype(bool)).mean()
        mkt = ((s.mkt > 0.5) == s.won.astype(bool)).mean()
        imp = np.where(sp, s.mkt, 1 - s.mkt).mean()
        odds = np.where(sp, s.player_odd, s.rival_odd)
        pnl = np.where(sp == s.won.astype(bool), odds - 1, -1.0)
        print("      %d of %d agree   n=%-6d picks win %5.1f%%   mkt %5.1f%%   EDGE %+5.1fpt   ROI %+6.1f%%"
              % (k, len(CORE), len(s), 100 * hit, 100 * mkt, 100 * (hit - imp), 100 * pnl.mean()))

# ---------------------------------------------------------------- D
print("\n" + "=" * 112)
print("D. WHAT ADDS ANYTHING OVER THE PRICE -- offset fit, walk-forward by year")
print("=" * 112)
print("   (market log-odds enter as a fixed baseline; a stat is credited only for what it")
print("    explains ON TOP of the price. Standardised, so coefficients are per 1 SD.)")
# Requiring EVERY feature non-null gave zero rows: pressure points cover ~28k and sUTR a
# different subset, so the intersection is empty. Use the densely-covered core instead and
# report the coverage, rather than silently fitting on a sliver.
USE = [f for f in ["hold%", "break%", "1stSvAcc", "1stSvWon", "2ndSvWon", "retVs1st",
                   "retVs2nd", "aces/gm", "DF/gm", "BPsaved%", "BPconv%",
                   "win%52w", "win%L10", "win%L5", "oppRank"] if f in FEATS]
print("   features in the joint fit (%d): %s" % (len(USE), ", ".join(USE)))
for Gg, nm in (("M", "men"), ("W", "women")):
    sub = M[(M.G == Gg) & M[["d_" + f for f in USE]].notna().all(axis=1)].copy()
    if len(sub) < 2000:
        print("   %s: too few complete rows (%d)" % (nm, len(sub)))
        continue
    X = sub[["d_" + f for f in USE]].to_numpy(float)
    X = (X - X.mean(0)) / X.std(0, ddof=0)
    y = sub.won.to_numpy(float)
    mk = np.clip(sub.mkt.to_numpy(float), 1e-4, 1 - 1e-4)
    off = np.log(mk / (1 - mk))
    yrs = sub.yr.to_numpy()
    gain, w_last = [], None
    for ytest in sorted(set(yrs))[1:]:
        tr, te = yrs < ytest, yrs == ytest
        if tr.sum() < 1000 or te.sum() < 300:
            continue
        w = np.zeros(X.shape[1])
        for _ in range(3000):
            p = 1 / (1 + np.exp(-(off[tr] + X[tr] @ w)))
            w -= 0.1 * (X[tr].T @ (p - y[tr]) + 2.0 * w) / tr.sum()
        pte = np.clip(1 / (1 + np.exp(-(off[te] + X[te] @ w))), 1e-9, 1 - 1e-9)
        pm = np.clip(mk[te], 1e-9, 1 - 1e-9)
        ll_b = -np.mean(y[te] * np.log(pte) + (1 - y[te]) * np.log(1 - pte))
        ll_m = -np.mean(y[te] * np.log(pm) + (1 - y[te]) * np.log(1 - pm))
        gain.append((ytest, ll_m - ll_b, te.sum()))
        w_last = w
    print("\n   %s (n=%d complete):" % (nm, len(sub)))
    for ytest, gn, n in gain:
        print("      %d  out-of-sample log-loss gain vs the market: %+0.5f  (n=%d)  %s"
              % (ytest, gn, n, "beats the price" if gn > 0 else "loses to the price"))
    if w_last is not None:
        ordr = np.argsort(-np.abs(w_last))
        print("      strongest coefficients in the final fit (log-odds per 1 SD):")
        for j in ordr[:8]:
            print("         %-14s %+0.3f" % (USE[j], w_last[j]))
