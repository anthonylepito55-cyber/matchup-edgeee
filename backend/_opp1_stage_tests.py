"""OPP1 v3.5 stage-management synthetic suite — constructed frames and temp ledgers only.
Large-population stages are driven through the REAL stage code by stubbing only the runner's
finalized_frame data source; every registered rule (thinning, counts, DE, blinding) runs real.
"""
import os
import shutil
import subprocess
import sys
import tempfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import opp1_eval as EV                # noqa: E402
import opp1_runner as RN              # noqa: E402
import opp1_sample as SA              # noqa: E402
import opp1_stage as SG               # noqa: E402

PASS, FAIL = [], []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name)


TMP = tempfile.mkdtemp(prefix="opp1_stage_test_")
ART = os.path.join(TMP, "registered_spec.blob")
open(ART, "wb").write(subprocess.run(
    ["git", "show", "%s:%s" % (SA.REG_COMMIT, SA.REG_BLOB_PATH)],
    cwd=ROOT, capture_output=True, check=True).stdout)

BASE = pd.Timestamp("2027-01-04T00:00:00Z")      # a Monday


def frame(n, week_lo, week_span, months_mod=None, leagues=3, keys=300, prefix="S"):
    rows = []
    lg = ["atp", "atp_challenger", "itf_men"][:leagues]
    for i in range(n):
        wk = week_lo + (i % week_span)
        start = BASE + pd.Timedelta(weeks=wk, hours=12)
        rows.append({"fixture_id": "%s%05d" % (prefix, i), "league": lg[i % len(lg)],
                     "start": start, "K": ("t%d" % (i % keys), SA.iso_week(start)),
                     "evaluated": True, "y": i % 2})
    return pd.DataFrame(rows)


# ================================================================ pure registered thresholds
ample = frame(12000, 0, 40)                       # 40 weeks ~ 10 months, 3 tiers
check("dev raw: exactly 12,000 meets, 11,999 does not",
      SG.counts_ok(ample, "DEV")["ok"] and not SG.counts_ok(ample.head(11999), "DEV")["ok"])
m8 = frame(12000, 0, 32)                          # 32 weeks -> ~8 distinct months
c8 = SG.counts_ok(m8, "DEV")
check("dev months: below 9 ISO-months fails even at 12k raw",
      (not c8["ok"]) if c8["counts"]["iso_months"] < 9 else SG.counts_ok(
          frame(12000, 0, 30), "DEV")["counts"]["iso_months"] < 9)
two_tier = frame(12000, 0, 40, leagues=2)
check("dev tiers: 2 of 3 competition tiers fails", not SG.counts_ok(two_tier, "DEV")["ok"])
t_ok = frame(2250, 0, 12, prefix="T")
check("tier raw/weeks: exactly 2,250/12wk meets; 2,249 or 11wk fails",
      SG.counts_ok(t_ok, "TIER1")["ok"]
      and not SG.counts_ok(t_ok.head(2249), "TIER1")["ok"]
      and not SG.counts_ok(frame(2250, 0, 11, prefix="T"), "TIER1")["ok"])

# ================================================================ full lifecycle (stubbed data)
DEV_F = frame(12100, 0, 40)                               # dev window: weeks 0-39
T1_F = frame(2300, 41, 13, prefix="A")                    # tier-1 window: weeks 41-53
T2_F = frame(2300, 57, 14, prefix="B")                    # tier-2 window: weeks 57-70
ALL = pd.concat([DEV_F, T1_F, T2_F], ignore_index=True)
_orig_ff = RN.finalized_frame


def _stub_ff(ledger, as_of_ts):
    wk_end = ALL["start"].apply(SG._week_end_ts)
    return ALL[wk_end <= as_of_ts].reset_index(drop=True)


RN.finalized_frame = _stub_ff
L = RN.Ledger(os.path.join(TMP, "led"))
RN.activate(L, "2026-10-20T00:00:00Z", ART, 1.0)
AS1 = (BASE + pd.Timedelta(weeks=41)).timestamp()          # dev weeks complete
AS_MID = (BASE + pd.Timedelta(weeks=20)).timestamp()       # mid-accrual

st0 = SG.stage_state(L)
check("state: starts DEV/COLLECTING", st0 == {"stage": "DEV", "phase": "COLLECTING",
                                              "closed": {}, "verdict": None, "final": None})
try:
    SG.record_stage_decision(L, "DEV", ART, AS1, {"V_clust_H1": 1, "V_iid_H1": 1,
                                                  "V_clust_H2": 1, "V_iid_H2": 1}, "auth", 2.0)
    check("premature: decision before any eligible review refused", False)
except SG.StageError:
    check("premature: decision before any eligible review refused", True)
r_mid = SG.review_boundary(L, "DEV", ART, AS_MID, 2.0)
check("review: mid-accrual boundary ineligible, stage stays collecting",
      not r_mid["eligible"] and SG.stage_state(L)["phase"] == "COLLECTING")
try:
    SG.review_boundary(L, "TIER1", ART, AS1, 2.0)
    check("overlap: TIER1 review refused while DEV is current", False)
except SG.StageError:
    check("overlap: TIER1 review refused while DEV is current", True)
r1 = SG.review_boundary(L, "DEV", ART, AS1, 3.0)
check("review: dev boundary eligible at first qualifying as_of (thinned, counted)",
      r1["eligible"] and r1["n_pre"] == 12100 and SG.stage_state(L)["phase"] == "REVIEW")
r1b = SG.review_boundary(L, "DEV", ART, AS1, 4.0)
check("review: duplicate boundary review deduped and identical",
      r1b == r1 and len([e for e in L.events("stage_review")
                         if e["payload"]["as_of_ts"] == AS1]) == 1)
check("review eligibility is NOT success: no closure event exists",
      not L.events("stage_closed"))
for bad, name in ((None, "missing blinded inputs"),
                  ({"V_clust_H1": 1}, "incomplete blinded inputs")):
    try:
        SG.record_stage_decision(L, "DEV", ART, AS1, bad, "auth", 5.0)
        check("pending: %s refused" % name, False)
    except SG.StageError:
        check("pending: %s refused" % name, True)
try:
    SG.record_stage_decision(L, "DEV", ART, AS1, {"V_clust_H1": 1, "V_iid_H1": 1,
                                                  "V_clust_H2": 1, "V_iid_H2": 1}, "", 5.0)
    check("pending: missing owner authorization refused", False)
except SG.StageError:
    check("pending: missing owner authorization refused", True)
try:
    SG.record_stage_decision(L, "DEV", ART, AS1, {"V_clust_H1": 1, "V_iid_H1": 0,
                                                  "V_clust_H2": 1, "V_iid_H2": 1}, "auth", 5.0)
    check("degenerate: zero variance -> registered DataIntegrityAbort, no fallback", False)
except EV.DataIntegrityAbort:
    check("degenerate: zero variance -> registered DataIntegrityAbort, no fallback", True)
ext = SG.record_stage_decision(L, "DEV", ART, AS1,
                               {"V_clust_H1": 2.0, "V_iid_H1": 1.0,
                                "V_clust_H2": 1.0, "V_iid_H2": 1.0}, "auth-ext", 6.0)
check("extension: effective shortfall (DE=2 -> eff 6,050 < 8,000) extends, does NOT close",
      not ext["closed"] and SG.stage_state(L)["phase"] == "EXTENDING"
      and ext["extension"]["governing_DE"] == 2.0)
check("extension: blinded payload only (no mean/t/ci/roi keys)",
      not any(k in ext["extension"] for k in ("mean", "t", "ci95", "roi", "p_value")))
dec = SG.record_stage_decision(L, "DEV", ART, AS1,
                               {"V_clust_H1": 1.0, "V_iid_H1": 1.0,
                                "V_clust_H2": 1.0, "V_iid_H2": 1.0}, "auth-close", 7.0)
check("closure: dev closes at eff >= 8,000 with frozen membership + authorization + note",
      dec["closed"] and dec["record"]["effective_n"] == 12100
      and len(dec["record"]["membership"]) == 12100
      and "NOT a statistical verdict" in dec["record"]["note"])
check("state: TIER1 collecting after dev close",
      SG.stage_state(L) ["stage"] == "TIER1")
try:
    SG.record_stage_decision(L, "DEV", ART, AS1, {"V_clust_H1": 1, "V_iid_H1": 1,
                                                  "V_clust_H2": 1, "V_iid_H2": 1}, "x", 8.0)
    check("immutable: re-closing DEV refused", False)
except SG.StageError:
    check("immutable: re-closing DEV refused", True)

# chronology + no overlap: a late-settling row inside the dev window joins NO stage
late_row = frame(1, 10, 1, prefix="LATE")
ALL = pd.concat([ALL, late_row], ignore_index=True)
AS2 = (BASE + pd.Timedelta(weeks=55)).timestamp()
t1f = SG.stage_frame(L, "TIER1", AS2)
check("chronology: tier-1 frame excludes the dev window entirely (incl. late arrivals)",
      len(t1f) == 2300 and not set(t1f["fixture_id"]) & set(dec["record"]["membership"])
      and "LATE00000" not in set(t1f["fixture_id"]))
try:
    SG.stage_frame(L, "TIER2", AS2)
    check("chronology: TIER2 frame refused before TIER1 closes", False)
except SG.StageError:
    check("chronology: TIER2 frame refused before TIER1 closes", True)
rt1 = SG.review_boundary(L, "TIER1", ART, AS2, 9.0)
check("tier1: boundary eligible at first qualifying date (2,300 raw / 13 wks)",
      rt1["eligible"] and rt1["n_pre"] == 2300)
dt1 = SG.record_stage_decision(L, "TIER1", ART, AS2,
                               {"V_clust_H1": 1.0, "V_iid_H1": 1.0,
                                "V_clust_H2": 1.0, "V_iid_H2": 1.0}, "auth-t1", 10.0)
check("tier1: closes (eff 2,300 >= 1,500); state awaits verdict",
      dt1["closed"] and SG.stage_state(L)["stage"] == "TIER1_CLOSED_AWAITING_VERDICT")
try:
    SG.review_boundary(L, "TIER2", ART, AS2, 10.5)
    check("verdict gate: TIER2 cannot collect before the verdict document", False)
except SG.StageError:
    check("verdict gate: TIER2 cannot collect before the verdict document", True)
try:
    SG.record_verdict(L, {"h1_dev_pass": True}, "auth", 1.0, 11.0)
    check("verdict: incomplete authorized inputs refused (pending)", False)
except SG.StageError:
    check("verdict: incomplete authorized inputs refused (pending)", True)
VTS = (BASE + pd.Timedelta(weeks=56)).timestamp()
SG.record_verdict(L, {"h1_dev_pass": True, "h2_dev_pass": False,
                      "h1_tier1_pass": True, "h2_tier1_pass": False}, "auth-verdict",
                  VTS, 12.0)
check("verdict: recorded from authorized inputs, never computed; TIER2 opens",
      SG.stage_state(L)["stage"] == "TIER2"
      and SG.stage_state(L)["verdict"]["inputs"]["h2_dev_pass"] is False)
AS3 = (BASE + pd.Timedelta(weeks=72)).timestamp()
t2f = SG.stage_frame(L, "TIER2", AS3)
check("tier2: frame = starts strictly after verdict_ts, outside earlier windows",
      len(t2f) == 2300 and t2f["start"].min().timestamp() > VTS)
rt2 = SG.review_boundary(L, "TIER2", ART, AS3, 13.0)
dt2 = SG.record_stage_decision(L, "TIER2", ART, AS3,
                               {"V_clust_H1": 1.0, "V_iid_H1": 1.0,
                                "V_clust_H2": 1.0, "V_iid_H2": 1.0}, "auth-t2", 14.0)
check("tier2: closes under the registered rules", rt2["eligible"] and dt2["closed"])
VREF = SG.verdict_ref(L)
try:
    SG.record_final(L, "COMPLETE", "", 15.0, VREF)
    check("final: missing authorization refused", False)
except SG.StageError:
    check("final: missing authorization refused", True)
# ---- FINAL-VERDICT PROVENANCE (2026-10-19 hardening) ----
for bad, label in ((None, "missing"), ("", "empty"), (12345, "non-string"),
                   ("deadbeef" * 8, "non-matching")):
    try:
        SG.record_final(L, "COMPLETE", "auth-final", 15.0, bad)
        check("final provenance: %s verdict reference refused" % label, False)
    except SG.StageError:
        check("final provenance: %s verdict reference refused" % label, True)
check("final provenance: the reference IS the verdict event's content hash",
      VREF == [e for e in L.events("verdict_recorded")][-1]["hash"] and len(VREF) == 64)
fin_p = SG.record_final(L, "COMPLETE", "auth-final", 15.0, VREF)
check("final: authorized COMPLETE recorded with provenance, and COMPLETE never implies the "
      "gates passed",
      SG.stage_state(L)["stage"] == "COMPLETE" and fin_p["verdict_ref"] == VREF
      and fin_p["means_gates_passed"] is False
      and "h1_dev_pass" not in str(fin_p))
check("final provenance: gate booleans stay ONLY in the referenced verdict event",
      [e for e in L.events("verdict_recorded")][-1]["payload"]["inputs"]["h1_dev_pass"] is True)

# ---- FROZEN MEMBERSHIP REGRESSION: the 12,100 vs 12,105 case (2026-10-19) ----
# Before the fix, stage_frame('DEV') re-derived from the live finalized frame after closure, so
# five late-settling dev-window rows turned 12,100 into 12,105. It must now return exactly the
# ids frozen in the stage_closed event, however many times it is called.
DEV_CLOSED = SG.stage_state(L)["closed"]["DEV"]
frozen_ids = list(DEV_CLOSED["membership"])
ALL = pd.concat([ALL, frame(5, 10, 1, prefix="LATE2")], ignore_index=True)   # late dev-window
ALL = pd.concat([ALL, frame(400, 44, 8, prefix="FUT2")], ignore_index=True)  # new later rows
f1 = SG.stage_frame(L, "DEV", AS1)
f2 = SG.stage_frame(L, "DEV", (BASE + pd.Timedelta(weeks=80)).timestamp())
check("frozen membership: closed DEV returns exactly the 12,100 frozen ids, not 12,105",
      len(f1) == 12100 == len(frozen_ids) and sorted(f1["fixture_id"].astype(str)) == sorted(frozen_ids))
check("frozen membership: repeated calls at ANY later as_of return the identical population",
      len(f2) == 12100 and sorted(f2["fixture_id"].astype(str)) == sorted(f1["fixture_id"].astype(str)))
check("frozen membership: no LATE/FUT row can enter a closed stage",
      not any(str(f).startswith(("LATE", "FUT")) for f in f1["fixture_id"])
      and not any(str(f).startswith(("LATE", "FUT")) for f in f2["fixture_id"]))
check("frozen membership: the closure event itself was not rewritten",
      SG.stage_state(L)["closed"]["DEV"]["membership"] == frozen_ids)
_t1f = SG.stage_frame(L, "TIER1", (BASE + pd.Timedelta(weeks=80)).timestamp())
check("frozen membership: DEV / TIER1 / TIER2 stay chronologically disjoint after the fix",
      not (set(_t1f["fixture_id"].astype(str)) & set(frozen_ids))
      and not any(str(f).startswith("LATE") for f in _t1f["fixture_id"]))

# restart determinism
snap = SG.stage_state(L)
L.close()
L2 = RN.Ledger(os.path.join(TMP, "led"))
check("restart: refolded stage state identical", SG.stage_state(L2) == snap)
L2.close()
RN.finalized_frame = _orig_ff

# ================================================================ real-runner integration
L3 = RN.Ledger(os.path.join(TMP, "led3"))
RN.activate(L3, "2026-10-20T00:00:00Z", ART, 1.0)


def srow(book, sel, price, poll, qts, fid, start):
    return {"fixture_id": fid, "league": "atp", "start_date": start,
            "home": "Novak Djokovic", "away": "Carlos Alcaraz", "sportsbook": book,
            "selection": sel, "norm_selection": sel.lower(), "market": "moneyline",
            "price": price, "limit_max": None, "top_size": 100.0, "order_book": None,
            "quote_ts": qts, "deep_link": None, "poll_ts": poll}


S = pd.Timestamp("2026-10-15T12:00:00Z").timestamp()
expo = pd.DataFrame([srow("Pinnacle", "Novak Djokovic", -150, S - 3600, S - 3605, "FEXPO",
                          "2026-10-15T12:00:00Z"),
                     srow("Pinnacle", "Carlos Alcaraz", 130, S - 3600, S - 3605, "FEXPO",
                          "2026-10-15T12:00:00Z")])
expo["league"] = "atp"
LOG = pd.DataFrame([{"fixture_id": "FEXPO", "player_1": "Djokovic N.",
                     "player_2": "Alcaraz C.", "start_time_utc": "2026-10-15T12:00:00Z",
                     "tournament": "Vienna, Austria", "settled": True, "p1_won": True,
                     "void": False, "score": "6-3 6-4", "best_of_5": False, "mc2_p1": 0.6,
                     "mc2_recon": False, "pm_src": "x"}])
NOWR = pd.Timestamp("2026-10-27T00:00:00Z").timestamp()
RN.process_snapshot(L3, expo, LOG, NOWR, NOWR)
RN.settle_pass(L3, LOG, NOWR)
check("integration: registered exposure exclusion keeps Oct 11-19 rows out of every stage",
      len(SG.stage_frame(L3, "DEV", NOWR)) == 0)
check("integration: operational pre-activation restriction documented in the stage module",
      "post-registration operational restriction" in SG.__doc__
      and "boundary_conflict" in SG.__doc__)
L3.close()

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
if FAIL:
    print("FAILED:", *FAIL, sep="\n  ")
sys.exit(1 if FAIL else 0)
