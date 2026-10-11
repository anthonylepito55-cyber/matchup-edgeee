"""WHICH STATS ACTUALLY SEPARATE WINNERS FROM LOSERS (2026-10-10, user ask: "look through a
bunch of tennis matches and look at who won and what stats mattered the most for the wins").

Three different questions, answered separately because they have different answers:

  PART A -- IN-MATCH. Across every match where the archive holds BOTH sides, compare the
    winner's number against the loser's. The headline metric is the share of matches in which
    the winner had the better figure, which is the same thing as the AUC of that single stat
    and needs no units. This is descriptive, not predictive: some of it is near-tautological
    (whoever won more games won), but the RANKING tells you which parts of a match decide it.
    Uses tennis_archive with require_mirror=True -- this is exactly the job the guard exists
    for, since pairing winner against loser needs both rows.

  PART B -- PRE-MATCH. The same families measured BEFORE the match (52-week-on-surface and
    last-10 form diffs), scored on how well each one alone picks the winner.

  PART C -- BEYOND THE PRICE. Part B ranks stats by predicting the winner, which the market
    already does. Part C asks the only question that pays: within a price band, does the stat
    still separate outcomes once the market has spoken?
"""
import numpy as np
import pandas as pd

import tennis_archive as TA

RAW = ["first_serve_accuracy", "first_serve_points", "second_serve_points",
       "return_1st_serve_points", "return_2nd_serve_points", "aces", "double_faults",
       "serve_pressure_all", "serve_pressure_won", "return_pressure_all",
       "return_pressure_won", "service_games_won", "return_games_won",
       "breakpoints_saved_count", "breakpoints_converted_count", "surface",
       "tournament_level", "round", "score"]


def frac(s):
    p = s.astype(str).str.extract(r"^(\d+)/(\d+)$")
    return pd.to_numeric(p[0], errors="coerce"), pd.to_numeric(p[1], errors="coerce")


def build():
    df = TA.load(columns=RAW, require_mirror=True, with_flags=False, verbose=True)
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

    # the stat set, each as a rate so the two sides are comparable
    df["hold%"] = r(df.sg_w, df.sg_a)
    df["break%"] = r(df.rg_w, df.rg_a)
    df["1st serve in%"] = df.first_serve_accuracy
    df["1st serve won%"] = df.first_serve_points
    df["2nd serve won%"] = df.second_serve_points
    df["ret vs 1st%"] = df.return_1st_serve_points
    df["ret vs 2nd%"] = df.return_2nd_serve_points
    df["BP saved%"] = r(df.bps_w, df.bps_a)
    df["BP converted%"] = r(df.bpc_w, df.bpc_a)
    df["BP faced /svc gm"] = r(df.bps_a, df.sg_a, 1.0)
    df["BP earned /ret gm"] = r(df.bpc_a, df.rg_a, 1.0)
    df["aces /svc gm"] = r(df.aces, df.sg_a, 1.0)
    df["DFs /svc gm"] = r(df.double_faults, df.sg_a, 1.0)
    df["svc pressure won%"] = r(df.serve_pressure_won, df.serve_pressure_all)
    df["ret pressure won%"] = r(df.return_pressure_won, df.return_pressure_all)
    # serve points won overall, and the two summary ratios Model C/D use
    svp = (df["1st serve won%"] * df["1st serve in%"]
           + df["2nd serve won%"] * (100 - df["1st serve in%"])) / 100.0
    rtp = (df["ret vs 1st%"] + df["ret vs 2nd%"]) / 2.0
    df["serve pts won%"] = svp
    df["return pts won%"] = rtp
    df["dominance ratio"] = (rtp / (100 - svp).clip(1)).clip(0, 5)
    df["games won share"] = r(df.sg_w + df.rg_w, (df.sg_a + df.rg_a))
    df["total pts margin"] = svp + rtp - 100          # >0 means won more points than lost
    return df


STATS = ["games won share", "total pts margin", "dominance ratio", "break%", "hold%",
         "ret pressure won%", "svc pressure won%", "return pts won%", "serve pts won%",
         "BP converted%", "BP saved%", "BP earned /ret gm", "BP faced /svc gm",
         "ret vs 1st%", "ret vs 2nd%", "1st serve won%", "2nd serve won%",
         "1st serve in%", "aces /svc gm", "DFs /svc gm"]
#: stats where a LOWER number is better
LOWER_BETTER = {"BP faced /svc gm", "DFs /svc gm"}

df = build()
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
df["G"] = df.player_slug.map(GM)
df["won"] = df.result.eq("Win")
df["lvl"] = df.tournament_level.astype(str)
df["surf"] = df.surface.astype(str).str.title().replace({"I.Hard": "Hard", "Carpet": "Hard"})
# one row per match per side -> pair them
lo = np.minimum(df.player_slug.values, df.rival_slugname.values)
hi = np.maximum(df.player_slug.values, df.rival_slugname.values)
df["mid"] = df.date.astype(str) + "|" + lo + "|" + hi
W = df[df.won].drop_duplicates("mid").set_index("mid")
L = df[~df.won].drop_duplicates("mid").set_index("mid")
common = W.index.intersection(L.index)
W, L = W.loc[common], L.loc[common]
print(f"\nmatches with both sides AND a winner/loser pair: {len(common)}")
print(f"   {W.date.min().date()}..{W.date.max().date()}  "
      f"men {int((W.G == 'M').sum())}  women {int((W.G == 'W').sum())}")


def table(mask=None, label="", floor=400):
    w, l = (W[mask], L[mask]) if mask is not None else (W, L)
    if len(w) < floor:
        print(f"\n{label}: n={len(w)} (thin)")
        return
    rows = []
    for s in STATS:
        a, b = pd.to_numeric(w[s], errors="coerce"), pd.to_numeric(l[s], errors="coerce")
        m = a.notna() & b.notna()
        if m.sum() < floor:
            continue
        a, b = a[m], b[m]
        d = (b - a) if s in LOWER_BETTER else (a - b)
        ties = float((a.values == b.values).mean())
        share = float((d > 0).mean() + 0.5 * ties)   # AUC, ties split
        rows.append((s, 100 * share, float(d.mean()), float(d.mean() / d.std()), int(m.sum())))
    rows.sort(key=lambda r: -r[1])
    print(f"\n{label}  (n={len(w)} matches)")
    print(f"   {'stat':22s} {'winner better':>14s} {'avg edge':>10s} {'effect':>8s} {'n':>8s}")
    for s, sh, mn, ef, n in rows:
        arrow = " (lower)" if s in LOWER_BETTER else ""
        print(f"   {s + arrow:22s} {sh:13.1f}% {mn:+10.2f} {ef:+8.2f} {n:8d}")
    return rows


print("\n" + "=" * 82)
print("PART A -- IN-MATCH: how often did the winner hold the better number?")
print("=" * 82)
print("   'winner better' = share of matches where the winner's figure was the better one")
print("   (ties split). 50% means the stat says nothing about who won.")
table(None, "ALL MATCHES")
table((W.G == "M").values, "MEN")
table((W.G == "W").values, "WOMEN")
for sf in ("Hard", "Clay", "Grass"):
    table((W.surf == sf).values, f"SURFACE: {sf}", floor=300)
for lv in ("ATP", "WTA", "Challengers", "Futures", "Grand Slams"):
    table((W.lvl == lv).values, f"LEVEL: {lv}", floor=300)
print("\n" + "=" * 82)
print("CLOSE MATCHES ONLY -- decided in 3 sets, where the margins actually matter")
print("=" * 82)
sets3 = W.score.astype(str).str.count(r"\d+-\d+").ge(3).values
table(sets3, "THREE-SET MATCHES")
