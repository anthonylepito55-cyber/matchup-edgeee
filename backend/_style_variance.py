"""HOW BIG IS THE TRUE SPREAD OF PLAYER STYLE LEANS? (2026-10-14)

User: "identify players that tend to perform worse against better servers or better returners".

The split-half test said a lean does not persist (r +0.023 against a null of +0.025). But it only
had power to catch a LARGE trait: it needed 10+ matches of each opponent type in BOTH halves, so
only 111 players qualified out of 161,510 matches, and each half-lean carried a standard error
near 0.20. A real-but-modest lean would have been invisible. Absence of evidence, not evidence of
absence.

THIS SETTLES IT PROPERLY. Instead of splitting samples, separate the two sources of variance
arithmetically -- the classic variance-components identity:

    Var(observed leans)  =  tau^2 (the TRUE spread between players)  +  mean sampling variance

Every player's lean L_i comes with its own sampling variance v_i, computable from his own match
counts and residual spread. So

    tau^2_hat = Var(L) - mean(v_i)      (floored at 0)

uses EVERY player and every match -- no split, no discarded data, full power. tau is then the
honest answer to "how different are players from each other", in probability points.

AND IT GIVES THE LIST THE USER ASKED FOR. With tau known, each player's lean shrinks toward zero
by how noisy his own estimate is:

    shrunk_i = L_i * tau^2 / (tau^2 + v_i)

A player with 400 matches keeps most of his measured lean; one with 25 is pulled most of the way
to zero. That is the difference between a list of real leans and a list of small samples -- the
unshrunk list was topped by Fritz (391 vs servers, 10 vs returners) and Andreeva (10 vs 133).

NULL: shuffle the opponent-type label WITHIN each player and recompute tau^2_hat, 400 times. That
holds every player's schedule, era and form fixed and asks only whether WHICH opponents were
servers matters. If observed tau^2 sits inside that null, there is no between-player style
structure at all and no list is possible.

Profiles are AS-OF throughout (trailing 24 months), since full-archive profiles leaked the future.

Run: ./venv/bin/python _style_variance.py
"""
import numpy as np
import pandas as pd

SRC = "data_cache/tennisratio/all_match_logs.parquet"
COLS = ["player_slug", "rival_slugname", "result", "player_odd", "rival_odd",
        "service_games_won", "return_games_won", "date"]
WIN_M, MIN_N, MIN_SIDE = 24, 20, 8

d = pd.read_parquet(SRC, columns=COLS)
d["player_slug"] = d["player_slug"].astype(str).str.strip().str.lower()
d["rival_slugname"] = d["rival_slugname"].astype(str).str.strip().str.lower()
d["date"] = pd.to_datetime(d["date"], errors="coerce")
for c in ("player_odd", "rival_odd"):
    d[c] = pd.to_numeric(d[c], errors="coerce")


def frac(col):
    sp = col.astype(str).str.extract(r"^\s*(\d+)\s*/\s*(\d+)\s*$")
    den = pd.to_numeric(sp[1], errors="coerce")
    return np.where(den > 0, pd.to_numeric(sp[0], errors="coerce") / den, np.nan)


d["sv"], d["rt"] = frac(d["service_games_won"]), frac(d["return_games_won"])
d = d[d.date.notna()].sort_values("date").reset_index(drop=True)
d["ym"] = d.date.dt.to_period("M")

stats = d[["player_slug", "ym", "sv", "rt"]].dropna(subset=["sv", "rt"])
rows = []
for m0 in sorted(pd.unique(d.ym)):
    w = stats[(stats.ym >= m0 - WIN_M) & (stats.ym < m0)]
    if len(w) < 500:
        continue
    g = w.groupby("player_slug").agg(sv=("sv", "mean"), rt=("rt", "mean"), n=("sv", "size"))
    g = g[g.n >= MIN_N]
    if len(g) < 50:
        continue
    g["sv_pct"], g["rt_pct"] = g.sv.rank(pct=True), g.rt.rank(pct=True)
    g["ym"] = m0
    rows.append(g.reset_index()[["player_slug", "ym", "sv_pct", "rt_pct"]])
prof = pd.concat(rows, ignore_index=True)

m = d[d.player_odd.notna() & d.rival_odd.notna() & (d.player_odd > 1) & (d.rival_odd > 1)].copy()
m["won"] = m["result"].astype(str).str.strip().str.lower().str.startswith("w")
ip, ir = 1.0 / m.player_odd, 1.0 / m.rival_odd
m["resid"] = m.won.astype(float) - ip / (ip + ir)
m = m.merge(prof.rename(columns={"player_slug": "rival_slugname",
                                 "sv_pct": "o_sv", "rt_pct": "o_rt"}),
            on=["rival_slugname", "ym"], how="inner")
m["srv"] = (m.o_sv >= 0.60) & (m.o_rt < 0.60)
m["ret"] = (m.o_rt >= 0.60) & (m.o_sv < 0.60)
m = m[m.srv | m.ret].copy()
print("matches vs a clear server-type or returner-type: %d" % len(m))

res = m.resid.to_numpy()
is_srv = m.srv.to_numpy()
codes, names = pd.factorize(m.player_slug)
order = np.argsort(codes, kind="stable")
res, is_srv, codes = res[order], is_srv[order], codes[order]
groups = np.split(np.arange(len(codes)), np.flatnonzero(np.diff(codes)) + 1)


def leans_and_var(flag):
    """per player: lean, its sampling variance, and the two counts"""
    L, V, NA, NB, IDX = [], [], [], [], []
    for g in groups:
        a, b = res[g][flag[g]], res[g][~flag[g]]
        if len(a) < MIN_SIDE or len(b) < MIN_SIDE:
            continue
        va = a.var(ddof=1) / len(a)
        vb = b.var(ddof=1) / len(b)
        L.append(a.mean() - b.mean()); V.append(va + vb)
        NA.append(len(a)); NB.append(len(b)); IDX.append(g[0])
    return (np.array(L), np.array(V), np.array(NA), np.array(NB), np.array(IDX))


L, V, NA, NB, IDX = leans_and_var(is_srv)
print("players with >=%d of each type: %d" % (MIN_SIDE, len(L)))
tau2 = max(0.0, L.var(ddof=1) - V.mean())
tau = np.sqrt(tau2)
BAR = "=" * 96
print("\n" + BAR)
print("HOW BIG IS THE TRUE BETWEEN-PLAYER SPREAD?")
print(BAR)
print("   variance of observed leans   %.5f" % L.var(ddof=1))
print("   mean sampling variance       %.5f   <- noise from finite match counts" % V.mean())
print("   TRUE variance tau^2          %.5f" % tau2)
print("   TRUE spread tau              %.4f   = %.1f percentage points" % (tau, 100 * tau))

rng = np.random.default_rng(41)
sims = np.empty(400)
for i in range(400):
    f = np.empty(len(res), dtype=bool)
    for g in groups:
        f[g] = rng.permutation(is_srv[g])
    Ls, Vs, _, _, _ = leans_and_var(f)
    sims[i] = max(0.0, Ls.var(ddof=1) - Vs.mean())
z = (tau2 - sims.mean()) / max(sims.std(), 1e-9)
print("\n   permutation null (opponent type shuffled WITHIN each player, 400 runs):")
print("      tau^2 mean %.5f   sd %.5f   ->   observed z = %+.2f" % (sims.mean(), sims.std(), z))
print("      null tau = %.4f (%.1f pts)" % (np.sqrt(sims.mean()), 100 * np.sqrt(sims.mean())))

print("\n" + BAR)
print("THE SHRUNK LIST  (lean x tau^2/(tau^2+v) -- small samples pulled toward 0)")
print(BAR)
if tau2 <= 0:
    print("   tau^2 is zero: every measured lean is consistent with pure noise, so every")
    print("   shrunk estimate is 0.0 and NO player can be identified. No list is possible.")
else:
    sh = L * tau2 / (tau2 + V)
    nm = [names[codes[i]] for i in IDX]
    o = np.argsort(sh)
    print("   %-30s %8s %8s %7s %7s" % ("player", "raw", "shrunk", "vs srv", "vs ret"))
    print("   -- worse than the price vs SERVERS (edge when they face a RETURNER) --")
    for i in o[:10]:
        print("   %-30s %+8.3f %+8.3f %7d %7d" % (nm[i], L[i], sh[i], NA[i], NB[i]))
    print("   -- worse vs RETURNERS (edge when they face a SERVER) --")
    for i in o[-10:]:
        print("   %-30s %+8.3f %+8.3f %7d %7d" % (nm[i], L[i], sh[i], NA[i], NB[i]))
    print("\n   biggest shrunk magnitude overall: %.3f (%.1f pts)"
          % (np.abs(sh).max(), 100 * np.abs(sh).max()))

print("\n" + BAR)
print("READ: z near 0, or tau near the null's tau, means the spread between players is entirely")
print("sampling noise -- no player has an identifiable style lean. A clearly positive z with tau")
print("of a few points means real leans exist and the shrunk column is the usable list.")
print(BAR)
