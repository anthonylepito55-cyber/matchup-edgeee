"""IS TENNIS NON-TRANSITIVE? (2026-10-14)

User: "player a won player b and player b won player c, doesnt always mean player a won player c"
-- i.e. do STYLE MATCHUPS exist on top of raw strength.

THE TEST. Count intransitive triads in the archive -- triples (A,B,C) where A beat B, B beat C
and C beat A -- and compare that count to what a STRENGTH-ONLY world would produce.

Why this is the right first question: if style matchups are real, the match graph must contain
MORE cycles than strength plus coin-flip noise can explain. If it contains the same number, then
"A beat B, B beat C, C beat A" is just what happens when three similar players play three close
matches, and there is nothing for a model to learn.

THE NULL MODEL. A Bradley-Terry / Elo-style strength fit: every player gets one number, and
P(A beats B) = sigmoid(s_A - s_B). That world has NO styles at all -- only strength and noise --
but it still produces cycles, because close matches are near coin flips. The question is purely
whether the real archive has more.

Fitted on the SAME pairs that are counted, then the observed cycle count is compared with the
distribution of cycle counts from simulated seasons drawn from the fitted probabilities. If the
observed count sits inside that distribution, style adds nothing measurable.

Run on EC2: ./venv/bin/python _intransitivity_test.py
"""
import os
import random

import numpy as np
import pandas as pd

SRC = "data_cache/tennisratio/all_match_logs.parquet"
assert os.path.exists(SRC), SRC

df = pd.read_parquet(SRC)
print("archive rows: %d" % len(df))
print("columns:", [c for c in df.columns][:25])

# ---- work out which columns name the two players and the winner ----
# the archive is PLAYER-CENTRIC: one row per player per match, the player named by
# `player_slug`, the opponent by `rival_slugname`, the outcome by `result` ("Win"/"Loss").
# Every match therefore appears twice, once from each side.
need = ("player_slug", "rival_slugname", "result")
for c in need:
    assert c in df.columns, "missing column %s" % c
d = df[list(need) + (["surface"] if "surface" in df.columns else [])].dropna().copy()
d.columns = ["p", "o", "w"] + (["surface"] if "surface" in df.columns else [])
d["w"] = d["w"].astype(str).str.strip().str.lower().str.startswith("w")
d["p"] = d["p"].astype(str).str.strip().str.lower()
d["o"] = d["o"].astype(str).str.strip().str.lower()
d = d[(d.p != "") & (d.o != "") & (d.p != d.o)]
# keep ONE row per match (each is logged from both sides) -- take the winner's row
d = d[d.w].copy()
print("usable matches (deduped to the winner's row): %d" % len(d))

# ---- keep players with enough matches so the strength fit is meaningful ----
MIN_M = 40
TOP_N = 400   # cap: the cycle count needs a matrix cube, which is O(P^3)
for _ in range(6):
    cnt = pd.concat([d.p, d.o]).value_counts()
    keep = set(cnt[cnt >= MIN_M].index)
    n0 = len(d)
    d = d[d.p.isin(keep) & d.o.isin(keep)]
    if len(d) == n0:
        break
cnt = pd.concat([d.p, d.o]).value_counts()
players = sorted(cnt.head(TOP_N).index)
d = d[d.p.isin(set(players)) & d.o.isin(set(players))]
idx = {n: i for i, n in enumerate(players)}
P = len(players)
print("players with >=%d matches: %d   matches between them: %d" % (MIN_M, P, len(d)))

# ---- head-to-head matrix: wins[a][b] = times a beat b ----
W = np.zeros((P, P), dtype=np.int32)
for p, o, w in zip(d.p.to_numpy(), d.o.to_numpy(), d.w.to_numpy()):
    a, b = idx[p], idx[o]
    if w:
        W[a, b] += 1
    else:
        W[b, a] += 1
N = W + W.T                       # games played between each pair
print("pairs that have met at least once: %d" % int((N > 0).sum() // 2))

# ---- fit one strength per player (Bradley-Terry, NEWTON steps) ----
# 2026-10-14: the first version used a hand-set learning rate and did NOT converge -- it left the
# strengths compressed (-0.44..1.37 instead of -1.74..2.61, loglik -31059 vs -30265). A squashed
# strength scale makes the null predict near-coin-flips, which manufactures cycles, so the test
# reported the archive as far MORE transitive than the null (z -13.9). That was the fit, not tennis.
s = np.zeros(P)
for it in range(300):
    diff = s[:, None] - s[None, :]
    p_win = 1.0 / (1.0 + np.exp(-diff))
    grad = (W - N * p_win).sum(axis=1)
    hess = (N * p_win * (1 - p_win)).sum(axis=1) + 1e-6
    s += grad / hess
    s -= s.mean()
print("strength fit done; spread %.2f to %.2f" % (s.min(), s.max()))

# ---- count intransitive triads among pairs that actually met ----
MET = (N > 0)
# a directed edge a->b when a has the winning head-to-head record
BEAT = np.zeros((P, P), dtype=bool)
BEAT[(W > W.T) & MET] = True


def count_cycles(beat):
    """number of directed 3-cycles a->b->c->a (each counted once)"""
    b = beat.astype(np.float32)
    # trace(B^3)/3 counts each cycle once per rotation
    return int(round(float(np.trace(b @ b @ b)) / 3.0))


obs = count_cycles(BEAT)
# number of triangles where all three pairs met
Mi = MET.astype(np.float32)
closed = int(round(float(np.trace(Mi @ Mi @ Mi)) / 6.0))
print("\nOBSERVED")
print("   triangles where all three pairs have met: %d" % closed)
print("   intransitive (rock-paper-scissors) triads: %d" % obs)
print("   share of triangles that are cycles: %.2f%%" % (100.0 * obs / max(closed, 1)))

# ---- simulate the same schedule from the strength-only model ----
diff = s[:, None] - s[None, :]
PW = 1.0 / (1.0 + np.exp(-diff))
rng = np.random.default_rng(7)
sims = []
RUNS = 20
for r in range(RUNS):
    simW = rng.binomial(N, PW)              # a's wins in their N meetings
    simW = np.triu(simW) + np.tril(N - simW.T, -1) * 0   # keep upper triangle authoritative
    full = np.zeros((P, P), dtype=np.int32)
    iu = np.triu_indices(P, 1)
    full[iu] = simW[iu]
    full.T[iu] = N[iu] - simW[iu]
    sb = np.zeros((P, P), dtype=bool)
    sb[(full > full.T) & MET] = True
    sims.append(count_cycles(sb))
sims = np.array(sims)
print("\nSTRENGTH-ONLY NULL (%d simulated archives, same schedule, same strengths)" % RUNS)
print("   cycles: mean %.0f   sd %.0f   range %d..%d"
      % (sims.mean(), sims.std(), sims.min(), sims.max()))
z = (obs - sims.mean()) / max(sims.std(), 1e-9)
print("   observed %d  ->  z = %+.2f" % (obs, z))
print("\nREAD: z near 0 means the archive has exactly the cycles that strength plus noise makes,")
print("and style matchups are not measurable here. A large POSITIVE z is the user's hypothesis:")
print("more rock-paper-scissors than strength alone can explain.")
