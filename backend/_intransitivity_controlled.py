"""IS THE EXCESS NON-TRANSITIVITY STYLE? -- LAMBDA CHOSEN BY HELD-OUT PREDICTION (2026-10-14)

THIRD VERSION. v1 used an unconverged fit (z -13.9, a bug). v2 used an unregularised fit inside
thin surface-year cells (z +10.7) -- but the ridge sweep showed the answer IS the prior:
   lam 0 -> z +10.73   lam 1 -> z -2.25   lam 4 -> z -11.36
A test whose verdict is set by a free parameter measures nothing. The null has to be the BEST
strength-only model, not an arbitrary one, so lambda is now chosen PER CELL by held-out
log-loss: fit on 80% of the cell's matches, score the other 20%, keep the lambda that predicts
best, refit on everything with it, then simulate. Excess cycles then mean structure that no
well-calibrated strength model can explain -- which is the actual question.


The pooled test found MORE rock-paper-scissors triads than a strength-only null predicts:
63,579 observed against 61,059 expected, z = +3.81. Real, but it pooled every surface and every
year, and two mundane things produce exactly that signature with no style effect at all:

  SURFACE  A beats B on clay, B beats C on grass, C beats A on hard.
  TIME     A beat B in 2024 when A was better; C beat A in 2026 after A declined.

Both are already handled by the models (per-surface ratings, recency weighting), so if the excess
is mostly those, there is nothing new to build.

THE CONTROL. Re-run the identical count inside a SINGLE surface and a SINGLE season, where neither
explanation can operate: every match in a cell is on the same court type within one year, so a
cycle there cannot be caused by surface change or by a player's level drifting across seasons.

Each cell is fitted and simulated on its own, then the z scores are pooled by Stouffer's method
(sum z / sqrt(k)), since the cells are independent samples of the same question.

Expect smaller cells and therefore noisier individual z's -- the pooled figure is the answer.

Run: ./venv/bin/python _intransitivity_controlled.py
"""
import numpy as np
import pandas as pd

SRC = "data_cache/tennisratio/all_match_logs.parquet"
MIN_M = 12          # matches a player needs INSIDE the cell
TOP_N = 260         # cap per cell: the cycle count is O(P^3)
RUNS = 20
import sys
LAM = float(sys.argv[sys.argv.index('--lam') + 1]) if '--lam' in sys.argv else 1.0

df = pd.read_parquet(SRC, columns=["player_slug", "rival_slugname", "result", "surface", "date"])
d = df.dropna(subset=["player_slug", "rival_slugname", "result"]).copy()
d.columns = ["p", "o", "w", "surface", "date"]
d["w"] = d["w"].astype(str).str.strip().str.lower().str.startswith("w")
d["p"] = d["p"].astype(str).str.strip().str.lower()
d["o"] = d["o"].astype(str).str.strip().str.lower()
d = d[(d.p != "") & (d.o != "") & (d.p != d.o)]
d = d[d.w]                                   # one row per match, the winner's
d["year"] = pd.to_datetime(d["date"], errors="coerce").dt.year
d["surface"] = d["surface"].astype(str).str.strip().str.lower()
d = d[d.year.notna()]
d["year"] = d["year"].astype(int)
print("matches: %d   surfaces: %s   years: %d..%d"
      % (len(d), sorted(d.surface.unique())[:6], d.year.min(), d.year.max()))


def cycles(beat):
    b = beat.astype(np.float32)
    return int(round(float(np.trace(b @ b @ b)) / 3.0))


def cell_z(sub, label):
    cnt = pd.concat([sub.p, sub.o]).value_counts()
    for _ in range(6):
        keep = set(cnt[cnt >= MIN_M].index)
        n0 = len(sub)
        sub = sub[sub.p.isin(keep) & sub.o.isin(keep)]
        if len(sub) == n0:
            break
        cnt = pd.concat([sub.p, sub.o]).value_counts()
    if sub.empty:
        return None
    players = sorted(cnt.head(TOP_N).index)
    sub = sub[sub.p.isin(set(players)) & sub.o.isin(set(players))]
    idx = {n: i for i, n in enumerate(players)}
    P = len(players)
    if P < 40 or len(sub) < 300:
        return None
    W = np.zeros((P, P))
    for p, o in zip(sub.p.to_numpy(), sub.o.to_numpy()):
        W[idx[p], idx[o]] += 1
    N = W + W.T
    # LAMBDA BY HELD-OUT PREDICTION. The ridge sweep proved an arbitrary prior decides the
    # verdict, so the null must be the strength model that genuinely predicts best: fit on 80%
    # of this cell's matches at several lambdas, score the held-out 20% by log-loss, keep the
    # winner, refit on all of it. Nothing about cycles enters the choice.
    def _fit(Wm, Nm, lam):
        ss = np.zeros(P)
        for _ in range(300):
            dd = ss[:, None] - ss[None, :]
            pp = 1.0 / (1.0 + np.exp(-dd))
            g = (Wm - Nm * pp).sum(axis=1) - lam * ss
            h = (Nm * pp * (1 - pp)).sum(axis=1) + lam + 1e-6
            ss += g / h
            ss -= ss.mean()
        return ss

    rows = sub[["p", "o"]].to_numpy()
    rng0 = np.random.default_rng(3)
    order = rng0.permutation(len(rows))
    cut = int(0.8 * len(rows))
    tr, te = rows[order[:cut]], rows[order[cut:]]
    Wtr = np.zeros((P, P))
    for a, b in tr:
        Wtr[idx[a], idx[b]] += 1
    Ntr = Wtr + Wtr.T
    best, best_ll = None, None
    for lam in (0.25, 0.5, 1.0, 2.0, 4.0, 8.0):
        st = _fit(Wtr, Ntr, lam)
        ll = 0.0
        for a, b in te:
            pr = 1.0 / (1.0 + np.exp(-(st[idx[a]] - st[idx[b]])))
            ll += np.log(max(pr, 1e-12))
        if best_ll is None or ll > best_ll:
            best_ll, best = ll, lam
    LAMc = best
    s = _fit(W, N, LAMc)
    MET = N > 0
    BEAT = np.zeros((P, P), dtype=bool)
    BEAT[(W > W.T) & MET] = True
    obs = cycles(BEAT)
    Mi = MET.astype(np.float32)
    closed = int(round(float(np.trace(Mi @ Mi @ Mi)) / 6.0))
    if closed < 200:
        return None
    diff = s[:, None] - s[None, :]
    PW = 1.0 / (1.0 + np.exp(-diff))
    rng = np.random.default_rng(11)
    sims = []
    iu = np.triu_indices(P, 1)
    for _ in range(RUNS):
        draw = rng.binomial(N.astype(int), PW)
        full = np.zeros((P, P))
        full[iu] = draw[iu]
        full.T[iu] = N[iu] - draw[iu]
        sb = np.zeros((P, P), dtype=bool)
        sb[(full > full.T) & MET] = True
        sims.append(cycles(sb))
    sims = np.array(sims, dtype=float)
    z = (obs - sims.mean()) / max(sims.std(), 1e-9)
    print("   %-18s lam=%-5.2f P=%-4d matches=%-6d tri=%-7d obs=%-6d null=%-7.0f z=%+5.2f"
          % (label, LAMc, P, len(sub), closed, obs, sims.mean(), z))
    return z, obs, sims.mean(), closed


print("\nSURFACE x YEAR cells (neither surface change nor multi-year drift can make a cycle here)")
print("=" * 104)
zs = []
tot_obs = tot_exp = tot_tri = 0
for surf in ("hard", "clay", "grass"):
    for yr in sorted(d.year.unique()):
        sub = d[(d.surface == surf) & (d.year == yr)]
        if len(sub) < 500:
            continue
        r = cell_z(sub, "%s %d" % (surf, yr))
        if r:
            zs.append(r[0]); tot_obs += r[1]; tot_exp += r[2]; tot_tri += r[3]

print("\n" + "=" * 104)
if zs:
    pooled = sum(zs) / np.sqrt(len(zs))
    print("CELLS: %d    pooled Stouffer z = %+.2f" % (len(zs), pooled))
    print("   total observed cycles %d   vs null %.0f   over %d triangles"
          % (tot_obs, tot_exp, tot_tri))
    print("   excess: %+.1f%% more cycles than strength alone"
          % (100.0 * (tot_obs - tot_exp) / max(tot_exp, 1)))
else:
    print("no cell was large enough")
print("""
READ: the pooled test found z = +3.81 across everything. If the pooled z HERE is still clearly
positive, surface and time cannot explain it and something matchup-shaped is real. If it falls to
around zero, the pooled excess was surface and drift -- which the per-surface ratings and recency
weighting already handle, and there is nothing new to build.""")
