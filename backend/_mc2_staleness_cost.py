"""HOW MUCH DOES MC2's FROZEN RATING STATE COST? (2026-10-13)

Found by looking: NOTHING rebuilds the rating state. No systemd timer and no script references
_mc2_stage1b_serve_return.py or _mc3_build.py. Meanwhile the source match data IS being
refreshed -- all_match_logs.parquet is dated 2026-10-12 -- so the inputs move and the ratings
built from them do not.

    data_cache/_mc2_state.pkl        2026-10-08 13:15   <- what every card has been priced off
    data_cache/tennisratio/...       2026-10-12 10:11   <- the data it should have been built from

Coverage is not the symptom: MC2 priced 100% of logged rows on every day since 2026-10-09, so no
player is going unrated. The cost is accuracy decay -- every player's Elo and serve/return
rating is frozen before the last several days of results.

This sizes it instead of asserting it. `_mc2_state_sk1000000000.pkl` is the career-only control
built today from data through 2026-10-12 -- that is MC2's own recipe (the per-surface weight is
switched off at KS=1e9), so the two states are directly comparable and the only difference is
four extra days of matches.

Reports the rating drift and, more usefully, what it does to the PROBABILITY on cards actually
on the board today: if the median card moves a fraction of a point, a nightly rebuild is
housekeeping; if it moves points, MC2 has been quoting numbers that are materially out of date.
"""
import pickle

import numpy as np
import pandas as pd

import tennis_log
import tennis_mc2 as M2

OLD = "data_cache/_mc2_state.pkl"
NEW = "data_cache/_mc2_state_sk1000000000.pkl"
with open(OLD, "rb") as f:
    SO = pickle.load(f)
with open(NEW, "rb") as f:
    SN = pickle.load(f)
po, pn = SO["players"], SN["players"]
print("players: frozen state %d, rebuilt state %d, shared %d"
      % (len(po), len(pn), len(set(po) & set(pn))))

shared = sorted(set(po) & set(pn))
d_elo, d_S, d_R, d_n = [], [], [], []
for k in shared:
    a, b = po[k], pn[k]
    d_elo.append(b["elo"] - a["elo"])
    d_S.append(b["S"] - a["S"])
    d_R.append(b["R"] - a["R"])
    d_n.append(b["nS"] - a["nS"])
d_elo, d_S, d_R, d_n = map(np.array, (d_elo, d_S, d_R, d_n))
moved = d_n > 0
print("\nplayers who played in the gap: %d of %d (%.0f%%)"
      % (int(moved.sum()), len(shared), 100 * moved.mean()))
print("new serve observations for them: median %.0f, max %.0f"
      % (np.median(d_n[moved]) if moved.any() else 0, d_n.max()))
print("\nrating drift among those who played:")
for lab, v in (("Elo", d_elo[moved]), ("S (serve)", d_S[moved]), ("R (return)", d_R[moved])):
    if not len(v):
        continue
    print("   %-11s mean %+8.4f   median |d| %7.4f   p90 |d| %7.4f   max |d| %7.4f"
          % (lab, v.mean(), np.median(np.abs(v)), np.percentile(np.abs(v), 90),
             np.abs(v).max()))

# ---- what it does to today's actual board ----
L = pd.read_parquet(tennis_log.LOG_PATH)
L["day"] = L["date"].astype(str).str[:10]
today = L[L["day"] == L["day"].max()]
print("\nscoring %d rows on the latest logged day (%s) under both states ..."
      % (len(today), L["day"].max()))


def price_all(state):
    M2._S = state
    M2._anchor.cache_clear()
    out = []
    for _, r in today.iterrows():
        try:
            q = M2.predict(r["player_1"], r["player_2"], r.get("surface"))
        except Exception:                                          # noqa: BLE001
            q = None
        out.append(q["p1_prob"] if q else np.nan)
    return np.array(out, dtype=float)


a = price_all(SO)
b = price_all(SN)
both = ~np.isnan(a) & ~np.isnan(b)
diff = 100 * (b - a)[both]
print("   priced by both: %d of %d" % (int(both.sum()), len(today)))
if both.any():
    print("\nPROBABILITY CHANGE from a 4-day-fresher state, on today's board:")
    print("   median |change| %.2fpt   mean |change| %.2fpt   p90 %.2fpt   max %.2fpt"
          % (np.median(np.abs(diff)), np.abs(diff).mean(),
             np.percentile(np.abs(diff), 90), np.abs(diff).max()))
    for t in (1, 2, 3, 5):
        print("   cards moving more than %dpt: %d (%.0f%%)"
              % (t, int((np.abs(diff) > t).sum()), 100 * (np.abs(diff) > t).mean()))
    # does it change which side MC2 picks?
    flips = ((a[both] >= 0.5) != (b[both] >= 0.5)).sum()
    print("   cards where MC2's PICK flips side: %d" % int(flips))
print("\nalso: players present in the rebuilt state but MISSING from the frozen one")
print("   (these would return None on a card today): %d" % len(set(pn) - set(po)))
