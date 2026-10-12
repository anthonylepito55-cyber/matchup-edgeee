"""WHICH GRAY-LINE DOG CELLS QUALIFY FOR THE DARK-BLUE MARK? (2026-10-11, user: "Mark all of
those dog picks dark blue with positive roi in backtest and live for women or men")

The gate the user set is BOTH layers positive, per gender. So this produces the exact table the
mark needs: for each gray line (A, B, C) on the market dog, the backtest ROI (3-year and
2026-only) and the LIVE ROI, split men/women. A (head x gender) cell qualifies only if backtest
AND live are both above zero.

Model D's gray line is NOT here: the shipped backtest prep (`_tennis_abc6_agree_bt.py`) builds
core_a / core_b / core_c only, so there is no way to walk-forward D's market-aware head with
this rig. D-gray-dog looks strong live (+26.8%, n=33) but with no backtest it cannot satisfy a
"both layers" gate, so it is excluded by the rule rather than by the evidence -- worth revisiting
if a D core is ever built.
"""
import numpy as np
import pandas as pd

ns = {}
src = open("_tennis_abc6_agree_bt.py", encoding="utf-8").read()
exec(compile(src.split("tot = {")[0], "_prep6", "exec"), ns)
KEY = ns["KEY"]
mC = ns["mC"] if "mC" in ns else ns["m"]
CORES = [("A", ns["core_a"], ns["FC_A"]), ("B", ns["core_b"], ns["FC_B"]),
         ("C", ns["core_c"], ns["FC_C"])]

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


def fit_ms(core, FC, yr):
    """Only the market-aware head is needed here."""
    tr = core[core["date"].dt.year < yr]
    te = core[core["date"].dt.year == yr]
    Xtr, Xte = tr[FC].fillna(0), te[FC].fillna(0)
    lr_ms = LogisticRegression(max_iter=3000, C=0.5).fit(
        np.column_stack([lg(tr["mkt"]), Xtr]), tr["won"])
    p_ms = lr_ms.predict_proba(np.column_stack([lg(te["mkt"]), Xte]))[:, 1]
    return {k: (float(pm), bool(w), float(m1), a, b)
            for k, pm, w, m1, a, b in zip(te[KEY].itertuples(index=False, name=None),
                                          p_ms, te["won"].values, te["mkt"].values,
                                          te["player_odd"].values, te["rival_odd"].values)}


BT = {}
for nm, core, FC in CORES:
    rows, seen = [], set()
    for yr in (2024, 2025, 2026):
        for k, (pm, w1, m1, a, b) in fit_ms(core, FC, yr).items():
            pair = (k[0], *sorted((str(k[1]), str(k[2]))))
            if pair in seen:
                continue
            seen.add(pair)
            g = lvl.get(k, "?")
            if g == "?" or not a or not b or a <= 1.005 or b <= 1.005:
                continue
            dog1 = m1 < 0.5
            if (pm >= 0.5) != dog1:                 # must be on the DOG
                continue
            o = a if dog1 else b
            rows.append({"pnl": (o - 1) if (w1 == dog1) else -1.0, "won": w1 == dog1,
                         "imp": m1 if dog1 else 1 - m1, "yr": yr, "G": g, "dog_dec": o})
    BT[nm] = pd.DataFrame(rows)
    print("%s gray on the dog: %d backtest bets" % (nm, len(BT[nm])))

# -------------------------------------------------------------------- live
d = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
S = d[(d["settled"] == True) & d.p1_won.notna() & d.p1_odds.notna()       # noqa: E712
      & d.p2_odds.notna()].copy()
for c in ("surface_bad", "inplay_suspect"):
    if c in S.columns:
        S = S[~S[c].fillna(False).astype(bool)]


def dec(x):
    x = float(x)
    return 1 + x / 100.0 if x > 0 else 1 + 100.0 / abs(x)


S["d1"], S["d2"] = S.p1_odds.map(dec), S.p2_odds.map(dec)
i1, i2 = 1 / S.d1, 1 / S.d2
S["mkt1"] = i1 / (i1 + i2)
S["dog1"] = S.mkt1 < 0.5
lgs = S.league.astype(str)
S["G"] = np.where(lgs.str.contains("wta") | lgs.str.contains("itf_women"), "W", "M")
COL = {"A": "model_ama_p1", "B": "model_bma_p1", "C": "model_cma_p1"}


def st(s):
    n = len(s)
    if n == 0:
        return None
    return n, 100 * s.pnl.mean(), (100 * s.pnl.std(ddof=1) / np.sqrt(n)) if n > 1 else float("nan")


print("\n" + "=" * 118)
print("QUALIFYING TABLE -- gray line on the DOG, per gender. Gate: backtest AND live both > 0")
print("=" * 118)
print("   %-18s %-26s %-26s %-26s %s" % ("head / gender", "bt 3-year", "bt 2026", "LIVE", "verdict"))
verdict_rows = []
for nm in ("C", "A", "B"):
    B = BT[nm]
    col = COL[nm]
    L = S[S[col].notna()].copy()
    side = L[col].astype(float) >= 0.5
    L = L[side == L.dog1]
    won = L.p1_won.astype(bool) == L.dog1
    odds = np.where(L.dog1, L.d1, L.d2)
    L = L.assign(pnl=np.where(won, odds - 1, -1.0), won=won)
    for Gg, gname in (("M", "men"), ("W", "women")):
        b3, b26, lv = st(B[B.G == Gg]), st(B[(B.G == Gg) & (B.yr == 2026)]), st(L[L.G == Gg])

        def f(t, thin):
            if t is None or t[0] < thin:
                return "n=%-4s --" % (t[0] if t else 0)
            return "%+6.1f%% ±%4.1f (n=%d)" % (t[1], t[2], t[0])
        ok_bt = b3 is not None and b3[0] >= 100 and b3[1] > 0
        ok_lv = lv is not None and lv[0] >= 10 and lv[1] > 0
        verdict = ("QUALIFIES" if (ok_bt and ok_lv) else
                   "no: live thin" if (ok_bt and (lv is None or lv[0] < 10)) else
                   "no: live negative" if ok_bt else
                   "no: backtest fails" if (b3 and b3[0] >= 100) else "no: backtest thin")
        print("   %-18s %-26s %-26s %-26s %s"
              % ("%s gray / %s" % (nm, gname), f(b3, 100), f(b26, 60), f(lv, 10), verdict))
        verdict_rows.append((nm, Gg, b3, b26, lv, verdict))

print("\n   the +100..+200 slice of the qualifying head(s), for reference:")
for nm in ("C",):
    B = BT[nm]
    Bb = B[(B.dog_dec >= 2.0) & (B.dog_dec <= 3.0)]
    for Gg, gname in (("M", "men"), ("W", "women")):
        t3, t26 = st(Bb[Bb.G == Gg]), st(Bb[(Bb.G == Gg) & (Bb.yr == 2026)])
        print("      %s gray dog +100..+200 / %-6s bt3y %+6.1f%% (n=%d)   bt2026 %+6.1f%% (n=%d)"
              % (nm, gname, t3[1], t3[0], t26[1], t26[0]))

print("\n   HL_BT values to hardcode (backtest provenance for the mark):")
for nm, Gg, b3, b26, lv, v in verdict_rows:
    if v == "QUALIFIES":
        print("      %s gray / %s : bt3y %+.1f%%, bt2026 %+.1f%%, live %+.1f%% (n=%d)"
              % (nm, "men" if Gg == "M" else "women", b3[1], b26[1], lv[1], lv[0]))
