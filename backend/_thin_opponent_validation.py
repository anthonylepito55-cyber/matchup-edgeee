"""Roster-churn fix, feature-aware version: THIN-OPPONENT rule (user call 2026-09-07).

Diagnosis recap: September favorite overshoot flows through roster-built baseball features;
the failed proportional shrink proved (p, mkt) space cannot separate real conviction from
churn blindness. The separator lives in the FEATURES: the flagship failure cases (SF@NYM,
Pecko, Jobe, Adams) all share one measurable trait -- the underdog's starter has a thin or
absent season track record, so the model's read on that side is a league-average guess and
its favorite edge is partly fiction.

RULE UNDER TEST (pre-registered): a FAVORITE bet whose opposing starter has under IP_THIN
season innings must clear the heavy bar (6 pts) regardless of price; variant B skips it
entirely. Missing IP counts as thin (no data = the purest guess).

VALIDATION (both samples are TRUE FORWARD data, frozen pre-game in the live log):
  discovery window: 8/20 -> now, frozen model_e_prob (where the problem was found)
  validation window: 7/10 -> 8/19, frozen model_home_win_prob (site model) -- never examined
    for this rule, structurally identical logging
Pre-registered bar: rule improves the DISCOVERY window and does not hurt the VALIDATION
window by more than 1 pt. Grading: current menu (incl. 6-pt heavy bar), consensus - 3.5% vig.
"""
import json

import numpy as np
import pandas as pd

import model_e

VIG = 0.035
IP_THIN = 40.0
EC2_LOG = r"C:\Users\ACTSL~1.DES\AppData\Local\Temp\claude\C--Users-actsl-DESKTOP-5CTNC21-OneDrive-Documents-Desktop-mlb-predictor\1526a1fa-20df-4322-a22b-68bd03e256ae\scratchpad\ec2_log_fresh.parquet"

log = pd.read_parquet(EC2_LOG)
log = log[(log["settled"] == True) & log["home_won"].notna() & log["market_home_prob"].notna()]  # noqa: E712


def opp_ip(r, side_is_home):
    try:
        ss = json.loads(r["season_stats_json"]) if pd.notna(r.get("season_stats_json")) else None
    except (TypeError, ValueError):
        return None
    if not ss:
        return None
    opp = ss.get("away" if side_is_home else "home") or {}
    return opp.get("ip")


def replay(rows, prob_col, mode):
    """mode: 'base' | 'require6' | 'skip'"""
    pnl, blocked = [], []
    for _, r in rows.iterrows():
        p, mkt = float(r[prob_col]), float(r["market_home_prob"])
        bt = model_e.compute_bet(p, mkt, "H", "A")
        if not bt:
            continue
        dec = (1.0 / bt["market_prob"]) * (1 - VIG)
        won = bool(r["home_won"]) if bt["side_is_home"] else not bool(r["home_won"])
        res = (dec - 1.0) if won else -1.0
        if bt["type"] == "favorite":
            ip = opp_ip(r, bt["side_is_home"])
            thin = (ip is None) or (float(ip) < IP_THIN)
            if thin and mode == "skip":
                blocked.append(res)
                continue
            if thin and mode == "require6" and bt["edge"] < 0.06:
                blocked.append(res)
                continue
        pnl.append(res)
    roi = 100 * np.mean(pnl) if pnl else float("nan")
    broi = 100 * np.mean(blocked) if blocked else float("nan")
    return roi, len(pnl), len(blocked), broi


for label, mask, col in (
    ("DISCOVERY: E-era 8/20+ (frozen model_e_prob)", (log["date"] >= "2026-08-20") & log["model_e_prob"].notna(), "model_e_prob"),
    ("VALIDATION: A-era 7/10-8/19 (frozen site model)", (log["date"] < "2026-08-20") & log["model_home_win_prob"].notna(), "model_home_win_prob"),
):
    rows = log[mask]
    print(f"\n{label}: {len(rows)} games")
    for mode in ("base", "require6", "skip"):
        roi, n, nb, broi = replay(rows, col, mode)
        extra = f"  (blocked {nb} bets that ran {broi:+.1f}%)" if nb else ""
        print(f"  {mode:<10} ROI {roi:+.1f}% on {n} bets{extra}")
print("\npre-registered bar: rule improves DISCOVERY and does not hurt VALIDATION by >1 pt; prefer require6 over skip if both pass (less intervention)")
