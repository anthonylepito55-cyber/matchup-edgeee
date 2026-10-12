"""WHY DOES THE RECON LOOKUP MISS? (2026-10-12)

The coverage diagnostic says 508 of the 509 missing rows have BOTH players clearing G's
52-week-on-surface floor, so the window is NOT the blocker and my "structural floor" answer was
wrong. The recon reported 492 of them as "not in the as-of archive", which means the
(date, slug, slug) lookup into the archive's paired frame failed.

This finds out why, by taking the missing rows and checking, in order:
  * do both names resolve to slugs
  * does the archive hold a row for this player on this date at all (and on what date, in case
    the log and the archive disagree by a day -- there is precedent for a timezone rollover here)
  * does the PAIRED frame hold the match (it needs BOTH orientations present to survive the
    mirror join)
  * does it survive core's feature-completeness filter
"""
import numpy as np
import pandas as pd

import tennis_log
import tennis_model_a as T

ns = {}
src = open("_tennis_model_g_build.py", encoding="utf-8").read()
exec(compile(src.split("from sklearn.linear_model")[0], "_g_prep", "exec"), ns)
m, keep = ns["m"], ns["keep"]
m = m.copy()
m["d"] = m["date"].astype(str).str[:10]
paired = set(zip(m["d"], m["player_slug"].astype(str), m["rival_slugname"].astype(str)))
in_core = set(zip(m.loc[keep, "d"], m.loc[keep, "player_slug"].astype(str),
                  m.loc[keep, "rival_slugname"].astype(str)))
print("paired archive matches: %d | surviving core: %d" % (len(paired), len(in_core)), flush=True)

raw = T._parse(pd.read_parquet(T.LOGS_PARQUET))
raw["d"] = pd.to_datetime(raw["date"]).dt.strftime("%Y-%m-%d")
# every (player, date) the archive knows, and every (player, opponent) pair ignoring the date
pd_seen = set(zip(raw["player_slug"].astype(str), raw["d"]))
pair_anyday = {}
for a, b, d in zip(raw["player_slug"].astype(str), raw["rival_slugname"].astype(str), raw["d"]):
    pair_anyday.setdefault((a, b), set()).add(d)

log = pd.read_parquet(tennis_log.LOG_PATH)
log["d"] = log["date"].astype(str).str[:10]
miss = log[log["p1_won"].notna() & log["model_g_p1"].isna()].copy()
print("missing settled rows: %d" % len(miss), flush=True)

rc = {}


def slug(nm):
    if nm not in rc:
        try:
            rc[nm] = T.resolve(nm)
        except Exception:  # noqa: BLE001
            rc[nm] = None
    return rc[nm]


tally, offsets, examples = {}, {}, {}
for r in miss.itertuples():
    s1, s2 = slug(r.player_1), slug(r.player_2)
    if not s1 or not s2:
        k = "A name does not resolve"
    else:
        a, b = (s1, s2) if s1 < s2 else (s2, s1)
        if (r.d, a, b) in in_core:
            k = "E in core -- should have been filled (real bug)"
        elif (r.d, a, b) in paired:
            k = "D paired but dropped by the feature filter"
        else:
            days = pair_anyday.get((a, b), set()) | pair_anyday.get((b, a), set())
            if not days:
                if (s1, r.d) in pd_seen or (s2, r.d) in pd_seen:
                    k = "C both played that day, but not each other (pair absent)"
                else:
                    k = "B neither player has an archive row for that date"
            else:
                near = sorted(days)
                off = min((abs((pd.Timestamp(x) - pd.Timestamp(r.d)).days), x) for x in near)
                if off[0] <= 3:
                    k = "F archive has the pair on a DIFFERENT date (off by %d)" % off[0]
                    offsets[off[0]] = offsets.get(off[0], 0) + 1
                else:
                    k = "G pair exists but far from this date"
    tally[k] = tally.get(k, 0) + 1
    examples.setdefault(k, (r.d, r.player_1, r.player_2, s1, s2))

print("\nwhy each missing row misses:")
for k in sorted(tally):
    print("   %-52s %5d  (%4.1f%%)" % (k, tally[k], 100 * tally[k] / len(miss)))
    print("        e.g. %s" % (examples[k],))
if offsets:
    print("\ndate offsets seen:", dict(sorted(offsets.items())))
