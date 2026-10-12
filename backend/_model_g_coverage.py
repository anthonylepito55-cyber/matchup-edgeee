"""WHY IS MODEL G MISSING SO OFTEN? (2026-10-12, user "model g is missing for so many")

G needs a prior-365-day window ON THIS SURFACE, with at least 5 matches, for BOTH players. This
counts how many settled log rows fail, and at which step, so the fix targets the biggest bucket
instead of the first one I think of:

  1 name does not resolve to a slug at all
  2 slug resolves but the player has NO archive history whatsoever
  3 has history, but none on this surface inside 365 days
  4 has some on this surface but under the 5-match floor
  5 both players clear the floor (so G should have priced it)

Run against the authoritative EC2 log. Prints the per-surface and per-level breakdown too,
because the ITF stats audit says 91% of ITF players have no context at all -- if that is where
the misses live, no amount of window-widening recovers them and the honest answer is a floor.
"""
import numpy as np
import pandas as pd

import tennis_log
import tennis_model_a as T

log = pd.read_parquet(tennis_log.LOG_PATH)
log["d"] = log["date"].astype(str).str[:10]
s = log[log["p1_won"].notna()].copy()
print("settled log rows: %d   with G: %d   missing: %d"
      % (len(s), int(s["model_g_p1"].notna().sum()), int(s["model_g_p1"].isna().sum())), flush=True)

raw = T._parse(pd.read_parquet(T.LOGS_PARQUET))
raw["date"] = pd.to_datetime(raw["date"]).dt.normalize()
raw["surf"] = raw["surface"].astype(str).str.title()
by_slug = {k: v for k, v in raw.groupby("player_slug")}
print("archive players: %d" % len(by_slug), flush=True)

rcache = {}


def slug(nm):
    if nm not in rcache:
        try:
            rcache[nm] = T.resolve(nm)
        except Exception:  # noqa: BLE001
            rcache[nm] = None
    return rcache[nm]


def step(nm, surf, day):
    """Which step this player fails at, plus the window sizes that matter."""
    sl = slug(nm)
    if not sl:
        return 1, 0, 0
    g = by_slug.get(sl)
    if g is None or not len(g):
        return 2, 0, 0
    d0 = pd.Timestamp(day)
    w = g[(g["date"] < d0) & (g["date"] >= d0 - pd.Timedelta(days=365))]
    on = w[w["surf"] == str(surf or "").title()]
    if not len(on):
        return 3, 0, len(w)
    if len(on) < 5:
        return 4, len(on), len(w)
    return 5, len(on), len(w)


rows = []
for r in s.itertuples():
    a, na, wa = step(r.player_1, getattr(r, "surface", None), r.d)
    b, nb, wb = step(r.player_2, getattr(r, "surface", None), r.d)
    rows.append({"d": r.d, "league": str(getattr(r, "league", "") or ""),
                 "surface": str(getattr(r, "surface", "") or ""),
                 "has_g": bool(pd.notna(r.model_g_p1)),
                 "worst": max(a, b), "s1": a, "s2": b,
                 "on1": na, "on2": nb, "any1": wa, "any2": wb})
c = pd.DataFrame(rows)

NAMES = {1: "1 name unresolved", 2: "2 no archive history", 3: "3 none on this surface",
         4: "4 under the 5-match floor", 5: "5 both clear -> G should price it"}
print("\nWORST-OF-THE-TWO-PLAYERS step (a match needs BOTH sides):")
t = c.groupby("worst").agg(rows=("has_g", "size"), with_g=("has_g", "sum"))
t["pct_of_all"] = (100 * t["rows"] / len(c)).round(1)
t.index = [NAMES[i] for i in t.index]
print(t.to_string())

print("\nthe MISSING rows only, by step:")
miss = c[~c.has_g]
t2 = miss.groupby("worst").size().rename("rows").to_frame()
t2["pct_of_missing"] = (100 * t2["rows"] / len(miss)).round(1)
t2.index = [NAMES[i] for i in t2.index]
print(t2.to_string())

print("\nmissing rows by level:")
miss = miss.copy()
miss["lvl"] = np.where(miss.league.str.startswith("itf"), "itf",
                       np.where(miss.league.str.contains("challenger"), "challenger", "tour"))
print(miss.groupby(["lvl", "worst"]).size().unstack(fill_value=0).to_string())

print("\nHOW MUCH WOULD A WIDER WINDOW RECOVER?")
print("Rows failing only at step 3/4 (thin or empty ON SURFACE) but with real recent history:")
thin = c[(~c.has_g) & (c.worst.isin([3, 4]))]
for lab, q in (("both sides have 5+ matches in 365d on ANY surface", (thin.any1 >= 5) & (thin.any2 >= 5)),
               ("both sides have 10+ on any surface", (thin.any1 >= 10) & (thin.any2 >= 10)),
               ("both sides have 3+ on this surface", (thin.on1 >= 3) & (thin.on2 >= 3))):
    print("   %-52s %5d of %d thin rows" % (lab, int(q.sum()), len(thin)))
print("\nso a surface-agnostic fallback could lift coverage from %.1f%% to about %.1f%%"
      % (100 * c.has_g.mean(),
         100 * (c.has_g.sum() + int(((thin.any1 >= 5) & (thin.any2 >= 5)).sum())) / len(c)))
c.to_parquet("data_cache/_model_g_coverage.parquet")
