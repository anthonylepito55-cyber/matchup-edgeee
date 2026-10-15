"""DO PLAYERS HAVE PERSONAL TROUBLE WITH SERVERS OR RETURNERS? (2026-10-14)

User: "are u able to see if people struggle with returners or servers and if they're playing a
good return or server".

Yes -- the archive carries service_games_won and return_games_won on every match row, so every
player gets a serve and a return percentile, and every match therefore has a known OPPONENT TYPE.

THE BASELINE IS THE MARKET, not a model. Three reasons:
  * it is already calibrated, so there is nothing to fit and no lambda to choose -- the failure
    that made the rock-paper-scissors test useless (it returned z -13.9, +10.7 and -6.2 depending
    only on how confident its null was made);
  * 170k matches instead of the 1,392 the MC2 log holds;
  * and it is the only version that can pay. If the MARKET already prices style matchups, there is
    no bet no matter what our models do.

    residual = (player won) - (de-vigged market probability the player wins)

Mean residual ~0 in a slice = the market already handles that matchup. Systematically negative in
"opponent is a big server" = players really are underpriced-against / overrated-against big
servers there.

THREE QUESTIONS
  1. does the residual move by OPPONENT ARCHETYPE at all (pooled over everyone)?
  2. does it move by the GAP between the opponent's serve and this player's return?
  3. THE DECISIVE ONE -- per player, is (mean residual vs big servers) - (vs weak servers)
     spread WIDER than chance? Pooled effects can cancel; a personal vulnerability shows up as
     spread. The null is a PERMUTATION that shuffles the high/low-serve label WITHIN each player,
     holding that player's own form, era and schedule fixed, so only the split by opponent type
     is tested. That null also makes the profile-leakage question moot.

CAVEAT recorded up front: profiles are computed over the whole archive, so a player's own matches
contribute to their percentile. That is fine for a descriptive question and the permutation test
is immune to it, but it would need an as-of profile before any of this became a live feature.

Run: ./venv/bin/python _matchup_vs_market.py
"""
import numpy as np
import pandas as pd

SRC = "data_cache/tennisratio/all_match_logs.parquet"
COLS = ["player_slug", "rival_slugname", "result", "player_odd", "rival_odd",
        "service_games_won", "return_games_won", "surface", "date"]
d = pd.read_parquet(SRC, columns=COLS)
d["player_slug"] = d["player_slug"].astype(str).str.strip().str.lower()
d["rival_slugname"] = d["rival_slugname"].astype(str).str.strip().str.lower()
for c in ("player_odd", "rival_odd"):
    d[c] = pd.to_numeric(d[c], errors="coerce")
# service_games_won / return_games_won are "made/total" STRINGS ("15/17"), not numbers --
# to_numeric silently NaNs every one of them, which is why the first run profiled 0 players.
def _frac(col):
    sp = col.astype(str).str.extract(r"^\s*(\d+)\s*/\s*(\d+)\s*$")
    num = pd.to_numeric(sp[0], errors="coerce")
    den = pd.to_numeric(sp[1], errors="coerce")
    return np.where((den > 0), num / den, np.nan)
d["service_games_won"] = _frac(d["service_games_won"])
d["return_games_won"] = _frac(d["return_games_won"])
print("parsed serve/return rows: %d of %d"
      % (int(pd.notna(d["service_games_won"]).sum()), len(d)))
print("archive rows: %d" % len(d))

# ---- every player's serve / return percentile ----
prof = d.groupby("player_slug").agg(sv=("service_games_won", "mean"),
                                    rt=("return_games_won", "mean"),
                                    n=("service_games_won", "count"))
prof = prof[(prof.n >= 25) & prof.sv.notna() & prof.rt.notna()]
prof["sv_pct"] = prof.sv.rank(pct=True)
prof["rt_pct"] = prof.rt.rank(pct=True)
print("players profiled (>=25 matches with stats): %d" % len(prof))
print("   serve%% range %.1f..%.1f   return%% range %.1f..%.1f"
      % (prof.sv.min(), prof.sv.max(), prof.rt.min(), prof.rt.max()))
SV, RT = prof.sv_pct.to_dict(), prof.rt_pct.to_dict()

# ---- the market's view, de-vigged ----
m = d[d.player_odd.notna() & d.rival_odd.notna() & (d.player_odd > 1) & (d.rival_odd > 1)].copy()
m["won"] = m["result"].astype(str).str.strip().str.lower().str.startswith("w")
ip, ir = 1.0 / m.player_odd, 1.0 / m.rival_odd
m["mkt"] = ip / (ip + ir)
m["resid"] = m.won.astype(float) - m.mkt
m["o_sv"] = m.rival_slugname.map(SV)
m["o_rt"] = m.rival_slugname.map(RT)
m["my_rt"] = m.player_slug.map(RT)
m["my_sv"] = m.player_slug.map(SV)
m = m.dropna(subset=["o_sv", "o_rt", "my_rt", "my_sv"])
print("matches with prices AND both players profiled: %d" % len(m))
print("market calibration check -- mean residual overall: %+.4f  (0 = perfectly priced)"
      % m.resid.mean())


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
print("1. BY OPPONENT ARCHETYPE")
print(BAR)
hs, hr = m.o_sv >= 0.67, m.o_rt >= 0.67
ls, lr = m.o_sv <= 0.33, m.o_rt <= 0.33
line(hs & ~hr, "opponent = BIG SERVER")
line(hr & ~hs, "opponent = STRONG RETURNER")
line(hs & hr, "opponent = ALL-COURT")
line(ls & lr, "opponent = GRINDER")

print("\n" + BAR)
print("2. BY THE GAP: opponent serve percentile MINUS my return percentile")
print(BAR)
gap = m.o_sv - m.my_rt
for lo, hi, lab in ((-1.01, -0.4, "their serve far below my return"),
                    (-0.4, -0.15, "-0.40..-0.15"), (-0.15, 0.15, "evenly matched"),
                    (0.15, 0.4, "+0.15..+0.40"),
                    (0.4, 1.01, "their serve far above my return")):
    line((gap > lo) & (gap <= hi), lab)

print("\n" + BAR)
print("3. DECISIVE -- per player: vs HIGH-serve opponents minus vs LOW-serve opponents")
print(BAR)
m["hi"] = (m.o_sv >= 0.5).astype(np.int8)
MINP, MINSIDE = 40, 15
res = m.resid.to_numpy()
hi = m.hi.to_numpy()
codes, _ = pd.factorize(m.player_slug)
order = np.argsort(codes, kind="stable")
res, hi, codes = res[order], hi[order], codes[order]
bounds = np.flatnonzero(np.diff(codes)) + 1
groups = np.split(np.arange(len(codes)), bounds)
groups = [g for g in groups if len(g) >= MINP
          and hi[g].sum() >= MINSIDE and (len(g) - hi[g].sum()) >= MINSIDE]
print("   players with >=%d matches and >=%d on each side: %d" % (MINP, MINSIDE, len(groups)))
diffs = np.array([res[g][hi[g] == 1].mean() - res[g][hi[g] == 0].mean() for g in groups])
obs_sd = diffs.std()
print("   observed spread of per-player differences: sd = %.4f" % obs_sd)
rng = np.random.default_rng(17)
sims = np.empty(400)
for i in range(400):
    vals = np.empty(len(groups))
    for j, g in enumerate(groups):
        p = rng.permutation(hi[g])
        vals[j] = res[g][p == 1].mean() - res[g][p == 0].mean()
    sims[i] = vals.std()
z = (obs_sd - sims.mean()) / max(sims.std(), 1e-9)
print("   permutation null (label shuffled WITHIN each player, 400 runs):")
print("      mean %.4f   sd %.4f   ->   observed z = %+.2f" % (sims.mean(), sims.std(), z))
k = np.argsort(-np.abs(diffs))[:10]
names = [m.player_slug.to_numpy()[order][g[0]] for g in groups]
print("\n   largest personal gaps (negative = does WORSE than the price vs big servers):")
for i in k:
    print("      %-30s %+7.4f   (%d matches)" % (names[i], diffs[i], len(groups[i])))
print("\n" + BAR)
print("READ: z near 0 in test 3 means the spread of personal differences is exactly what")
print("shuffling produces -- no stable personal vulnerability, only noise. A clearly positive z")
print("means some players really do have a type they struggle with, beyond their own ratings,")
print("and the market is not already charging for it.")
print(BAR)
