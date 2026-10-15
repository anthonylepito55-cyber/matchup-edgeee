"""DO MC2's ERRORS HAVE STRUCTURE BY OPPONENT TYPE? (2026-10-14)

User: "maybe one player has a hard time with good servers and one have a hard time with good
returners ... a lot of game results could change with this information".

WHY THIS TEST AND NOT THE TRIAD TEST. The rock-paper-scissors count needed a fitted strength model
as its null, and the verdict turned out to track how confident that null was made:
    unconverged fit  z -13.9  |  no regularisation  z +10.7  |  lambda by prediction  z -6.2
Three principled specifications, three different answers. That method cannot settle it.

This one has no null to fit and nothing to tune. MC2 is GIVEN -- already calibrated, already
validated -- and the only question asked is whether its RESIDUALS carry a pattern:

    residual = (did player 1 win) - (MC2's probability that player 1 wins)

If MC2 fully understands a matchup, residuals are noise: mean zero in every slice. If a player is
genuinely worse than his ratings suggest against big servers, then in the slice "opponent is a big
server" his residuals are systematically negative. That is the user's hypothesis, stated so the
data can refuse it.

WHAT IS SLICED
  1. OPPONENT ARCHETYPE  by the opponent's own 52-week serve and return percentiles:
     big server, strong returner, all-court (both high), grinder (both low).
  2. THE GAP            opponent serve percentile MINUS this player's return percentile, bucketed --
     "how far out of his depth is he against this serve".
  3. PER-PLAYER         for players with enough matches, their mean residual against high-serve
     opponents vs against low-serve opponents. A real style effect means the SPREAD of those
     per-player differences is wider than resampling noise allows -- that is the decisive one,
     because it is what a per-player correction would have to exploit.

The per-player test uses a PERMUTATION null: shuffle which matches count as high-serve WITHIN each
player, recompute the spread, repeat. That holds every player's own form and schedule fixed and
asks only whether the SPLIT by opponent serve is special.

Run: ./venv/bin/python _matchup_residuals.py
"""
import numpy as np
import pandas as pd

import tennis_log

LOG = tennis_log.LOG_PATH
ARCH = "data_cache/tennisratio/all_match_logs.parquet"

# ---------- MC2's predictions and what happened ----------
log = pd.read_parquet(LOG)
bad = np.zeros(len(log), bool)
for c in ("surface_bad", "resolve_bad", "inplay_suspect", "void"):
    if c in log.columns:
        bad |= log[c].fillna(False).astype(bool).to_numpy()
log = log[~bad]
log = log[log["mc2_p1"].notna() & log["p1_won"].notna()].copy()
log["mc2"] = pd.to_numeric(log["mc2_p1"], errors="coerce")
log["won"] = log["p1_won"].astype(bool)
log["resid"] = log["won"].astype(float) - log["mc2"]
log["p1n"] = log["player_1"].astype(str).str.strip().str.lower()
log["p2n"] = log["player_2"].astype(str).str.strip().str.lower()
log["date"] = pd.to_datetime(log["date"], errors="coerce")
print("MC2-priced settled matches: %d  (%s .. %s)"
      % (len(log), log.date.min().date(), log.date.max().date()))

# ---------- each player's serve / return profile from the archive ----------
a = pd.read_parquet(ARCH, columns=["player_slug", "date", "service_games_won", "return_games_won"])
a["date"] = pd.to_datetime(a["date"], errors="coerce")
cut = log.date.min() - pd.Timedelta(days=400)
a = a[(a.date >= cut) & (a.date <= log.date.max())]
a["player_slug"] = a["player_slug"].astype(str).str.strip().str.lower()
for c in ("service_games_won", "return_games_won"):
    a[c] = pd.to_numeric(a[c], errors="coerce")
prof = a.groupby("player_slug").agg(sv=("service_games_won", "mean"),
                                    rt=("return_games_won", "mean"),
                                    n=("service_games_won", "size"))
prof = prof[prof.n >= 15]
prof["sv_pct"] = prof.sv.rank(pct=True)
prof["rt_pct"] = prof.rt.rank(pct=True)
print("players with a serve/return profile: %d" % len(prof))

SV = prof.sv_pct.to_dict()
RT = prof.rt_pct.to_dict()
log["o_sv"] = log.p2n.map(SV)      # opponent's serve percentile
log["o_rt"] = log.p2n.map(RT)
log["m_rt"] = log.p1n.map(RT)      # this player's return percentile
log["m_sv"] = log.p1n.map(SV)
d = log.dropna(subset=["o_sv", "o_rt", "m_rt"]).copy()
print("matches where both players are profiled: %d" % len(d))


def line(mask, lab, ind="   "):
    n = int(mask.sum())
    if n < 20:
        print("%s%-30s n=%-5d (too few)" % (ind, lab, n)); return
    r = d.resid[mask]
    se = r.std() / np.sqrt(n)
    print("%s%-30s n=%-5d  mean residual %+6.3f  (se %.3f)  t %+5.2f"
          % (ind, lab, n, r.mean(), se, r.mean() / max(se, 1e-9)))


BAR = "=" * 92
print("\n" + BAR)
print("1. BY OPPONENT ARCHETYPE  (residual = won - MC2; 0 means MC2 had it right)")
print(BAR)
hi_s, hi_r = d.o_sv >= 0.67, d.o_rt >= 0.67
lo_s, lo_r = d.o_sv <= 0.33, d.o_rt <= 0.33
line(hi_s & ~hi_r, "opp = BIG SERVER")
line(hi_r & ~hi_s, "opp = STRONG RETURNER")
line(hi_s & hi_r, "opp = ALL-COURT (both high)")
line(lo_s & lo_r, "opp = GRINDER (both low)")
line(np.ones(len(d), bool), "ALL matches (baseline)")

print("\n" + BAR)
print("2. BY THE GAP  (opponent serve percentile MINUS this player's return percentile)")
print(BAR)
gap = d.o_sv - d.m_rt
for lo, hi, lab in ((-1.01, -0.4, "way below me (-1.0..-0.4)"), (-0.4, -0.15, "-0.4..-0.15"),
                    (-0.15, 0.15, "evenly matched"), (0.15, 0.4, "+0.15..+0.4"),
                    (0.4, 1.01, "way above me (+0.4..+1.0)")):
    line((gap > lo) & (gap <= hi), lab)

print("\n" + BAR)
print("3. PER-PLAYER: is the SPREAD of (vs big servers - vs weak servers) wider than chance?")
print(BAR)
MINP = 12
d["hi"] = (d.o_sv >= 0.5).astype(int)
g = d.groupby("p1n")
rows = []
for nm, sub in g:
    if len(sub) < MINP:
        continue
    a1 = sub[sub.hi == 1].resid
    a0 = sub[sub.hi == 0].resid
    if len(a1) >= 5 and len(a0) >= 5:
        rows.append((nm, a1.mean() - a0.mean(), len(sub)))
if len(rows) < 10:
    print("   only %d players qualify -- not enough to measure a spread" % len(rows))
else:
    diffs = np.array([r[1] for r in rows])
    obs_sd = diffs.std()
    print("   players with >=%d matches and >=5 on each side: %d" % (MINP, len(rows)))
    print("   observed spread (sd of per-player difference): %.4f" % obs_sd)
    rng = np.random.default_rng(5)
    sims = []
    sub_by = {nm: sub for nm, sub in g if len(sub) >= MINP}
    for _ in range(300):
        vals = []
        for nm, diff, _n in rows:
            sub = sub_by[nm]
            perm = rng.permutation(sub.hi.to_numpy())
            r = sub.resid.to_numpy()
            if perm.sum() >= 5 and (len(perm) - perm.sum()) >= 5:
                vals.append(r[perm == 1].mean() - r[perm == 0].mean())
        if vals:
            sims.append(np.std(vals))
    sims = np.array(sims)
    z = (obs_sd - sims.mean()) / max(sims.std(), 1e-9)
    print("   permutation null (shuffling WITHIN each player, 300 runs):")
    print("      mean %.4f   sd %.4f   ->  observed z = %+.2f" % (sims.mean(), sims.std(), z))
    print()
    print("   biggest per-player gaps (positive = does BETTER than MC2 expects vs big servers):")
    rows.sort(key=lambda r: -abs(r[1]))
    for nm, diff, n in rows[:8]:
        print("      %-28s %+6.3f   (%d matches)" % (nm, diff, n))

print("\n" + BAR)
print("READ: a mean residual near 0 in every archetype slice means MC2 already handles the")
print("matchup. For the per-player test, z near 0 means the spread of player-specific")
print("differences is exactly what shuffling produces -- i.e. there is no stable personal")
print("vulnerability to model, only noise.")
print(BAR)
