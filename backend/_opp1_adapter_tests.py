"""OPP1 v3.5 adapter integration tests — CONSTRUCTED source-format records only.
No snapshot store, no frozen log, no live data, no outcomes/prices from real records.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import opp1_adapters as AD             # noqa: E402
import opp1_eligibility as EL          # noqa: E402
import opp1_features as FE             # noqa: E402
import opp1_report as RP               # noqa: E402
import opp1_sample as SA               # noqa: E402
from oo_feed import am_to_prob         # noqa: E402

PASS, FAIL = [], []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name)


S_ISO = "2026-10-21T12:00:00Z"
S = pd.Timestamp(S_ISO).timestamp()


def srow(book, sel_name, price, poll, qts, fid="FX1", start=S_ISO,
         home="Novak Djokovic", away="Carlos Alcaraz", market="moneyline"):
    """A synthetic row in the EXACT snapshot-store schema."""
    return {"fixture_id": fid, "league": "atp", "start_date": start, "home": home,
            "away": away, "sportsbook": book, "selection": sel_name,
            "norm_selection": sel_name.lower(), "market": market, "price": price,
            "limit_max": None, "top_size": 100.0, "order_book": None,
            "quote_ts": qts, "deep_link": None, "poll_ts": poll}


def store_fixture(prices=(-150, 130, -140, 125), fid="FX1", start=S_ISO, start0=None,
                  home="Novak Djokovic", away="Carlos Alcaraz"):
    """Pinnacle + Kalshi two-sided at T*-4h (original start row) and in-window."""
    first = start0 or start
    return pd.DataFrame([
        srow("Pinnacle", home, prices[0], S - 5 * 3600, S - 5 * 3600 - 5, fid, first, home, away),
        srow("Pinnacle", away, prices[1], S - 5 * 3600, S - 5 * 3600 - 5, fid, first, home, away),
        srow("Kalshi", home, prices[2], S - 5 * 3600, S - 5 * 3600 - 9, fid, first, home, away),
        srow("Kalshi", away, prices[3], S - 5 * 3600, S - 5 * 3600 - 9, fid, first, home, away),
        srow("Pinnacle", home, prices[0], S - 40 * 60, S - 41 * 60, fid, start, home, away),
        srow("Pinnacle", away, prices[1], S - 40 * 60, S - 41 * 60, fid, start, home, away),
        srow("Kalshi", home, prices[2], S - 40 * 60, S - 42 * 60, fid, start, home, away),
        srow("Kalshi", away, prices[3], S - 40 * 60, S - 42 * 60, fid, start, home, away),
    ])


def log_rec(fid="FX1", p1="Djokovic N.", p2="Alcaraz C.", start=S_ISO, tour="Shanghai, China",
            settled=True, p1_won=True, void=False, score="6-3 6-4", bo5=False,
            mc2=0.61, recon=False):
    return {"fixture_id": fid, "player_1": p1, "player_2": p2, "start_time_utc": start,
            "tournament": tour, "settled": settled, "p1_won": p1_won, "void": void,
            "score": score, "best_of_5": bo5, "mc2_p1": mc2, "mc2_recon": recon}


OUT1 = pd.DataFrame([log_rec()])

# ---------------------------------------------------------------- odds conversion + mapping
q, drops = AD.quotes_from_store(store_fixture())
check("adapter: American odds -> prob via oo_feed.am_to_prob exactly",
      abs(q[(q.sportsbook == "Pinnacle") & (q.selection == "p1")]["prob"].iloc[0]
          - am_to_prob(-150)) < 1e-12 and abs(am_to_prob(-150) - 0.6) < 1e-12
      and abs(am_to_prob(130) - 1 / 2.3) < 1e-12)
check("adapter: p1 = HOME slot, p2 = AWAY slot (fixed deterministic orientation)",
      set(q["selection"]) == {"p1", "p2"} and len(q) == 8 and sum(drops.values()) == 0)
bad = store_fixture()
bad.loc[0, "price"] = 0
bad.loc[1, "norm_selection"] = "someone else"
bad.loc[1, "selection"] = "Someone Else"
bad.loc[2, "poll_ts"] = "not-a-ts"
bad.loc[3, "market"] = "totals"
q2, d2 = AD.quotes_from_store(bad)
check("adapter: invalid price / unmapped selection / bad ts / non-moneyline dropped AND counted",
      d2 == {"non_moneyline": 1, "unmapped_selection": 1, "bad_price": 1, "bad_timestamp": 1}
      and len(q2) == 4)

# ---------------------------------------------------------------- pairing + staleness via path
r = AD.fixture_to_row(store_fixture(), OUT1)
check("path: two-sided Pinnacle pair -> eligible, fair exact",
      r["evaluated_candidate"] and abs(r["fair"] - 0.6 / (0.6 + 1 / 2.3)) < 1e-12)
one_sided = store_fixture()
one_sided = one_sided[~((one_sided.sportsbook == "Pinnacle")
                        & (one_sided.selection == "Carlos Alcaraz"))]
r1 = AD.fixture_to_row(one_sided, OUT1)
check("path: one-sided Pinnacle -> ineligible (no pair)",
      not r1["evaluated_candidate"] and "no_pinnacle_pair" in r1["labels"])
stale = store_fixture()
stale.loc[stale.sportsbook == "Pinnacle", "quote_ts"] = S - 25 * 3600
r2 = AD.fixture_to_row(stale, OUT1)
check("path: stale pair (quote_ts < S-24h) rejected",
      not r2["evaluated_candidate"] and "pinnacle_pair_stale" in r2["labels"])
late = store_fixture()
late.loc[late.sportsbook == "Pinnacle", "poll_ts"] = S - 10 * 60   # polled after window end
r3 = AD.fixture_to_row(late, OUT1)
check("path: quotes polled after the T* window are invisible",
      not r3["evaluated_candidate"] and "no_pinnacle_pair" in r3["labels"])

# ---------------------------------------------------------------- timestamps + membership
garb = store_fixture(start="garbage")
r4 = AD.fixture_to_row(garb, OUT1)
check("path: malformed scheduled start -> ts_malformed, excluded, never coerced",
      not r4["evaluated_candidate"] and "ts_malformed" in r4["labels"])
# store vs log UTC-day contradiction -> pending; documented resolution readmits
out_wrongday = pd.DataFrame([log_rec(start="2026-10-22T12:00:00Z")])
r5 = AD.fixture_to_row(store_fixture(), out_wrongday)
check("path: store/log day disagreement -> validation_pending, excluded",
      not r5["evaluated_candidate"] and "validation_pending" in r5["labels"])
r6 = AD.fixture_to_row(store_fixture(), out_wrongday,
                       resolution={"source": "store", "reason": "log carried next-day qual slot"})
check("path: documented resolution (store adopted) readmits", r6["evaluated_candidate"])
expo = "2026-10-15T12:00:00Z"
Sx = pd.Timestamp(expo).timestamp()
fx_expo = store_fixture(start=expo)
for c in ("poll_ts", "quote_ts"):
    fx_expo[c] = fx_expo[c] - (S - Sx)
r7 = AD.fixture_to_row(fx_expo, pd.DataFrame([log_rec(start=expo)]))
check("path: registered Oct 11-19 exposure exclusion fires independently",
      not r7["evaluated_candidate"] and "analyst_exposure_excluded" in r7["labels"]
      and "before_dev_cutoff" in r7["labels"])

# ---------------------------------------------------------------- reschedule evidence
resched = store_fixture(start0="2026-10-21T04:00:00Z")      # first-seen 8h earlier
r8 = AD.fixture_to_row(resched, OUT1)
check("path: store start moved 8h -> rescheduled_gt6h, excluded",
      not r8["evaluated_candidate"] and "rescheduled_gt6h" in r8["labels"])
small = store_fixture(start0="2026-10-21T08:00:00Z")        # moved 4h only
r9 = AD.fixture_to_row(small, OUT1)
check("path: 4h move does not fire the >6h rule", r9["evaluated_candidate"])
st = AD.starts_from_store(store_fixture(start0="2026-10-21T04:00:00Z"))
check("adapter: original = first-seen, latest = last-seen start",
      st["original_start"] == "2026-10-21T04:00:00Z" and st["latest_start"] == S_ISO
      and st["n_distinct_starts"] == 2)

# ---------------------------------------------------------------- settlement -> taxonomy
check("adapter: void log row -> status void",
      AD.status_from_log(log_rec(void=True, settled=True))["status"] == "void")
ret = AD.status_from_log(log_rec(score="6-3 2-1", p1_won=True))
check("adapter: undecisive settled score replicates settler retirement rule; advancing=winner",
      ret["status"] == "retired" and ret["advancing"] == "p1")
check("adapter: decisive bo3 score is not a retirement",
      AD.status_from_log(log_rec(score="6-3 6-4"))["status"] is None)
check("adapter: bo5 needs 3 sets (2-0 settled = retirement)",
      AD.status_from_log(log_rec(score="6-3 6-4", bo5=True))["status"] == "retired")
check("adapter: unsettled -> no status, no winner",
      AD.status_from_log(log_rec(settled=False)) ==
      {"status": None, "winner": None, "advancing": None, "labels": []})
rr = AD.fixture_to_row(store_fixture(), pd.DataFrame([log_rec(score="6-3 2-1")]))
check("path: retirement stays eligible, outcome = advancing player",
      rr["evaluated_candidate"] and rr["outcome"] == "p1")
rv = AD.fixture_to_row(store_fixture(), pd.DataFrame([log_rec(void=True, p1_won=None)]))
check("path: void fixture excluded via taxonomy",
      not rv["evaluated_candidate"] and "void" in rv["labels"])

# ---------------------------------------------------------------- linkage
out_amb = pd.DataFrame([log_rec(fid=""), log_rec(fid="", p1="N. Djokovic", p2="C. Alcaraz",
                                                 tour="other event")])
ra = AD.fixture_to_row(store_fixture(fid="FXZ"), out_amb)
check("path: two same-day name candidates -> ambiguous, excluded (A-O3)",
      not ra["evaluated_candidate"] and "ambiguous_linkage" in ra["labels"])
out_none = pd.DataFrame([log_rec(fid="", p1="Somebody Q.", p2="Unknown Z.")])
rn = AD.fixture_to_row(store_fixture(fid="FXZ"), out_none)
check("path: no candidate -> unlinked, excluded",
      not rn["evaluated_candidate"] and "no_candidate" in rn["labels"])
badday = pd.DataFrame([log_rec(fid="FX9", start="not a time")])
check("adapter: unparseable log start -> day=None (fixture_id-only linkage)",
      AD.outcomes_from_log(badday)["day"].isna().iloc[0])

# ---------------------------------------------------------------- MC2
rm = AD.fixture_to_row(store_fixture(), pd.DataFrame([log_rec(recon=True)]))
fm = FE.build_features(rm["quotes"], rm["tstar"], mc2_p1=rm["mc2_p1"], mc2_recon=rm["mc2_recon"])
check("path: mc2_recon flows through to the registered missing path",
      fm["logit_mc2_ind"] == 1 and fm["mc2_recon_affected"] == 1)
rm2 = AD.fixture_to_row(store_fixture(), pd.DataFrame([log_rec(mc2=None)]))
fm2 = FE.build_features(rm2["quotes"], rm2["tstar"], mc2_p1=rm2["mc2_p1"],
                        mc2_recon=rm2["mc2_recon"])
check("path: missing frozen mc2 -> missing path (never recomputed)", fm2["logit_mc2_ind"] == 1)

# ---------------------------------------------------------------- N_pre / thinning / reports
rows, lab_lists = [], []
for i in range(12):
    fid = "FX%02d" % i
    fx = store_fixture(fid=fid) if i != 7 else store_fixture(
        fid=fid, start0="2026-10-21T04:00:00Z")           # one rescheduled >6h
    out = pd.DataFrame([log_rec(fid=fid)])
    rr = AD.fixture_to_row(fx, out)
    lab_lists.append(rr["labels"])
    rows.append(rr)
cand = [r for r in rows if r["evaluated_candidate"]]
check("path: excluded fixture never reaches the candidate set",
      len(cand) == 11 and all(r["fixture_id"] != "FX07" for r in cand))
cdf = pd.DataFrame({"fixture_id": [r["fixture_id"] for r in cand],
                    "K": [r["K"] for r in cand]})
seed = SA.registered_seed(os.path.dirname(HERE))
kept, info = SA.thin(cdf, seed)
check("path: N_pre counts candidates only (12 fixtures -> N_pre 11)",
      info["n_pre"] == 11 and info["cap_size"] == 1)
er = RP.exclusion_report(lab_lists)
check("report: adapter labels feed the registered exclusion counts",
      er["rescheduled_gt6h"] == 1 and er["ambiguous_linkage"] == 0)
check("path: all candidates share one K (same event-week)",
      cdf["K"].nunique() == 1 and cdf["K"].iloc[0] == ("shanghai, china", "2026-W43"))
check("report: per-key share table denominators from the post-thinning set",
      RP.per_key_share_table(kept)["den"] == len(kept))

# ================================================================ targeted corrections
def store_multi(starts_seq, fid="FXR"):
    """Fixture polled once per entry in starts_seq (full 2-book two-sided rows each time)."""
    frames = []
    for i, st in enumerate(starts_seq):
        t = S - 5 * 3600 + i * 3600
        frames.append(pd.DataFrame([
            srow("Pinnacle", "Novak Djokovic", -150, t, t - 5, fid, st),
            srow("Pinnacle", "Carlos Alcaraz", 130, t, t - 5, fid, st),
            srow("Kalshi", "Novak Djokovic", -140, t, t - 9, fid, st),
            srow("Kalshi", "Carlos Alcaraz", 125, t, t - 9, fid, st)]))
    # final in-window batch at the LAST scheduled start value
    t = S - 40 * 60
    frames.append(pd.DataFrame([
        srow("Pinnacle", "Novak Djokovic", -150, t, t - 60, fid, starts_seq[-1]),
        srow("Pinnacle", "Carlos Alcaraz", 130, t, t - 60, fid, starts_seq[-1]),
        srow("Kalshi", "Novak Djokovic", -140, t, t - 120, fid, starts_seq[-1]),
        srow("Kalshi", "Carlos Alcaraz", 125, t, t - 120, fid, starts_seq[-1])]))
    return pd.concat(frames, ignore_index=True)


OUTR = pd.DataFrame([log_rec(fid="FXR")])
rev = store_multi(["2026-10-21T12:00:00Z", "2026-10-21T20:00:00Z", "2026-10-21T12:00:00Z"])
rrv = AD.fixture_to_row(rev, OUTR)
check("resched: A->B->A reversion (range 8h) excluded",
      not rrv["evaluated_candidate"] and "rescheduled_gt6h" in rrv["labels"])
multi = store_multi(["2026-10-21T04:00:00Z", "2026-10-21T08:00:00Z", "2026-10-21T12:00:00Z"])
rmu = AD.fixture_to_row(multi, OUTR)
check("resched: two 4h steps (net 8h range) excluded",
      not rmu["evaluated_candidate"] and "rescheduled_gt6h" in rmu["labels"]
      and rmu["starts"]["max_observed_shift_s"] == 8 * 3600)
exact6 = AD.fixture_to_row(store_multi(["2026-10-21T06:00:00Z", "2026-10-21T12:00:00Z"]), OUTR)
check("resched: exactly 6h range NOT excluded (strict > boundary)",
      exact6["evaluated_candidate"] and "rescheduled_gt6h" not in exact6["labels"])
just_over = AD.fixture_to_row(
    store_multi(["2026-10-21T05:59:59Z", "2026-10-21T12:00:00Z"]), OUTR)
check("resched: 6h+1s range excluded", not just_over["evaluated_candidate"]
      and "rescheduled_gt6h" in just_over["labels"])
single = AD.fixture_to_row(store_fixture(fid="FXR"), OUTR)
check("resched: single observed start -> no fire + diagnostics present",
      single["evaluated_candidate"] and single["starts"]["n_distinct_starts"] == 1
      and single["starts"]["max_observed_shift_s"] == 0.0
      and single["starts"]["first_seen_before_start_s"] > 0)
partial = store_multi(["garbage-value", "2026-10-21T12:00:00Z"])
rpa = AD.fixture_to_row(partial, OUTR)
check("resched: unparseable observed value -> ratified unverifiable label, counted NOT excluded",
      rpa["evaluated_candidate"] and "reschedule_unverifiable" in rpa["labels"])
# within-poll conflict + input-order invariance
conf = store_fixture(fid="FXR")
conf.loc[0, "start_date"] = "2026-10-21T18:00:00Z"   # same poll_ts batch, different start
rc1 = AD.fixture_to_row(conf, OUTR)
rc2 = AD.fixture_to_row(conf.sample(frac=1, random_state=42).reset_index(drop=True), OUTR)
check("resched: within-poll conflict -> start_conflict_within_poll, excluded pending",
      not rc1["evaluated_candidate"] and "start_conflict_within_poll" in rc1["labels"])
check("resched: conflict handling invariant to input row order",
      rc1["labels"] == rc2["labels"] and rc1["evaluated_candidate"] == rc2["evaluated_candidate"])
sh1 = AD.starts_from_store(rev)
sh2 = AD.starts_from_store(rev.sample(frac=1, random_state=7).reset_index(drop=True))
check("resched: starts_from_store fully order-invariant", sh1 == sh2)

# ---- NaN-safe settlement flags ----
check("flags: p1_won=None -> settled_no_winner, no invented winner",
      AD.status_from_log(log_rec(p1_won=None))["winner"] is None
      and "settled_no_winner" in AD.status_from_log(log_rec(p1_won=None))["labels"])
check("flags: p1_won=NaN -> settled_no_winner (bool(nan) trap closed)",
      AD.status_from_log(log_rec(p1_won=float("nan")))["winner"] is None)
check("flags: missing winner is never read as player 2",
      AD.status_from_log(log_rec(p1_won=None))["advancing"] is None)
check("flags: void=NaN is NOT void",
      AD.status_from_log(log_rec(void=float("nan")))["status"] is None)
check("flags: settled=NaN treated as unsettled",
      AD.status_from_log(log_rec(settled=float("nan")))["winner"] is None)
check("flags: best_of_5=NaN -> bo3 basis (decisive bo3 score not retired)",
      AD.status_from_log(log_rec(score="6-3 6-4", bo5=float("nan")))["status"] is None)
check("flags: malformed string flag -> malformed_settlement_flag label",
      "malformed_settlement_flag" in AD.status_from_log(log_rec(void="yes"))["labels"])
check("flags: valid decisive outcome keeps recorded winner orientation",
      AD.status_from_log(log_rec(p1_won=False))["winner"] == "p2")
rnw = AD.fixture_to_row(store_fixture(), pd.DataFrame([log_rec(p1_won=None)]))
check("path: settled_no_winner row never enters the evaluated population",
      not rnw["evaluated_candidate"] and "settled_no_winner" in rnw["labels"])
runs = AD.fixture_to_row(store_fixture(), pd.DataFrame([log_rec(settled=False)]))
check("path: unsettled row (no outcome) never enters the evaluated population",
      not runs["evaluated_candidate"])
check("flags: walkover / empty score settled -> normal with recorded winner",
      AD.status_from_log(log_rec(score=""))["winner"] == "p1"
      and AD.status_from_log(log_rec(score="w/o"))["status"] is None)
mm = AD.status_from_log(log_rec(score="6-3 2-1", p1_won=False))
check("retire: score-leader vs recorded winner disagreement -> diagnostic only, winner stands",
      mm["status"] == "retired" and mm["winner"] == "p2" and mm["advancing"] == "p2"
      and "retirement_winner_mismatch" in mm["labels"])
rmm = AD.fixture_to_row(store_fixture(), pd.DataFrame([log_rec(score="6-3 2-1", p1_won=False)]))
check("path: mismatch diagnostic does not exclude or flip the outcome",
      rmm["evaluated_candidate"] and rmm["outcome"] == "p2"
      and "retirement_winner_mismatch" in rmm["labels"])
er2 = RP.exclusion_report([rc1["labels"], rnw["labels"], rrv["labels"]])
check("report: new diagnostic labels are counted, never dropped, and gate nothing",
      er2.get("start_conflict_within_poll") == 1 and er2.get("settled_no_winner") == 1
      and er2["rescheduled_gt6h"] == 1)

print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
if FAIL:
    print("FAILED:", *FAIL, sep="\n  ")
sys.exit(1 if FAIL else 0)
