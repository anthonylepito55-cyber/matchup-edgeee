"""PHASE 1 AUDIT, part 2: are the logged PRICES real, offered, pre-match prices?

Every ROI on the board is computed at the logged price, so a price that was never on offer
inflates or deflates everything downstream. Three suspects from part 1:
  (a) 156 rows whose two prices imply an overround <= 1.00 -- a real book never offers that
  (b) 154 rows whose price was logged AFTER the start, only 34 of which carry inplay_suspect
  (c) 65 rows where both prices share a sign (both negative is a NORMAL pick'em quote, both
      positive is not -- part 1 lumped them together, which was my error; split here)
Then: what those rows do to measured ROI, and whether our prices are biased against the close.
"""
import pandas as pd
import tennis_log as T

log = pd.read_parquet(T.LOG_PATH)


def dec(a):
    a = float(a)
    return 1.0 + (a / 100.0 if a > 0 else 100.0 / -a)


log["ovr"] = [1 / dec(a) + 1 / dec(b) for a, b in zip(log["p1_odds"], log["p2_odds"])]
log["both_neg"] = (log["p1_odds"] < 0) & (log["p2_odds"] < 0)
log["both_pos"] = (log["p1_odds"] > 0) & (log["p2_odds"] > 0)
st = pd.to_datetime(log["start_time_utc"], errors="coerce", utc=True)
lg = pd.to_datetime(log["logged_at"], errors="coerce", utc=True)
log["late_min"] = (lg - st).dt.total_seconds() / 60.0
flagged = log["inplay_suspect"].fillna(False).astype(bool)
settled = log["settled"].fillna(False).astype(bool) & log["p1_won"].notna()

print("=" * 100)
print("(c) SAME-SIGN PRICES -- correcting part 1")
print("=" * 100)
print("   both NEGATIVE (normal near-pick'em, e.g. -110/-110): %d   median overround %.4f"
      % (log["both_neg"].sum(), log.loc[log["both_neg"], "ovr"].median()))
print("   both POSITIVE (not a real two-way book quote):       %d   median overround %.4f"
      % (log["both_pos"].sum(), log.loc[log["both_pos"], "ovr"].median() if log["both_pos"].any() else float("nan")))
if log["both_pos"].any():
    print(log.loc[log["both_pos"], ["date", "league", "player_1", "player_2", "p1_odds", "p2_odds", "ovr", "source"]]
          .head(8).to_string(index=False))

print("")
print("=" * 100)
print("(a) OVERROUND <= 1.00 -- prices that imply a free arb, i.e. not a real offered pair")
print("=" * 100)
sus = log[log["ovr"] <= 1.0001]
print("   rows %d of %d (%.1f%%)   settled %d" % (len(sus), len(log), 100 * len(sus) / len(log), (settled & (log["ovr"] <= 1.0001)).sum()))
print("   by league : %s" % dict(sus["league"].astype(str).value_counts()))
print("   by date   : %s" % dict(sus["date"].astype(str).str[:10].value_counts().head(10)))
if "source" in log.columns:
    print("   by source : %s" % dict(sus["source"].astype(str).value_counts()))
print("   exact overround distribution: ==1.0000 %d   <1.0000 %d   min %.4f"
      % ((sus["ovr"].round(4) == 1.0).sum(), (sus["ovr"] < 0.9999).sum(), sus["ovr"].min()))
print("   how many are already flagged by some other quality flag:")
for c in ("surface_bad", "inplay_suspect", "resolve_bad", "void"):
    print("      %-16s %d" % (c, sus[c].fillna(False).astype(bool).sum()))
print(sus[["date", "league", "player_1", "player_2", "p1_odds", "p2_odds", "ovr"]].head(6).to_string(index=False))

print("")
print("=" * 100)
print("(b) PRICE LOGGED AFTER THE START")
print("=" * 100)
late = log["late_min"] > 0
print("   logged after start: %d   of which flagged inplay_suspect: %d   UNFLAGGED: %d"
      % (late.sum(), (late & flagged).sum(), (late & ~flagged).sum()))
print("   minutes late, unflagged rows: median %.1f  p90 %.1f  max %.1f"
      % (log.loc[late & ~flagged, "late_min"].median(), log.loc[late & ~flagged, "late_min"].quantile(.9),
         log.loc[late & ~flagged, "late_min"].max()))
print("   by league (unflagged): %s" % dict(log.loc[late & ~flagged, "league"].astype(str).value_counts()))
print("   NOTE: a late log timestamp is not proof of a stale price -- the row may be re-written")
print("   on settlement. The question is whether the PRICE moved, which overround + drift show.")

print("")
print("=" * 100)
print("IMPACT: what these rows do to measured ROI")
print("=" * 100)


def roi(mask, side="dog"):
    g = log[mask & settled]
    pn = []
    for _, r in g.iterrows():
        d1, d2 = dec(r["p1_odds"]), dec(r["p2_odds"])
        mk1 = (1 / d1) / ((1 / d1) + (1 / d2))
        dog1 = mk1 < 0.5
        take1 = dog1 if side == "dog" else (not dog1)
        won = bool(r["p1_won"]) if take1 else not bool(r["p1_won"])
        pn.append(((d1 if take1 else d2) - 1.0) if won else -1.0)
    n = len(pn)
    return "n=%-5d %s %+7.2f%%" % (n, side, 100 * sum(pn) / n) if n else "n=0"


clean = (log["ovr"] > 1.0001) & ~flagged & ~log["surface_bad"].fillna(False).astype(bool) \
    & ~log["resolve_bad"].fillna(False).astype(bool) & ~log["void"].fillna(False).astype(bool)
print("   every match, CLEAN rows only        : %s | %s" % (roi(clean, "dog"), roi(clean, "fav")))
print("   every match, overround<=1 rows only : %s | %s" % (roi(log["ovr"] <= 1.0001, "dog"), roi(log["ovr"] <= 1.0001, "fav")))
print("   every match, late+unflagged only    : %s | %s" % (roi(late & ~flagged, "dog"), roi(late & ~flagged, "fav")))
print("   every match, ALL rows (what lanes would see without flags): %s | %s"
      % (roi(pd.Series(True, index=log.index), "dog"), roi(pd.Series(True, index=log.index), "fav")))
print("")
print("   overround band vs blind dog ROI (a de-vigged price pays the dog the vig):")
for lo, hi, lab in ((0, 1.0001, "<=1.000"), (1.0001, 1.04, "1.00-1.04"), (1.04, 1.06, "1.04-1.06"),
                    (1.06, 1.08, "1.06-1.08"), (1.08, 99, ">1.08")):
    m = (log["ovr"] > lo) & (log["ovr"] <= hi)
    print("      %-10s %s | %s" % (lab, roi(m, "dog"), roi(m, "fav")))
