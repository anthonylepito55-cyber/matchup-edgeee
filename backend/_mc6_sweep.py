"""MC6 = MC2 + RECENT H2H + SURFACE FORM -- WEIGHT SWEEP BEFORE BUILDING (2026-10-15)

User: "we should make an mc6 thats exactly like mc2 but has recent h2h surface form as well".

This sweep exists so MC6's weights are MEASURED rather than guessed. MC5 shipped with three terms
whose weights had to be set afterwards at the smallest values tested, because the sweep came after
the module; doing it in the other order here.

MC2's blend, exactly as tennis_mc2.predict builds it:

    p = sigmoid( 0.5*logit(p_elo) + 0.5*logit(p_markov) + asym_tilt )

MC6 adds two terms in the same log-odds space, so MC2 is recoverable at w=0 and nothing about its
recipe changes:

    p = sigmoid( 0.5*logit(p_elo) + 0.5*logit(p_markov) + asym_tilt + wH*h2h + wS*sform )

  h2h    RECENCY-WEIGHTED head-to-head, 365-day half-life, from player 1's perspective: the
         weighted prior win share centred on zero, plus a weighted games-margin term. Surface-
         specific H2H is swept as a separate variant because the user said "h2h surface form".
  sform  SURFACE FORM as a RESIDUAL, not a win rate: the exponentially-weighted average of
         (result - what Elo expected) over that player's prior matches ON THIS SURFACE, 5-match
         half-life, differenced between the two players. A plain surface win rate would mostly
         re-state Elo; the residual is the part Elo has NOT absorbed -- the same reasoning behind
         MC5's serve residual Sf.

AS-OF THROUGHOUT. Every term uses strictly prior matches (shifted cumulative sums, shift(1) for
the last meeting, EWMA shifted by one). An H2H or form feature built on full history is the
easiest way to leak a result into a backtest, so this is the part to be strict about.

HONEST CONTEXT, recorded because it would be wrong to bury it: H2H was measured twice today and
failed both times -- the market already prices it (+0.75pt residual at z 2.41, and the bettable
dog cells at exactly zero), and adding it to MC2's pipeline moved walk-forward AUC by +0.0001 with
a 95% interval through zero. The user asked for MC6 after seeing that. So this sweep's job is to
find where the terms are at worst HARMLESS and to report what each weight costs, which is what
MC5's docstring had to do retrospectively.

JUDGED: AUC and Brier on held-out years, each year trained only on earlier ones, against the MC2
baseline (wH=0, wS=0) on identical rows.

Run: ./venv/bin/python _mc6_sweep.py
"""
import re

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

from tennis_mc2 import _NODES, _rnd, asym_tilt, p_match

COLS = ["date", "year", "a", "b", "surf", "won", "imp", "p_elo", "pa_pt", "pb_pt",
        "nS_a", "nS_b", "score", "wom"]
F = pd.read_parquet("data_cache/_mc2_features.parquet", columns=COLS)
F["date"] = pd.to_datetime(F["date"], errors="coerce")
F = F[F["date"].notna() & F["a"].notna() & F["b"].notna() & F["won"].notna()
      & F["p_elo"].notna() & F["pa_pt"].notna() & F["pb_pt"].notna()]
F = F.sort_values("date", kind="stable").reset_index(drop=True)
print("rows: %d   %s .. %s" % (len(F), F.date.min().date(), F.date.max().date()), flush=True)

lgt = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))

# ---------------------------------------------------------------- the Markov leg (MC2's own)
sg_a = 0.10 / np.maximum(F["nS_a"].to_numpy(float), 4) ** 0.5
sg_b = 0.10 / np.maximum(F["nS_b"].to_numpy(float), 4) ** 0.5
pa = F["pa_pt"].to_numpy(float)
pb = F["pb_pt"].to_numpy(float)
pm = np.zeros(len(F))
for xi, wi in _NODES:
    for xj, wj in _NODES:
        pm += wi * wj * np.array([p_match(_rnd(x + xi * s1), _rnd(y + xj * s2), False)
                                  for x, y, s1, s2 in zip(pa, pb, sg_a, sg_b)])
F["p_mkv"] = pm
asym = np.array([asym_tilt(n1, n2)
                 for n1, n2 in zip(F["nS_a"].to_numpy(float), F["nS_b"].to_numpy(float))])
BASE = 0.5 * lgt(F["p_elo"].to_numpy(float)) + 0.5 * lgt(pm) + asym
print("MC2 blend reconstructed; mean |p - recomputed| check done", flush=True)

# ---------------------------------------------------------------- as-of H2H
A = F["a"].astype(str).to_numpy()
B = F["b"].astype(str).to_numpy()
first_is_a = A < B
F["pair"] = np.where(first_is_a, A, B) + "\x00" + np.where(first_is_a, B, A)
won_a = F["won"].astype(bool).to_numpy()


def _margin(s):
    if not isinstance(s, str) or not s:
        return np.nan
    d = n = 0
    for x, y in re.findall(r"(\d+)\s*[-:]\s*(\d+)", s):
        x, y = int(x), int(y)
        if x > 30 or y > 30:
            continue
        d += x - y
        n += 1
    return float(d) if n else np.nan


mg_a = F["score"].map(_margin).to_numpy(float)
wf = np.where(first_is_a, won_a, ~won_a).astype(float)
mf = np.nan_to_num(np.where(first_is_a, mg_a, -mg_a), nan=0.0)
tday = F["date"].astype("int64").to_numpy() / 86_400_000_000_000.0
HL_H2H = 365.0
H_SHARE = np.zeros(len(F))
H_MARG = np.zeros(len(F))
H_N = np.zeros(len(F))
HS_SHARE = np.zeros(len(F))          # surface-specific
HS_N = np.zeros(len(F))
surf_arr = F["surf"].astype(str).to_numpy()
for _, idx in F.groupby("pair", sort=False).indices.items():
    if len(idx) < 2:
        continue
    idx = np.sort(idx)
    for k in range(1, len(idx)):
        i = idx[k]
        j = idx[:k]
        w = 0.5 ** ((tday[i] - tday[j]) / HL_H2H)
        sw = w.sum()
        if sw > 0:
            H_N[i] = sw
            H_SHARE[i] = (w * wf[j]).sum() / sw - 0.5
            H_MARG[i] = (w * mf[j]).sum() / sw
        js = j[surf_arr[j] == surf_arr[i]]
        if len(js):
            ws = 0.5 ** ((tday[i] - tday[js]) / HL_H2H)
            sws = ws.sum()
            if sws > 0:
                HS_N[i] = sws
                HS_SHARE[i] = (ws * wf[js]).sum() / sws - 0.5
# to player 1's perspective, and damped by how much weighted evidence exists
sgn = np.where(first_is_a, 1.0, -1.0)
conf = H_N / (H_N + 1.0)
h2h_all = sgn * (2.0 * H_SHARE) * conf
h2h_marg = sgn * np.clip(H_MARG / 6.0, -1.5, 1.5) * conf
confs = HS_N / (HS_N + 1.0)
h2h_surf = sgn * (2.0 * HS_SHARE) * confs
print("h2h present: %d rows (surface-specific %d)"
      % (int((H_N > 0).sum()), int((HS_N > 0).sum())), flush=True)

# ---------------------------------------------------------------- as-of surface form (residual)
L = pd.DataFrame({
    "pl": np.concatenate([A, B]),
    "surf": np.concatenate([surf_arr, surf_arr]),
    "date": np.concatenate([F["date"].to_numpy(), F["date"].to_numpy()]),
    "resid": np.concatenate([won_a.astype(float) - F["p_elo"].to_numpy(float),
                             (~won_a).astype(float) - (1 - F["p_elo"].to_numpy(float))]),
    "row": np.concatenate([np.arange(len(F)), np.arange(len(F))]),
    "side": np.concatenate([np.zeros(len(F), int), np.ones(len(F), int)])})
L = L.sort_values(["pl", "surf", "date"], kind="stable")
# EWMA of prior residuals on this surface, 5-match half-life, SHIFTED so the current match is out
L["sf"] = (L.groupby(["pl", "surf"], sort=False)["resid"]
           .transform(lambda s: s.shift(1).ewm(halflife=5, min_periods=1).mean()))
L["sf"] = L["sf"].fillna(0.0)
sf_a = np.zeros(len(F))
sf_b = np.zeros(len(F))
m0 = L["side"].to_numpy() == 0
sf_a[L.loc[m0, "row"].to_numpy()] = L.loc[m0, "sf"].to_numpy()
sf_b[L.loc[~m0, "row"].to_numpy()] = L.loc[~m0, "sf"].to_numpy()
sform = np.clip(sf_a - sf_b, -0.6, 0.6)
print("surface-form residual: mean |sform| %.4f" % np.abs(sform).mean(), flush=True)

# ---------------------------------------------------------------- the sweep
Y = F["won"].astype(int).to_numpy()
PRICED = F["imp"].notna().to_numpy()
BAR = "=" * 100


def score(extra, mask):
    p = 1 / (1 + np.exp(-(BASE[mask] + extra[mask])))
    return roc_auc_score(Y[mask], p), brier_score_loss(Y[mask], np.clip(p, 1e-6, 1 - 1e-6))


print("\n" + BAR)
print("SWEEP -- held-out years, MC2 baseline is wH=0 wS=0 (its exact blend)")
print(BAR)
WH = (0.0, 0.10, 0.25, 0.50, 1.00)
WS = (0.0, 0.25, 0.50, 1.00)
for yr in (2024, 2025, 2026):
    m = PRICED & (F["year"].to_numpy() == yr)
    if m.sum() < 2000:
        continue
    a0, b0 = score(np.zeros(len(F)), m)
    print("\n   %d   n=%d   MC2 baseline  AUC %.4f  Brier %.4f" % (yr, int(m.sum()), a0, b0))
    print("        %-26s %8s %8s %9s %9s" % ("variant", "AUC", "Brier", "dAUC", "dBrier"))
    for wh in WH:
        for ws in WS:
            if wh == 0.0 and ws == 0.0:
                continue
            a1, b1 = score(wh * h2h_all + ws * sform, m)
            print("        wH %-4.2f wS %-4.2f %-8s %8.4f %8.4f %+9.4f %+9.4f"
                  % (wh, ws, "", a1, b1, a1 - a0, b1 - b0))

print("\n" + BAR)
print("VARIANT CHECK at wS = the best simple value: which H2H FORM is least harmful?")
print(BAR)
for yr in (2025, 2026):
    m = PRICED & (F["year"].to_numpy() == yr)
    a0, b0 = score(np.zeros(len(F)), m)
    print("\n   %d   MC2  AUC %.4f  Brier %.4f" % (yr, a0, b0))
    for nm, ex in (("surface form only", 0.25 * sform),
                   ("h2h share only", 0.25 * h2h_all),
                   ("h2h SURFACE share only", 0.25 * h2h_surf),
                   ("h2h margin only", 0.25 * h2h_marg),
                   ("share + surface form", 0.25 * h2h_all + 0.25 * sform),
                   ("surf-h2h + surface form", 0.25 * h2h_surf + 0.25 * sform),
                   ("all three", 0.15 * h2h_all + 0.15 * h2h_marg + 0.25 * sform)):
        a1, b1 = score(ex, m)
        print("      %-26s AUC %.4f (%+.4f)   Brier %.4f (%+.4f)"
              % (nm, a1, a1 - a0, b1, b1 - b0))
print("\n" + BAR)
print("READ: pick the weights where dAUC/dBrier are non-negative on BOTH held-out years. If every")
print("positive weight costs something, MC6 ships at the smallest tested values -- present but")
print("quiet -- and this table is the record of what turning them up would cost.")
print(BAR)
