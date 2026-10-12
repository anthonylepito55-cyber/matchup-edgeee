"""SEASON-TO-DATE vs TRAILING 52 WEEKS (2026-10-11, user: "test this season stats vs 52 week
stats").

The card now shows pressure on the SEASON window and everything else on 52 WEEKS. That is an
inconsistency worth justifying or fixing, so this measures which window is actually better.

Both are computed on the same matches, same surface, same `.shift(1)` discipline, so the only
thing varying is the window:

    SEASON   calendar year to date, on this surface
    52W      trailing 365 days, on this surface

Three questions:
  A. which window picks the winner more often?
  B. which has the better EDGE against the no-vig line?
  C. where they DISAGREE, who is right? -- the decisive test, because agreement cells tell you
     nothing about which window to prefer

Note the structural difference: in January the season window is nearly empty while 52w is full,
so season is thinner on average and its advantage (if any) has to overcome that. The month
split at the end shows whether season only works late in the year.
"""
import numpy as np
import pandas as pd

import tennis_archive as TA

MIN_M = 6          # matches needed in a window before it is used


def frac(s):
    p = s.astype(str).str.extract(r"^(\d+)/(\d+)$")
    return pd.to_numeric(p[0], errors="coerce"), pd.to_numeric(p[1], errors="coerce")


df = TA.load(columns=["surface", "service_games_won", "return_games_won",
                      "first_serve_points", "second_serve_points",
                      "return_1st_serve_points", "return_2nd_serve_points",
                      "serve_pressure_all", "serve_pressure_won",
                      "return_pressure_all", "return_pressure_won", "tournament_level"],
             priced_only=True, require_mirror=True, verbose=False)
df["surf"] = df["surface"].astype(str).str.title().replace({"I.Hard": "Hard", "Carpet": "Hard"})
df["won"] = df["result"].eq("Win").astype(int)
df["sg_w"], df["sg_a"] = frac(df["service_games_won"])
df["rg_w"], df["rg_a"] = frac(df["return_games_won"])
for c in ("first_serve_points", "second_serve_points", "return_1st_serve_points",
          "return_2nd_serve_points", "serve_pressure_all", "serve_pressure_won",
          "return_pressure_all", "return_pressure_won"):
    df[c] = pd.to_numeric(df[c], errors="coerce")
df["yr"] = df["date"].dt.year
df = df.sort_values(["player_slug", "surf", "date"], kind="stable").reset_index(drop=True)

SUM = ["sg_w", "sg_a", "rg_w", "rg_a", "serve_pressure_all", "serve_pressure_won",
       "return_pressure_all", "return_pressure_won", "won"]
AVG = ["first_serve_points", "second_serve_points",
       "return_1st_serve_points", "return_2nd_serve_points"]

# ---- SEASON: cumulative within (player, surface, year), excluding this match
gs = df.groupby(["player_slug", "surf", "yr"], sort=False)
for c in SUM:
    df["S_" + c] = gs[c].cumsum() - df[c].fillna(0)
for c in AVG:
    df["S_" + c] = (gs[c].cumsum() - df[c].fillna(0)) / \
        (gs[c].cumcount()).replace(0, np.nan)
df["S_n"] = gs.cumcount()

# ---- 52W: trailing 40 matches on the surface as a stand-in for a year of play
g = df.groupby(["player_slug", "surf"], sort=False)
for c in SUM:
    df["W_" + c] = (g[c].shift(1).groupby([df.player_slug, df.surf])
                    .rolling(40, min_periods=MIN_M).sum().reset_index(level=[0, 1], drop=True))
for c in AVG:
    df["W_" + c] = (g[c].shift(1).groupby([df.player_slug, df.surf])
                    .rolling(40, min_periods=MIN_M).mean().reset_index(level=[0, 1], drop=True))
df["W_n"] = (g["won"].shift(1).groupby([df.player_slug, df.surf])
             .rolling(40, min_periods=MIN_M).count().reset_index(level=[0, 1], drop=True))


def build(pfx):
    o = pd.DataFrame(index=df.index)
    sg = df[pfx + "_sg_a"].replace(0, np.nan)
    rg = df[pfx + "_rg_a"].replace(0, np.nan)
    o["hold"] = 100 * df[pfx + "_sg_w"] / sg
    o["brk"] = 100 * df[pfx + "_rg_w"] / rg
    o["sv1"] = df[pfx + "_first_serve_points"]
    o["sv2"] = df[pfx + "_second_serve_points"]
    o["r1"] = df[pfx + "_return_1st_serve_points"]
    o["r2"] = df[pfx + "_return_2nd_serve_points"]
    o["svP"] = 100 * df[pfx + "_serve_pressure_won"] / \
        df[pfx + "_serve_pressure_all"].replace(0, np.nan)
    o["rtP"] = 100 * df[pfx + "_return_pressure_won"] / \
        df[pfx + "_return_pressure_all"].replace(0, np.nan)
    o["win%"] = 100 * df[pfx + "_won"] / df[pfx + "_n"].replace(0, np.nan)
    return o.add_prefix(pfx + "@")


STATS = ["hold", "brk", "sv1", "sv2", "r1", "r2", "svP", "rtP", "win%"]
df = pd.concat([df, build("S"), build("W")], axis=1)
df = df[(df.S_n >= MIN_M) & (df.W_n >= MIN_M)].copy()
cols = ["S@" + s for s in STATS] + ["W@" + s for s in STATS]

key = ["date", "player_slug", "rival_slugname"]
opp = df[key + cols].rename(columns={"player_slug": "rival_slugname",
                                     "rival_slugname": "player_slug",
                                     **{c: "o_" + c for c in cols}})
M = df.merge(opp, on=key, how="inner")
i1 = 1 / M.player_odd.where(M.player_odd > 1.005)
i2 = 1 / M.rival_odd.where(M.rival_odd > 1.005)
M["mkt"] = i1 / (i1 + i2)
M = M[M.mkt.notna()].copy()
M["pair"] = [tuple(sorted((a, str(b)))) for a, b in zip(M.player_slug.astype(str),
                                                        M.rival_slugname)]
M = M.drop_duplicates(["date", "pair"]).reset_index(drop=True)
M["mon"] = M.date.dt.month
print("matches with BOTH windows on both players: %d   %s..%s\n"
      % (len(M), M.date.min().date(), M.date.max().date()))


def score(sel, side_p1, lab, floor=400):
    n = int(sel.sum())
    if n < floor:
        print("   %-34s n=%d (thin)" % (lab, n))
        return None
    s = M[sel]
    sp = side_p1[sel]
    hit = (sp == s.won.astype(bool)).mean()
    imp = np.where(sp, s.mkt, 1 - s.mkt).mean()
    odds = np.where(sp, s.player_odd, s.rival_odd)
    pnl = np.where(sp == s.won.astype(bool), odds - 1, -1.0)
    print("   %-34s picks win %5.1f%%   EDGE %+5.1fpt   ROI %+6.1f%%   (n=%d)"
          % (lab, 100 * hit, 100 * (hit - imp), 100 * pnl.mean(), n))
    return hit


print("=" * 104)
print("A+B. SAME STAT, TWO WINDOWS")
print("=" * 104)
print("   %-12s %24s %24s" % ("stat", "SEASON", "52 WEEKS"))
res = {}
for st in STATS:
    ds = M["S@" + st] - M["o_S@" + st]
    dw = M["W@" + st] - M["o_W@" + st]
    ok = ds.notna() & dw.notna() & (ds != 0) & (dw != 0)
    n = int(ok.sum())
    if n < 400:
        continue
    out = []
    for d in (ds, dw):
        sp = d > 0
        s = M[ok]
        spp = sp[ok]
        hit = (spp == s.won.astype(bool)).mean()
        imp = np.where(spp, s.mkt, 1 - s.mkt).mean()
        odds = np.where(spp, s.player_odd, s.rival_odd)
        pnl = np.where(spp == s.won.astype(bool), odds - 1, -1.0)
        out.append((100 * hit, 100 * (hit - imp), 100 * pnl.mean()))
    res[st] = (out[0], out[1], n)
    print("   %-12s   %5.1f%% EDGE %+4.1f ROI %+5.1f%%   %5.1f%% EDGE %+4.1f ROI %+5.1f%%  (n=%d)  %s"
          % (st, out[0][0], out[0][1], out[0][2], out[1][0], out[1][1], out[1][2], n,
             "SEASON" if out[0][0] > out[1][0] else "52W"))
wins_s = sum(1 for v in res.values() if v[0][0] > v[1][0])
print("\n   season picks the winner more often on %d of %d stats" % (wins_s, len(res)))

print("\n" + "=" * 104)
print("C. WHERE THEY DISAGREE -- who is right? (the decisive test)")
print("=" * 104)
for st in STATS:
    ds = M["S@" + st] - M["o_S@" + st]
    dw = M["W@" + st] - M["o_W@" + st]
    dis = ds.notna() & dw.notna() & ((ds > 0) != (dw > 0))
    if dis.sum() < 400:
        continue
    print("   %s  (disagree on %d matches, %.0f%% of the time)"
          % (st, int(dis.sum()), 100 * dis.sum() / len(M)))
    score(dis, ds > 0, "      follow SEASON")
    score(dis, dw > 0, "      follow 52W")

print("\n" + "=" * 104)
print("DOES SEASON ONLY WORK LATE IN THE YEAR? (hold+break, by month)")
print("=" * 104)
ds = (M["S@hold"] + M["S@brk"]) - (M["o_S@hold"] + M["o_S@brk"])
dw = (M["W@hold"] + M["W@brk"]) - (M["o_W@hold"] + M["o_W@brk"])
dis = ds.notna() & dw.notna() & ((ds > 0) != (dw > 0))
for lo, hi, lab in ((1, 4, "Jan-Mar"), (4, 7, "Apr-Jun"), (7, 10, "Jul-Sep"), (10, 13, "Oct-Dec")):
    m = dis & M.mon.between(lo, hi - 1)
    if m.sum() < 300:
        continue
    print("   %s:" % lab)
    score(m, ds > 0, "      follow SEASON")
    score(m, dw > 0, "      follow 52W")
