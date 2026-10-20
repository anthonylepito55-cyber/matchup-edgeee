"""DQU — prospective evaluation of missing_result_flag on the LIVE paper predictions.

Runs the test registered in DQU_PROSPECTIVE_PREREGISTRATION.md, and refuses to compute a
single outcome-dependent statistic until the registered stopping criterion is met. Until
then it prints progress only: how many settled, how many flagged, what is still missing.

That refusal is the point. Reporting a Brier difference at n=40 and again at n=90 and again
at n=200 is how a null result becomes a finding, so the gate is in the code rather than in
an intention.

    python dqu_prospective.py              # progress, or the one registered analysis
    python dqu_prospective.py --status     # progress only, never the analysis

Reads the two beta ledgers and nothing else. Writes one report file. The frozen model, the
original predictions, the official trial and production are untouched: predictions are read
exactly as written, with their original probability, flags, timestamp and model version.
"""
import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dqu_validate as V  # noqa: E402
import tsm_beta_settle as S  # noqa: E402

PREREG = os.path.join(HERE, "DQU_PROSPECTIVE_PREREGISTRATION.md")
OUT = os.path.join(HERE, "dqu_data", "prospective_report.json")

# ---- registered, do not edit without a new pre-registration -------------------
MIN_SETTLED = 300
MIN_FLAGGED = 60
NULL_K = 2000
BETA_VERSION = "TSM-D_rest-BETA-paper/1"
# -------------------------------------------------------------------------------


def prereg_sha():
    h = hashlib.sha256()
    with open(PREREG, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def gather():
    """The registered population, with every exclusion applied and counted."""
    preds, pred_head = S.read_predictions()
    invalid = S.read_invalidated()
    latest = S.latest_settlements()
    _, settle_head = S.read_settlements()

    excl = collections.Counter()
    rows, pending = [], 0
    for p in preds:
        if p["fixture_identity"] in invalid:
            excl["invalidated"] += 1
            continue
        if p.get("beta_version") != BETA_VERSION:
            excl["other_beta_version"] += 1
            continue
        if str(p.get("tier")) == "Grand Slams" or str(p.get("level")) == "Grand Slams":
            excl["grand_slam"] += 1
            continue
        st = latest.get(p["fixture_identity"])
        if st is None:
            pending += 1
            continue
        # the settlement ledger records the WINNING SIDE as the integer 1 or 2, and a
        # non-result as the string "void" -- not the p1_won/p2_won labels used elsewhere
        oc = st.get("outcome")
        if oc not in (1, 2):
            excl["void_or_unscoreable"] += 1
            continue
        y = 1 if oc == 1 else 0
        rows.append({
            # every field is the ORIGINAL as written; nothing is recomputed
            "key": p["identity_digest"],
            "date": str(p["scheduled_start_utc"])[:10],
            "tournament": str(p.get("tournament") or "?").lower(),
            "tier": str(p.get("tier") or "?"),
            "surface": str(p.get("surface") or "?"),
            "band": str(p.get("band") or "?"),
            "p1_prob": float(p["p1_prob"]),
            "confidence": float(p["confidence"]),
            "model_version": p.get("beta_version"),
            "prediction_ts_utc": p.get("prediction_ts_utc"),
            "missing_result_risk": int(p.get("missing_result_risk") or 0),
            "missing_result_flag": bool((p.get("missing_result_risk") or 0) > 0),
            "elo_only": bool(p.get("elo_only")),
            "calibrator_saturated": bool(p.get("calibrator_saturated")),
            "outcome_p1_won": y,
            "settled_utc": st.get("retrieved_utc"),
            "result_source": st.get("result_source"),
        })
    return rows, pending, excl, pred_head, settle_head


def status_block(rows, pending, excl):
    flagged = sum(1 for r in rows if r["missing_result_flag"])
    return {
        "settled_eligible": len(rows), "flagged": flagged,
        "unflagged": len(rows) - flagged,
        "pending": pending, "exclusions": dict(excl),
        "required": {"settled": MIN_SETTLED, "flagged": MIN_FLAGGED},
        "still_needed": {"settled": max(0, MIN_SETTLED - len(rows)),
                         "flagged": max(0, MIN_FLAGGED - flagged)},
        "criterion_met": bool(len(rows) >= MIN_SETTLED and flagged >= MIN_FLAGGED),
    }


def analyse(rows):
    """The single registered analysis. Only ever called when the gate is open."""
    def flag(r):
        return bool(r["missing_result_flag"])
    f = [r for r in rows if flag(r)]
    b = [r for r in rows if not flag(r)]
    obs = V.diff(f, b)
    nul = V.null_tail(rows, len(f) / float(len(rows)), NULL_K, "prospective")
    import dqu_report as R
    controls = {}
    for name, fn in (("parity", R.neg_control_parity), ("random37", R.neg_control_random)):
        cf = [r for r in rows if fn(r)]
        cb = [r for r in rows if not fn(r)]
        if len(cf) < 30 or len(cb) < 30:
            controls[name] = {"verdict": "n_too_small"}
            continue
        cobs = V.diff(cf, cb)
        cnul = V.null_tail(rows, len(cf) / float(len(rows)), NULL_K, "ctrl_" + name)
        controls[name] = {
            "diff": round(cobs, 5),
            "empirical_p": round(float((np.abs(cnul) >= abs(cobs)).mean()), 5),
            "beats_all_nulls": bool(abs(cobs) > np.abs(cnul).max()),
            "verdict": "FAILED_AS_IT_SHOULD" if abs(cobs) <= np.abs(cnul).max()
                       else "CONTROL_PASSED_result_is_inconclusive"}
    return {
        "primary_brier": {
            "diff": round(obs, 5),
            "flagged": R.metrics(f), "unflagged": R.metrics(b),
            "empirical_p_two_sided": round(
                float((np.abs(nul) >= abs(obs)).mean()), 5),
            "beats_all_nulls": bool(abs(obs) > np.abs(nul).max()),
            "null_K": int(len(nul)), "null_sd": round(float(nul.std()), 5),
            "null_max_abs": round(float(np.abs(nul).max()), 5)},
        "log_loss_diff": round(R._ll(f) - R._ll(b), 5),
        "accuracy_diff": round(
            float(np.mean([r["correct"] for r in f]
                          if "correct" in (f[0] if f else {}) else
                          [(r["p1_prob"] >= 0.5) == (r["outcome_p1_won"] == 1)
                           for r in f]))
            - float(np.mean([(r["p1_prob"] >= 0.5) == (r["outcome_p1_won"] == 1)
                             for r in b])), 5),
        "calibration": {"flagged": R.calibration(f), "unflagged": R.calibration(b)},
        "clustered": {"by_tournament": V.cluster_se(rows, flag, "tournament"),
                      "by_date": V.cluster_se(rows, flag, "date")},
        "adjusted": V.item_6_adjusted(rows, flag),
        "strata": V.item_5_strata(rows, flag),
        "negative_controls": controls,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true",
                    help="progress only; never runs the analysis")
    a = ap.parse_args()

    rows, pending, excl, phead, shead = gather()
    st = status_block(rows, pending, excl)
    rep = {
        "module": "DQU-prospective",
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "preregistration": {"file": os.path.basename(PREREG), "sha256": prereg_sha()},
        "ledgers": {"prediction_chain_head": phead, "settlement_chain_head": shead},
        "registered_criterion": {"min_settled": MIN_SETTLED, "min_flagged": MIN_FLAGGED,
                                 "looks_allowed": 1, "null_K": NULL_K},
        "status": st,
        "analysis": None,
    }
    print("PRE-REGISTERED PROSPECTIVE EVALUATION")
    print("  preregistration sha256 %s" % rep["preregistration"]["sha256"][:32])
    print("  settled & eligible %d (need %d)   flagged %d (need %d)   pending %d"
          % (st["settled_eligible"], MIN_SETTLED, st["flagged"], MIN_FLAGGED,
             st["pending"]))
    if st["exclusions"]:
        print("  exclusions: %s" % json.dumps(st["exclusions"]))

    if a.status or not st["criterion_met"]:
        print("\n  stopping criterion NOT met -> no outcome-dependent statistic is "
              "computed or printed.")
        print("  still needed: %d more settled, %d more flagged"
              % (st["still_needed"]["settled"], st["still_needed"]["flagged"]))
    else:
        print("\n  criterion met -> running the ONE registered analysis")
        rep["analysis"] = analyse(rows)
        p = rep["analysis"]["primary_brier"]
        print("  Brier diff %+.5f  empirical p %.5f  beats_all_nulls=%s"
              % (p["diff"], p["empirical_p_two_sided"], p["beats_all_nulls"]))
        for n, c in rep["analysis"]["negative_controls"].items():
            print("  control %-10s %s" % (n, c["verdict"]))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
    print("\nwritten %s" % os.path.relpath(OUT, HERE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
