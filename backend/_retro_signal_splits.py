"""Signal/class ROIs over the FULL walk-forward 2026 window (user ask 9/4: "use all the data
we have access to and redo the forward rois").

Honesty frame: the live log only has frozen Model E bets from 2026-08-20 (the day E shipped).
Everything earlier is RETRO-COMPUTED WALK-FORWARD: each slice predicted by an ensemble trained
only on games strictly before it, bets from the CURRENT menu rules, graded at the de-vigged
close minus 3.5% vig (realistic shop). Same discipline and label as the retro record. A retro
record cannot lose to line movement/limits the way a live bettor can -- upper bound, not diary.

Outputs: overall menu ROI, current-rules (with the omega-co-fire demotion), PEN+WHIP split,
class splits (dog A/B, favorites), e_alone vs omega_same -- all on ~a full season of bets.
Caches per-game OOF probs to data_cache/model_e_oof_2026.parquet so future asks don't retrain.
"""
import os

import numpy as np
import pandas as pd

import model as model_module
import model_e
from build_training_data import TRAINING_CACHE

START = "2026-03-25"
N_SLICES = 6
VIG = 0.035
OOF_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_cache", "model_e_oof_2026.parquet")

df = pd.read_parquet(TRAINING_CACHE).sort_values("game_date").reset_index(drop=True)
df = df[df["home_win"].notna()].reset_index(drop=True)
y = df["home_win"].astype(int).values
mkt = (0.5 + df["consensus_prob_diff"]).values
gdate = df["game_date"].astype(str).values

win_idx = np.where((gdate >= START) & ~np.isnan(mkt))[0]
print(f"window {START}..{gdate[win_idx].max()}: {len(win_idx)} games with a market close", flush=True)

from features import BASEBALL_ONLY_FEATURE_COLUMNS

if os.path.exists(OOF_CACHE):
    oof = pd.read_parquet(OOF_CACHE).set_index("game_pk")
    pE = df["game_pk"].map(oof["p_e"]).values
    pB = df["game_pk"].map(oof["p_h13"]).values
    pA = df["game_pk"].map(oof["p_a"]).values
    print("loaded cached OOF probs")
else:
    pE = np.full(len(df), np.nan)
    pB = np.full(len(df), np.nan)  # baseball-only leg (h13) for the omega co-fire retro-check
    pA = np.full(len(df), np.nan)  # Model A (baseball-only primary), same walk-forward frame
    for si, sl in enumerate(np.array_split(win_idx, N_SLICES)):
        a = sl.min()
        for cols, tgt in ((model_e.MODEL_E_FEATURE_COLUMNS, pE), (model_e.MODEL_E_BASEBALL_COLUMNS, pB),
                          (BASEBALL_ONLY_FEATURE_COLUMNS, pA)):
            ps = []
            for s in model_module.ENSEMBLE_SEEDS:
                m, med, _ = model_module.train(df.iloc[:a], "home_win", save=False, feature_columns=cols, random_state=s)
                ps.append(m.predict_proba(df.iloc[sl][cols].fillna(med))[:, 1])
            tgt[sl] = np.mean(ps, axis=0)
        print(f"  slice {si+1}/{N_SLICES}: {gdate[sl.min()]}..{gdate[sl.max()]} done", flush=True)
    pd.DataFrame({"game_pk": df["game_pk"].values[win_idx], "game_date": gdate[win_idx],
                  "p_e": pE[win_idx], "p_h13": pB[win_idx], "p_a": pA[win_idx]}).to_parquet(OOF_CACHE)
    print(f"cached OOF probs -> {OOF_CACHE}")

bets = []
for i in win_idx:
    if np.isnan(pE[i]):
        continue
    bt = model_e.compute_bet(float(pE[i]), float(mkt[i]), "H", "A")
    if not bt:
        continue
    dec = (1.0 / bt["market_prob"]) * (1 - VIG)
    won = bool(y[i]) if bt["side_is_home"] else not bool(y[i])
    cofired = False
    if not np.isnan(pB[i]):
        op = model_e.compute_omega_prob(float(pB[i]), float(mkt[i]))
        if op is not None:
            ob = model_e.compute_bet(op, float(mkt[i]), "H", "A")
            cofired = bool(ob and ob.get("side_is_home") == bt.get("side_is_home"))
    w, b = df["whip_diff"].iloc[i], df["bullpen_fip_diff"].iloc[i]
    pw = None
    if pd.notna(w) and pd.notna(b):
        sh = bool(bt["side_is_home"])
        pw = bool(((w > 0) if sh else (w < 0)) and ((b > 0) if sh else (b < 0)))
    bets.append({"date": gdate[i], "type": bt["type"], "dog_grade": bt.get("dog_grade"),
                 "won": won, "flat": (dec - 1.0) if won else -1.0, "cofired": cofired, "pen_whip": pw})

bdf = pd.DataFrame(bets)
print(f"\nmenu bets under CURRENT rules, {START} -> {bdf['date'].max()}: {len(bdf)}")


def show(m, label):
    d = bdf[m] if m is not None else bdf
    if not len(d):
        print(f"{label}: n=0")
        return
    n = len(d)
    print(f"{label:<44} n={n:<5} win {100 * d['won'].mean():5.1f}%  ROI {100 * d['flat'].mean():+6.1f}%  (noise ±{200 / n ** 0.5:.0f} pts)")


show(None, "ALL menu bets (at close, 3.5% vig)")
show(~bdf["cofired"], "current rules (omega-co-fired demoted out)")
show(bdf["cofired"], "omega co-fired (the demoted group)")
print()
show(bdf["pen_whip"] == True, "PEN+WHIP yes (both pitching edges)")  # noqa: E712
show(bdf["pen_whip"] == False, "PEN+WHIP no")  # noqa: E712
print()
show(bdf["type"] == "favorite", "favorites")
show((bdf["type"] == "underdog") & (bdf["dog_grade"] == "A"), "grade-A dogs")
show((bdf["type"] == "underdog") & (bdf["dog_grade"] != "A"), "grade-B dogs")
print()
show((bdf["pen_whip"] == True) & ~bdf["cofired"], "current rules AND pen+whip yes")  # noqa: E712

# Model A through the same menu, same window (the "A selectivity" question at season scale)
bets_a = []
for i in win_idx:
    if np.isnan(pA[i]):
        continue
    bt = model_e.compute_bet(float(pA[i]), float(mkt[i]), "H", "A")
    if not bt:
        continue
    dec = (1.0 / bt["market_prob"]) * (1 - VIG)
    won = bool(y[i]) if bt["side_is_home"] else not bool(y[i])
    w, b = df["whip_diff"].iloc[i], df["bullpen_fip_diff"].iloc[i]
    pw = None
    if pd.notna(w) and pd.notna(b):
        sh = bool(bt["side_is_home"])
        pw = bool(((w > 0) if sh else (w < 0)) and ((b > 0) if sh else (b < 0)))
    bets_a.append({"type": bt["type"], "dog_grade": bt.get("dog_grade"), "won": won,
                   "flat": (dec - 1.0) if won else -1.0, "pen_whip": pw})
adf = pd.DataFrame(bets_a)
print(f"\nMODEL A through the same menu: {len(adf)} bets")
if len(adf):
    print(f"  all: win {100 * adf['won'].mean():.1f}%  ROI {100 * adf['flat'].mean():+.1f}%  (noise ±{200 / len(adf) ** 0.5:.0f})")
    for lbl, m in (("pen+whip yes", adf["pen_whip"] == True), ("pen+whip no", adf["pen_whip"] == False)):  # noqa: E712
        d = adf[m]
        if len(d):
            print(f"  {lbl}: n={len(d)}  win {100 * d['won'].mean():.1f}%  ROI {100 * d['flat'].mean():+.1f}%")
print("\nlabel: retro-computed walk-forward at the close -- NOT a live log; upper bound on the period")
