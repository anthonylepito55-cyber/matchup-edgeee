"""2026-season-only walk-forward backtest of EVERY model, ranked by ROI (user ask 9/6).

Method: each model's probability for each game comes from an ensemble trained only on games
strictly before it (6 chronological slices, 5 seeds) -- the cached OOF file for A/E/h13,
freshly trained here for B, the existing OOF cache for C, and Omega computed from h13 + the
market close via the exact production formula. Every model is pushed through the IDENTICAL
current bet menu (fav >= 3 pts, dog flip >= 6 pts) and graded at the de-vigged close minus
3.5% vig. Retro-computed walk-forward: no leakage, but not a live log -- upper bound.
"""
import os

import numpy as np
import pandas as pd

import model as model_module
import model_e
from features import BASEBALL_ONLY_FEATURE_COLUMNS, FEATURE_COLUMNS
from build_training_data import TRAINING_CACHE

VIG = 0.035
START = "2026-03-25"
_here = os.path.dirname(os.path.abspath(__file__))
OOF_CACHE = os.path.join(_here, "data_cache", "model_e_oof_2026.parquet")

df = pd.read_parquet(TRAINING_CACHE).sort_values("game_date").reset_index(drop=True)
df = df[df["home_win"].notna()].reset_index(drop=True)
y = df["home_win"].astype(int).values
mkt = (0.5 + df["consensus_prob_diff"]).values
gdate = df["game_date"].astype(str).values
win_idx = np.where((gdate >= START) & ~np.isnan(mkt))[0]

oof = pd.read_parquet(OOF_CACHE).set_index("game_pk")
pE = df["game_pk"].map(oof["p_e"]).values
pH = df["game_pk"].map(oof["p_h13"]).values
pA = df["game_pk"].map(oof["p_a"]).values

if "p_b" in oof.columns:
    pB = df["game_pk"].map(oof["p_b"]).values
    print("loaded cached B probs")
else:
    print("training walk-forward Model B (market-aware, full feature set)...", flush=True)
    pB = np.full(len(df), np.nan)
    for si, sl in enumerate(np.array_split(win_idx, 6)):
        a = sl.min()
        ps = []
        for s in model_module.ENSEMBLE_SEEDS:
            m, med, _ = model_module.train(df.iloc[:a], "home_win", save=False,
                                           feature_columns=FEATURE_COLUMNS, random_state=s)
            ps.append(m.predict_proba(df.iloc[sl][FEATURE_COLUMNS].fillna(med))[:, 1])
        pB[sl] = np.mean(ps, axis=0)
        print(f"  slice {si + 1}/6 done", flush=True)
    add = pd.DataFrame({"game_pk": df["game_pk"].values, "p_b": pB}).dropna().drop_duplicates("game_pk")
    oof2 = oof.reset_index().drop_duplicates("game_pk").merge(add, on="game_pk", how="left")
    oof2.to_parquet(OOF_CACHE)
    print("cached B probs")

# Model C from its own OOF cache (walk-forward folds, 6-book features)
c_oof = pd.read_parquet(os.path.join(_here, "data_cache", "model_c_oof_with_market.parquet"))
c_oof = c_oof[c_oof["game_date"].astype(str) >= START].drop_duplicates("game_pk").set_index("game_pk")
pC = df["game_pk"].map(c_oof["model_c_prob"]).values

# Omega from h13 + market, exact production formula
pO = np.array([model_e.compute_omega_prob(float(h), float(m)) if (not np.isnan(h) and not np.isnan(m)) else np.nan
               for h, m in zip(pH, mkt)], dtype=float)

MODELS = [("A (baseball-only primary)", pA), ("B (market-aware)", pB), ("C (6-book)", pC),
          ("E (betting model)", pE), ("h13 (E baseball leg)", pH), ("Omega (Jacob's formula)", pO)]

print(f"\n2026 season, {START} -> {gdate[win_idx].max()}, identical menu, close - 3.5% vig:")
print(f"{'model':<28}{'games':>6}{'bets':>6}{'hit':>7}{'flat ROI':>10}{'noise':>7}")
res = []
for name, p in MODELS:
    ok = [i for i in win_idx if not np.isnan(p[i])]
    pnl, wins = [], 0
    for i in ok:
        bt = model_e.compute_bet(float(p[i]), float(mkt[i]), "H", "A")
        if not bt:
            continue
        dec = (1.0 / bt["market_prob"]) * (1 - VIG)
        won = bool(y[i]) if bt["side_is_home"] else not bool(y[i])
        wins += int(won)
        pnl.append((dec - 1.0) if won else -1.0)
    n = len(pnl)
    roi = 100 * np.mean(pnl) if n else float("nan")
    res.append((name, roi, n))
    print(f"{name:<28}{len(ok):>6}{n:>6}{100 * wins / n if n else 0:>6.1f}%{roi:>+9.1f}%{f'±{200 / np.sqrt(n):.0f}' if n else '':>7}")
print("\nranked by ROI:")
for name, roi, n in sorted(res, key=lambda x: -(x[1] if x[1] == x[1] else -999)):
    print(f"  {name}: {roi:+.1f}% on {n} bets")
print("\nlabel: retro-computed walk-forward at the close -- not a live log; live edges typically come in near half")
