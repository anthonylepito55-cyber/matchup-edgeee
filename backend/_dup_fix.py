"""REMOVE THE 6 DUPLICATE LOG ROWS (2026-10-13). Run with --apply to write.

Six matches were each logged twice, under two name spellings, by two price paths. Each one
double-counts in every lane and in every ROI computed off the log.

WHICH ROW SURVIVES, and why it is not arbitrary. Inspection showed one row of each pair carries
raw book odds (implied probabilities summing to more than 100%, i.e. with vig) and the other
carries prices that de-vig to exactly 100.0%:

    -360 / +280  ->  78.3% + 26.3% = 104.6%   raw book line
    -277 / +277  ->  64.2% + 35.8% = 100.0%   de-vigged fair price

The lanes compute ROI at the frozen price, and a de-vigged fair price is not a price anyone can
be filled at -- backing it would quietly credit every lane with the bookmaker's margin. So the
VIGGED row survives in every pair, even where that costs a tournament label or a few model
columns, because price integrity outranks metadata completeness in a betting log.

The script re-derives the pairs and the vig itself rather than trusting hardcoded indices, so it
cannot delete the wrong row if the log has shifted since inspection, and it refuses to act on any
group it cannot resolve by that rule.
"""
import re
import shutil
import sys

import numpy as np
import pandas as pd

import tennis_log

APPLY = "--apply" in sys.argv
LOG = tennis_log.LOG_PATH
L = pd.read_parquet(LOG).reset_index(drop=True)
L["_d"] = L["date"].astype(str).str[:10]
L["_dt"] = pd.to_datetime(L["_d"], errors="coerce")
print("log rows: %d" % len(L))


def norm_score(s):
    if not isinstance(s, str):
        return ""
    return re.sub(r"[^0-9-]", "", re.sub(r"\([^)]*\)", "", s))


def surn(x):
    x = str(x).strip()
    return x.split()[-1].lower() if x else ""


def implied_sum(o1, o2):
    """Total implied probability. >100% means the row carries the book's vig."""
    def dec(a):
        a = float(a)
        return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)
    try:
        return 1 / dec(o1) + 1 / dec(o2)
    except Exception:                                              # noqa: BLE001
        return np.nan


L["_k"] = L["score"].map(norm_score)
L["_pair"] = [" | ".join(sorted([surn(a), surn(b)]))
              for a, b in zip(L["player_1"], L["player_2"])]

groups = []
for (_p, _k), v in L[L["_k"] != ""].groupby(["_pair", "_k"]).groups.items():
    v = list(v)
    if len(v) < 2:
        continue
    sub = L.loc[v]
    if (sub["_dt"].max() - sub["_dt"].min()).days <= 3:
        groups.append(v)
print("duplicate groups found: %d" % len(groups))

drop, unresolved = [], []
print("\n%-34s %-7s %-9s %-9s %s" % ("pair", "keep", "vig-sum", "drop", "reason"))
print("-" * 96)
for g in groups:
    sub = L.loc[g].copy()
    sub["_vig"] = [implied_sum(a, b) for a, b in zip(sub["p1_odds"], sub["p2_odds"])]
    vigged = sub[sub["_vig"] > 1.005]
    fair = sub[sub["_vig"] <= 1.005]
    if len(vigged) == 1 and len(fair) == len(sub) - 1:
        keep = vigged.index[0]
        gone = [i for i in g if i != keep]
        drop.extend(gone)
        print("%-34s %-7d %-9.4f %-9s %s"
              % (sub.iloc[0]["_pair"], keep, float(vigged.iloc[0]["_vig"]),
                 ",".join(map(str, gone)),
                 "kept the vigged book line (dropped %s)"
                 % ", ".join("%.4f" % v for v in fair["_vig"])))
    else:
        unresolved.append(g)
        print("%-34s %-7s %-9s %-9s %s"
              % (sub.iloc[0]["_pair"], "-", "-", ",".join(map(str, g)),
                 "UNRESOLVED: %d vigged / %d fair -- left alone" % (len(vigged), len(fair))))

print("\nrows to drop: %d | unresolved groups left alone: %d" % (len(drop), len(unresolved)))
if not drop:
    raise SystemExit(0)

# what the removal does to the lanes, before and after
print("\nlane records BEFORE (the numbers these duplicates were inflating):")
try:
    before = tennis_log.get_ab25_record()["study"]
except Exception as e:                                             # noqa: BLE001
    before = {}
    print("   (could not read: %s)" % e)

if not APPLY:
    print("\nDRY RUN -- nothing written. Re-run with --apply.")
    raise SystemExit(0)

bak = LOG + ".bak_dupfix"
shutil.copy2(LOG, bak)
out = L.drop(index=drop).drop(columns=[c for c in ("_d", "_dt", "_k", "_pair")
                                       if c in L.columns])
out.to_parquet(LOG, index=False)
print("\nwrote %d rows (was %d), backup at %s" % (len(out), len(L), bak.split("/")[-1]))

chk = pd.read_parquet(LOG)
assert len(chk) == len(L) - len(drop), "row count after write is wrong"
print("verified: %d rows on disk" % len(chk))

# re-read the lanes through a fresh module state
import importlib                                                   # noqa: E402

importlib.reload(tennis_log)
after = tennis_log.get_ab25_record()["study"]
print("\nlanes whose record CHANGED:")
moved = 0
for k in sorted(set(before) | set(after)):
    b = (before.get(k) or {})
    a = (after.get(k) or {})
    if b.get("n") != a.get("n") or b.get("roi_pct") != a.get("roi_pct"):
        moved += 1
        print("   %-22s n %s -> %s   roi %s -> %s"
              % (k, b.get("n"), a.get("n"), b.get("roi_pct"), a.get("roi_pct")))
if not moved:
    print("   (none -- the duplicates were not inside any registered lane)")
print("\nRESULT: OK")
