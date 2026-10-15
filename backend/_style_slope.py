"""PER-PLAYER STYLE SLOPE, WITHIN GENDER, CONTINUOUS (2026-10-14)

User: "run it, it also seems like majority of men rely on serve while majority of women rely on
return" -- and that observation exposed a fatal confound in every earlier version of this test.

MEASURED: men hold 73.0% and break 30.6%; women hold 61.1% and break 45.0%. Ranking serve
percentiles across EVERYONE therefore made 100% of women "high return" and only 5% "high serve",
so the server-type / returner-type split was largely a GENDER split. All six earlier tests were
partly measuring men against women rather than style. This version fixes both problems:

  1. GENDER-AWARE. Labels come from tournament_level (WTA -> woman, ATP/Challengers/Next Gen ->
     man) and then PROPAGATE through the opponent graph, because Futures events are
     gender-segregated: anyone who plays a labelled woman is a woman. Percentiles are ranked
     WITHIN gender, so "big server" means big relative to peers. Cross-gender rows are dropped.

  2. CONTINUOUS, not a binary split. Each player gets a SLOPE from regressing his match residuals
     on the opponent's serve percentile, so every match counts instead of only the extremes --
     Medvedev is fitted on ~450 matches rather than on the eleven that happened to be
     "returner-types".

     slope < 0  =  does worse than the price the better the opponent serves (the user's idea)

The between-player true spread is the same variance-components estimate as before: Var(slopes)
minus the mean sampling variance of a slope, against a permutation null that shuffles opponent
serve percentiles WITHIN each player.
"""
import numpy as np
import pandas as pd

SRC = "data_cache/tennisratio/all_match_logs.parquet"
WIN_M, MIN_N, MIN_M = 24, 20, 30

d = pd.read_parquet(SRC, columns=["player_slug", "rival_slugname", "result", "player_odd",
                                  "rival_odd", "service_games_won", "return_games_won",
                                  "date", "tournament_level"])
for c in ("player_slug", "rival_slugname"):
    d[c] = d[c].astype(str).str.strip().str.lower()
d["date"] = pd.to_datetime(d["date"], errors="coerce")
for c in ("player_odd", "rival_odd"):
    d[c] = pd.to_numeric(d[c], errors="coerce")


def fr(c):
    sp = d[c].astype(str).str.extract(r"^(\d+)/(\d+)$")
    den = pd.to_numeric(sp[1], errors="coerce")
    return np.where(den > 0, pd.to_numeric(sp[0], errors="coerce") / den, np.nan)


d["sv"] = fr("service_games_won")
d["rt"] = fr("return_games_won")
d = d[d.date.notna()].sort_values("date").reset_index(drop=True)
d["ym"] = d.date.dt.to_period("M")

# ---- gender: anchor on ATP/WTA, then propagate through the opponent graph ----
lv = d.groupby("player_slug").tournament_level.agg(lambda s: set(s.dropna()))
lab = {}
for p, s in lv.items():
    if "WTA" in s:
        lab[p] = "W"
    elif s & {"ATP", "Challengers", "Next Gen"}:
        lab[p] = "M"
print("anchored by tour: M %d  W %d  (of %d players)"
      % (sum(v == "M" for v in lab.values()), sum(v == "W" for v in lab.values()), len(lv)))
edges = d[["player_slug", "rival_slugname"]].drop_duplicates().to_numpy()
for _ in range(12):
    changed = 0
    for a, b in edges:
        if a in lab and b not in lab:
            lab[b] = lab[a]
            changed += 1
        elif b in lab and a not in lab:
            lab[a] = lab[b]
            changed += 1
    if not changed:
        break
print("after propagating through opponents: M %d  W %d  unlabelled %d"
      % (sum(v == "M" for v in lab.values()), sum(v == "W" for v in lab.values()),
         len(lv) - len(lab)))
d["g"] = d.player_slug.map(lab)
d["og"] = d.rival_slugname.map(lab)
d = d[d.g.notna() & (d.g == d.og)]
print("same-gender matches with a label: %d" % len(d))

# ---- as-of serve profiles, ranked WITHIN gender ----
stats = d[["player_slug", "ym", "sv", "g"]].dropna(subset=["sv"])
rows = []
for m0 in sorted(pd.unique(d.ym)):
    w = stats[(stats.ym >= m0 - WIN_M) & (stats.ym < m0)]
    if len(w) < 500:
        continue
    g = w.groupby(["player_slug", "g"]).agg(sv=("sv", "mean"), n=("sv", "size")).reset_index()
    g = g[g.n >= MIN_N]
    if len(g) < 50:
        continue
    g["sv_pct"] = g.groupby("g").sv.rank(pct=True)
    g["ym"] = m0
    rows.append(g[["player_slug", "ym", "sv_pct"]])
prof = pd.concat(rows, ignore_index=True)

m = d[d.player_odd.notna() & d.rival_odd.notna() & (d.player_odd > 1) & (d.rival_odd > 1)].copy()
m["won"] = m["result"].astype(str).str.strip().str.lower().str.startswith("w")
ip, ir = 1.0 / m.player_odd, 1.0 / m.rival_odd
m["resid"] = m.won.astype(float) - ip / (ip + ir)
m = m.merge(prof.rename(columns={"player_slug": "rival_slugname", "sv_pct": "o_sv"}),
            on=["rival_slugname", "ym"], how="inner")
print("matches with a within-gender as-of opponent serve percentile: %d" % len(m))

res = m.resid.to_numpy()
x = m.o_sv.to_numpy() - 0.5
codes, names = pd.factorize(m.player_slug)
o = np.argsort(codes, kind="stable")
res, x, codes = res[o], x[o], codes[o]
gl = m.g.to_numpy()[o]
groups = [g for g in np.split(np.arange(len(codes)), np.flatnonzero(np.diff(codes)) + 1)
          if len(g) >= MIN_M and x[g].std() > 0.05]
print("players with >=%d matches and real spread in opponent serve: %d" % (MIN_M, len(groups)))


def slopes(xx):
    S, V, N, I = [], [], [], []
    for g in groups:
        xg, rg = xx[g], res[g]
        sxx = ((xg - xg.mean()) ** 2).sum()
        if sxx <= 0:
            continue
        b = ((xg - xg.mean()) * (rg - rg.mean())).sum() / sxx
        pred = rg.mean() + b * (xg - xg.mean())
        s2 = ((rg - pred) ** 2).sum() / max(len(g) - 2, 1)
        S.append(b)
        V.append(s2 / sxx)
        N.append(len(g))
        I.append(g[0])
    return np.array(S), np.array(V), np.array(N), np.array(I)


S, V, N, I = slopes(x)
tau2 = max(0.0, S.var(ddof=1) - V.mean())
BAR = "=" * 96
print("\n" + BAR)
print("TRUE BETWEEN-PLAYER SPREAD OF THE STYLE SLOPE (within gender, continuous)")
print(BAR)
print("   players: %d   median matches each: %d" % (len(S), int(np.median(N))))
print("   variance of observed slopes  %.5f" % S.var(ddof=1))
print("   mean sampling variance       %.5f" % V.mean())
print("   TRUE variance tau^2          %.5f" % tau2)
print("   TRUE spread tau              %.4f" % np.sqrt(tau2))
print("   (a slope of 0.10 = 10 points worse against the best server than the worst)")

rng = np.random.default_rng(53)
sims = np.empty(300)
for i in range(300):
    xs = x.copy()
    for g in groups:
        xs[g] = rng.permutation(x[g])
    Ss, Vs, _, _ = slopes(xs)
    sims[i] = max(0.0, Ss.var(ddof=1) - Vs.mean())
z = (tau2 - sims.mean()) / max(sims.std(), 1e-9)
print("\n   permutation null (opponent serve shuffled WITHIN player, 300 runs):")
print("      tau^2 %.5f +/- %.5f   ->   z = %+.2f" % (sims.mean(), sims.std(), z))

print("\n" + BAR)
print("SHRUNK PER-PLAYER SLOPES")
print(BAR)
if tau2 <= 0:
    print("   tau^2 = 0: all spread is sampling noise, no player is identifiable.")
else:
    sh = S * tau2 / (tau2 + V)
    nm = [names[codes[i]] for i in I]
    gg = [gl[i] for i in I]
    ordr = np.argsort(sh)
    print("   %-30s %s %9s %9s %7s" % ("player", "g", "raw", "shrunk", "n"))
    print("   -- WORSE the better the opponent serves --")
    for i in ordr[:12]:
        print("   %-30s %s %+9.3f %+9.3f %7d" % (nm[i], gg[i], S[i], sh[i], N[i]))
    print("   -- BETTER the better the opponent serves --")
    for i in ordr[-12:]:
        print("   %-30s %s %+9.3f %+9.3f %7d" % (nm[i], gg[i], S[i], sh[i], N[i]))
    print("\n   largest shrunk magnitude: %.3f" % np.abs(sh).max())
print("\n" + BAR)
