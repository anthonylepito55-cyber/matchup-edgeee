"""GRAY-DOG CELL: BACKTEST vs LIVE, LIKE FOR LIKE (2026-10-11, user: "Backtest vs the live").

Two things make a naive comparison misleading, and both are fixed here.

1. **Period.** The live log is 2026 only (and really just Sep-Oct). Comparing it to a 2024-26
   backtest pool compares it to years it never saw, and this cell DECAYS (+20.5 / +18.8 /
   +12.6% by year). So every row below shows the 3-year backtest AND the 2026-only backtest
   next to live.
2. **The 10pt threshold question.** The previous run found the edge concentrated at 10pt+
   (+25.5% vs +17.5% overall) and I said live could not split that. That was an assumption --
   this actually does the split and shows the error bars, so the claim is measured rather than
   asserted.

Same shipped walk-forward rig; live from the frozen log with surface_bad / inplay_suspect
excluded, as every lane does.
"""
import numpy as np
import pandas as pd

ns = {}
src = open("_tennis_abc6_agree_bt.py", encoding="utf-8").read()
exec(compile(src.split("tot = {")[0], "_prep6", "exec"), ns)
KEY = ns["KEY"]
core_c, FC_C = ns["core_c"], ns["FC_C"]
mC = ns["mC"] if "mC" in ns else ns["m"]
lvl = {}
for k, l in zip(mC[KEY].itertuples(index=False, name=None), mC["tournament_level"].astype(str)):
    s = l.lower()
    lvl[k] = "W" if ("wom" in s or "wta" in s) else (
        "M" if ("atp" in s or "men" in s or "challenger" in s or "future" in s) else "?")

from sklearn.linear_model import LogisticRegression          # noqa: E402
import xgboost as xgb                                        # noqa: E402


def lg(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def fit_p(core, FC, yr):
    tr = core[core["date"].dt.year < yr]
    te = core[core["date"].dt.year == yr]
    Xtr, Xte = tr[FC].fillna(0), te[FC].fillna(0)
    ytr = tr["won"]
    lr = LogisticRegression(max_iter=3000, C=0.5).fit(Xtr, ytr)
    bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                            colsample_bytree=0.8, n_jobs=8, eval_metric="logloss").fit(Xtr, ytr)
    p = 0.5 * (lr.predict_proba(Xte)[:, 1] + bst.predict_proba(Xte)[:, 1])
    lr_ms = LogisticRegression(max_iter=3000, C=0.5).fit(
        np.column_stack([lg(tr["mkt"]), Xtr]), ytr)
    p_ms = lr_ms.predict_proba(np.column_stack([lg(te["mkt"]), Xte]))[:, 1]
    return {k: (float(pr), float(pm), bool(w), float(m1), a, b)
            for k, pr, pm, w, m1, a, b in zip(te[KEY].itertuples(index=False, name=None),
                                              p, p_ms, te["won"].values, te["mkt"].values,
                                              te["player_odd"].values, te["rival_odd"].values)}


rows, seen = [], set()
for yr in (2024, 2025, 2026):
    for k, (pcr, pcg, w1, m1, a, b) in fit_p(core_c, FC_C, yr).items():
        pair = (k[0], *sorted((str(k[1]), str(k[2]))))
        if pair in seen:
            continue
        seen.add(pair)
        g = lvl.get(k, "?")
        if g == "?" or not a or not b or a <= 1.005 or b <= 1.005:
            continue
        dog1 = m1 < 0.5
        if (pcg >= 0.5) != dog1:
            continue
        mdog = m1 if dog1 else 1 - m1
        gdog = pcg if dog1 else 1 - pcg
        o = a if dog1 else b
        rows.append({"pnl": (o - 1) if (w1 == dog1) else -1.0, "won": w1 == dog1,
                     "imp": mdog, "yr": yr, "G": g, "dog_dec": o,
                     "agree": (pcr >= 0.5) == dog1, "gap_pp": 100 * (gdog - mdog)})
B = pd.DataFrame(rows)

# ------------------------------------------------------------------ live
d = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
S = d[(d["settled"] == True) & d.p1_won.notna() & d.p1_odds.notna()       # noqa: E712
      & d.p2_odds.notna() & d.model_cma_p1.notna()].copy()
for c in ("surface_bad", "inplay_suspect"):
    if c in S.columns:
        S = S[~S[c].fillna(False).astype(bool)]


def dec(x):
    x = float(x)
    return 1 + x / 100.0 if x > 0 else 1 + 100.0 / abs(x)


S["d1"], S["d2"] = S.p1_odds.map(dec), S.p2_odds.map(dec)
i1, i2 = 1 / S.d1, 1 / S.d2
S["mkt1"] = i1 / (i1 + i2)
out = []
for r in S.itertuples():
    dog1 = r.mkt1 < 0.5
    if (float(r.model_cma_p1) >= 0.5) != dog1:
        continue
    mdog = r.mkt1 if dog1 else 1 - r.mkt1
    gdog = float(r.model_cma_p1) if dog1 else 1 - float(r.model_cma_p1)
    o = r.d1 if dog1 else r.d2
    won = bool(r.p1_won) == dog1
    ag = None
    if r.model_c_p1 is not None and not pd.isna(r.model_c_p1):
        ag = (float(r.model_c_p1) >= 0.5) == dog1
    out.append({"pnl": (o - 1) if won else -1.0, "won": won, "imp": mdog, "dog_dec": o,
                "agree": ag, "gap_pp": 100 * (gdog - mdog),
                "G": "W" if ("wta" in str(r.league) or "itf_women" in str(r.league)) else "M"})
L = pd.DataFrame(out)


def stat(s):
    n = len(s)
    if n == 0:
        return None
    roi = 100 * s.pnl.mean()
    se = 100 * s.pnl.std(ddof=1) / np.sqrt(n) if n > 1 else float("nan")
    return n, roi, se


def line(lab, bsel, lsel):
    b3 = stat(B[bsel])
    b26 = stat(B[bsel & (B.yr == 2026)])
    lv = stat(L[lsel])

    def f(t, thin):
        if t is None or t[0] < thin:
            return "n=%-4s  --" % (t[0] if t else 0)
        return "%+6.1f%% ±%4.1f (n=%d)" % (t[1], t[2], t[0])
    print("   %-26s  bt3y %-24s  bt2026 %-24s  LIVE %s"
          % (lab, f(b3, 40), f(b26, 40), f(lv, 8)))


print("\n" + "=" * 124)
print("GRAY LINE ON THE DOG -- 3-year backtest vs 2026 backtest vs LIVE (2026 Sep-Oct)")
print("=" * 124)
line("every gray dog pick", B.index == B.index, L.index == L.index)
line("   + Model C agrees", B.agree, L.agree == True)                     # noqa: E712
print()
print("   by gap (gray above market on the dog) -- the 10pt threshold question:")
for lo, hi, nm in ((0, 4, "under 4pt"), (4, 10, "4-10pt"), (10, 999, "10pt+")):
    line("      %s" % nm, (B.gap_pp >= lo) & (B.gap_pp < hi),
         (L.gap_pp >= lo) & (L.gap_pp < hi))
print()
print("   by dog price:")
for lo, hi, nm in ((1.0, 2.0, "under +100"), (2.0, 3.0, "+100..+200"), (3.0, 99, "+200+")):
    line("      %s" % nm, (B.dog_dec >= lo) & (B.dog_dec < hi),
         (L.dog_dec >= lo) & (L.dog_dec < hi))
print()
print("   by gender:")
for Gg, nm in (("M", "men"), ("W", "women")):
    line("      %s" % nm, B.G == Gg, L.G == Gg)

print("\n" + "=" * 124)
print("IS LIVE ACTUALLY BELOW THE BACKTEST? (z of the difference, live vs bt2026)")
print("=" * 124)
for lab, bsel, lsel in (("every gray dog pick", B.index == B.index, L.index == L.index),
                        ("+ C agrees", B.agree, L.agree == True),          # noqa: E712
                        ("10pt+ gap", B.gap_pp >= 10, L.gap_pp >= 10),
                        ("+100..+200", (B.dog_dec >= 2) & (B.dog_dec < 3),
                         (L.dog_dec >= 2) & (L.dog_dec < 3))):
    b26 = stat(B[bsel & (B.yr == 2026)])
    lv = stat(L[lsel])
    if not b26 or not lv or lv[0] < 8:
        print("   %-24s live too thin (n=%s)" % (lab, lv[0] if lv else 0))
        continue
    diff = lv[1] - b26[1]
    sed = (lv[2] ** 2 + b26[2] ** 2) ** 0.5
    print("   %-24s live %+6.1f%%  vs bt2026 %+6.1f%%   diff %+6.1f%% ± %4.1f  -> z %+4.1f  %s"
          % (lab, lv[1], b26[1], diff, sed, diff / sed if sed else 0,
             "consistent" if abs(diff / sed) < 2 else "DIVERGENT"))
