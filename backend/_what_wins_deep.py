"""WHAT POST-MATCH STATS LEAD TO A WIN -- the non-tautological version (2026-10-10).

The first pass ranked in-match stats by how often the winner held the better number and found
the hold/break battle at 94.0% of 167,013 matches. That is nearly definitional: winning more
service games IS most of winning. This pass asks the three questions that are not circular.

  1. THRESHOLDS -- what level of each stat actually wins? Win rate by band, so the numbers are
     usable rather than just ranked.
  2. POINTS vs CONVERSION -- how much of winning is winning more points, and how much is
     converting the points you win? Stage a model on serve/return point stats alone, then add
     the clutch layer (break points, pressure points, tiebreaks) and measure what it adds.
  3. THE TIGHT-MARGIN STUDY -- restrict to matches where BOTH players won almost exactly the
     same share of total points, where the raw-quality stats cancel by construction. Whatever
     separates the winner THERE is what actually converts an even match into a win.

Both sides of every match are required, so this runs through the mirror guard.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

import tennis_archive as TA

RAW = ["first_serve_accuracy", "first_serve_points", "second_serve_points",
       "return_1st_serve_points", "return_2nd_serve_points", "aces", "double_faults",
       "serve_pressure_all", "serve_pressure_won", "return_pressure_all",
       "return_pressure_won", "service_games_won", "return_games_won",
       "breakpoints_saved_count", "breakpoints_converted_count", "surface",
       "tournament_level", "score"]


def frac(s):
    p = s.astype(str).str.extract(r"^(\d+)/(\d+)$")
    return pd.to_numeric(p[0], errors="coerce"), pd.to_numeric(p[1], errors="coerce")


def build():
    df = TA.load(columns=RAW, require_mirror=True, verbose=True)
    for c in ("first_serve_accuracy", "first_serve_points", "second_serve_points",
              "return_1st_serve_points", "return_2nd_serve_points", "aces", "double_faults",
              "serve_pressure_all", "serve_pressure_won", "return_pressure_all",
              "return_pressure_won"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["sg_w"], df["sg_a"] = frac(df["service_games_won"])
    df["rg_w"], df["rg_a"] = frac(df["return_games_won"])
    df["bps_w"], df["bps_a"] = frac(df["breakpoints_saved_count"])
    df["bpc_w"], df["bpc_a"] = frac(df["breakpoints_converted_count"])

    def r(a, b, scale=100.0):
        return scale * a / b.replace(0, np.nan)

    df["hold"] = r(df.sg_w, df.sg_a)
    df["brk"] = r(df.rg_w, df.rg_a)
    df["breaks"] = df.rg_w
    df["bpsav"] = r(df.bps_w, df.bps_a)
    df["bpconv"] = r(df.bpc_w, df.bpc_a)
    df["bp_earned"] = r(df.bpc_a, df.rg_a, 1.0)
    df["bp_faced"] = r(df.bps_a, df.sg_a, 1.0)
    df["svcpr"] = r(df.serve_pressure_won, df.serve_pressure_all)
    df["retpr"] = r(df.return_pressure_won, df.return_pressure_all)
    df["svp"] = (df.first_serve_points * df.first_serve_accuracy
                 + df.second_serve_points * (100 - df.first_serve_accuracy)) / 100.0
    df["rtp"] = (df.return_1st_serve_points + df.return_2nd_serve_points) / 2.0
    df["ptshare"] = (df.svp + df.rtp) / 2.0          # ~share of all points won
    df["tb_w"] = df.score.astype(str).str.count(r"7-6")
    df["tb_n"] = df.tb_w + df.score.astype(str).str.count(r"6-7")
    df["won"] = df.result.eq("Win")
    return df


df = build()
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
df["G"] = df.player_slug.map(GM)
lo = np.minimum(df.player_slug.values, df.rival_slugname.values)
hi = np.maximum(df.player_slug.values, df.rival_slugname.values)
df["mid"] = df.date.astype(str) + "|" + lo + "|" + hi
W = df[df.won].drop_duplicates("mid").set_index("mid")
L = df[~df.won].drop_duplicates("mid").set_index("mid")
cm = W.index.intersection(L.index)
W, L = W.loc[cm], L.loc[cm]
print(f"matched matches: {len(cm)}  ({W.date.min().date()}..{W.date.max().date()})")

# ---------------------------------------------------------------- 1. THRESHOLDS
print("\n" + "=" * 90)
print("1. WHAT LEVEL ACTUALLY WINS -- win rate by band (every player-match, both sides)")
print("=" * 90)
A = pd.concat([W.assign(w=1), L.assign(w=0)])
BANDS = {
    "hold% (service games held)": ("hold", [0, 50, 60, 70, 75, 80, 85, 90, 95, 101]),
    "break% (return games won)": ("brk", [0, 5, 10, 15, 20, 25, 30, 40, 50, 101]),
    "breaks of serve (count)": ("breaks", [0, 1, 2, 3, 4, 5, 6, 8, 100]),
    "BP conversion%": ("bpconv", [0, 20, 30, 35, 40, 45, 50, 60, 101]),
    "BP saved%": ("bpsav", [0, 30, 40, 50, 55, 60, 65, 75, 101]),
    "points won%": ("ptshare", [0, 44, 46, 48, 49, 50, 51, 52, 54, 56, 101]),
    "1st serve in%": ("first_serve_accuracy", [0, 50, 55, 60, 65, 70, 75, 80, 101]),
    "aces (count)": ("aces", [0, 1, 2, 4, 6, 9, 13, 20, 500]),
}
for lab, (col, edges) in BANDS.items():
    s = A[A[col].notna()]
    g = s.groupby(pd.cut(s[col], edges, right=False), observed=True)["w"].agg(["mean", "size"])
    g = g[g["size"] >= 300]
    if g.empty:
        continue
    print(f"\n   {lab}")
    for iv, row in g.iterrows():
        bar = "#" * int(round(row["mean"] * 40))
        print(f"      {str(iv):>14s}  win {100 * row['mean']:5.1f}%  n={int(row['size']):7d}  {bar}")

# ---------------------------------------------------------------- 2. POINTS vs CONVERSION
print("\n" + "=" * 90)
print("2. HOW MUCH OF WINNING IS WINNING POINTS, AND HOW MUCH IS CONVERTING THEM?")
print("=" * 90)
PTS = ["first_serve_accuracy", "first_serve_points", "second_serve_points",
       "return_1st_serve_points", "return_2nd_serve_points", "aces", "double_faults"]
CLUTCH = ["bpconv", "bpsav", "bp_earned", "bp_faced", "svcpr", "retpr", "tb_w", "tb_n"]


def pair_frame(cols):
    d = (W[cols].astype(float) - L[cols].astype(float))
    d = d.dropna()
    # each match contributes once as winner-minus-loser (y=1) and once mirrored (y=0)
    X = pd.concat([d, -d]).values
    y = np.r_[np.ones(len(d)), np.zeros(len(d))]
    return X, y, len(d)


def auc_of(cols, label):
    X, y, n = pair_frame(cols)
    if n < 2000:
        print(f"   {label:46s} n={n} (thin)")
        return None
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1
    Xs = (X - mu) / sd
    m = LogisticRegression(max_iter=2000, C=1.0).fit(Xs, y)
    p = m.predict_proba(Xs)[:, 1]
    r = pd.Series(p).rank().values
    n1 = int(y.sum())
    a = (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * (len(y) - n1))
    print(f"   {label:46s} AUC {100 * a:5.1f}%   (n={n} matches)")
    return a, m, cols, mu, sd


print("   fitted on winner-minus-loser diffs, mirrored so the base rate is exactly 50%:")
a1 = auc_of(PTS, "serve/return POINT stats only")
a2 = auc_of(CLUTCH, "CLUTCH/conversion stats only")
a3 = auc_of(PTS + CLUTCH, "both together")
if a1 and a2 and a3:
    print(f"\n   points alone get you to {100 * a1[0]:.1f}%; adding the clutch layer takes it to "
          f"{100 * a3[0]:.1f}%  (+{100 * (a3[0] - a1[0]):.1f}pt)")
    print(f"   clutch ALONE is already {100 * a2[0]:.1f}% -- converting matters nearly as much "
          f"as winning points")
    print("\n   standardised weights in the combined model (bigger = more decisive):")
    _, m3, cols3, _, _ = a3
    for c, w in sorted(zip(cols3, m3.coef_[0]), key=lambda t: -abs(t[1])):
        print(f"      {c:28s} {w:+.3f}  {'#' * int(min(abs(w) * 12, 40))}")

# ---------------------------------------------------------------- 3. TIGHT MARGINS
print("\n" + "=" * 90)
print("3. THE TIGHT-MARGIN STUDY -- when both players won the SAME share of points,")
print("   what separated the winner? (this is the part that is not circular)")
print("=" * 90)
gap = (W.ptshare.astype(float) - L.ptshare.astype(float)).abs()
STATS = {"bpconv": "BP conversion%", "bpsav": "BP saved%", "svcpr": "serve pressure-pt%",
         "retpr": "return pressure-pt%", "bp_earned": "BPs earned /ret gm",
         "bp_faced": "BPs faced /svc gm", "tb_w": "tiebreaks won",
         "hold": "hold%", "brk": "break%", "aces": "aces", "double_faults": "double faults",
         "first_serve_accuracy": "1st serve in%", "svp": "serve pts won%",
         "rtp": "return pts won%"}
for lo_, hi_, lab in ((0, 0.5, "points won within 0.5pt -- a coin flip on raw quality"),
                      (0, 1.0, "points won within 1pt"),
                      (0, 2.0, "points won within 2pt")):
    m = ((gap >= lo_) & (gap < hi_)).values
    w, l = W[m], L[m]
    if len(w) < 500:
        continue
    print(f"\n   {lab}   (n={len(w)} matches)")
    res = []
    for c, nm in STATS.items():
        a, b = pd.to_numeric(w[c], errors="coerce"), pd.to_numeric(l[c], errors="coerce")
        k = a.notna() & b.notna()
        if k.sum() < 400:
            continue
        d = a[k] - b[k]
        ties = float((a[k].values == b[k].values).mean())
        res.append((nm, 100 * (float((d > 0).mean()) + 0.5 * ties), float(d.mean()), int(k.sum())))
    res.sort(key=lambda r: -abs(r[1] - 50))
    print(f"      {'stat':24s} {'winner better':>14s} {'avg edge':>10s} {'n':>8s}")
    for nm, sh, mn, n in res:
        print(f"      {nm:24s} {sh:13.1f}% {mn:+10.2f} {n:8d}")
