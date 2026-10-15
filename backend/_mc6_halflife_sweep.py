"""HOW FAR BACK SHOULD MC6's H2H LOOK? (2026-10-15)

MC6_HL_DAYS = 365 is the one number in MC6 that was chosen by hand rather than measured -- the
weights were swept, the half-life was assumed. Two reasons that is worth fixing:

  * The user's premise was "recent h2h matters, old h2h matters less", and 365 days was my
    encoding of it. An assumption that came from the brief is still an assumption.
  * The market-residual test earlier today pointed the OTHER way. Against the de-vigged close,
    the only recency bucket with real signal was the oldest one:
        < 6 months  +0.48pt (z 0.86)     1-2 years   +1.15pt (z 1.71)
        6-12 months -0.70pt (z -0.96)    over 2 years +1.69pt (z 2.90)
    There is no contradiction -- that table is about MISPRICING (the market forgets old results)
    and MC6 is tuned for ACCURACY -- but it does mean a long memory cannot be dismissed without
    measuring it.

SWEPT: half-lives of 180d / 365d (current) / 730d / 1825d / no decay at all, on MC5's base (the
base MC6 now sits on), at several H2H weights, judged on held-out years.

The damping term w/(w+1) interacts with this and is why the weight has to be re-swept rather than
held fixed: a longer half-life means more surviving weighted evidence on every pair, so the same
wH is effectively a larger nudge. Reported alongside is the mean weighted evidence per half-life,
so the two effects can be told apart.

AS-OF THROUGHOUT -- strictly prior meetings only.

Run: ./venv/bin/python _mc6_halflife_sweep.py
"""
import re

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

from tennis_mc2 import _NODES, _rnd, asym_tilt, p_match

COLS = ["date", "year", "a", "b", "surf", "won", "imp", "p_elo", "pa_pt", "pb_pt",
        "nS_a", "nS_b", "score"]
lgt = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))

# MC5's feature table is the base MC6 now sits on
F = pd.read_parquet("data_cache/_mc5_features.parquet", columns=COLS)
F["date"] = pd.to_datetime(F["date"], errors="coerce")
F = F[F["date"].notna() & F["a"].notna() & F["b"].notna() & F["won"].notna()
      & F["p_elo"].notna() & F["pa_pt"].notna() & F["pb_pt"].notna()]
F = F.sort_values("date", kind="stable").reset_index(drop=True)
print("rows: %d" % len(F), flush=True)

A = F["a"].astype(str).to_numpy()
B = F["b"].astype(str).to_numpy()
surf = F["surf"].astype(str).to_numpy()
won_a = F["won"].astype(bool).to_numpy()
first_is_a = A < B
F["pair"] = np.where(first_is_a, A, B) + "\x00" + np.where(first_is_a, B, A)


def _margin(s):
    if not isinstance(s, str) or not s:
        return 0.0
    d = n = 0
    for x, y in re.findall(r"(\d+)\s*[-:]\s*(\d+)", s):
        x, y = int(x), int(y)
        if x > 30 or y > 30:
            continue
        d += x - y
        n += 1
    return float(d) if n else 0.0


mg_a = F["score"].map(_margin).to_numpy(float)
wf = np.where(first_is_a, won_a, ~won_a).astype(float)
mf = np.where(first_is_a, mg_a, -mg_a)
tday = F["date"].astype("int64").to_numpy() / 86_400_000_000_000.0
sgn = np.where(first_is_a, 1.0, -1.0)
PAIRS = {k: np.sort(v) for k, v in F.groupby("pair", sort=False).indices.items() if len(v) > 1}
print("pairs with 2+ meetings: %d" % len(PAIRS), flush=True)


def build_h2h(hl):
    """MC6's h2h term at a given half-life in days. hl=None means NO decay (flat weights)."""
    HW = np.zeros(len(F))
    HS = np.zeros(len(F))
    HM = np.zeros(len(F))
    for idx in PAIRS.values():
        for k in range(1, len(idx)):
            i, j = idx[k], idx[:k]
            w = (np.ones(len(j)) if hl is None
                 else 0.5 ** ((tday[i] - tday[j]) / float(hl)))
            sw = w.sum()
            if sw > 0:
                HW[i] = sw
                HS[i] = (w * wf[j]).sum() / sw - 0.5
                HM[i] = (w * mf[j]).sum() / sw
    raw = 0.65 * (2.0 * HS) + 0.35 * np.clip(HM / 6.0, -1.5, 1.5)
    return sgn * raw * (HW / (HW + 1.0)), HW


# ---- MC5's blend, and the surface-form term (unchanged across the sweep) ----
sga = 0.10 / np.maximum(F["nS_a"].to_numpy(float), 4) ** 0.5
sgb = 0.10 / np.maximum(F["nS_b"].to_numpy(float), 4) ** 0.5
pm = np.zeros(len(F))
for xi, wi in _NODES:
    for xj, wj in _NODES:
        pm += wi * wj * np.array([p_match(_rnd(x + xi * s1), _rnd(y + xj * s2), False)
                                  for x, y, s1, s2 in zip(F["pa_pt"].to_numpy(float),
                                                          F["pb_pt"].to_numpy(float), sga, sgb)])
az = np.array([asym_tilt(n1, n2) for n1, n2 in
               zip(F["nS_a"].to_numpy(float), F["nS_b"].to_numpy(float))])
BASE = 0.5 * lgt(F["p_elo"].to_numpy(float)) + 0.5 * lgt(pm) + az

p_elo = F["p_elo"].to_numpy(float)
L = pd.DataFrame({
    "pl": np.concatenate([A, B]), "surf": np.concatenate([surf, surf]),
    "date": np.concatenate([F["date"].to_numpy(), F["date"].to_numpy()]),
    "resid": np.concatenate([won_a.astype(float) - p_elo, (~won_a).astype(float) - (1 - p_elo)]),
    "row": np.concatenate([np.arange(len(F)), np.arange(len(F))]),
    "side": np.concatenate([np.zeros(len(F), int), np.ones(len(F), int)])})
L = L.sort_values(["pl", "surf", "date"], kind="stable")
L["sf"] = (L.groupby(["pl", "surf"], sort=False)["resid"]
           .transform(lambda s: s.shift(1).ewm(halflife=5, min_periods=1).mean())).fillna(0.0)
sf_a = np.zeros(len(F))
sf_b = np.zeros(len(F))
m0 = L["side"].to_numpy() == 0
sf_a[L.loc[m0, "row"].to_numpy()] = L.loc[m0, "sf"].to_numpy()
sf_b[L.loc[~m0, "row"].to_numpy()] = L.loc[~m0, "sf"].to_numpy()
SFORM = np.clip(sf_a - sf_b, -0.6, 0.6)
WS = 0.50

Y = F["won"].astype(int).to_numpy()
PRICED = F["imp"].notna().to_numpy()
YEAR = F["year"].to_numpy()
BAR = "=" * 104


def sc(z, m):
    p = 1 / (1 + np.exp(-z[m]))
    return roc_auc_score(Y[m], p), brier_score_loss(Y[m], np.clip(p, 1e-6, 1 - 1e-6))


print("\n" + BAR)
print("H2H HALF-LIFE SWEEP on MC5's base, surface form fixed at wS = %.2f" % WS)
print(BAR)
base_ref = {}
for yr in (2025, 2026):
    m = PRICED & (YEAR == yr)
    a0, b0 = sc(BASE + WS * SFORM, m)
    base_ref[yr] = (a0, b0)
    print("   %d  base + sform only (wH = 0):  AUC %.4f  Brier %.4f  n=%d"
          % (yr, a0, b0, int(m.sum())))

for hl, lab in ((180, "180 days"), (365, "365 days  <- shipped"), (730, "2 years"),
                (1825, "5 years"), (None, "no decay (flat)")):
    h2h, HW = build_h2h(hl)
    act = HW > 0
    print("\n   half-life %-22s  rows with h2h %d   mean weighted evidence w %.3f"
          % (lab, int(act.sum()), float(HW[act].mean()) if act.any() else 0.0))
    for wh in (0.10, 0.25, 0.50, 1.00):
        out = []
        for yr in (2025, 2026):
            m = PRICED & (YEAR == yr)
            a1, b1 = sc(BASE + wh * h2h + WS * SFORM, m)
            a0, b0 = base_ref[yr]
            out.append("%d dAUC %+0.4f dBrier %+0.4f" % (yr, a1 - a0, b1 - b0))
        print("      wH %-5.2f  %s" % (wh, "   |   ".join(out)))

print("\n" + BAR)
print("READ: the comparison is against 'base + sform only', so every number is what the H2H term")
print("adds on top of a model that already has surface form. If a longer half-life beats 365 days")
print("on BOTH held-out years, MC6_HL_DAYS should move; if they are all inside a thousandth of")
print("each other, the half-life does not matter and 365 can stay on the grounds that it is the")
print("one the user's own reasoning asked for.")
print(BAR)
