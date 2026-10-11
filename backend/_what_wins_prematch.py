"""PARTS B AND C of "what stats mattered most for the wins" (2026-10-10).

Part A measured stats INSIDE the match and found the hold/break battle decides it (the winner
held the better hold% in 94.0% of 167,013 matches) while first-serve percentage barely matters
(55.8%). That is descriptive. These two parts ask the questions that can actually be used.

  PART B -- PRE-MATCH PREDICTION. Each stat measured BEFORE the match (52-week-on-surface
    window, last-10 form, etc., always as dog-minus-favourite), scored by AUC: the probability
    that the stat ranks the actual winner above the loser. 50% = no information.

  PART C -- BEYOND THE PRICE. Part B rewards stats the market has already priced, which pays
    nothing. Part C sorts each stat into terciles inside the price band and reports the ROI of
    backing the dog in the top vs the bottom -- the spread is what the stat is worth AFTER the
    market has spoken.

Universe: the Model P rows -- market dogs at +100..+250 with the favourite priced accordingly,
2022-26, the band the board actually bets. Stated plainly because it is a slice, not all tennis.
"""
import numpy as np
import pandas as pd

D = pd.read_parquet("data_cache/_model_p250_rows.parquet")
D["won"] = D["won"].astype(bool)
D["date"] = pd.to_datetime(D["date"])

#: pre-match stat -> readable name. All are dog-minus-favourite.
NAMES = {
    "d_c_sgw": "hold% (52w on surface)",
    "d_c_rgw": "break% (52w on surface)",
    "d_c_sp": "serve pressure-pt% (52w)",
    "d_c_rp": "return pressure-pt% (52w)",
    "d_c_bpsav": "BP saved% (52w)",
    "d_c_bpconv": "BP converted% (52w)",
    "d_c_bpcre_pg": "BP earned per return gm",
    "d_c_bpdef_pg": "BP faced per service gm",
    "d_c_aces_pg": "aces per service gm",
    "d_c_dfs_pg": "DFs per service gm",
    "d_c_tb": "tiebreak win% (52w)",
    "d_m_first_serve_accuracy": "1st serve in% (52w)",
    "d_m_first_serve_points": "1st serve won% (52w)",
    "d_m_second_serve_points": "2nd serve won% (52w)",
    "d_m_return_1st_serve_points": "return vs 1st% (52w)",
    "d_m_return_2nd_serve_points": "return vs 2nd% (52w)",
    "d_m_won": "win rate (52w on surface)",
    "d_m_perf": "vs-the-price record (52w)",
    "d_m_dr": "dominance ratio (52w)",
    "d_m_meff": "games-won share (52w)",
    "d_t10_win": "last-10 win rate",
    "d_t10_faced": "level of opponents faced (L10)",
    "d_t10_beaten": "level of opponents BEATEN (L10)",
    "d_t10_bestwin": "best win in last 10",
    "d_t10_losscl": "how close the losses were (L10)",
    "d_form_win": "form vs own 52w baseline",
    "d_vs_band": "record vs this calibre of foe",
    "d_sutr": "court-UTR gap",
    "d_lrank": "ranking gap",
    "d_rest": "days of rest",
    "d_sn_win": "win rate this season",
    "d_hold": "hold% (last 10)",
    "d_break": "break% (last 10)",
}
FEATS = [c for c in NAMES if c in D.columns]
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
if "G" not in D.columns:
    D["G"] = D.player_slug.astype(str).map(GM)
print(f"universe: {len(D)} market dogs +100..+250, {D.date.min().date()}..{D.date.max().date()}"
      f"  men {int((D.G == 'M').sum())}  women {int((D.G == 'W').sum())}")
print(f"base rate: the dog wins {100 * D.won.mean():.1f}% of them\n")


def auc(x, y):
    """P(stat ranks a winner above a loser), ties split. Rank-based, so monotone-invariant."""
    m = pd.notna(x)
    x, y = np.asarray(x)[m], np.asarray(y)[m].astype(bool)
    n1, n0 = int(y.sum()), int((~y).sum())
    if n1 < 30 or n0 < 30:
        return np.nan, 0
    r = pd.Series(x).rank().values
    return (r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0), n1 + n0


def roi(s):
    return 100 * np.where(s.won.values, s.player_odd.values - 1, -1).mean()


print("=" * 94)
print("PART B -- PRE-MATCH: how well does each stat alone pick the winner?")
print("=" * 94)
print("   AUC 50% = no information. Above 50% means a higher value really does mean the dog")
print("   is more likely to win. Measured on the SAME rows for every stat where available.\n")
rows = []
for f in FEATS:
    a_all, n_all = auc(D[f], D.won)
    a_m, _ = auc(D.loc[D.G == "M", f], D.loc[D.G == "M", "won"])
    a_w, _ = auc(D.loc[D.G == "W", f], D.loc[D.G == "W", "won"])
    if not np.isnan(a_all):
        rows.append((NAMES[f], 100 * a_all, 100 * a_m, 100 * a_w, n_all, f))
rows.sort(key=lambda r: -abs(r[1] - 50))
print(f"   {'stat (dog minus favourite)':32s} {'AUC':>7s} {'men':>7s} {'women':>7s} {'n':>8s}")
for nm, a, am, aw, n, f in rows:
    print(f"   {nm:32s} {a:6.1f}% {am:6.1f}% {aw:6.1f}% {n:8d}")
# the market itself, for scale
am_, _ = auc(D.mkt, D.won)   # mkt is the DOG's implied prob: higher = dog more likely
print(f"\n   {'>>> THE MARKET PRICE itself':32s} {100 * am_:6.1f}%   <- the bar every stat is up against")

print("\n" + "=" * 94)
print("PART C -- BEYOND THE PRICE: ROI of backing the dog, top vs bottom tercile of each stat")
print("=" * 94)
print("   Inside the band the market has already judged these matches. If a stat still sorts")
print("   outcomes, the top tercile must beat the bottom. Flat 1u on the dog at closing odds.\n")
out = []
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    S = D[D.G == G]
    base = roi(S)
    print(f"   {gl}  -- backing EVERY dog in the band: {base:+.1f}% (n={len(S)})")
    res = []
    for nm, a, am2, aw2, n, f in rows:
        s = S[S[f].notna()]
        if len(s) < 600:
            continue
        q = s[f].quantile([1 / 3, 2 / 3]).values
        lo, hi = s[s[f] <= q[0]], s[s[f] >= q[1]]
        if min(len(lo), len(hi)) < 200:
            continue
        res.append((nm, roi(hi), roi(lo), roi(hi) - roi(lo), len(hi), len(lo)))
    res.sort(key=lambda r: -r[3])
    print(f"      {'stat':32s} {'top 3rd':>9s} {'bottom':>9s} {'spread':>8s} {'n top':>7s}")
    for nm, rh, rl, sp, nh, nl in res:
        print(f"      {nm:32s} {rh:+8.1f}% {rl:+8.1f}% {sp:+7.1f} {nh:7d}")
    out.append((gl, res))

print("\n" + "=" * 94)
print("WHICH STATS SURVIVE BOTH GENDERS (a real effect should not flip sign)")
print("=" * 94)
mm = {nm: sp for nm, _, _, sp, _, _ in out[0][1]}
ww = {nm: sp for nm, _, _, sp, _, _ in out[1][1]}
both = [(nm, mm[nm], ww[nm]) for nm in mm if nm in ww]
both.sort(key=lambda r: -(min(r[1], r[2])))
print(f"   {'stat':32s} {'men spread':>11s} {'women spread':>13s} {'weaker side':>12s}")
for nm, a, b in both[:12]:
    print(f"   {nm:32s} {a:+10.1f} {b:+12.1f} {min(a, b):+11.1f}")
print("\n   (positive on BOTH = the top tercile beat the bottom for men and women alike)")
