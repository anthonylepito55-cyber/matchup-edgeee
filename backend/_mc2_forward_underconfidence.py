"""IS THE UNDER-CONFIDENCE REAL ON THE LIVE LOG, OR ONLY IN THE ARCHIVE? (2026-10-13)

Tier 3 found MC3's log-odds want stretching by ~1.6, measured on the TennisRatio archive
(2024-2026). Before shipping a calibration layer off that, it has to be checked against the one
dataset this project trusts, because the archive has burned it repeatedly: six favourite cells
passed the backtest and failed forward, every pre-rebuild backtest number turned out
stale-cache-inflated, and live Model E was measured inflating favourites against its own clean
recipe on identical games.

The asymmetry is what makes this worth a run rather than a shrug. A calibration layer makes the
head MORE extreme. If the under-confidence is genuine we gain about .0016 Brier. If instead
there is an archive-to-live discrepancy of the kind this project keeps finding, sharpening
AMPLIFIES it by 60%.

MC3 has no forward rows at all -- it shipped today -- so the test uses MC2's frozen forward log.
The Elo/Markov blend and the sigma integration are identical between MC2 and MC3, and those are
exactly the variance-reducing steps a scale term would be correcting, so MC2's forward rows are
the right proxy.

Fits the one parameter directly: logit(p_live) -> scale * logit(p_live), choosing scale by
out-of-sample-free direct Brier/log-loss minimisation on the forward rows, and reports the
standard error so "1.0 vs 1.6" can actually be told apart at this sample size.

Also reports the archive (recon) rows through the same code as a positive control -- if the
method recovers ~1.6 there and ~1.0 forward, the discrepancy is the answer.
"""
import math

import numpy as np
import pandas as pd

import tennis_log

L = pd.read_parquet(tennis_log.LOG_PATH)
d = L[L["mc2_p1"].notna() & L["p1_odds"].notna() & L["p2_odds"].notna()
      & L["p1_won"].notna() & (L["settled"] == True)].copy()      # noqa: E712
for c in ("surface_bad", "inplay_suspect"):
    if c in d.columns:
        d = d[~d[c].fillna(False).astype(bool)]
rc = (d["mc2_recon"].fillna(False).astype(bool).to_numpy()
      if "mc2_recon" in d.columns else np.zeros(len(d), bool))
FWD = ~rc
print("settled MC2 rows %d  (forward %d, archive-backfill %d)" % (len(d), int(FWD.sum()), int(rc.sum())))


def dec(a):
    a = float(a)
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


o1 = d["p1_odds"].map(dec).to_numpy()
o2 = d["p2_odds"].map(dec).to_numpy()
mk = (1 / o1) / ((1 / o1) + (1 / o2))
p = d["mc2_p1"].astype(float).to_numpy()
y = d["p1_won"].astype(bool).to_numpy().astype(float)


def lg(v):
    v = np.clip(v, 1e-6, 1 - 1e-6)
    return np.log(v / (1 - v))


Z = lg(p)


def fit_scale(m):
    """MLE of a single scale on logit(p), no intercept, plus its standard error."""
    z, yy = Z[m], y[m]
    if len(z) < 30:
        return None
    s = 1.0
    for _ in range(100):
        q = 1 / (1 + np.exp(-s * z))
        g = float(np.sum(z * (yy - q)))                # gradient
        h = float(np.sum(z * z * q * (1 - q)))         # observed information
        if h <= 1e-12:
            break
        step = g / h
        s += step
        if abs(step) < 1e-10:
            break
    q = 1 / (1 + np.exp(-s * z))
    h = float(np.sum(z * z * q * (1 - q)))
    se = (1 / math.sqrt(h)) if h > 0 else float("nan")
    return s, se, len(z)


def brier_at(m, s):
    q = 1 / (1 + np.exp(-s * Z[m]))
    return float(((q - y[m]) ** 2).mean())


BAR = "=" * 88
print("\n" + BAR)
print("FITTED LOG-ODDS SCALE  (1.00 = MC2 as shipped; Tier 3 found 1.55-1.66 on the archive)")
print(BAR)
for lab, m in (("FORWARD (the live log)", FWD), ("archive backfill", rc), ("both pooled", np.ones(len(d), bool))):
    r = fit_scale(m)
    if not r:
        print("   %-24s too few rows" % lab)
        continue
    s, se, n = r
    lo, hi = s - 1.96 * se, s + 1.96 * se
    verdict = ("under-confident" if lo > 1.0 else
               ("OVER-confident" if hi < 1.0 else "indistinguishable from 1.0"))
    print("   %-24s n=%-5d scale %.3f +/- %.3f   95%% CI [%.2f, %.2f]   -> %s"
          % (lab, n, s, se, lo, hi, verdict))

print("\n" + BAR)
print("BRIER AT A GRID OF SCALES -- forward rows only, the number that would decide a ship")
print(BAR)
best = None
for s in (1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8):
    b = brier_at(FWD, s)
    star = ""
    if best is None or b < best[1]:
        best = (s, b)
    print("   scale %.1f   forward Brier %.4f%s" % (s, b, star))
print("   best on forward: scale %.1f (Brier %.4f) vs shipped 1.0 (Brier %.4f)"
      % (best[0], best[1], brier_at(FWD, 1.0)))
print("   archive for contrast: best-scale check ->", end=" ")
ab = min(((s, brier_at(rc, s)) for s in (1.0, 1.2, 1.4, 1.6, 1.8)), key=lambda t: t[1])
print("scale %.1f (Brier %.4f) vs 1.0 (%.4f)" % (ab[0], ab[1], brier_at(rc, 1.0)))

print("\n" + BAR)
print("HOW SPREAD IS MC2 vs THE MARKET, forward rows -- the direct read on under-dispersion")
print(BAR)
for lab, m in (("forward", FWD), ("archive", rc)):
    if m.sum() < 30:
        continue
    print("   %-10s sd(logit MC2) %.3f   sd(logit market) %.3f   ratio %.3f"
          % (lab, float(np.std(Z[m])), float(np.std(lg(mk[m]))),
             float(np.std(Z[m]) / np.std(lg(mk[m])))))
print("\n   (a ratio well under 1 means MC2's probabilities really are compressed relative to")
print("    the price, which is the mechanism a scale term would be correcting)")
