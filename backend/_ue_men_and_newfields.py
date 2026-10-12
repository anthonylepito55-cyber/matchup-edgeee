"""(1) WHAT DOES GOALSERVE ADD THAT WE DO NOT ALREADY HAVE, AND (2) HOW DOES UE DO FOR MEN?
(2026-10-12, user: "any new stats it adds? and how does unforced errors do for mens games")

Part 1 diffs Goalserve's stat list against the TennisRatio archive's columns, so "new" is
established rather than asserted.

Part 2 re-opens the men's UE question. The existing note says men showed no edge -- but the
WOMEN'S edge only appeared once it was gated to HARD COURT (+16.9% hard, +22.2% grass,
-16.6% clay; ungated it was +10.5%). If the men's conclusion was reached ungated, it was never
given the same chance. So this re-runs it with the full split: surface, price band, level and
year, on the MCP men's charting data.

UE is expressed per set, which is how the women's lane defines it, so a long match does not
look careless simply for lasting.
"""
import numpy as np
import pandas as pd

# ---------------------------------------------------------------- part 1
TR = pd.read_parquet("data_cache/tennisratio/all_match_logs.parquet", columns=None)
tr_cols = set(c.lower() for c in TR.columns)
GOALSERVE = ["Aces", "Double Faults", "1st serve percentage", "1st serve points won",
             "2nd serve points won", "Break Points Saved", "1st return points won",
             "2nd return points won", "Break Points Converted", "Service Points Won",
             "Return Points Won", "Total Points Won", "Match points saved",
             "Service games won", "Return games won", "Total games won",
             "Last 10 balls", "Winners", "Unforced errors", "Net points won"]
ALIAS = {
    "Aces": "aces", "Double Faults": "double_faults",
    "1st serve percentage": "first_serve_accuracy",
    "1st serve points won": "first_serve_points",
    "2nd serve points won": "second_serve_points",
    "Break Points Saved": "breakpoints_saved_count",
    "Break Points Converted": "breakpoints_converted_count",
    "1st return points won": "return_1st_serve_points",
    "2nd return points won": "return_2nd_serve_points",
    "Service games won": "service_games_won", "Return games won": "return_games_won",
}
print("=" * 100)
print("1. WHAT GOALSERVE ADDS vs THE TENNISRATIO ARCHIVE")
print("=" * 100)
new, have = [], []
for g in GOALSERVE:
    a = ALIAS.get(g)
    if a and a in tr_cols:
        have.append((g, a))
    elif g.lower().replace(" ", "_") in tr_cols:
        have.append((g, g.lower().replace(" ", "_")))
    else:
        new.append(g)
print("   ALREADY HAVE (%d):" % len(have))
for g, a in have:
    print("      %-26s = %s" % (g, a))
print("\n   NEW (%d):" % len(new))
for g in new:
    print("      %s" % g)
print("\n   note: TennisRatio also has pressure buckets (serve_0_30 ... serve_40_A and the")
print("   return equivalents) plus serve/return_pressure_all/won, which Goalserve does NOT")
print("   break out -- though its point-by-point feed would let them be rebuilt.")

# ---------------------------------------------------------------- part 2
print("\n" + "=" * 100)
print("2. UNFORCED ERRORS -- MEN, with the same surface gating that rescued the women")
print("=" * 100)
try:
    U = pd.read_parquet("data_cache/_mcp_ue_rows.parquet")
except Exception as e:
    raise SystemExit("   no UE rows: %s" % e)
print("   rows: %d | columns: %s" % (len(U), sorted(U.columns.tolist())[:18]))
low = {c.lower(): c for c in U.columns}


def pick(*names):
    for n in names:
        if n in low:
            return low[n]
    return None


cg = pick("gender", "g", "sex")
cs = pick("surface", "surf")
cd = pick("is_dog", "dog", "dog1")
cu = pick("ue_set_diff", "ue_set5_diff", "ue_diff", "d_ue", "ue_gap")
co = pick("odds", "player_odd", "dec_odds", "price")
cw = pick("won", "win", "result")
cl = pick("level", "tournament_level", "lvl")
cy = pick("year", "yr")
print("   mapped -> gender=%s surface=%s dog=%s ue=%s odds=%s won=%s level=%s"
      % (cg, cs, cd, cu, co, cw, cl))
if not all((cu, co, cw)):
    print("\n   the UE row store does not carry the fields this needs; printing a sample so the")
    print("   right columns can be identified:")
    print(U.head(3).to_string()[:1200])
    raise SystemExit

U = U.copy()
if cy is None:
    for c in U.columns:
        if "date" in c.lower():
            U["yr"] = pd.to_datetime(U[c], errors="coerce").dt.year
            cy = "yr"
            break
men = U[U[cg].astype(str).str.upper().str[0] == "M"] if cg else U
print("\n   men's rows with a UE diff: %d" % len(men))


def rep(s, lab, floor=25):
    n = len(s)
    if n < floor:
        print("   %-44s n=%d (thin)" % (lab, n))
        return
    w = s[cw].astype(bool)
    o = s[co].astype(float)
    pnl = np.where(w, o - 1, -1.0)
    se = 100 * pnl.std(ddof=1) / np.sqrt(n)
    print("   %-44s %d-%d  wins %4.1f%%  ROI %+6.1f%% ± %4.1f  (n=%d)"
          % (lab, int(w.sum()), n - int(w.sum()), 100 * w.mean(),
             100 * pnl.mean(), se, n))


# the women's lane definition: back the DOG that makes FEWER errors per set
sel = men[men[cu].astype(float) < 0] if cu else men
if cd is not None:
    sel = sel[sel[cd].astype(bool)]
print("   (cell = men's dogs whose UE/set is LOWER than the favourite's)")
rep(sel, "all men's low-UE dogs")
if cs is not None:
    print("   by surface:")
    for sf in ("Hard", "Clay", "Grass"):
        rep(sel[sel[cs].astype(str).str.title().str.startswith(sf[:4])], "      %s" % sf)
if co is not None:
    print("   by price:")
    for lo, hi, nm in ((2.0, 2.5, "+100..+150"), (2.0, 3.5, "+100..+250"),
                       (3.5, 99, "+250 and longer")):
        rep(sel[sel[co].astype(float).between(lo, hi)], "      %s" % nm)
if cl is not None:
    print("   by level:")
    lv = sel[cl].astype(str).str.lower()
    for nm, m in (("tour", ~lv.str.contains("chall|itf|future")),
                  ("challenger", lv.str.contains("chall")),
                  ("ITF", lv.str.contains("itf|future"))):
        rep(sel[m], "      %s" % nm)
if cy is not None:
    print("   by year:")
    for y in sorted(set(pd.to_numeric(sel[cy], errors="coerce").dropna().astype(int))):
        if y < 2023:
            continue
        rep(sel[pd.to_numeric(sel[cy], errors="coerce") == y], "      %d" % y)
print("   tightened (bigger UE advantage):")
for x in (0, 1, 2, 3):
    rep(sel[sel[cu].astype(float) <= -x], "      UE/set at least %dpt lower" % x)
