"""SHOULD MC6 HAVE BEEN BUILT ON MC5 INSTEAD OF MC2? (2026-10-15)

User: "instead of mc2 should i have made mc6 the same as mc5 with the h2h and sform".

A fair question with a measurable answer, and the answer is NOT simply "MC5 is the better base so
yes". Two forces pull against each other:

  * MC5 is the stronger starting point (MC2 -> MC3 -> MC5 each measured better), so base + terms
    starts higher.
  * MC5 ALREADY CONTAINS surface information -- per-surface serve/return ratings and surface Elo
    from MC3, a recency-weighted last five ON THIS SURFACE, and season-to-date on that surface.
    The surface-form residual is therefore at risk of being redundant on MC5 in a way it is not
    on MC2. That is exactly the failure mode MC5's own docstring records: its three terms all
    measured neutral because MC3 already held the information in a better form.

So the thing to measure is not which base is higher, but how much the two terms ADD on each base,
and which total ends up on top.

METHOD -- identical treatment for all three bases, so the comparison is clean:
    base blend reconstructed from that base's OWN legs, exactly as the head forms it:
        p = sigmoid(0.5*logit(p_elo) + 0.5*logit(p_markov) + asym_tilt)
    the two terms computed ONCE from identical as-of definitions and applied to each base:
        h2h    recency-weighted H2H, 365-day half-life, damped by w/(w+1), share + margin
        sform  EWMA of (result - what Elo expected) on this surface, 5-match half-life
    then the same weight grid on each base, judged on held-out years.

Each base uses its own feature table (_mc2 / _mc3 / _mc5_features.parquet), and the script first
checks whether those tables actually differ -- if MC5's file is byte-identical to MC3's on the
legs, then MC5's extra terms live at predict time rather than in the features, and that is
reported rather than silently treated as MC5.

AS-OF THROUGHOUT: shifted cumulative sums, shift(1) for the last meeting, EWMA shifted by one.

Run: ./venv/bin/python _mc6_base_choice.py
"""
import re

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

from tennis_mc2 import _NODES, _rnd, asym_tilt, p_match

COLS = ["date", "year", "a", "b", "surf", "won", "imp", "p_elo", "pa_pt", "pb_pt",
        "nS_a", "nS_b", "score"]
lgt = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))


def load(tag):
    F = pd.read_parquet("data_cache/_%s_features.parquet" % tag, columns=COLS)
    F["date"] = pd.to_datetime(F["date"], errors="coerce")
    F = F[F["date"].notna() & F["a"].notna() & F["b"].notna() & F["won"].notna()
          & F["p_elo"].notna() & F["pa_pt"].notna() & F["pb_pt"].notna()]
    return F.sort_values("date", kind="stable").reset_index(drop=True)


BASES = {}
for tag in ("mc2", "mc3", "mc5"):
    BASES[tag] = load(tag)
    print("%s: %d rows" % (tag, len(BASES[tag])), flush=True)

# do the bases actually differ? if not, say so rather than pretend
ref = BASES["mc2"]
for tag in ("mc3", "mc5"):
    o = BASES[tag]
    same = (len(o) == len(ref)
            and np.allclose(o["p_elo"].to_numpy(float), ref["p_elo"].to_numpy(float), atol=1e-9)
            and np.allclose(o["pa_pt"].to_numpy(float), ref["pa_pt"].to_numpy(float), atol=1e-9))
    print("   %s legs identical to mc2? %s" % (tag, same))
m3, m5 = BASES["mc3"], BASES["mc5"]
print("   mc5 legs identical to mc3? %s"
      % (len(m3) == len(m5)
         and np.allclose(m3["pa_pt"].to_numpy(float), m5["pa_pt"].to_numpy(float), atol=1e-9)
         and np.allclose(m3["p_elo"].to_numpy(float), m5["p_elo"].to_numpy(float), atol=1e-9)))

# ---------------------------------------------------------------- shared as-of terms (from mc2's
# table; the match identity and result are the same in all three, only the legs differ)
F = BASES["mc2"]
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
HL = 365.0
HW = np.zeros(len(F))
HS = np.zeros(len(F))
HM = np.zeros(len(F))
for _, idx in F.groupby("pair", sort=False).indices.items():
    if len(idx) < 2:
        continue
    idx = np.sort(idx)
    for k in range(1, len(idx)):
        i, j = idx[k], idx[:k]
        w = 0.5 ** ((tday[i] - tday[j]) / HL)
        sw = w.sum()
        if sw > 0:
            HW[i] = sw
            HS[i] = (w * wf[j]).sum() / sw - 0.5
            HM[i] = (w * mf[j]).sum() / sw
sgn = np.where(first_is_a, 1.0, -1.0)
damp = HW / (HW + 1.0)
h2h = sgn * (0.65 * (2.0 * HS) + 0.35 * np.clip(HM / 6.0, -1.5, 1.5)) * damp

p_elo2 = F["p_elo"].to_numpy(float)
L = pd.DataFrame({
    "pl": np.concatenate([A, B]), "surf": np.concatenate([surf, surf]),
    "date": np.concatenate([F["date"].to_numpy(), F["date"].to_numpy()]),
    "resid": np.concatenate([won_a.astype(float) - p_elo2,
                             (~won_a).astype(float) - (1 - p_elo2)]),
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
sform = np.clip(sf_a - sf_b, -0.6, 0.6)
print("terms built: h2h on %d rows, mean |sform| %.4f"
      % (int((HW > 0).sum()), float(np.abs(sform).mean())), flush=True)

# ---------------------------------------------------------------- each base's own blend
Y = F["won"].astype(int).to_numpy()
PRICED = F["imp"].notna().to_numpy()
YEAR = F["year"].to_numpy()
BASE_Z = {}
for tag, G in BASES.items():
    if len(G) != len(F):
        print("   !! %s row count differs (%d vs %d) -- skipped" % (tag, len(G), len(F)))
        continue
    sga = 0.10 / np.maximum(G["nS_a"].to_numpy(float), 4) ** 0.5
    sgb = 0.10 / np.maximum(G["nS_b"].to_numpy(float), 4) ** 0.5
    pa = G["pa_pt"].to_numpy(float)
    pb = G["pb_pt"].to_numpy(float)
    pm = np.zeros(len(G))
    for xi, wi in _NODES:
        for xj, wj in _NODES:
            pm += wi * wj * np.array([p_match(_rnd(x + xi * s1), _rnd(y + xj * s2), False)
                                      for x, y, s1, s2 in zip(pa, pb, sga, sgb)])
    az = np.array([asym_tilt(n1, n2) for n1, n2 in
                   zip(G["nS_a"].to_numpy(float), G["nS_b"].to_numpy(float))])
    BASE_Z[tag] = 0.5 * lgt(G["p_elo"].to_numpy(float)) + 0.5 * lgt(pm) + az
    print("   %s blend reconstructed" % tag, flush=True)

BAR = "=" * 104


def sc(z, mask):
    p = 1 / (1 + np.exp(-z[mask]))
    return roc_auc_score(Y[mask], p), brier_score_loss(Y[mask], np.clip(p, 1e-6, 1 - 1e-6))


print("\n" + BAR)
print("EACH BASE ALONE, AND EACH BASE + THE TWO TERMS (wH .25 / wS .50 as shipped)")
print(BAR)
print("   %-6s %-22s %8s %8s %9s %9s" % ("year", "model", "AUC", "Brier", "dAUC", "dBrier"))
for yr in (2025, 2026):
    m = PRICED & (YEAR == yr)
    print()
    ref_a = None
    for tag in ("mc2", "mc3", "mc5"):
        if tag not in BASE_Z:
            continue
        z = BASE_Z[tag]
        a0, b0 = sc(z, m)
        if ref_a is None:
            ref_a, ref_b = a0, b0
        a1, b1 = sc(z + 0.25 * h2h + 0.50 * sform, m)
        print("   %-6d %-22s %8.4f %8.4f %+9.4f %+9.4f"
              % (yr, tag.upper() + " alone", a0, b0, a0 - ref_a, b0 - ref_b))
        print("   %-6s %-22s %8.4f %8.4f %+9.4f %+9.4f   <- terms add %+0.4f AUC"
              % ("", tag.upper() + " + h2h + sform", a1, b1, a1 - ref_a, b1 - ref_b, a1 - a0))

print("\n" + BAR)
print("HOW MUCH DO THE TERMS ADD ON EACH BASE?  (the redundancy question)")
print(BAR)
for yr in (2025, 2026):
    m = PRICED & (YEAR == yr)
    print("\n   %d" % yr)
    for tag in ("mc2", "mc3", "mc5"):
        if tag not in BASE_Z:
            continue
        z = BASE_Z[tag]
        a0, _ = sc(z, m)
        ah, _ = sc(z + 0.25 * h2h, m)
        as_, _ = sc(z + 0.50 * sform, m)
        ab, _ = sc(z + 0.25 * h2h + 0.50 * sform, m)
        print("      %-5s base %.4f | +h2h %+0.4f | +sform %+0.4f | +both %+0.4f"
              % (tag.upper(), a0, ah - a0, as_ - a0, ab - a0))

print("\n" + BAR)
print("BEST WEIGHTS PER BASE  (is .25/.50 still right on a stronger base?)")
print(BAR)
for tag in ("mc2", "mc3", "mc5"):
    if tag not in BASE_Z:
        continue
    z = BASE_Z[tag]
    print("\n   %s" % tag.upper())
    for wh in (0.0, 0.25, 0.50):
        row = []
        for ws in (0.0, 0.25, 0.50, 1.00):
            d = []
            for yr in (2025, 2026):
                m = PRICED & (YEAR == yr)
                a0, _ = sc(z, m)
                a1, _ = sc(z + wh * h2h + ws * sform, m)
                d.append(a1 - a0)
            row.append("wS%.2f %+0.4f/%+0.4f" % (ws, d[0], d[1]))
        print("      wH %.2f  %s" % (wh, "   ".join(row)))
print("\n" + BAR)
print("READ: if the terms add LESS on MC5 than on MC2, that is the redundancy -- MC5 already")
print("holds surface information. The base to build on is whichever TOTAL is highest, not")
print("whichever base is highest.")
print(BAR)
