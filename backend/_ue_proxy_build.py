"""HOW ACCURATE IS AN ESTIMATED UNFORCED-ERROR NUMBER? (2026-10-09, user: "anyway to get an
unforced errors number for every single game?")

Real UE comes from the Match Charting Project, which is volunteer-charted: both players are
charted on 42.9% of our settled ATP games, 20.6% of WTA, 0.5% of challengers and effectively no
ITF futures -- and futures are 348k of the archive's 615k player-matches. A real UE number for
every game does not exist and cannot be scraped into existence.

So this measures the alternative: learn UE/set from the stat line every match DOES have
(tennis_ue_proxy.build_feats) using the charted matches where the true count is known, and see
how close it gets -- walk-forward by year, plus the thing that actually matters for a signal:
given the two players in one match, does the estimate put the lower-error one in front?

_ue_proxy_backtest.py then asks whether that estimate carries the betting edge.
"""
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

import tennis_ue_proxy as P

GAP = 2.264        # the women's median real-UE gap the live lane uses

print("loading…", flush=True)
A = P.prep(pd.read_parquet("data_cache/tennisratio/all_match_logs.parquet"))
J = P.charted_truth(A)
print(f"charted player-matches joined to a stat line: {len(J)}")
print(f"  by year: {J.d.dt.year.value_counts().sort_index().to_dict()}")
print(f"  by level: {J.lvl.value_counts().to_dict()}")
print(f"  true UE/set: mean {J.ue_set.mean():.2f}, sd {J.ue_set.std():.2f} "
      f"| women {J[J.is_w == 1].ue_set.mean():.2f} men {J[J.is_w == 0].ue_set.mean():.2f}")

X = P.build_feats(J, J["is_w"].values)
yr = J["d"].dt.year.values

print("\n=== ACCURACY, trained only on earlier years ===")
for name, yv, unit in (("UE per set", J.ue_set.values, "errors/set"),
                       ("UE per 100 pts", J.ue_100.values, "per 100pts")):
    print(f"  {name}:")
    for Y in (2024, 2025, 2026):
        tr, te = yr < Y, yr == Y
        if te.sum() < 100 or tr.sum() < 500:
            continue
        m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.06, random_state=0)
        m.fit(X[tr], yv[tr])
        pred = m.predict(X[te])
        print(f"    {Y}: MAE {mean_absolute_error(yv[te], pred):.2f} {unit} "
              f"(guess-the-mean {mean_absolute_error(yv[te], np.full(te.sum(), yv[tr].mean())):.2f}) | "
              f"R2 {r2_score(yv[te], pred):+.3f} | corr {np.corrcoef(pred, yv[te])[0, 1]:+.3f}")

print("\n=== DOES IT RANK THE TWO PLAYERS IN A MATCH CORRECTLY? ===")
tr = yr < 2025
m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.06, random_state=0)
m.fit(X[tr], J.ue_set.values[tr])
T = J[~tr].copy()
T["pred_set"] = m.predict(X[~tr])
T["mkey"] = [f"{d:%Y%m%d}-" + "-".join(sorted([a, b])) for d, a, b in zip(T.d, T.key, T.okey)]
pairs = []
for _, x in T.groupby("mkey"):
    if len(x) != 2:
        continue
    a, b = x.iloc[0], x.iloc[1]
    pairs.append((a.ue_set - b.ue_set, a.pred_set - b.pred_set))
Pr = pd.DataFrame(pairs, columns=["true_gap", "pred_gap"]).dropna()
print(f"  matches with both sides charted + predicted (2025-26): {len(Pr)}")
print(f"  estimate names the LOWER-ERROR player correctly: "
      f"{100 * (np.sign(Pr.true_gap) == np.sign(Pr.pred_gap)).mean():.1f}%")
big = Pr[Pr.pred_gap.abs() >= GAP]
if len(big):
    print(f"  when the estimated gap clears {GAP}/set (n={len(big)}): "
          f"{100 * (np.sign(big.true_gap) == np.sign(big.pred_gap)).mean():.1f}% correct, "
          f"true gap then averages {big.true_gap.abs().mean():.2f}/set")
print(f"  correlation of estimated gap with true gap: {Pr.pred_gap.corr(Pr.true_gap):+.3f}")
sys.stdout.flush()
