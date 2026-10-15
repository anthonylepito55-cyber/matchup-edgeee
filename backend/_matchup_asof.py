"""THE SAME TEST WITH AS-OF PROFILES -- DOES THE ALL-COURT EFFECT SURVIVE? (2026-10-14)

The full-archive version found the market missing badly against opponents who are good at BOTH
serve and return (-4.80%, t -5.02) and generous against opponents weak at both (+2.90%, t +2.31).

BUT THE PROFILES WERE COMPUTED OVER THE WHOLE ARCHIVE, including matches that had not happened
yet. A player who became good LATER carries a high percentile for their early matches, when the
market correctly priced them as an unknown. "Good at everything" opponents would then beat their
old prices automatically, with no matchup effect at all. That alone could produce the entire
result.

THIS RUN REBUILDS EVERY PROFILE AS-OF THE MATCH: an opponent's serve and return percentiles come
only from THEIR OWN MATCHES BEFORE that date. Nothing from the future enters. A rolling 24-month
window with a 20-match minimum, percentiles recomputed per calendar month against everyone else's
as-of numbers, so a percentile always means "relative to the field at the time".

If the all-court effect survives at anything like -4.8%, it is real and worth building on.
If it collapses toward zero, the look-ahead was the whole thing and the question is closed.

The per-player permutation test is repeated too, though it was already immune to look-ahead
(shuffling happens inside one player) and already came back null at z +0.98.

Run: ./venv/bin/python _matchup_asof.py
"""
import numpy as np
import pandas as pd

SRC = "data_cache/tennisratio/all_match_logs.parquet"
COLS = ["player_slug", "rival_slugname", "result", "player_odd", "rival_odd",
        "service_games_won", "return_games_won", "date"]
d = pd.read_parquet(SRC, columns=COLS)
d["player_slug"] = d["player_slug"].astype(str).str.strip().str.lower()
d["rival_slugname"] = d["rival_slugname"].astype(str).str.strip().str.lower()
d["date"] = pd.to_datetime(d["date"], errors="coerce")
for c in ("player_odd", "rival_odd"):
    d[c] = pd.to_numeric(d[c], errors="coerce")


def frac(col):
    sp = col.astype(str).str.extract(r"^\s*(\d+)\s*/\s*(\d+)\s*$")
    num = pd.to_numeric(sp[0], errors="coerce")
    den = pd.to_numeric(sp[1], errors="coerce")
    return np.where(den > 0, num / den, np.nan)


d["sv"] = frac(d["service_games_won"])
d["rt"] = frac(d["return_games_won"])
d = d[d.date.notna()].sort_values("date").reset_index(drop=True)
print("rows: %d   with parsed serve/return: %d" % (len(d), int(pd.notna(d.sv).sum())))

# ---------- AS-OF profiles: month by month, from a trailing 24-month window ----------
WIN_M, MIN_N = 24, 20
d["ym"] = d.date.dt.to_period("M")
months = sorted(pd.unique(d.ym))
stats = d[["player_slug", "ym", "sv", "rt"]].dropna(subset=["sv", "rt"])
prof_rows = []
for m0 in months:
    lo = m0 - WIN_M            # Period arithmetic: months, cleanly
    w = stats[(stats.ym >= lo) & (stats.ym < m0)]        # strictly BEFORE this month
    if len(w) < 500:
        continue
    g = w.groupby("player_slug").agg(sv=("sv", "mean"), rt=("rt", "mean"), n=("sv", "size"))
    g = g[g.n >= MIN_N]
    if len(g) < 50:
        continue
    g["sv_pct"] = g.sv.rank(pct=True)
    g["rt_pct"] = g.rt.rank(pct=True)
    g["ym"] = m0
    prof_rows.append(g.reset_index()[["player_slug", "ym", "sv_pct", "rt_pct"]])
prof = pd.concat(prof_rows, ignore_index=True)
print("as-of profile rows (player x month): %d   months covered: %d"
      % (len(prof), prof.ym.nunique()))

# ---------- join the market view to the as-of profiles ----------
m = d[d.player_odd.notna() & d.rival_odd.notna() & (d.player_odd > 1) & (d.rival_odd > 1)].copy()
m["won"] = m["result"].astype(str).str.strip().str.lower().str.startswith("w")
ip, ir = 1.0 / m.player_odd, 1.0 / m.rival_odd
m["mkt"] = ip / (ip + ir)
m["resid"] = m.won.astype(float) - m.mkt

opp = prof.rename(columns={"player_slug": "rival_slugname", "sv_pct": "o_sv", "rt_pct": "o_rt"})
me = prof.rename(columns={"sv_pct": "my_sv", "rt_pct": "my_rt"})
m = m.merge(opp, on=["rival_slugname", "ym"], how="inner")
m = m.merge(me, on=["player_slug", "ym"], how="inner")
print("matches with AS-OF profiles for both players: %d" % len(m))
print("market calibration: mean residual %+.4f" % m.resid.mean())


def line(mask, lab, ind="   "):
    n = int(mask.sum())
    if n < 200:
        print("%s%-34s n=%-6d (too few)" % (ind, lab, n)); return
    r = m.resid[mask]
    se = r.std() / np.sqrt(n)
    print("%s%-34s n=%-6d  mean residual %+7.4f  se %.4f   t %+6.2f"
          % (ind, lab, n, r.mean(), se, r.mean() / max(se, 1e-9)))


BAR = "=" * 96
print("\n" + BAR)
print("1. BY OPPONENT ARCHETYPE -- AS-OF (compare with the full-archive run)")
print(BAR)
hs, hr = m.o_sv >= 0.67, m.o_rt >= 0.67
ls, lr = m.o_sv <= 0.33, m.o_rt <= 0.33
line(hs & ~hr, "opponent = BIG SERVER")
line(hr & ~hs, "opponent = STRONG RETURNER")
line(hs & hr, "opponent = ALL-COURT")
line(ls & lr, "opponent = GRINDER")
print("\n   full-archive run said:  ALL-COURT -0.0480 (t -5.02)   GRINDER +0.0290 (t +2.31)")
print("                           BIG SERVER -0.0049 (t -3.74)")

print("\n" + BAR)
print("2. BY THE GAP (opponent serve pct minus my return pct), AS-OF")
print(BAR)
gap = m.o_sv - m.my_rt
for lo, hi, lab in ((-1.01, -0.4, "their serve far below my return"),
                    (-0.4, -0.15, "-0.40..-0.15"), (-0.15, 0.15, "evenly matched"),
                    (0.15, 0.4, "+0.15..+0.40"),
                    (0.4, 1.01, "their serve far above my return")):
    line((gap > lo) & (gap <= hi), lab)

print("\n" + BAR)
print("3. PER-PLAYER spread, AS-OF (was z +0.98 on full-archive profiles)")
print(BAR)
m["hi"] = (m.o_sv >= 0.5).astype(np.int8)
MINP, MINSIDE = 40, 15
mm = m.sort_values("player_slug")
res = mm.resid.to_numpy()
hi = mm.hi.to_numpy()
codes, _ = pd.factorize(mm.player_slug)
bounds = np.flatnonzero(np.diff(codes)) + 1
groups = [g for g in np.split(np.arange(len(codes)), bounds)
          if len(g) >= MINP and hi[g].sum() >= MINSIDE and (len(g) - hi[g].sum()) >= MINSIDE]
print("   qualifying players: %d" % len(groups))
if len(groups) >= 30:
    diffs = np.array([res[g][hi[g] == 1].mean() - res[g][hi[g] == 0].mean() for g in groups])
    obs = diffs.std()
    rng = np.random.default_rng(23)
    sims = np.empty(400)
    for i in range(400):
        v = np.empty(len(groups))
        for j, g in enumerate(groups):
            p = rng.permutation(hi[g])
            v[j] = res[g][p == 1].mean() - res[g][p == 0].mean()
        sims[i] = v.std()
    print("   observed spread %.4f   null %.4f +/- %.4f   ->   z = %+.2f"
          % (obs, sims.mean(), sims.std(), (obs - sims.mean()) / max(sims.std(), 1e-9)))

print("\n" + BAR)
print("READ: if ALL-COURT stays near -4.8%, the effect is real and the look-ahead was not the")
print("cause. If it collapses toward 0, the full-archive profiles were leaking the future and")
print("there is no matchup effect to model.")
print(BAR)
