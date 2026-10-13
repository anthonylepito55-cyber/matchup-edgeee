"""FIND AND INSPECT DUPLICATE LOG ROWS (2026-10-13). READ ONLY -- decides nothing.

Found while checking Diaz Acosta: the same Shanghai match was logged twice, on consecutive days,
under two name spellings ("Facundo Diaz Acosta" / "Facundo Acosta") and two tournament strings
("Shanghai, China" / "Shanghai Rolex Masters"), with different odds. Each duplicate
double-counts in every lane and in every ROI computed off the log.

Three detectors, widest first, because a single rule either misses cases or invents them:
  A  exact (date, player_1, player_2) repeats          -- unambiguous
  B  same fixture_id twice                             -- unambiguous
  C  same player surnames + same normalised score within a few days -- the one that caught
     Shanghai. Score is normalised by stripping tiebreak parentheses and all non-digit/dash
     characters. A genuine rematch inside 3 days with an IDENTICAL scoreline is possible but
     vanishingly rare, so C is reported with full detail for a human read rather than acted on
     blind, and the day-span is printed so a 0-day pair (same day, two spellings) can be told
     from a 2-3 day one.

For every candidate it prints what is needed to choose a survivor: both dates, tournaments,
odds, scores, settle state, logged_at, and how many model columns each row actually carries --
because the row with more model values is the one the board really priced.
"""
import re

import numpy as np
import pandas as pd

import tennis_log

L = pd.read_parquet(tennis_log.LOG_PATH)
L = L.reset_index(drop=True)
L["_d"] = L["date"].astype(str).str[:10]
print("log rows: %d  (%s .. %s)" % (len(L), L["_d"].min(), L["_d"].max()))

MODELCOLS = [c for c in L.columns
             if c.endswith("_p1") or c in ("mc_p1", "mc2_p1", "mc3_p1")]
L["_nmodels"] = L[MODELCOLS].notna().sum(axis=1)


def norm_score(s):
    if not isinstance(s, str):
        return ""
    s = re.sub(r"\([^)]*\)", "", s)
    return re.sub(r"[^0-9-]", "", s)


def surn(x):
    x = str(x).strip()
    return x.split()[-1].lower() if x else ""


L["_k"] = L["score"].map(norm_score)
L["_a"] = L["player_1"].map(surn)
L["_b"] = L["player_2"].map(surn)
L["_pair"] = [" | ".join(sorted([a, b])) for a, b in zip(L["_a"], L["_b"])]
L["_dt"] = pd.to_datetime(L["_d"], errors="coerce")

SHOW = ["_d", "tournament", "player_1", "player_2", "p1_odds", "p2_odds",
        "score", "settled", "p1_won", "logged_at", "_nmodels", "fixture_id"]


def dump(tag, groups):
    print("\n" + "=" * 100)
    print("%s -- %d candidate group(s)" % (tag, len(groups)))
    print("=" * 100)
    for g in groups:
        sub = L.loc[g].sort_values("_d")
        span = int((sub["_dt"].max() - sub["_dt"].min()).days)
        print("\n   pair %s | score %s | span %d day(s) | rows %d"
              % (sub.iloc[0]["_pair"], sub.iloc[0]["_k"] or "(none)", span, len(sub)))
        for i, r in sub.iterrows():
            print("      idx %-5d %s  %-26s %-22s v %-22s %7s/%-7s  %-14s settled=%-5s won=%-5s models=%-3d logged=%s"
                  % (i, r["_d"], str(r["tournament"])[:26], str(r["player_1"])[:22],
                     str(r["player_2"])[:22], r["p1_odds"], r["p2_odds"],
                     str(r["score"])[:14], r["settled"], r["p1_won"], r["_nmodels"],
                     str(r["logged_at"])[:19]))


# ---- A: exact (date, p1, p2) ----
ga = [list(v) for _, v in L.groupby(["_d", "player_1", "player_2"]).groups.items()
      if len(v) > 1]
dump("A: exact same date and both names", ga)

# ---- B: same fixture_id ----
gb = []
if "fixture_id" in L.columns:
    fid = L[L["fixture_id"].notna() & (L["fixture_id"].astype(str) != "")]
    gb = [list(v) for _, v in fid.groupby("fixture_id").groups.items() if len(v) > 1]
dump("B: same fixture_id", gb)

# ---- C: same surnames + same score, close in time ----
gc = []
for (pair, k), v in L[L["_k"] != ""].groupby(["_pair", "_k"]).groups.items():
    v = list(v)
    if len(v) < 2:
        continue
    sub = L.loc[v].sort_values("_dt")
    span = (sub["_dt"].max() - sub["_dt"].min()).days
    if span <= 3:
        gc.append(v)
dump("C: same surnames + same score within 3 days", gc)

# ---- C-wide: the same rule with no day limit, to see if any legitimate rematches exist ----
wide = []
for (pair, k), v in L[L["_k"] != ""].groupby(["_pair", "_k"]).groups.items():
    v = list(v)
    if len(v) < 2:
        continue
    sub = L.loc[v].sort_values("_dt")
    span = (sub["_dt"].max() - sub["_dt"].min()).days
    if span > 3:
        wide.append((pair, k, span, len(v)))
print("\n" + "=" * 100)
print("C-wide: same surnames + same score but MORE than 3 days apart -- %d group(s)" % len(wide))
print("   (these are most likely genuine rematches that happened to share a scoreline;")
print("    listed only so the 3-day cut can be sanity-checked, NOT candidates)")
print("=" * 100)
for pair, k, span, n in sorted(wide, key=lambda t: t[2])[:12]:
    print("   %-34s score %-10s %4d days apart, %d rows" % (pair, k, span, n))

allg = {tuple(sorted(g)) for g in (ga + gb + gc)}
print("\n" + "=" * 100)
print("TOTAL distinct duplicate groups across A/B/C: %d  (extra rows: %d)"
      % (len(allg), sum(len(g) - 1 for g in allg)))
print("=" * 100)
