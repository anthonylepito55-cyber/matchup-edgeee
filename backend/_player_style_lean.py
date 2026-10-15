"""IDENTIFY PLAYERS WITH A STYLE LEAN -- AND DOES IT PERSIST? (2026-10-14)

User: "im asking to identify players that tend to perform worse against better servers or better
returners or both ... if a player struggles against good servers but does fine against mediocre
servers but good returner then he does better against return players therefore he probably has an
edge against someone thats good at returning but not so much as serving".

So: ONE NUMBER PER PLAYER -- his LEAN.

    lean = (mean residual vs SERVER-type opponents) - (mean residual vs RETURNER-type opponents)

    residual = won - de-vigged market probability, so 0 means "performed exactly as priced"
    SERVER-type   opponent serve pct high, return pct not high
    RETURNER-type opponent return pct high, serve pct not high

A negative lean is the user's example: worse than the price against servers, better against
returners, therefore an edge when facing a returner-type.

THE TEST THAT DECIDES WHETHER THE LIST IS WORTH ANYTHING. Naming the most extreme players is easy
and meaningless on its own -- with 600+ players someone always looks extreme. The question is
whether a lean PERSISTS:

    compute each player's lean on the FIRST half of his matches  (lean_A)
    compute it again on the SECOND half                          (lean_B)
    correlate lean_A with lean_B across players

    r near 0   -> the lean is noise; last year's "struggles with servers" tells you nothing
                  about next year, and any list is just naming whoever got unlucky
    r positive -> it is a real, stable trait, and the list is actionable

A permutation null is run alongside: shuffle each player's own matches between the two halves and
recompute r. That holds his schedule and form fixed and asks only whether TIME ORDER matters.

Profiles are AS-OF (trailing 24 months, recomputed monthly), because full-archive profiles leaked
the future badly enough to manufacture a -4.8% effect that vanished when the leak was closed.

Run: ./venv/bin/python _player_style_lean.py
"""
import numpy as np
import pandas as pd

SRC = "data_cache/tennisratio/all_match_logs.parquet"
COLS = ["player_slug", "rival_slugname", "result", "player_odd", "rival_odd",
        "service_games_won", "return_games_won", "date"]
WIN_M, MIN_N = 24, 20
MIN_SIDE = 10          # matches needed against each opponent type, per half

d = pd.read_parquet(SRC, columns=COLS)
d["player_slug"] = d["player_slug"].astype(str).str.strip().str.lower()
d["rival_slugname"] = d["rival_slugname"].astype(str).str.strip().str.lower()
d["date"] = pd.to_datetime(d["date"], errors="coerce")
for c in ("player_odd", "rival_odd"):
    d[c] = pd.to_numeric(d[c], errors="coerce")


def frac(col):
    sp = col.astype(str).str.extract(r"^\s*(\d+)\s*/\s*(\d+)\s*$")
    return np.where(pd.to_numeric(sp[1], errors="coerce") > 0,
                    pd.to_numeric(sp[0], errors="coerce")
                    / pd.to_numeric(sp[1], errors="coerce"), np.nan)


d["sv"], d["rt"] = frac(d["service_games_won"]), frac(d["return_games_won"])
d = d[d.date.notna()].sort_values("date").reset_index(drop=True)
d["ym"] = d.date.dt.to_period("M")

# ---- as-of opponent profiles ----
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
print("as-of profiles: %d player-months" % len(prof))

m = d[d.player_odd.notna() & d.rival_odd.notna() & (d.player_odd > 1) & (d.rival_odd > 1)].copy()
m["won"] = m["result"].astype(str).str.strip().str.lower().str.startswith("w")
ip, ir = 1.0 / m.player_odd, 1.0 / m.rival_odd
m["resid"] = m.won.astype(float) - ip / (ip + ir)
m = m.merge(prof.rename(columns={"player_slug": "rival_slugname",
                                 "sv_pct": "o_sv", "rt_pct": "o_rt"}),
            on=["rival_slugname", "ym"], how="inner")
print("matches with an as-of opponent profile: %d" % len(m))

# ---- opponent type ----
m["server_type"] = (m.o_sv >= 0.60) & (m.o_rt < 0.60)
m["returner_type"] = (m.o_rt >= 0.60) & (m.o_sv < 0.60)
m = m[m.server_type | m.returner_type].sort_values(["player_slug", "date"])
print("matches against a clear server-type or returner-type: %d" % len(m))


def leans(frame):
    """lean per player = mean residual vs SERVER-types minus vs RETURNER-types"""
    out = {}
    for nm, sub in frame.groupby("player_slug"):
        a = sub.resid[sub.server_type]
        b = sub.resid[sub.returner_type]
        if len(a) >= MIN_SIDE and len(b) >= MIN_SIDE:
            out[nm] = (a.mean() - b.mean(), len(a), len(b))
    return out


# ---- split each player's own matches in half by TIME ----
m["half"] = m.groupby("player_slug").cumcount()
sz = m.groupby("player_slug")["resid"].transform("size")
m["half"] = (m["half"] >= sz / 2).astype(int)
A, B = leans(m[m.half == 0]), leans(m[m.half == 1])
both = sorted(set(A) & set(B))
print("\nplayers with >=%d of each type in BOTH halves: %d" % (MIN_SIDE, len(both)))
if len(both) < 25:
    print("not enough players to measure persistence")
    raise SystemExit(0)

la = np.array([A[p][0] for p in both])
lb = np.array([B[p][0] for p in both])
r = float(np.corrcoef(la, lb)[0, 1])

BAR = "=" * 94
print("\n" + BAR)
print("DOES A PLAYER'S STYLE LEAN PERSIST?")
print(BAR)
print("   first-half lean  vs  second-half lean, across %d players" % len(both))
print("   correlation r = %+.4f" % r)

rng = np.random.default_rng(31)
sims = []
for _ in range(400):
    sa, sb = [], []
    for p in both:
        sub = m[m.player_slug == p]
        h = rng.permutation(sub.half.to_numpy())
        s0, s1 = sub[h == 0], sub[h == 1]
        a0, b0 = s0.resid[s0.server_type], s0.resid[s0.returner_type]
        a1, b1 = s1.resid[s1.server_type], s1.resid[s1.returner_type]
        if len(a0) >= 5 and len(b0) >= 5 and len(a1) >= 5 and len(b1) >= 5:
            sa.append(a0.mean() - b0.mean())
            sb.append(a1.mean() - b1.mean())
    if len(sa) > 25:
        sims.append(float(np.corrcoef(sa, sb)[0, 1]))
sims = np.array(sims)
print("   permutation null (same matches, halves shuffled): mean r %+.4f  sd %.4f"
      % (sims.mean(), sims.std()))
print("   ->  z = %+.2f" % ((r - sims.mean()) / max(sims.std(), 1e-9)))

print("\n" + BAR)
print("THE LIST -- biggest leans using ALL of a player's matches")
print("(negative = worse than the price vs SERVERS, better vs RETURNERS -- the user's example)")
print(BAR)
ALL = leans(m)
tab = sorted(ALL.items(), key=lambda kv: kv[1][0])
print("   %-30s %8s %7s %7s   %s" % ("player", "lean", "vs srv", "vs ret", "first/second half"))
for nm, (ln, na, nb) in tab[:10] + tab[-10:]:
    ab = "%+.3f / %+.3f" % (A[nm][0], B[nm][0]) if nm in A and nm in B else "n/a"
    print("   %-30s %+8.3f %7d %7d   %s" % (nm, ln, na, nb, ab))

print("\n" + BAR)
print("READ: r near 0 means a lean measured on one half tells you nothing about the other --")
print("the names above are whoever got unlucky, not players with a real weakness. r clearly")
print("positive means the trait is stable and the list can be used.")
print(BAR)
