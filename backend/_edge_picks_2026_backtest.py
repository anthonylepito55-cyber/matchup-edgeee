"""Edge-picks strategy replayed over the 2026 season (user ask 9/6).

STRONG TEST BY CONSTRUCTION: the profile rules (E alone / agreement+edges good, consensus and
no-edges bad, co-fire excluded) were discovered on LIVE bets from 2026-08-20 onward. This
window (2026-03-25 -> 08-18) shares ZERO games with that discovery sample -- if the structure
holds here, it's real out-of-sample evidence, not curve-fit recall.

Replay: cached walk-forward OOF probs (E, h13, A, B, C), current menu, de-vigged close minus
3.5% vig, flat 1u. Profiles need all three of A/C/h13 present (same rule as live).
"""
import os

import numpy as np
import pandas as pd

import model_e
from build_training_data import TRAINING_CACHE

VIG = 0.035
START = "2026-03-25"
_here = os.path.dirname(os.path.abspath(__file__))

df = pd.read_parquet(TRAINING_CACHE).sort_values("game_date").reset_index(drop=True)
df = df[df["home_win"].notna()].drop_duplicates("game_pk").reset_index(drop=True)
oof = pd.read_parquet(os.path.join(_here, "data_cache", "model_e_oof_2026.parquet")).drop_duplicates("game_pk").set_index("game_pk")
c_oof = pd.read_parquet(os.path.join(_here, "data_cache", "model_c_oof_with_market.parquet"))
c_oof = c_oof[c_oof["game_date"].astype(str) >= START].drop_duplicates("game_pk").set_index("game_pk")

df["p_e"] = df["game_pk"].map(oof["p_e"])
df["p_h"] = df["game_pk"].map(oof["p_h13"])
df["p_a"] = df["game_pk"].map(oof["p_a"])
df["p_c"] = df["game_pk"].map(c_oof["model_c_prob"])
df["mkt"] = 0.5 + df["consensus_prob_diff"]
w = df[(df["game_date"].astype(str) >= START) & df["mkt"].notna() & df["p_e"].notna()].reset_index(drop=True)
print(f"window {START}..{w['game_date'].astype(str).max()}: {len(w)} games (discovery sample was 8/20+ live -- no overlap)")

bets = []
for _, r in w.iterrows():
    bt = model_e.compute_bet(float(r["p_e"]), float(r["mkt"]), "H", "A")
    if not bt:
        continue
    sh = bool(bt["side_is_home"])
    # ours_agree: A, C, h13 through the same menu (require all three, like live)
    agree = avail = 0
    for p in (r["p_a"], r["p_c"], r["p_h"]):
        if pd.isna(p):
            continue
        avail += 1
        ob = model_e.compute_bet(float(p), float(r["mkt"]), "H", "A")
        if ob and ob.get("side_is_home") == sh:
            agree += 1
    # pen+whip
    pw = None
    if pd.notna(r["whip_diff"]) and pd.notna(r["bullpen_fip_diff"]):
        pw = bool(((r["whip_diff"] > 0) if sh else (r["whip_diff"] < 0))
                  and ((r["bullpen_fip_diff"] > 0) if sh else (r["bullpen_fip_diff"] < 0)))
    # omega co-fire
    cof = False
    if pd.notna(r["p_h"]):
        op = model_e.compute_omega_prob(float(r["p_h"]), float(r["mkt"]))
        if op is not None:
            ob = model_e.compute_bet(op, float(r["mkt"]), "H", "A")
            cof = bool(ob and ob.get("side_is_home") == sh)
    dec = (1.0 / bt["market_prob"]) * (1 - VIG)
    won = bool(r["home_win"]) if sh else not bool(r["home_win"])
    prof = None
    if avail == 3:
        if agree == 0:
            prof = "e_alone"
        elif pw is not None:
            prof = ("consensus_pw" if pw else "consensus_nopw") if agree == 3 else ("agree_pw" if pw else "agree_nopw")
    bets.append({"prof": prof, "cof": cof, "pw": pw, "won": won, "flat": (dec - 1.0) if won else -1.0})
b = pd.DataFrame(bets)
print(f"E menu bets: {len(b)}  ({int(b['prof'].notna().sum())} with a full 3-model profile read)")


def show(m, lbl):
    x = b[m]
    n = len(x)
    if not n:
        print(f"  {lbl}: n=0")
        return
    print(f"  {lbl:<52} n={n:<4} win {100 * x['won'].mean():5.1f}%  ROI {100 * x['flat'].mean():+6.1f}%  (±{200 / np.sqrt(n):.0f})")


print("\nprofile cells, OUT-OF-SAMPLE (rules from live 8/20+, tested on 3/25-8/18):")
show(b["prof"] == "e_alone", "E alone")
show(b["prof"] == "agree_pw", "1-2 agree + both edges")
show(b["prof"] == "agree_nopw", "1-2 agree, no edges")
show(b["prof"] == "consensus_pw", "full consensus + edges")
show(b["prof"] == "consensus_nopw", "full consensus, no edges")
print("\nthe EDGE-PICKS portfolio vs what it excludes:")
winners = b["prof"].isin(["e_alone", "agree_pw"]) & ~b["cof"]
trims = (b["prof"] == "consensus_pw") & ~b["cof"]
show(winners, "TAB: winning profiles, not co-fired (full stake)")
show(trims, "TAB: breakeven cell, not co-fired (half stake)")
show(winners | trims, "TAB: everything it lists")
show(~(winners | trims) & b["prof"].notna(), "excluded (losing profiles + co-fired)")
# half-stake weighting
port = pd.concat([b[winners].assign(stk=1.0), b[trims].assign(stk=0.5)])
print(f"\n  portfolio as sized (full + half): {100 * (port['flat'] * port['stk']).sum() / port['stk'].sum():+.1f}% on {port['stk'].sum():.0f}u staked, {len(port)} bets")

# golden fade component (site model = A retro; both-edge team faded)
g = w[w["p_a"].notna()].copy()
pw_home = (g["whip_diff"] > 0) & (g["bullpen_fip_diff"] > 0)
pw_away = (g["whip_diff"] < 0) & (g["bullpen_fip_diff"] < 0)
has = (pw_home | pw_away)
p_pw = np.where(pw_home, g["p_a"], 1 - g["p_a"])
mkt_pw = np.where(pw_home, g["mkt"], 1 - g["mkt"])
win_pw = np.where(pw_home, g["home_win"], 1 - g["home_win"]).astype(float)
fade = has.values & (p_pw < 0.5)
dec = (1.0 / mkt_pw) * (1 - VIG)
pnl = np.where(win_pw > 0.5, dec - 1.0, -1.0)
print("\ngolden contrarian, same window:")
n = int(fade.sum())
print(f"  all fades: n={n}  win {100 * win_pw[fade].mean():.1f}%  ROI {100 * pnl[fade].mean():+.1f}%  (±{200 / np.sqrt(n):.0f})")
fd = fade & (mkt_pw < 0.5)
n = int(fd.sum())
print(f"  DOG wing:  n={n}  win {100 * win_pw[fd].mean():.1f}%  ROI {100 * pnl[fd].mean():+.1f}%  (±{200 / np.sqrt(n):.0f})")
