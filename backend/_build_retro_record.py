"""Builds the backdated 2026-season Model E record the Profit tab displays alongside the live
log: 2026-03-25 -> 2026-08-19, retro-computed walk-forward at the de-vigged close -- NOT a
live log, and labeled as such everywhere it appears. (user request 2026-09-04)

Method: the season window is split into 5 chronological slices; each slice is predicted by a
5-seed ensemble trained only on games BEFORE it (full 2024+ history), so no game is ever
predicted by a model that saw it. Bets come from model_e.compute_bet under the CURRENT rule
(fav >= 3 pts, dog flip >= 6 pts, post-9/4 thresholds), settled at the fair de-vigged closing
consensus, with a secondary number at 3.5% vig (realistic multi-book shop). Honesty notes
baked into the JSON: retro records cannot lose to line movement, bet limits, or missed
prices the way a live bettor can -- treat as an upper bound on the period, not a diary.

Writes model_artifacts/model_e_retro_record.json (committed; served by
/api/model-e-retro-record). Rerun after any threshold/model change to keep it truthful."""
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import model as model_module
import model_e
from build_training_data import TRAINING_CACHE

START, END = "2026-03-25", "2026-08-19"
N_SLICES = 5
VIG = 0.035

df = pd.read_parquet(TRAINING_CACHE).sort_values("game_date").reset_index(drop=True)
df = df[df["home_win"].notna()].reset_index(drop=True)
y = df["home_win"].astype(int).values
mkt = (0.5 + df["consensus_prob_diff"]).values
gdate = df["game_date"].astype(str).values

win_idx = np.where((gdate >= START) & (gdate <= END) & ~np.isnan(mkt))[0]
print(f"window {START}..{END}: {len(win_idx)} games with a market close")
slices = np.array_split(win_idx, N_SLICES)

pE = np.full(len(df), np.nan)
for si, sl in enumerate(slices):
    a = sl.min()  # train on everything strictly before this slice's first game
    ps = []
    for s in model_module.ENSEMBLE_SEEDS:
        m, med, _ = model_module.train(df.iloc[:a], "home_win", save=False,
                                       feature_columns=model_e.MODEL_E_FEATURE_COLUMNS, random_state=s)
        ps.append(m.predict_proba(df.iloc[sl][model_e.MODEL_E_FEATURE_COLUMNS].fillna(med))[:, 1])
    pE[sl] = np.mean(ps, axis=0)
    print(f"  slice {si+1}/{N_SLICES}: {gdate[sl.min()]}..{gdate[sl.max()]}, trained on {a} prior games")

rows = []
for i in win_idx:
    if np.isnan(pE[i]):
        continue
    bt = model_e.compute_bet(float(pE[i]), float(mkt[i]), "H", "A")
    if not bt:
        continue
    won = bool(y[i]) if bt["side_is_home"] else not bool(y[i])
    dec_fair = 1.0 / bt["market_prob"]
    rows.append({"date": gdate[i], "month": gdate[i][:7], "type": bt["type"],
                 "dog_grade": bt.get("dog_grade"), "won": won,
                 "pnl_fair": (dec_fair - 1.0) if won else -1.0,
                 "pnl_vig": (dec_fair * (1 - VIG) - 1.0) if won else -1.0})
d = pd.DataFrame(rows)


def agg(s):
    return {"n": int(len(s)), "wins": int(s["won"].sum()), "hit_rate": round(float(s["won"].mean()), 4),
            "flat_roi_pct": round(100 * float(s["pnl_fair"].mean()), 2),
            "flat_roi_pct_at_vig": round(100 * float(s["pnl_vig"].mean()), 2),
            "units_profit": round(float(s["pnl_fair"].sum()), 2)}


out = {
    "label": f"{START} → {END} (retro-computed walk-forward at close · not a live log)",
    "start": START, "end": END,
    "computed_at": datetime.now(timezone.utc).isoformat(),
    "rule": "fav >= 3 pts, dog flip >= 6 pts (post-2026-09-04 thresholds)",
    "settle": "fair de-vigged closing consensus; _at_vig fields assume a 3.5% effective vig",
    "note": ("Retro-computed: every game predicted by an ensemble trained only on earlier games, "
             "but no retro record pays vig variance, gets limited, or misses a close -- treat as an "
             "upper bound on the period, not a diary."),
    "all": agg(d),
    "by_type": {t: agg(s) for t, s in d.groupby("type")},
    "by_class": {
        "dog_a": agg(d[(d["type"] == "underdog") & (d["dog_grade"] == "A")]),
        "dog_b": agg(d[(d["type"] == "underdog") & (d["dog_grade"] != "A")]),
        "favorite": agg(d[d["type"] == "favorite"]),
    },
    "by_month": [{"month": m, **agg(s)} for m, s in d.groupby("month")],
}
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model_artifacts", "model_e_retro_record.json")
with open(path, "w") as f:
    json.dump(out, f, indent=1)
print(f"\nwrote {path}")
print(f"ALL: {out['all']}")
for r in out["by_month"]:
    print(f"  {r['month']}: n={r['n']} hit={r['hit_rate']} roi_fair={r['flat_roi_pct']}% roi_vig={r['flat_roi_pct_at_vig']}% units={r['units_profit']}")
print("DONE")
