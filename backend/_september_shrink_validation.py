"""September favorite-shrink: design + validation (user call 2026-09-07 "start sept fix").

Diagnosis (see _heavy_fav_diagnostic.py + ablation session): in the post-deadline regime the
model's roster-built baseball features scream for favorites while the market prices September
context the features cannot see; the model's fav-side overshoot is real overconfidence, not a
plumbing bug. Fix: p' = mkt + LAMBDA * (p - mkt), applied ONLY when the model exceeds the
market ON THE FAVORITE side -- dog flips and market-side leans untouched.

Validation (pre-registered):
  1. LIVE replay: all settled games since 8/20 (frozen probs + frozen consensus -- true
     forward inputs), menu re-run with p' at each lambda, graded at consensus minus 3.5% vig.
     Bar: overall ROI improves vs lambda=1.
  2. Season-replay non-regression: same rule on the 2026 OOF probs (regime mostly absent).
     Bar: neither half worse by more than 1 pt.
Decision rule fixed in advance: ship the LARGEST lambda (least intervention) passing both.
"""
import numpy as np
import pandas as pd

import model_e

VIG = 0.035
EC2_LOG = r"C:\Users\ACTSL~1.DES\AppData\Local\Temp\claude\C--Users-actsl-DESKTOP-5CTNC21-OneDrive-Documents-Desktop-mlb-predictor\1526a1fa-20df-4322-a22b-68bd03e256ae\scratchpad\ec2_log_fresh.parquet"


def shrink(p, mkt, lam):
    fav_home = mkt >= 0.5
    p_fav = p if fav_home else 1 - p
    m_fav = mkt if fav_home else 1 - mkt
    if p_fav > m_fav:  # model exceeds market on the favorite side -> damp
        p_fav = m_fav + lam * (p_fav - m_fav)
    return p_fav if fav_home else 1 - p_fav


def replay(games, lam):
    pnl = []
    n_fav = n_dog = 0
    for p, mkt, won_home in games:
        bt = model_e.compute_bet(shrink(p, mkt, lam), mkt, "H", "A")
        if not bt:
            continue
        dec = (1.0 / bt["market_prob"]) * (1 - VIG)
        won = won_home if bt["side_is_home"] else not won_home
        pnl.append((dec - 1.0) if won else -1.0)
        n_fav += bt["type"] == "favorite"
        n_dog += bt["type"] == "underdog"
    roi = 100 * np.mean(pnl) if pnl else float("nan")
    return roi, len(pnl), n_fav, n_dog


log = pd.read_parquet(EC2_LOG)
l = log[(log["settled"] == True) & log["model_e_prob"].notna()  # noqa: E712
        & log["market_home_prob"].notna() & log["home_won"].notna()].sort_values("date")
live = list(zip(l["model_e_prob"].astype(float), l["market_home_prob"].astype(float), l["home_won"].astype(bool)))
half = len(live) // 2
print(f"LIVE frozen games since 8/20: {len(live)}  (menu includes the shipped 6-pt heavy bar)")
print(f"{'lambda':>7}{'live all':>12}{'1st half':>12}{'2nd half':>12}{'bets':>6}{'favs':>6}{'dogs':>6}")
for lam in (1.0, 0.8, 0.65, 0.5):
    r_all, n, nf, nd = replay(live, lam)
    r1, n1, _, _ = replay(live[:half], lam)
    r2, n2, _, _ = replay(live[half:], lam)
    print(f"{lam:>7}{r_all:>+11.1f}%{r1:>+11.1f}%{r2:>+11.1f}%{n:>6}{nf:>6}{nd:>6}")

df = pd.read_parquet("data_cache/training_dataset.parquet").drop_duplicates("game_pk").sort_values("game_date")
oof = pd.read_parquet("data_cache/model_e_oof_2026.parquet").drop_duplicates("game_pk").set_index("game_pk")
df["p"] = df["game_pk"].map(oof["p_e"])
df["mkt"] = 0.5 + df["consensus_prob_diff"]
r = df[df["p"].notna() & df["mkt"].notna() & df["home_win"].notna()]
rep = list(zip(r["p"], r["mkt"], r["home_win"].astype(bool)))
halfr = len(rep) // 2
print(f"\nSEASON REPLAY non-regression ({len(rep)} games):")
print(f"{'lambda':>7}{'1st half':>12}{'2nd half':>12}{'bets':>6}")
for lam in (1.0, 0.8, 0.65, 0.5):
    r1, n1, _, _ = replay(rep[:halfr], lam)
    r2, n2, _, _ = replay(rep[halfr:], lam)
    print(f"{lam:>7}{r1:>+11.1f}%{r2:>+11.1f}%{n1 + n2:>6}")
print("\ndecision rule (pre-registered): largest lambda improving LIVE overall with neither replay half worse by >1 pt")
