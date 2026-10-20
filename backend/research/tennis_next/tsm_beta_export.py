"""TSM D_rest paper beta — export a READ-ONLY public snapshot for the dashboard tab.

    python tsm_beta_export.py            # write backend/data_cache/tsm_beta_public.json

Reads the immutable paper prediction ledger and the settlement ledger and writes a flat
JSON snapshot. It never writes to either ledger, runs no model, contacts no feed, and
carries no odds, stake, ROI or bet of any kind -- this is a PAPER PREDICTION record.

The dashboard only ever reads this file, so the tab cannot trigger computation and cannot
drift from the ledger: the snapshot carries both chain heads so it can be checked.
"""
import collections
import datetime as dt
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tsm_beta as B  # noqa: E402
import tsm_beta_settle as S  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "data_cache", "tsm_beta_public.json")


def build():
    preds, pred_head = S.read_predictions()
    latest = S.latest_settlements()
    _, settle_head = S.read_settlements()
    rows = []
    for p in preds:
        st = latest.get(p["fixture_identity"])
        res = None
        if st is not None:
            if st["outcome"] == "void":
                res = {"status": "void", "note": st.get("outcome_note")}
            else:
                won = (1 if p["p1_prob"] >= 0.5 else 2) == st["outcome"]
                res = {"status": "settled", "winner": st.get("winner_name"),
                       "correct": bool(won), "note": st.get("outcome_note"),
                       "source": st.get("result_source"),
                       "retrieved_utc": st.get("retrieved_utc")}
        rows.append({
            "id": p["identity_digest"],
            "p1": p["player_1"], "p2": p["player_2"],
            "tournament": p["tournament"], "level": p["level"], "tier": p["tier"],
            "surface": p["surface"], "round": p["round"], "format": p["format"],
            "start_utc": p["scheduled_start_utc"],
            "predicted_utc": p["prediction_ts_utc"],
            "pick": p["predicted_winner"],
            "p1_prob": p["p1_prob"], "confidence": p["confidence"], "band": p["band"],
            "data_quality": p["data_quality"],
            "dq_reasons": p.get("data_quality_reasons") or [],
            "elo_only": bool(p.get("elo_only")),
            "ceil": bool(p.get("calibrator_saturated")),
            "archive_age_days": p.get("archive_age_days"),
            "missing_result_risk": p.get("missing_result_risk"),
            "result": res})
    rows.sort(key=lambda r: (r["start_utc"] or "", -r["confidence"]))
    settled = [r for r in rows if r["result"] and r["result"]["status"] == "settled"]
    snap = {
        "schema": "tsm-d_rest-paper-beta/1",
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "PAPER_ONLY": "paper predictions only - no money, no wager, no odds, no staking",
        "NO_ACCURACY_CLAIM": "live predictive accuracy has NOT been established; any "
                             "figures here are preliminary and small-sample",
        "SEPARATE_FROM_OFFICIAL_TRIAL": "this is the supervised paper beta; the official "
                                        "16-week prospective trial is inactive and has its "
                                        "own untouched ledger",
        "model": {"version": B.BETA_VERSION,
                  "artifact_sha256": None, "refit": False},
        "ledger": {"prediction_chain_head": pred_head,
                   "settlement_chain_head": settle_head,
                   "predictions": len(rows)},
        "counts": {
            "total": len(rows),
            "settled": len(settled),
            "void": sum(1 for r in rows if r["result"]
                        and r["result"]["status"] == "void"),
            "pending": sum(1 for r in rows if not r["result"]),
            "no_known_data_issue": sum(1 for r in rows
                                       if r["data_quality"] == "NO_KNOWN_DATA_ISSUE"),
            "data_quality_unverified": sum(
                1 for r in rows if r["data_quality"] == "DATA-QUALITY-UNVERIFIED"),
            "elo_only": sum(1 for r in rows if r["elo_only"]),
            "ceil": sum(1 for r in rows if r["ceil"]),
            "ge90": sum(1 for r in rows if r["confidence"] >= 0.90),
            "ge90_clean": sum(1 for r in rows if r["confidence"] >= 0.90
                              and r["data_quality"] == "NO_KNOWN_DATA_ISSUE")},
        "by_tier": dict(collections.Counter(r["tier"] for r in rows)),
        "by_band": dict(collections.Counter(r["band"] for r in rows)),
        "dq_reasons": dict(collections.Counter(x for r in rows for x in r["dq_reasons"])),
        "performance": S.report(),
        "predictions": rows}
    try:
        snap["model"]["artifact_sha256"] = json.load(
            open(B.ARTIFACT, encoding="utf-8"))["content_sha256"]
    except Exception:  # noqa: BLE001
        pass
    return snap


if __name__ == "__main__":
    s = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(s, fh)
    body = open(OUT, "rb").read()
    print(json.dumps({k: s[k] for k in ("schema", "generated_utc", "counts", "by_tier",
                                        "dq_reasons")}, indent=1))
    print("\nledger heads:", json.dumps(s["ledger"]))
    print("performance :", s["performance"].get("status")
          or ("scored %d" % s["performance"].get("scored", 0)))
    print("written     :", os.path.relpath(OUT, HERE), "%d bytes" % len(body),
          "sha256", hashlib.sha256(body).hexdigest()[:16])
