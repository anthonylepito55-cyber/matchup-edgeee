"""DOES EXCLUDING UNFINISHED MATCHES IMPROVE MC6? (2026-10-16)

User: "build it and measure it", after the audit found 4.32% of archive matches never finished
and 1 in 33 "dominant wins" (+4 games) is actually a retirement.

Run on MC5's base -- the base MC6 sits on -- with the terms built exactly as tennis_mc6 builds
them, so the only thing that varies is which rows the terms are allowed to read.

VARIANTS, each isolating one claim:

  BASE             MC5 alone, no terms. The floor.
  dirty            MC6 as it ships today: every row counted, retirements included.
  margin-clean     the H2H MARGIN component ignores unfinished meetings, but their WIN/LOSS
                   still counts. This is the targeted fix: a retirement is a real win and
                   belongs in the record, while its games differential is not a real margin.
  h2h-drop         unfinished meetings dropped from the H2H term entirely, win included.
                   Stricter, and tested to show whether keeping the result was right.
  sform-nowo       walkovers excluded from the surface-form residual (no tennis was played).
  sform-nounf      ALL unfinished excluded from sform, not just walkovers.
  both-clean       margin-clean + sform-nowo, the combination that would ship.
  all-clean        h2h-drop + sform-nounf, the strictest version.

Judged on held-out years with the shipped weights (wH .25 / wS .50), AUC and Brier, so the
comparison is like-for-like with every earlier MC6 measurement.

AS-OF THROUGHOUT: strictly prior meetings, EWMA shifted by one.

Run: ./venv/bin/python _mc6_clean_sweep.py
"""
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

import tennis_score as TS
from tennis_mc2 import _NODES, _rnd, asym_tilt, p_match
from tennis_mc6 import MC6_HL_DAYS, MC6_MARG_W, MC6_SFORM_CAP, MC6_WH, MC6_WS

COLS = ["date", "year", "a", "b", "surf", "won", "imp", "p_elo", "pa_pt", "pb_pt",
        "nS_a", "nS_b", "score"]
lgt = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))

F = pd.read_parquet("data_cache/_mc5_features.parquet", columns=COLS)
F["date"] = pd.to_datetime(F["date"], errors="coerce")
F = F[F["date"].notna() & F["a"].notna() & F["b"].notna() & F["won"].notna()
      & F["p_elo"].notna() & F["pa_pt"].notna() & F["pb_pt"].notna()]
F = F.sort_values("date", kind="stable").reset_index(drop=True)

CLS = F["score"].map(TS.classify).to_numpy()
UNF = CLS != TS.COMPLETE
WO = CLS == TS.WALKOVER
print("rows %d   unfinished %d (%.2f%%)   walkovers %d"
      % (len(F), int(UNF.sum()), 100 * UNF.mean(), int(WO.sum())), flush=True)

A = F["a"].astype(str).to_numpy()
B = F["b"].astype(str).to_numpy()
SU = F["surf"].astype(str).to_numpy()
WON = F["won"].astype(bool).to_numpy()
PE = F["p_elo"].to_numpy(float)
TD = F["date"].astype("int64").to_numpy() / 86_400_000_000_000.0
first = A < B
MG = F["score"].map(TS.games_margin).to_numpy(float)
wf = np.where(first, WON, ~WON).astype(float)
mf = np.where(first, MG, -MG)
sgn = np.where(first, 1.0, -1.0)
F["pair"] = np.where(first, A, B) + "\x00" + np.where(first, B, A)
PAIRS = {k: np.sort(v) for k, v in F.groupby("pair", sort=False).indices.items() if len(v) > 1}


def build_h2h(drop_unfinished_entirely=False, clean_margin=False):
    HW = np.zeros(len(F)); HS = np.zeros(len(F)); HM = np.zeros(len(F)); MW = np.zeros(len(F))
    for idx in PAIRS.values():
        for k in range(1, len(idx)):
            i, j = idx[k], idx[:k]
            if drop_unfinished_entirely:
                j = j[~UNF[j]]
                if not len(j):
                    continue
            w = 0.5 ** ((TD[i] - TD[j]) / MC6_HL_DAYS)
            sw = w.sum()
            if sw <= 0:
                continue
            HW[i] = sw
            HS[i] = (w * wf[j]).sum() / sw - 0.5
            # the margin component may read a narrower set of meetings than the win share
            jm = j[~UNF[j]] if clean_margin else j
            if len(jm):
                wm = 0.5 ** ((TD[i] - TD[jm]) / MC6_HL_DAYS)
                swm = wm.sum()
                if swm > 0:
                    HM[i] = (wm * mf[jm]).sum() / swm
                    MW[i] = swm
    share = 2.0 * HS
    marg = np.clip(HM / 6.0, -1.5, 1.5)
    raw = (1.0 - MC6_MARG_W) * share + MC6_MARG_W * marg
    return sgn * raw * (HW / (HW + 1.0))


def build_sform(exclude):
    """exclude: boolean mask of rows that must not contribute to anyone's surface form."""
    keep = ~exclude
    L = pd.DataFrame({
        "pl": np.concatenate([A, B]), "surf": np.concatenate([SU, SU]),
        "date": np.concatenate([F["date"].to_numpy(), F["date"].to_numpy()]),
        "resid": np.concatenate([WON.astype(float) - PE, (~WON).astype(float) - (1 - PE)]),
        "row": np.concatenate([np.arange(len(F)), np.arange(len(F))]),
        "side": np.concatenate([np.zeros(len(F), int), np.ones(len(F), int)]),
        "keep": np.concatenate([keep, keep])})
    L = L.sort_values(["pl", "surf", "date"], kind="stable")
    # an excluded row contributes nothing but must not reorder the others: drop then EWMA
    K = L[L["keep"]].copy()
    K["sf"] = (K.groupby(["pl", "surf"], sort=False)["resid"]
               .transform(lambda s: s.shift(1).ewm(halflife=5, min_periods=1).mean()))
    L = L.merge(K[["row", "side", "sf"]], on=["row", "side"], how="left")
    L["sf"] = L["sf"].fillna(0.0)
    a = np.zeros(len(F)); b = np.zeros(len(F))
    m0 = L["side"].to_numpy() == 0
    a[L.loc[m0, "row"].to_numpy()] = L.loc[m0, "sf"].to_numpy()
    b[L.loc[~m0, "row"].to_numpy()] = L.loc[~m0, "sf"].to_numpy()
    return np.clip(a - b, -MC6_SFORM_CAP, MC6_SFORM_CAP)


# ---- MC5's blend ----
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
print("base blend built", flush=True)

H_DIRTY = build_h2h()
H_MCLEAN = build_h2h(clean_margin=True)
H_DROP = build_h2h(drop_unfinished_entirely=True)
S_DIRTY = build_sform(np.zeros(len(F), bool))
S_NOWO = build_sform(WO)
S_NOUNF = build_sform(UNF)
print("terms built", flush=True)
print("   mean |h2h| dirty %.4f  margin-clean %.4f  drop %.4f"
      % (np.abs(H_DIRTY).mean(), np.abs(H_MCLEAN).mean(), np.abs(H_DROP).mean()))
print("   rows where margin-clean changes h2h by >0.01: %d"
      % int((np.abs(H_MCLEAN - H_DIRTY) > 0.01).sum()))
print("   mean |sform| dirty %.4f  no-wo %.4f  no-unf %.4f"
      % (np.abs(S_DIRTY).mean(), np.abs(S_NOWO).mean(), np.abs(S_NOUNF).mean()))

Y = F["won"].astype(int).to_numpy()
PRICED = F["imp"].notna().to_numpy()
YEAR = F["year"].to_numpy()
VARIANTS = [
    ("BASE (MC5 alone)", None, None),
    ("dirty (ships today)", H_DIRTY, S_DIRTY),
    ("margin-clean", H_MCLEAN, S_DIRTY),
    ("h2h-drop", H_DROP, S_DIRTY),
    ("sform-nowo", H_DIRTY, S_NOWO),
    ("sform-nounf", H_DIRTY, S_NOUNF),
    ("both-clean", H_MCLEAN, S_NOWO),
    ("all-clean", H_DROP, S_NOUNF),
]
BAR = "=" * 96
print("\n" + BAR)
print("HELD-OUT YEARS, shipped weights wH %.2f / wS %.2f" % (MC6_WH, MC6_WS))
print(BAR)
print("   %-22s %8s %8s %10s %10s" % ("variant", "AUC", "Brier", "dAUC", "dBrier"))
for yr in (2025, 2026):
    m = PRICED & (YEAR == yr)
    print("\n   %d   n=%d" % (yr, int(m.sum())))
    ref = None
    for nm, h, s in VARIANTS:
        z = BASE.copy()
        if h is not None:
            z = z + MC6_WH * h + MC6_WS * s
        p = 1 / (1 + np.exp(-z[m]))
        a = roc_auc_score(Y[m], p)
        b = brier_score_loss(Y[m], np.clip(p, 1e-6, 1 - 1e-6))
        if nm.startswith("dirty"):
            ref = (a, b)
        d = ("" if ref is None or nm.startswith("dirty")
             else "  %+9.5f %+9.5f" % (a - ref[0], b - ref[1]))
        print("   %-22s %8.5f %8.5f%s" % (nm, a, b, d))
print("\n" + BAR)
print("READ: dAUC/dBrier are against DIRTY, the version shipping today. A clean variant that")
print("beats it on BOTH held-out years, on both metrics, is worth shipping; the effect is")
print("expected to be small since unfinished rows are 4.3%% of the archive and feed only part")
print("of one term.")
print(BAR)
