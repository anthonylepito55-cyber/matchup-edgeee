"""Every model on the site, run through the SAME current bet menu, on the LIVE log only
(user ask 9/4: all models, all signals, real forward data -- no backtests).

Frame: each model's probability was FROZEN in the log pre-game (the log has the primary
model back to 2026-07-10; B from 8/07, C from 8/18, E/h13 from 8/20-21). For every settled
row, apply the current menu (fav >= 3 pts, dog flip >= 6 pts vs the frozen de-vigged market)
to the frozen probability, grade at the best logged book price (falling back to the de-vigged
consensus minus 3.5% vig when book odds were not logged yet -- pre-8/18 rows).

The only bets that are ALSO a real diary are Model E's (its slip was actually displayed).
The other models' menu records here are "what if this model's frozen number had been bet"
-- honest forward data (nothing recomputed), but nobody was following them, so no line-move
or first-seen story exists for them.
"""
import json

import numpy as np
import pandas as pd

import model_e

EC2_LOG = r"C:\Users\ACTSL~1.DES\AppData\Local\Temp\claude\C--Users-actsl-DESKTOP-5CTNC21-OneDrive-Documents-Desktop-mlb-predictor\1526a1fa-20df-4322-a22b-68bd03e256ae\scratchpad\ec2_prediction_log.parquet"
VIG = 0.035

log = pd.read_parquet(EC2_LOG)
log = log[(log["settled"] == True) & log["home_won"].notna() & log["market_home_prob"].notna()]  # noqa: E712
print(f"settled logged games with a frozen market: {len(log)}  ({log['date'].min()} -> {log['date'].max()})")

feats = pd.read_parquet("data_cache/training_dataset.parquet")
feats = feats.drop_duplicates("game_pk").set_index("game_pk")[["whip_diff", "bullpen_fip_diff"]]


def best_decimal(r, side_is_home):
    # UNIFORM grading for cross-model comparability: the frozen de-vigged consensus minus a
    # 3.5% vig haircut (the log's book_odds_json stores per-book devigged PROBS, not prices,
    # so a true best-price fill can't be reconstructed for every row). E's official record
    # at real logged best prices lives in /api/model-e-track-record; this report trades a
    # point or two of shopping edge for a level playing field.
    mp = float(r["market_home_prob"]) if side_is_home else 1 - float(r["market_home_prob"])
    return (1.0 / mp) * (1 - VIG), "consensus"


MODELS = [
    ("A (site primary, logged since 7/10)", "model_home_win_prob"),
    ("A raw (pre-override)", "raw_model_home_win_prob"),
    ("B (market-aware)", "market_model_prob"),
    ("C (6-book)", "model_c_prob"),
    ("E (betting model)", "model_e_prob"),
    ("h13 (E baseball leg)", "model_e_baseball_prob"),
]

all_bets = {}
for label, col in MODELS:
    rows = []
    for _, r in log[log[col].notna()].iterrows():
        p, mp = float(r[col]), float(r["market_home_prob"])
        bt = model_e.compute_bet(p, mp, "H", "A")
        if not bt:
            continue
        dec, src = best_decimal(r, bt["side_is_home"])
        won = bool(r["home_won"]) if bt["side_is_home"] else not bool(r["home_won"])
        gpk = r["game_pk"]
        pw = None
        if gpk in feats.index:
            w, b = feats.loc[gpk, "whip_diff"], feats.loc[gpk, "bullpen_fip_diff"]
            if pd.notna(w) and pd.notna(b):
                sh = bool(bt["side_is_home"])
                pw = bool(((w > 0) if sh else (w < 0)) and ((b > 0) if sh else (b < 0)))
        rows.append({"date": r["date"], "game_pk": gpk, "type": bt["type"], "dog_grade": bt.get("dog_grade"),
                     "side_home": bool(bt["side_is_home"]), "won": won,
                     "flat": (dec - 1.0) if won else -1.0, "pen_whip": pw})
    all_bets[label] = pd.DataFrame(rows)


def line(d, label, indent="  "):
    if d is None or not len(d):
        print(f"{indent}{label}: n=0")
        return
    n = len(d)
    print(f"{indent}{label:<34} n={n:<5} win {100 * d['won'].mean():5.1f}%  ROI {100 * d['flat'].mean():+6.1f}%  (±{200 / n ** 0.5:.0f})")


for label, _ in MODELS:
    d = all_bets[label]
    print(f"\n=== {label} ===")
    line(d, "all menu bets")
    if len(d):
        line(d[d["type"] == "favorite"], "favorites")
        line(d[d["type"] == "underdog"], "underdogs")
        line(d[d["pen_whip"] == True], "PEN+WHIP yes")  # noqa: E712
        line(d[d["pen_whip"] == False], "PEN+WHIP no")  # noqa: E712

# cross-model agreement on E's bets (the actual slip): how do E bets do when A / C / h13
# would fire the same side under the same menu?
e = all_bets["E (betting model)"]
if len(e):
    print("\n=== E bets split by which OTHER model's menu fires the same side ===")
    for other in ("A (site primary, logged since 7/10)", "C (6-book)", "h13 (E baseball leg)"):
        o = all_bets[other]
        if not len(o):
            continue
        key = o.set_index(["date", "game_pk"])["side_home"]
        agree = []
        for _, r in e.iterrows():
            k = (r["date"], r["game_pk"])
            agree.append(bool(k in key.index and key.loc[k] == r["side_home"]))
        e2 = e.assign(agree=agree)
        line(e2[e2["agree"]], f"{other.split(' ')[0]} fires same side")
        line(e2[~np.array(agree)], f"{other.split(' ')[0]} does not")
