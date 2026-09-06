"""Root-cause diagnostic: why does the LIVE system bet heavy favorites ~10x more often than
the season replay? (found 2026-09-06: live 29% of bets at devig>=0.60 vs replay 5%).

Decomposition on the SAME games (2026-08-20 -> 09-03, in both the live log and the training
build):
  p_live   = frozen pre-game probability from the live log (live model + live features)
  p_replay = fresh 5-seed ensemble trained only on games BEFORE 8/20 (replay conditions)
  p_box    = the actual production model (pulled from EC2, built Sep 3) on build features
             -- CAVEAT: in-sample on these games, labeled as such
Market audit: the live log's frozen consensus (odds_fetcher devig) vs the training build's
closing consensus for the same games -- a systematic offset here manufactures edges.
"""
import numpy as np
import pandas as pd

import model as model_module
import model_e

BOX_MODEL = r"C:\Users\ACTSL~1.DES\AppData\Local\Temp\claude\C--Users-actsl-DESKTOP-5CTNC21-OneDrive-Documents-Desktop-mlb-predictor\1526a1fa-20df-4322-a22b-68bd03e256ae\scratchpad\box_model_e.joblib"
EC2_LOG = r"C:\Users\ACTSL~1.DES\AppData\Local\Temp\claude\C--Users-actsl-DESKTOP-5CTNC21-OneDrive-Documents-Desktop-mlb-predictor\1526a1fa-20df-4322-a22b-68bd03e256ae\scratchpad\ec2_log_fresh.parquet"

df = pd.read_parquet("data_cache/training_dataset.parquet").sort_values("game_date")
df = df[df["home_win"].notna()].drop_duplicates("game_pk").reset_index(drop=True)
df["mkt"] = 0.5 + df["consensus_prob_diff"]
last_close = df[df["mkt"].notna()]["game_date"].astype(str).max()
print(f"NOTE: build closing consensus ends {last_close} (backfill lag) -- using the live log's "
      f"frozen consensus as the market for ALL sources, so every comparison is like-for-like.")
win = df[df["game_date"].astype(str) >= "2026-08-20"].reset_index(drop=True)
train = df[df["game_date"].astype(str) < "2026-08-20"]
print(f"comparison games (in build AND live era): {len(win)}  ({win['game_date'].astype(str).min()} -> {win['game_date'].astype(str).max()})")

cols = model_e.MODEL_E_FEATURE_COLUMNS
print("training replay ensemble (pre-8/20 data, 5 seeds)...", flush=True)
ps = []
for s in model_module.ENSEMBLE_SEEDS:
    m, med, _ = model_module.train(train, "home_win", save=False, feature_columns=cols, random_state=s)
    ps.append(m.predict_proba(win[cols].fillna(med))[:, 1])
win["p_replay"] = np.mean(ps, axis=0)

print("scoring production (box) model on the same build features...", flush=True)
p_box = []
for i in range(len(win)):
    row = win.iloc[[i]]
    p_box.append(model_module.predict_proba_ensemble(row, model_path=BOX_MODEL, feature_columns=cols)["home_win_prob"])
win["p_box"] = p_box

log = pd.read_parquet(EC2_LOG)
log = log[log["model_e_prob"].notna()].drop_duplicates("game_pk").set_index("game_pk")
win["p_live"] = win["game_pk"].map(log["model_e_prob"])
win["mkt_live"] = win["game_pk"].map(log["market_home_prob"])
w = win[win["p_live"].notna() & win["mkt_live"].notna()].reset_index(drop=True)
print(f"matched to frozen live probs + live consensus: {len(w)}")

# fav side by the LIVE frozen consensus (the market the menu actually compared against)
fav_home = w["mkt_live"] >= 0.5
def fav_side(col):
    return np.where(fav_home, w[col], 1 - w[col])
pf_live, pf_replay, pf_box, mf = fav_side("p_live"), fav_side("p_replay"), fav_side("p_box"), fav_side("mkt_live")

print("\nmean probability ON THE MARKET FAVORITE side (same games, market = live frozen consensus):")
print(f"  market: {100*np.nanmean(mf):.1f}%")
print(f"  p_live  (frozen live pipeline):   {100*np.nanmean(pf_live):.1f}%   mean(live - mkt) = {100*np.nanmean(pf_live - mf):+.1f} pts")
print(f"  p_replay (fresh pre-8/20 models): {100*np.nanmean(pf_replay):.1f}%   mean(replay - mkt) = {100*np.nanmean(pf_replay - mf):+.1f} pts")
print(f"  p_box (prod model, IN-SAMPLE):    {100*np.nanmean(pf_box):.1f}%   mean(box - mkt) = {100*np.nanmean(pf_box - mf):+.1f} pts")
print(f"  decomposition: live - replay = {100*np.nanmean(pf_live - pf_replay):+.1f} pts total"
      f"  |  live - box = {100*np.nanmean(pf_live - pf_box):+.1f} (serving/features, in-sample caveat)"
      f"  |  box - replay = {100*np.nanmean(pf_box - pf_replay):+.1f} (model/training-data, in-sample caveat)")

def menu_counts(pcol, label):
    n = fav = heavy = 0
    for _, r in w.iterrows():
        if pd.isna(r[pcol]):
            continue
        bt = model_e.compute_bet(float(r[pcol]), float(r["mkt_live"]), "H", "A")
        if not bt:
            continue
        n += 1
        if bt["type"] == "favorite":
            fav += 1
            if bt["market_prob"] >= 0.60:
                heavy += 1
    print(f"  {label:<46} bets {n:<4} favs {fav:<4} HEAVY favs {heavy}")

print("\nmenu fires on these same games, same market (live frozen consensus):")
menu_counts("p_live", "live frozen probs (what actually happened)")
menu_counts("p_replay", "replay probs (what the replay would have done)")
menu_counts("p_box", "box production model on build features (in-sample)")
