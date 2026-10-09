"""Follow-up to _season_2026_dossier.py: the dossier's FAVOURITE-side positives (stat bottom
fifth for the dog -> favourite ROI > 0). Year-by-year fav ROI, the cutoff values, fav price
bands, and a stacked "2+ fire" cell. Cutoffs are fixed from 2026 quantiles and then applied
unchanged to 2025, same as the dossier."""
import numpy as np
import pandas as pd

D = pd.read_parquet("data_cache/_season_2026_dossier_rows.parquet")
D["fav_am"] = np.where(D.rival_odd >= 2, (D.rival_odd - 1) * 100, -100 / (D.rival_odd - 1))
CELLS = [("d_vs_band", "low"), ("gapm_C", "low"), ("gap_C", "low"), ("gapm_D", "low"),
         ("d_m_won", "low"), ("d_form_win", "high"), ("d_m_perf", "low")]


def rep(s):
    if len(s) < 40:
        return f"n={len(s)} (thin)"
    fw = ~s.won
    p = np.where(fw, s.rival_odd - 1, -1.0)
    return f"{int(fw.sum())}-{int((~fw).sum())} fav win {100*fw.mean():4.1f}% vs mkt {100*(1-s.mkt.mean()):4.1f} favROI {100*p.mean():+6.1f}% (n={len(s)})"


for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    S = D[D.G == G].copy()
    S6 = S[S.yr == 2026]
    flags = []
    print(f"\n==================== {gl} ====================")
    for f, end in CELLS:
        q = S6[f].dropna().quantile(0.2 if end == "low" else 0.8)
        m = (S[f] <= q) if end == "low" else (S[f] >= q)
        S[f"x_{f}"] = m & S[f].notna()
        flags.append(f"x_{f}")
        print(f"\n  {f} {end} fifth (cut {q:+.3f})")
        for y in (2025, 2026):
            T = S[S[f"x_{f}"] & (S.yr == y)]
            print(f"    {y} all fav prices     {rep(T)}")
            print(f"    {y} fav -100..-200     {rep(T[T.fav_am.between(-200, -100)])}")
            print(f"    {y} fav -200..-400     {rep(T[T.fav_am.between(-400, -200)])}")
    S["nfire"] = S[flags].sum(axis=1)
    print("\n  STACK: how many of these favourite cells fire")
    for k in (0, 1, 2, 3, 4):
        for y in (2025, 2026):
            T = S[(S.nfire == k) if k < 4 else (S.nfire >= 4)]
            T = T[T.yr == y]
            print(f"    {k}{'+' if k == 4 else ' '} cells {y}: all {rep(T)} | fav -100..-250 {rep(T[T.fav_am.between(-250, -100)])}")
