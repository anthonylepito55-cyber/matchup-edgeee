"""MODEL G2 -- does the live last-10 block reproduce the training recipe? (2026-10-12)

The same check G got, aimed at the new half. The build computes the block as a rolling window
over completed matches grouped on player|surface and then merge_asof's it strictly backwards;
_profile instead takes the tail of the surface frame directly. Two different implementations of
one definition is exactly the setup that let Model E drift, so they are compared element by
element on the busiest players.
"""
import numpy as np
import pandas as pd

import tennis_model_a as T

mdl = T.g2_model()
if mdl is None:
    raise SystemExit("G2 artifact not built")
cache = T._load()
raw = T._parse(pd.read_parquet(T.LOGS_PARQUET))
raw["date"] = pd.to_datetime(raw["date"]).dt.normalize()
raw["surf"] = raw["surface"].astype(str).str.title()
SURF = "Hard"
today = raw["date"].max()

cands = (raw[(raw["surf"] == SURF) & (raw["date"] >= today - pd.Timedelta(days=365))]
         .groupby("player_slug").size().sort_values(ascending=False).head(40).index)
rows, worst = [], 0.0
for slug in cands:
    live = ((cache["profiles"].get(slug) or {}).get("surf", {}).get(SURF) or {}).get("t10g")
    if not live:
        continue
    on = raw[(raw["player_slug"] == slug) & (raw["surf"] == SURF)].sort_values("date")
    comp = on[~T._walkover_mask(on)]
    t = comp.tail(10)
    if len(t) < 3:
        continue
    wl = t.loc[t["won"] == 1, "logr"].dropna()
    ll = t.loc[t["won"] == 0, "logr"].dropna()
    sga = t["sg_all"].replace(0, np.nan)
    rga = t["rg_all"].replace(0, np.nan)

    def mn(v):
        v = pd.to_numeric(v, errors="coerce").dropna()
        return float(v.mean()) if len(v) else None
    rec = {"t10_win": float(t["won"].mean()), "t10_faced": mn(t["logr"]),
           "t10_beaten": float(wl.mean()) if len(wl) else None,
           "t10_bestwin": float(wl.min()) if len(wl) else None,
           "t10_lost": float(ll.mean()) if len(ll) else None,
           "t10_worstloss": float(ll.max()) if len(ll) else None,
           "t10_meff": mn(t["meff"]), "t10_losscl": mn(t["l_meff"]),
           "t10_hold": mn(t["sg_won"] / sga), "t10_brk": mn(t["rg_won"] / rga),
           "t10_n": float(len(t))}
    for k, v in rec.items():
        lv = live.get(k)
        if v is None and lv is None:
            continue
        if v is None or lv is None:
            rows.append({"slug": slug, "stat": k, "live": lv, "recipe": v, "diff": np.nan})
            continue
        rows.append({"slug": slug, "stat": k, "live": float(lv), "recipe": v,
                     "diff": abs(float(lv) - v)})
        worst = max(worst, abs(float(lv) - v))

d = pd.DataFrame(rows)
print("compared %d player-stat pairs across %d players" % (len(d), d["slug"].nunique()))
print("max |live - recipe| = %.3e" % worst)
print()
print(d.groupby("stat").agg(n=("diff", "size"), max_diff=("diff", "max"),
                            mean_live=("live", "mean")).to_string())
bad = d[d["diff"].fillna(9e9) > 1e-9]
if len(bad):
    print("\nMISMATCHES:")
    print(bad.sort_values("diff", ascending=False).head(20).to_string())
else:
    print("\nthe live last-10 block reproduces the recipe exactly on every stat.")
print("\nwalkovers dropped per player (live): mean %.2f, max %d"
      % (np.mean([((cache["profiles"][s]["surf"][SURF]["t10g"] or {}).get("wo_dropped") or 0)
                  for s in cands if ((cache["profiles"].get(s) or {}).get("surf", {}).get(SURF) or {}).get("t10g")]),
         max([((cache["profiles"][s]["surf"][SURF]["t10g"] or {}).get("wo_dropped") or 0)
              for s in cands if ((cache["profiles"].get(s) or {}).get("surf", {}).get(SURF) or {}).get("t10g")])))
