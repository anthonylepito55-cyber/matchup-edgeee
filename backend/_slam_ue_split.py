"""DID THE ROLAND GARROS DATA HELP OR HURT? (2026-10-10)

Adding RG women's singles 2024-26 lifted coverage (2026 slice 435 -> 516 gradeable, 35 of the
195 blocked players profiled, gate sample 276 -> 427) but the measured edge HALVED: +10.8%
(n=276) became +5.4% (n=427), WTA tour alone +4.5%, and 2026 went from +12.5% to -5.2%.

Two explanations, with opposite conclusions:

  A. DILUTION. The original +10.8% was partly a selection effect -- the matches where both
     players happened to be well charted. A wider sample reveals a weaker true edge, and the
     honest move is to accept the lower number.
  B. CONTAMINATION. Roland Garros is CLAY. ue_set_5 is surface-agnostic (last 5 matches on any
     court), so five clay matches drag a player's profile toward her clay error rate, which is
     then applied to her hard-court matches. That would make the new profiles actively
     misleading rather than merely thinner.

The test that separates them: score the gate on matches that were ALREADY gradeable before the
merge, versus matches gradeable ONLY because of it. If the old subset holds its number and the
new subset is bad, it is B and the slam data must stay out of the gate. If both sagged, it is A
and the edge was always weaker than measured.
"""
import sys

import numpy as np
import pandas as pd

import tennis_ue as U
from _slam_ue_impact import rep, universe

GAP = 2.264
W = universe()
print(f"women's WTA-tour/slam dogs +100..+250, 2024-26: {len(W)}", flush=True)

# profiles WITHOUT the slam rows -- same loader, slam source filtered out
U.load(force=True)
full = U._CACHE["df"]
U._CACHE["df"] = full[full["src"] != "manual"].copy()
U._CACHE["by"] = {k: g for k, g in U._CACHE["df"].groupby("key")}
old_ok = set()
rows = []
for r in W.itertuples():
    a, b = U.profile(r.player_slug, r.date), U.profile(r.rival_slugname, r.date)
    if a and b and a.get("ue_set_5") is not None and b.get("ue_set_5") is not None:
        old_ok.add((r.date, str(r.player_slug), str(r.rival_slugname)))
print(f"gradeable WITHOUT the slam data: {len(old_ok)}")

# and now with it
U._CACHE["df"] = full
U._CACHE["by"] = {k: g for k, g in full.groupby("key")}
for r in W.itertuples():
    a, b = U.profile(r.player_slug, r.date), U.profile(r.rival_slugname, r.date)
    if not a or not b or a.get("ue_set_5") is None or b.get("ue_set_5") is None:
        continue
    key = (r.date, str(r.player_slug), str(r.rival_slugname))
    rows.append({"won": bool(r.won), "player_odd": r.player_odd, "mkt": r.mkt, "lvl": r.lvl,
                 "yr": r.date.year, "gap": b["ue_set_5"] - a["ue_set_5"],
                 "was_old": key in old_ok})
R = pd.DataFrame(rows)
G = R[R.gap >= GAP]
print(f"gradeable WITH the slam data:    {len(R)}  (gate fires on {len(G)})\n")

print("=== THE SPLIT ===")
print(f"  gate, matches gradeable BEFORE the merge : {rep(G[G.was_old])}")
print(f"  gate, matches gradeable ONLY AFTER       : {rep(G[~G.was_old])}")
print()
print("  by year, old subset:")
for Y in (2024, 2025, 2026):
    s = G[G.was_old & (G.yr == Y)]
    if len(s) >= 20:
        print(f"    {Y}: {rep(s)}")
print("  by year, new subset:")
for Y in (2024, 2025, 2026):
    s = G[(~G.was_old) & (G.yr == Y)]
    if len(s) >= 20:
        print(f"    {Y}: {rep(s)}")

print("\n=== IS IT A CLAY PROBLEM? ===")
# do the newly-profiled players have clay-skewed profiles? compare their ue_set_5 against the
# population, since RG is clay and clay rallies are longer (more errors per set)
sl = pd.read_csv("data_cache/mcp/slam_ue.csv", dtype=str)
sl["ue"] = pd.to_numeric(sl["unforced"], errors="coerce") / pd.to_numeric(sl["sets"], errors="coerce")
mcp = full[full["src"] != "manual"]
mcp_ue = (mcp["unforced"] / mcp["sets"]).replace([np.inf, -np.inf], np.nan).dropna()
print(f"  UE/set in the Roland Garros rows (clay): mean {sl.ue.mean():.2f}  (n={sl.ue.notna().sum()})")
print(f"  UE/set across the charting project:      mean {mcp_ue.mean():.2f}  (n={len(mcp_ue)})")
d = sl.ue.mean() - mcp_ue.mean()
print(f"  difference: {d:+.2f} errors per set")
print("  -> a profile part-built from clay is shifted by roughly this much, which is "
      f"{abs(d) / GAP * 100:.0f}% of the {GAP}/set gap the gate requires")
sys.stdout.flush()
