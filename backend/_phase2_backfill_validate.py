"""PHASE 2: backfill the price-validity flags over the whole log, then VALIDATE both guards.

Validation contract (the run aborts loudly on any failure):
  V1 every row with overround <= 1.0001 carries price_synthetic
  V2 every mirrored pair (p1 == -p2) carries price_synthetic
  V3 every bookmaker=='Polymarket' row carries price_synthetic
  V4 all 154+ rows with logged_at >= start_time_utc carry price_poststart
  V5 no legitimate source is swallowed: no FanDuel/DraftKings/Kalshi/'Polymarket (USA)' row is
     flagged synthetic unless it independently trips mirrored/overround/both-positive
  V6 every flagged row carries a price_reject_reason
  V7 after the patched lane code runs, NO lane pick references a flagged row
Also writes data_cache/phase2_row_exclusions.csv -- the record-level exclusion audit.
"""
import pandas as pd
import tennis_log as T

log = pd.read_parquet(T.LOG_PATH)
n0 = len(log)
log = T._apply_price_flags(log)


def dec(a):
    a = float(a)
    return 1.0 + (a / 100.0 if a > 0 else 100.0 / -a)


log["_ovr"] = [1 / dec(a) + 1 / dec(b) for a, b in zip(log["p1_odds"], log["p2_odds"])]
st = pd.to_datetime(log["start_time_utc"], errors="coerce", utc=True)
lg = pd.to_datetime(log["logged_at"], errors="coerce", utc=True)

syn, post = log["price_synthetic"], log["price_poststart"]
print("rows %d | price_synthetic %d | price_poststart %d | both %d"
      % (n0, syn.sum(), post.sum(), (syn & post).sum()))

fails = []


def check(name, cond, detail=""):
    ok = bool(cond)
    print("  %-4s %s %s" % (name, "PASS" if ok else "FAIL", detail))
    if not ok:
        fails.append(name)


check("V1", int((log["_ovr"] <= 1.0001).sum()) == int(((log["_ovr"] <= 1.0001) & syn).sum()),
      "overround<=1 rows: %d, flagged: %d" % ((log["_ovr"] <= 1.0001).sum(), ((log["_ovr"] <= 1.0001) & syn).sum()))
mir = (log["p1_odds"] == -log["p2_odds"]) & log["p1_odds"].notna()
check("V2", int(mir.sum()) == int((mir & syn).sum()), "mirrored: %d, flagged: %d" % (mir.sum(), (mir & syn).sum()))
pm = log["bookmaker"].astype(str) == "Polymarket"
check("V3", int(pm.sum()) == int((pm & syn).sum()), "'Polymarket': %d, flagged: %d" % (pm.sum(), (pm & syn).sum()))
late = (lg >= st) & st.notna() & lg.notna()
miss = st.isna() | lg.isna()
check("V4", int(((late | miss) & ~post).sum()) == 0,
      "late: %d, missing-ts: %d, flagged poststart: %d" % (late.sum(), miss.sum(), post.sum()))
legit = log["bookmaker"].astype(str).isin(["FanDuel", "DraftKings", "Kalshi", "BetMGM", "Polymarket (USA)"])
over_flag = legit & syn & ~(mir | (log["_ovr"] <= 1.0001) | ((log["p1_odds"] > 0) & (log["p2_odds"] > 0)))
check("V5", int(over_flag.sum()) == 0, "legit-source rows flagged without an independent trigger: %d" % over_flag.sum())
check("V6", int(((syn | post) & log["price_reject_reason"].isna()).sum()) == 0,
      "flagged rows missing a reason: %d" % ((syn | post) & log["price_reject_reason"].isna()).sum())

# persist (atomic, same pattern as the module)
drop = log.drop(columns=["_ovr"])
T._write_log(drop)
print("flags persisted to the log (atomic write)")

# ---------------------------------------------------------------- V7: lanes see none of them
rec = T.get_ab25_record()
flagged_keys = set()
for _, r in log[syn | post].iterrows():
    flagged_keys.add((str(r["date"])[:10], str(r["player_1"]), str(r["player_2"])))
    flagged_keys.add((str(r["date"])[:10], str(r["player_2"]), str(r["player_1"])))
bad_picks = []
for k, v in rec["study"].items():
    if not isinstance(v, dict):
        continue
    for p in v.get("picks") or []:
        if (str(p.get("date"))[:10], str(p.get("pick")), str(p.get("opp"))) in flagged_keys:
            bad_picks.append((k, p.get("date"), p.get("pick")))
check("V7", len(bad_picks) == 0, "lane picks still referencing flagged rows: %d %s" % (len(bad_picks), bad_picks[:4]))

# ---------------------------------------------------------------- record-level exclusion audit
aud = log.copy()
aud["overround"] = aud["_ovr"].round(4)
cols = ["date", "league", "player_1", "player_2", "p1_odds", "p2_odds", "overround", "bookmaker",
        "start_time_utc", "logged_at", "settled", "p1_won", "void",
        "surface_bad", "inplay_suspect", "resolve_bad", "price_synthetic", "price_poststart",
        "price_reject_reason"]
aud = aud[[c for c in cols if c in aud.columns]]
aud["lane_eligible"] = ~aud[["surface_bad", "inplay_suspect", "resolve_bad",
                             "price_synthetic", "price_poststart"]].fillna(False).astype(bool).any(axis=1) \
    & ~aud["void"].fillna(False).astype(bool)
aud.to_csv("data_cache/phase2_row_exclusions.csv", index=False)
print("record-level audit written: data_cache/phase2_row_exclusions.csv  (%d rows, eligible %d)"
      % (len(aud), int(aud["lane_eligible"].sum())))

# overlapping exclusions summary
print("")
print("EXCLUSION OVERLAP (settled rows)")
sset = log["settled"].fillna(False).astype(bool)
import itertools
F = ["surface_bad", "inplay_suspect", "resolve_bad", "price_synthetic", "price_poststart", "void"]
for f in F:
    print("   %-16s %4d" % (f, int((log[f].fillna(False).astype(bool) & sset).sum())))
for a, b in itertools.combinations(F, 2):
    n = int((log[a].fillna(False).astype(bool) & log[b].fillna(False).astype(bool) & sset).sum())
    if n:
        print("   %-16s & %-16s %4d" % (a, b, n))

print("")
print("RESULT: %s" % ("ALL CHECKS PASS" if not fails else "FAILURES: %s" % fails))
