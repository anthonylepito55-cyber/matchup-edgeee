"""MODEL G -- does the LIVE path reproduce the training recipe? (2026-10-12)

This is the check that project_live_e_drift_audit exists to force. Model E passed every
backtest cell and then inflated favourites by 3.5-7.1 points live, on identical games,
because the live feature path had quietly drifted from the recipe the model was fit on. A
model is only as good as the agreement between the two.

Two independent paths are compared on the same players and the same window:
  LIVE    -- tennis_model_a._profile -> the g52 sums -> predict_g's stat() shrink
  RECIPE  -- the raw archive, windowed and discounted and shrunk directly here

They must agree to floating point. Anything bigger is a live/training mismatch, which is
the one failure mode that cannot be caught by any amount of backtesting.
"""
import numpy as np
import pandas as pd

import tennis_model_a as T

mdl = T.g_model()
if mdl is None:
    raise SystemExit("Model G artifact not built")
cache = T._load()
if not cache:
    raise SystemExit("profile cache unavailable")

raw = T._parse(pd.read_parquet(T.LOGS_PARQUET))
raw["date"] = pd.to_datetime(raw["date"]).dt.normalize()
today = raw["date"].max()
edges = np.asarray(mdl["bin_edges"], dtype=float)
NB = len(edges) - 1

GEN = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
SURF = "Hard"
rows, worst = [], 0.0
# the busiest hard-court players, so every stat has a real denominator
cands = (raw[(raw["surface"].astype(str).str.title() == SURF)
             & (raw["date"] >= today - pd.Timedelta(days=365))]
         .groupby("player_slug").size().sort_values(ascending=False).head(40).index)

for slug in cands:
    gd = GEN.get(slug)
    if gd not in ("M", "W"):
        continue
    prof = (cache["profiles"].get(slug) or {}).get("surf", {}).get(SURF) or {}
    g52 = prof.get("g52")
    if not g52:
        continue
    on = raw[(raw["player_slug"] == slug) & (raw["surface"].astype(str).str.title() == SURF)]
    w = on[on["date"] >= today - pd.Timedelta(days=365)]
    if len(w) < 5:
        # mirror the adaptive window: under 5 in the year, the last 20 on this surface
        w = on.sort_values("date").tail(20)
    if not len(w):
        continue
    b = np.clip(np.searchsorted(edges, w["logr"].to_numpy(float), side="left") - 1, 0, NB - 1)
    for nm, num, den in T.G_STATS:
        if den is None:
            r = pd.to_numeric(w[num], errors="coerce").astype(float)
            if nm != "win":
                r = r / 100.0
            r = r.where(r.between(0, 1))
            d = r.notna().astype(float)
        else:
            dd = pd.to_numeric(w[den], errors="coerce").astype(float).replace(0, np.nan)
            r = pd.to_numeric(w[num], errors="coerce").astype(float) / dd
            d = dd.where(r.notna())
        ok = r.notna().to_numpy() & np.isfinite(d.to_numpy(float))
        dv = np.where(ok, d.to_numpy(float), 0.0)
        rv = np.where(ok, r.to_numpy(float), 0.0)
        eff = np.asarray(mdl["opp_eff"].get((gd, nm), np.zeros(NB)), dtype=float)
        k = float(mdl["k"].get((gd, nm), 1.0))
        pr = float(mdl["prior"].get((gd, nm), 0.0))
        recipe = ((rv * dv).sum() - (eff[b] * dv).sum() + k * pr) / (dv.sum() + k)
        st = g52.get(nm) or {}
        if not st.get("den"):
            continue
        live = (st["num"] - st.get("eff" + gd, 0.0) + k * pr) / (st["den"] + k)
        rows.append({"slug": slug, "g": gd, "stat": nm, "live": live, "recipe": recipe,
                     "diff": abs(live - recipe), "den": st["den"]})
        worst = max(worst, abs(live - recipe))

d = pd.DataFrame(rows)
print("compared %d player-stat pairs across %d players" % (len(d), d["slug"].nunique()))
print("max |live - recipe| = %.3e" % worst)
print()
print("by stat:")
print(d.groupby("stat").agg(n=("diff", "size"), max_diff=("diff", "max"),
                            mean_live=("live", "mean"), mean_recipe=("recipe", "mean")).to_string())
bad = d[d["diff"] > 1e-9]
if len(bad):
    print("\nMISMATCHES (live path has drifted from the recipe):")
    print(bad.sort_values("diff", ascending=False).head(20).to_string())
else:
    print("\nthe live path reproduces the training recipe exactly on every stat.")

# and the raw-vs-adjusted spread, so the adjustment is visibly doing something live
print("\nwhat the opponent adjustment moves, live (percentage points on the stat):")
for nm in ("sgw", "rgw", "svp", "rtp", "win"):
    sub = d[d.stat == nm]
    if not len(sub):
        continue
    shift = []
    for _, r in sub.iterrows():
        prof = cache["profiles"][r.slug]["surf"][SURF]["g52"][nm]
        k = float(mdl["k"].get((r.g, nm), 1.0))
        pr = float(mdl["prior"].get((r.g, nm), 0.0))
        unadj = (prof["num"] + k * pr) / (prof["den"] + k)
        shift.append(100 * (r.live - unadj))
    print("   %-4s mean %+.2fpt   min %+.2f   max %+.2f" % (nm, np.mean(shift), min(shift), max(shift)))
