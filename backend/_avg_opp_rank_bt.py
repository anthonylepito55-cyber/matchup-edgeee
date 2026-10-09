"""AVERAGE-OPPONENT-RANK GAP (2026-10-09, user: "what if avg opponent is over 100 ranks
higher than who they're playing"). Each player's average opponent rank over the last 52
weeks on the surface (geometric mean of rival rank, the archive's m_logr -- the closest
replay of the card's TennisRatio 'avg opp #'). Gap = favourite's avg opp rank - dog's avg
opp rank (+ = the DOG has faced tougher opponents). One row per match (dog side), true
gender, 2024-26 closing odds."""
import numpy as np
import pandas as pd
ns = {}
src = open("_tennis_abc6_agree_bt.py", encoding="utf-8").read()
exec(compile(src.split("from sklearn.linear_model")[0].split("nb = {}")[0], "_k", "exec"), ns)
ncc = {}
srcc = open("_tennis_model_c_build.py", encoding="utf-8").read()
exec(compile(srcc.split("from sklearn.linear_model")[0], "_c_prep", "exec"), ncc)
m = ncc["m"]
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
m = m[(m["date"].dt.year >= 2024) & m["mkt"].notna() & (m["mkt"] < 0.5) & (m["player_odd"] > 1) & (m["rival_odd"] > 1)
      & m["m_logr"].notna() & m["o_m_logr"].notna()].copy()
m["G"] = m["player_slug"].astype(str).map(GM)
m = m[m.G.isin(["M", "W"])].drop_duplicates(["date", "player_slug", "rival_slugname"])
m["dog_opp"] = np.exp(m["m_logr"]); m["fav_opp"] = np.exp(m["o_m_logr"])
m["gap"] = m["fav_opp"] - m["dog_opp"]              # + = dog faced tougher (lower-numbered) opponents
m["won"] = m["won"].astype(bool); m["yr"] = m["date"].dt.year
m["dog_am"] = (m["player_odd"] - 1) * 100
m.to_parquet("data_cache/_avg_opp_rank_rows.parquet")
def rep(s, side="dog", f=40):
    n = len(s)
    if n < f: return f"n={n} (thin)"
    w = s.won if side == "dog" else ~s.won
    o = s.player_odd if side == "dog" else s.rival_odd
    return f"{int(w.sum())}-{n-int(w.sum())} win {100*w.mean():4.1f}% ROI {100*np.where(w, o-1, -1).mean():+6.1f}% (n={n})"
B = [(100, 1e9, "DOG faced tougher by 100+ ranks"), (50, 100, "dog tougher by 50-100"), (-50, 50, "similar (within 50)"),
     (-100, -50, "fav tougher by 50-100"), (-1e9, -100, "FAV faced tougher by 100+ ranks")]
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    for lab0, T in (("all dog prices", m[m.G == G]), ("dog +100..+250", m[(m.G == G) & m.dog_am.between(100, 250)])):
        print(f"\n{gl} {lab0}: every dog {rep(T)}")
        for lo, hi, lab in B:
            s = T[(T.gap > lo) & (T.gap <= hi)]
            print(f"   {lab:32s} back DOG {rep(s)} | back FAV {rep(s, 'fav')}")
        s = T[T.gap > 100]; print("   dog tougher 100+, by year: " + " | ".join(f"{y} {rep(s[s.yr == y], 'dog', 20)}" for y in (2024, 2025, 2026)))
        s = T[T.gap < -100]; print("   fav tougher 100+, back FAV by year: " + " | ".join(f"{y} {rep(s[s.yr == y], 'fav', 20)}" for y in (2024, 2025, 2026)))
