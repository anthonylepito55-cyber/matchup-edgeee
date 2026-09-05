"""Live-bet split (user ask 9/4): of the REAL settled Model E bets, how did the ones where
our bet side had BOTH a better starter WHIP and a better bullpen (pre-game values) do?

Uses only the forward log's frozen bets (side, price, stake, outcome as logged before first
pitch) joined to the walk-forward feature rows for whip_diff / bullpen_fip_diff (both are
positive = home team better, computed from stats as of the morning of the game -- the same
values the model saw). No backtest bets anywhere.
"""
import json

import pandas as pd

import model_e

# the LIVE log from the EC2 box (pulled fresh) -- the local one can lag the real record
EC2_LOG = r"C:\Users\ACTSL~1.DES\AppData\Local\Temp\claude\C--Users-actsl-DESKTOP-5CTNC21-OneDrive-Documents-Desktop-mlb-predictor\1526a1fa-20df-4322-a22b-68bd03e256ae\scratchpad\ec2_prediction_log.parquet"
log = pd.read_parquet(EC2_LOG)
settled = log[(log["settled"] == True) & log["model_e_bet_json"].notna()]  # noqa: E712

feats = pd.read_parquet("data_cache/training_dataset.parquet")
feats = feats.drop_duplicates("game_pk").set_index("game_pk")[["whip_diff", "bullpen_fip_diff"]]

rows = []
missing = 0
for _, r in settled.iterrows():
    try:
        bet = json.loads(r["model_e_bet_json"])
    except (TypeError, ValueError):
        continue
    if not bet or r["home_won"] is None or pd.isna(r["home_won"]):
        continue
    gpk = r.get("game_pk")
    if gpk not in feats.index:
        missing += 1
        continue
    w, b = feats.loc[gpk, "whip_diff"], feats.loc[gpk, "bullpen_fip_diff"]
    if pd.isna(w) or pd.isna(b):
        missing += 1
        continue
    side_home = bool(bet.get("side_is_home"))
    w_edge = (w > 0) if side_home else (w < 0)   # our side has the better starter WHIP
    b_edge = (b > 0) if side_home else (b < 0)   # our side has the better bullpen
    g = model_e.grade_bet(bet, bool(r["home_won"]))
    dec = model_e.american_to_decimal(bet.get("best_price"))
    if dec is None:
        continue
    rows.append({
        "date": r["date"], "matchup": f"{r['away_team_abbr']}@{r['home_team_abbr']}",
        "side": bet.get("side"), "type": bet.get("type"),
        "won": bool(g["won"]),
        "flat_profit": (dec - 1.0) if g["won"] else -1.0,
        "stake": bet.get("stake_units") or 0.0,
        "kelly_profit": g["profit_units"],
        "both": bool(w_edge and b_edge), "w_edge": bool(w_edge), "b_edge": bool(b_edge),
    })

df = pd.DataFrame(rows)
print(f"settled Model E bets matched to pre-game features: {len(df)} (skipped {missing} with no feature row)")


def show(m, label):
    d = df[m]
    if not len(d):
        print(f"{label}: n=0")
        return
    n = len(d)
    wr = d["won"].mean() * 100
    flat = d["flat_profit"].mean() * 100
    kroi = 100 * d["kelly_profit"].sum() / d["stake"].sum() if d["stake"].sum() else float("nan")
    noise = 200 / (n ** 0.5)
    print(f"{label}: n={n}  win {wr:.1f}%  flat ROI {flat:+.1f}%  Kelly-staked ROI {kroi:+.1f}%  (noise band ±{noise:.0f} pts)")


show(df["both"], "BOTH edges (starter WHIP + bullpen, our side)")
show(~df["both"], "everything else")
show(df["w_edge"] & ~df["b_edge"], "  starter WHIP edge only")
show(~df["w_edge"] & df["b_edge"], "  bullpen edge only")
show(~df["w_edge"] & ~df["b_edge"], "  neither edge")
print()
print("BOTH-edge bets, listed:")
for _, r in df[df["both"]].sort_values("date").iterrows():
    print(f"  {r['date']}  {r['matchup']:<9} {r['side']:<4} {r['type']:<9} {'WON ' if r['won'] else 'lost'}  flat {r['flat_profit']:+.2f}u")
