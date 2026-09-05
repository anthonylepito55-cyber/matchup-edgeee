"""Which pre-game stat edges have lined up with ROI on the REAL settled Model E bets?
(user ask 9/4). Same frame as the PEN+WHIP study: every settled live bet from the EC2 log,
joined to its deterministic pre-game walk-forward feature row; for each diff feature, split
bets by whether OUR SIDE had the edge, report win% / flat ROI of each side of the split.

HONESTY GUARD: ~20 features tested on ~118 bets means a couple will look great by luck alone
(the dog_a -53% problem in reverse). The output prints the same split on the FULL 6,700-game
history (win rate vs market-expected) next to each live number so a live fluke without
historical support is visible on sight.
"""
import json

import numpy as np
import pandas as pd

import model_e

EC2_LOG = r"C:\Users\ACTSL~1.DES\AppData\Local\Temp\claude\C--Users-actsl-DESKTOP-5CTNC21-OneDrive-Documents-Desktop-mlb-predictor\1526a1fa-20df-4322-a22b-68bd03e256ae\scratchpad\ec2_prediction_log.parquet"
log = pd.read_parquet(EC2_LOG)
feats_all = pd.read_parquet("data_cache/training_dataset.parquet")
feats = feats_all.drop_duplicates("game_pk").set_index("game_pk")

CANDS = [c for c in feats.columns if c.endswith("_diff") and feats[c].notna().mean() > 0.7]
# drop market-derived features -- the user asked about STATS, and market features are
# definitionally aligned with the market side, not a scoutable stat edge
CANDS = [c for c in CANDS if not any(s in c for s in (
    "consensus", "line", "market", "divergence", "prediction_market", "model_c", "prop", "total"))]

bets = []
for _, r in log[(log["settled"] == True) & log["model_e_bet_json"].notna()].iterrows():  # noqa: E712
    try:
        eb = json.loads(r["model_e_bet_json"])
    except (TypeError, ValueError):
        continue
    if not eb or r["home_won"] is None or pd.isna(r["home_won"]):
        continue
    gpk = r.get("game_pk")
    if gpk not in feats.index:
        continue
    g = model_e.grade_bet(eb, bool(r["home_won"]))
    dec = model_e.american_to_decimal(eb.get("best_price"))
    if dec is None:
        continue
    bets.append({"game_pk": gpk, "side_home": bool(eb.get("side_is_home")),
                 "won": bool(g["won"]), "flat": (dec - 1.0) if g["won"] else -1.0})
bdf = pd.DataFrame(bets)
print(f"settled live bets with feature rows: {len(bdf)}")

# full-history reference: win rate of the team with the edge, and what the market expected
hist = feats_all[feats_all["home_win"].notna()].drop_duplicates("game_pk")
hy = hist["home_win"].astype(int).values
hmkt = (0.5 + hist["consensus_prob_diff"]).values

rows = []
for c in CANDS:
    v = bdf["game_pk"].map(feats[c])
    edge = np.where(bdf["side_home"], v > 0, v < 0)
    ok = v.notna().values
    ye, no = bdf[ok & edge], bdf[ok & ~edge]
    if len(ye) < 20 or len(no) < 20:
        continue
    # historical: does the edge side beat the market at all?
    hv = hist[c].values
    hok = ~np.isnan(hv) & ~np.isnan(hmkt)
    h_win = np.concatenate([hy[hok & (hv > 0)], 1 - hy[hok & (hv < 0)]])
    h_mkt = np.concatenate([hmkt[hok & (hv > 0)], 1 - hmkt[hok & (hv < 0)]])
    rows.append({
        "feature": c,
        "live_edge_n": len(ye), "live_edge_win": 100 * ye["won"].mean(), "live_edge_roi": 100 * ye["flat"].mean(),
        "live_noedge_roi": 100 * no["flat"].mean(),
        "live_gap": 100 * (ye["flat"].mean() - no["flat"].mean()),
        "hist_win_minus_mkt": 100 * (h_win.mean() - h_mkt.mean()),
    })

out = pd.DataFrame(rows).sort_values("live_gap", ascending=False)
pd.set_option("display.width", 200)
print()
print("split: bets where OUR SIDE had the edge on this stat vs bets where it did not")
print(f"{'feature':<38}{'n✓':>4}{'win✓':>7}{'ROI✓':>8}{'ROI✗':>8}{'gap':>8}  hist(win-mkt)")
for _, r in out.iterrows():
    print(f"{r['feature']:<38}{r['live_edge_n']:>4.0f}{r['live_edge_win']:>6.1f}%{r['live_edge_roi']:>+7.1f}%{r['live_noedge_roi']:>+7.1f}%{r['live_gap']:>+7.1f}%  {r['hist_win_minus_mkt']:+.2f} pts")
print()
print(f"noise: one group of ~55 bets has a ±27-pt band; a 'gap' needs ~±37 pts to clear noise on its own.")
