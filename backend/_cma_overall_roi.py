"""THE MARKET-AWARE C's OVERALL ROI (2026-10-11, user: "c market aware model roi").

Everything so far has been a slice -- the dog side, a price band, a 4pt threshold. This is the
plain question: back the gray line's pick on EVERY match it prices. What does it return?

Reported as backtest (3-year and 2026-only, since the cell decays) against the live frozen log,
then broken down the one way that actually explains the number: dog vs favourite. The gray line
spends most of its picks on favourites, so its headline ROI is mostly a statement about that.

Shipped walk-forward rig, one row per match; live excludes surface_bad / inplay_suspect.
"""
import numpy as np
import pandas as pd

ns = {}
src = open("_tennis_abc6_agree_bt.py", encoding="utf-8").read()
exec(compile(src.split("tot = {")[0], "_prep6", "exec"), ns)
KEY = ns["KEY"]
core_c, FC_C = ns["core_c"], ns["FC_C"]
mC = ns["mC"] if "mC" in ns else ns["m"]
lvl, lvlraw = {}, {}
for k, l in zip(mC[KEY].itertuples(index=False, name=None), mC["tournament_level"].astype(str)):
    s = l.lower()
    lvl[k] = "W" if ("wom" in s or "wta" in s) else (
        "M" if ("atp" in s or "men" in s or "challenger" in s or "future" in s) else "?")
    lvlraw[k] = s

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
        side = pcg >= 0.5                       # the gray line's pick
        o = a if side else b
        lv = lvlraw.get(k, "")
        rows.append({"pnl": (o - 1) if (w1 == side) else -1.0, "won": w1 == side,
                     "imp": m1 if side else 1 - m1, "yr": yr, "G": g,
                     "on_dog": side == dog1, "price": o,
                     "level": ("itf" if ("itf" in lv or "future" in lv)
                               else "challenger" if "challenger" in lv else "tour")})
B = pd.DataFrame(rows)

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
    side = float(r.model_cma_p1) >= 0.5
    o = r.d1 if side else r.d2
    out.append({"pnl": (o - 1) if (bool(r.p1_won) == side) else -1.0,
                "won": bool(r.p1_won) == side,
                "imp": r.mkt1 if side else 1 - r.mkt1,
                "on_dog": side == dog1, "price": o,
                "G": "W" if ("wta" in str(r.league) or "itf_women" in str(r.league)) else "M",
                "level": ("itf" if "itf" in str(r.league)
                          else "challenger" if "challenger" in str(r.league) else "tour")})
L = pd.DataFrame(out)


def stat(s):
    n = len(s)
    if n == 0:
        return None
    return n, 100 * s.pnl.mean(), (100 * s.pnl.std(ddof=1) / np.sqrt(n)) if n > 1 else float("nan")


def line(lab, bsel, lsel, thin_b=40, thin_l=8):
    def f(t, thin):
        if t is None or t[0] < thin:
            return "n=%-5s --" % (t[0] if t else 0)
        return "%+6.1f%% ±%4.1f (n=%d)" % (t[1], t[2], t[0])
    print("   %-24s  bt3y %-24s  bt2026 %-24s  LIVE %s"
          % (lab, f(stat(B[bsel]), thin_b), f(stat(B[bsel & (B.yr == 2026)]), thin_b),
             f(stat(L[lsel]), thin_l)))


ALLB, ALLL = B.index == B.index, L.index == L.index
print("\n" + "=" * 122)
print("MARKET-AWARE C (gray line) -- ROI backing its pick on EVERY match")
print("=" * 122)
line("** ALL PICKS **", ALLB, ALLL)
print()
line("   on the FAVOURITE", ~B.on_dog, ~L.on_dog)
line("   on the DOG", B.on_dog, L.on_dog)
print("\n   share of its picks that are dogs:  bt3y %.0f%%   bt2026 %.0f%%   live %.0f%%"
      % (100 * B.on_dog.mean(), 100 * B[B.yr == 2026].on_dog.mean(), 100 * L.on_dog.mean()))
print()
print("   hit rate vs the market's own implied (is it even accurate?):")
for lab, sel in (("all picks", ALLB), ("favourite", ~B.on_dog), ("dog", B.on_dog)):
    s = B[sel]
    s26 = B[sel & (B.yr == 2026)]
    print("      %-12s bt3y hit %4.1f%% vs no-vig %4.1f%% (EDGE %+4.1fpt) | "
          "bt2026 hit %4.1f%% vs %4.1f%% (EDGE %+4.1fpt)"
          % (lab, 100 * s.won.mean(), 100 * s.imp.mean(),
             100 * (s.won.mean() - s.imp.mean()),
             100 * s26.won.mean(), 100 * s26.imp.mean(),
             100 * (s26.won.mean() - s26.imp.mean())))
sl = L
print("      %-12s LIVE hit %4.1f%% vs no-vig %4.1f%% (EDGE %+4.1fpt)  n=%d"
      % ("all picks", 100 * sl.won.mean(), 100 * sl.imp.mean(),
         100 * (sl.won.mean() - sl.imp.mean()), len(sl)))
print()
print("   by gender:")
for Gg, nm in (("M", "men"), ("W", "women")):
    line("      %s" % nm, B.G == Gg, L.G == Gg)
print("   by level:")
for lv in ("tour", "challenger", "itf"):
    line("      %s" % lv, B.level == lv, L.level == lv)
print("   by year (backtest):")
for y in (2024, 2025, 2026):
    t = stat(B[B.yr == y])
    print("      %-22s %+6.1f%% ±%4.1f (n=%d)" % (y, t[1], t[2], t[0]))
