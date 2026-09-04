"""Independent validation of the fav-3%/dog-6% threshold proposal (2026-09-04).

The sweep that found it (_e_vig_threshold_sweep.py) ran on the cached 7-slice OOF probs from
the .pre2021_backup parquet. This re-tests under everything-different-that-can-be-different:
  - fresh 5-seed walk-forward training on the CURRENT TRAINING_CACHE
  - 6-slice fold geometry (test folds 1-5) instead of 7 (test folds 2-6)
  - settled at 3.5% vig (realistic multi-book shop), 2% shown for continuity
Verdict bar (pre-registered): proposed beats current on ROI in BOTH halves AND in a majority
of individual folds, at 3.5% vig. Neighbor configs shown so a lone lucky peak is visible.
Poisoned 2025-07-13..20 week excluded from scoring (harmless if already repaired upstream).
Read-only; ships nothing."""
import os

import numpy as np
import pandas as pd

import model as model_module
import model_e
from build_training_data import TRAINING_CACHE

df = pd.read_parquet(TRAINING_CACHE).sort_values("game_date").reset_index(drop=True)
df = df[df["home_win"].notna()].reset_index(drop=True)
print(f"training cache: {len(df)} games, {df['game_date'].min()} -> {df['game_date'].max()}, "
      f"mtime {pd.Timestamp(os.path.getmtime(TRAINING_CACHE), unit='s')}")
y = df["home_win"].astype(int).values
mkt = (0.5 + df["consensus_prob_diff"]).values
gdate = df["game_date"].astype(str).values
fs = len(df) // 6
fid = np.full(len(df), -1)
for k in range(1, 6):
    fid[fs * k:fs * (k + 1) if k < 5 else len(df)] = k

print("fresh walk-forward OOF (6-slice geometry, 5 seeds)...", flush=True)
pE = np.full(len(df), np.nan)
for k in range(1, 6):
    a, b = fs * k, fs * (k + 1) if k < 5 else len(df)
    ps = []
    for s in model_module.ENSEMBLE_SEEDS:
        m, med, _ = model_module.train(df.iloc[:a], "home_win", save=False,
                                       feature_columns=model_e.MODEL_E_FEATURE_COLUMNS, random_state=s)
        ps.append(m.predict_proba(df.iloc[a:b][model_e.MODEL_E_FEATURE_COLUMNS].fillna(med))[:, 1])
    pE[a:b] = np.mean(ps, axis=0)

bad = (gdate >= "2025-07-13") & (gdate <= "2025-07-20")
ok = np.where((fid > 0) & ~np.isnan(mkt) & ~np.isnan(pE) & ~bad)[0]
half = len(ok) // 2
early_set = set(ok[:half].tolist())
print(f"{len(ok)} scored games; early/late split at {gdate[ok[half]]}\n")

bets = []
for i in ok:
    bt = model_e.compute_bet(float(pE[i]), float(mkt[i]), "H", "A")
    if not bt:
        continue
    p_side = pE[i] if bt["side_is_home"] else 1 - pE[i]
    won = bool(y[i]) if bt["side_is_home"] else not bool(y[i])
    bets.append({"edge": p_side - bt["market_prob"], "mkt": bt["market_prob"], "won": won,
                 "dog": bt["type"] == "underdog", "early": i in early_set, "fold": fid[i]})
print(f"{len(bets)} bets from the base rule")

CONFIGS = [("current 2/4", 0.02, 0.04), ("proposed 3/6", 0.03, 0.06),
           ("neighbor 3/4", 0.03, 0.04), ("neighbor 2/6", 0.02, 0.06), ("neighbor 4/6", 0.04, 0.06)]


def stats(min_fav, min_dog, vig, fold=None):
    pnl, early = [], []
    for b in bets:
        if fold is not None and b["fold"] != fold:
            continue
        if b["edge"] < (min_dog if b["dog"] else min_fav):
            continue
        dec = (1.0 / b["mkt"]) * (1 - vig)
        pnl.append((dec - 1.0) if b["won"] else -1.0)
        early.append(b["early"])
    if not pnl:
        return None
    pnl, early = np.array(pnl), np.array(early, dtype=bool)
    e = pnl[early].mean() * 100 if early.any() else float("nan")
    l = pnl[~early].mean() * 100 if (~early).any() else float("nan")
    return len(pnl), 100 * pnl.mean(), pnl.sum(), e, l


for vig in (0.035, 0.02):
    print(f"\n=== {vig*100:.1f}% vig ===")
    print(f"{'config':>14s} {'bets':>6s} {'ROI':>8s} {'units':>9s} {'early':>8s} {'late':>8s}")
    for name, mf, md in CONFIGS:
        r = stats(mf, md, vig)
        print(f"{name:>14s} {r[0]:6d} {r[1]:+7.2f}% {r[2]:+8.1f}u {r[3]:+7.2f}% {r[4]:+7.2f}%")

print("\n=== fold-by-fold at 3.5% vig, current vs proposed ===")
wins = 0
for k in range(1, 6):
    c = stats(0.02, 0.04, 0.035, fold=k)
    p = stats(0.03, 0.06, 0.035, fold=k)
    if c is None or p is None:
        continue
    if p[1] > c[1]:
        wins += 1
    print(f"  fold {k}: current {c[1]:+6.2f}% (n={c[0]})   proposed {p[1]:+6.2f}% (n={p[0]})   "
          f"{'proposed' if p[1] > c[1] else 'current'}")
print(f"proposed wins {wins} of 5 folds")

c = stats(0.02, 0.04, 0.035)
p = stats(0.03, 0.06, 0.035)
both = p[3] > c[3] and p[4] > c[4]
print(f"\nVERDICT: beats current in both halves: {'YES' if both else 'no'} "
      f"(early {p[3]:+.2f} vs {c[3]:+.2f}, late {p[4]:+.2f} vs {c[4]:+.2f}); "
      f"folds {wins}/5; ROI {p[1]:+.2f}% vs {c[1]:+.2f}%; units {p[2]:+.1f}u vs {c[2]:+.1f}u")
print("DONE")
