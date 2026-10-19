"""OPP1 v3.5 — development/confirmation STAGE MANAGEMENT (synthetic-only; nothing activated).

Registered rules implemented verbatim (v3.5 §4 at commit b0f59fb + addendum A-O1):
- DEV minimums on the final post-thinning evaluated set: >=12,000 raw, >=9 distinct ISO-months,
  >=3 competition tiers; effective n = n/DE >= 8,000 with the governing DE = max(DE_H1, DE_H2)
  floored at 1; the ONLY interim extension is whole ISO-weeks until effective n >= 8,000,
  decided blindly (variances/DE/effective-n only).
- TIER minimums: >=2,250 raw, >=12 distinct ISO-weeks, >=1,500 effective; each tier ends at the
  FIRST date both minimums are met.
- TIER-2 contains only matches starting after the recorded dev+Tier-1 VERDICT document
  (addendum A-O1 start-time basis).
- Splits are immutable once finalized; incomplete ISO weeks never count (runner rule).

WHAT THIS MODULE NEVER DOES: it never computes statistical success. Sample-size eligibility
only moves a stage to *_REVIEW. Closure requires an explicitly provided, owner-authorized
blinded decision input (the four variances), and gate verdicts are RECORDED from authorized
inputs, never derived here. Missing inputs leave a clear pending state. Degenerate variances
raise the registered DataIntegrityAbort via the committed machinery — no fallback.

OPERATIONAL ACTIVATION BOUNDARY (post-registration operational restriction, owner-directed,
NOT a change to the registered specification): fixtures first observed before the authorized
activation timestamp stay excluded from prospective accrual even when the registered dev
cutoff alone would admit them; the runner's visible boundary_conflict diagnostics are retained.

All state is derived by folding the committed runner's append-only ledger. New event types:
stage_review, stage_extension, stage_closed, verdict_recorded, experiment_final.
"""
from __future__ import annotations

import pandas as pd

import opp1_eval as EV
import opp1_runner as RN
import opp1_sample as SA

# ---- registered minimums (v3.5 §4) ----------------------------------------------------------
DEV_RAW, DEV_MONTHS, DEV_TIERS, DEV_EFF = SA.DEV_RAW_MIN, SA.DEV_ISO_MONTHS_MIN, \
    SA.DEV_TIERS_MIN, EV.EFF_MIN_DEV
TIER_RAW, TIER_WEEKS, TIER_EFF = SA.TIER_RAW_MIN, SA.TIER_ISO_WEEKS_MIN, 1500
STAGES = ("DEV", "TIER1", "TIER2")


class StageError(RuntimeError):
    """Refused stage operation (wrong state, missing authorized inputs, overlap, re-close)."""


def _week_end_ts(start: pd.Timestamp) -> float:
    return (start.normalize() - pd.Timedelta(days=start.weekday())
            + pd.Timedelta(days=7)).timestamp()


# ------------------------------------------------------------------ state fold
def stage_state(ledger: RN.Ledger) -> dict:
    """Deterministic fold: identical ledger -> identical stage state (restart-safe)."""
    st = {"stage": "DEV", "phase": "COLLECTING", "closed": {}, "verdict": None, "final": None}
    for e in ledger.events():
        p = e["payload"]
        if e["etype"] == "stage_review" and p["eligible"]:
            if p["stage"] == st["stage"] and p["stage"] not in st["closed"]:
                st["phase"] = "REVIEW"
        elif e["etype"] == "stage_extension":
            if p["stage"] == st["stage"]:
                st["phase"] = "EXTENDING"
        elif e["etype"] == "stage_closed":
            st["closed"][p["stage"]] = p
            if p["stage"] == "DEV":
                st["stage"], st["phase"] = "TIER1", "COLLECTING"
            elif p["stage"] == "TIER1":
                st["stage"], st["phase"] = "TIER1_CLOSED_AWAITING_VERDICT", "PENDING"
            elif p["stage"] == "TIER2":
                st["stage"], st["phase"] = "TIER2_CLOSED_AWAITING_FINAL", "PENDING"
        elif e["etype"] == "verdict_recorded":
            st["verdict"] = p
            if st["stage"] == "TIER1_CLOSED_AWAITING_VERDICT":
                st["stage"], st["phase"] = "TIER2", "COLLECTING"
        elif e["etype"] == "experiment_final":
            st["final"] = p
            st["stage"], st["phase"] = p["result"], "FINAL"
    return st


# ------------------------------------------------------------------ chronological stage frames
def stage_frame(ledger: RN.Ledger, stage: str, as_of_ts: float) -> pd.DataFrame:
    """The stage's candidate population.

    A CLOSED STAGE IS FROZEN (2026-10-19 hardening): its population is the immutable
    `membership` list recorded in that stage's `stage_closed` event and nothing else, so a
    closed stage can never pick up a late settlement, a new source row, or anything a later
    boundary check sees. Before the fix this re-derived from the live finalized frame and a
    post-closure call returned 12,105 rows against the frozen 12,100 -- informational at the
    time, because no decision path read it, but exactly the kind of drift that must not be
    reachable at all. Closure events are never rewritten; this only changes which rows are
    returned afterwards.

    An OPEN STAGE keeps its registered boundary behaviour unchanged: finalized rows (complete
    ISO weeks only, via the committed runner rule), chronologically partitioned so NO row can
    belong to two evaluated stages -- DEV = weeks ending <= dev close as_of; TIER1 = weeks
    strictly after that, <= its own as_of; TIER2 additionally requires start AFTER the recorded
    verdict timestamp."""
    st = stage_state(ledger)
    if stage in st["closed"]:
        rec = st["closed"][stage]
        frozen = [str(f) for f in (rec.get("membership") or [])]
        # rows are read as of the CLOSURE's own as_of, then restricted to the frozen ids
        src = RN.finalized_frame(ledger, float(rec["as_of_ts"]))
        if not len(src):
            if frozen:
                raise StageError("%s closed with %d frozen members but no source rows are "
                                 "reproducible -- integrity review required" % (stage, len(frozen)))
            return src
        out = src[src["fixture_id"].astype(str).isin(set(frozen))]
        if len(out) != len(frozen):
            raise StageError("%s frozen membership is not reproducible: %d of %d members "
                             "found -- integrity review required, nothing was rewritten"
                             % (stage, len(out), len(frozen)))
        return out.reset_index(drop=True)
    fin = RN.finalized_frame(ledger, as_of_ts)
    if not len(fin):
        return fin
    wk_end = fin["start"].apply(_week_end_ts)
    if stage == "DEV":
        return fin.reset_index(drop=True)
    if "DEV" not in st["closed"]:
        raise StageError("TIER frames do not exist before DEV closes")
    fin = fin[wk_end > st["closed"]["DEV"]["as_of_ts"]]
    wk_end = fin["start"].apply(_week_end_ts)
    if stage == "TIER1":
        return fin.reset_index(drop=True)
    if stage == "TIER2":
        if "TIER1" not in st["closed"]:
            raise StageError("TIER2 frame does not exist before TIER1 closes")
        fin = fin[wk_end > st["closed"]["TIER1"]["as_of_ts"]]
        if st["verdict"] is None:
            raise StageError("TIER2 collection cannot begin before the dev+Tier-1 verdict "
                             "document is recorded (registered rule)")
        starts = fin["start"].apply(lambda t: t.timestamp())
        fin = fin[starts > float(st["verdict"]["verdict_ts"])]
        return fin.reset_index(drop=True)
    raise StageError("unknown stage %r" % stage)


def counts_ok(frame: pd.DataFrame, stage: str) -> dict:
    """Pure registered raw-minimum evaluation on a POST-THINNING frame."""
    if stage == "DEV":
        c = SA.dev_counts(frame)
        return {"ok": bool(c["meets_dev_minimums"]), "counts": c}
    c = SA.tier_counts(frame)
    return {"ok": bool(c["meets_tier_minimums"]), "counts": c}


# ------------------------------------------------------------------ boundary review
def review_boundary(ledger: RN.Ledger, stage: str, seed_artifact: str, as_of_ts: float,
                    now_ts: float) -> dict:
    """Registered boundary check for the CURRENT stage: verified seed -> registered one-pass
    thinning on the stage window -> registered raw minimums. Sample-size sufficiency moves the
    stage to REVIEW only — it is NEVER statistical success and closes nothing."""
    st = stage_state(ledger)
    if st["stage"] != stage or st["phase"] not in ("COLLECTING", "EXTENDING", "REVIEW"):
        raise StageError("stage %s not collecting (current: %s/%s)"
                         % (stage, st["stage"], st["phase"]))
    seed = RN.verified_seed(seed_artifact)
    cand = stage_frame(ledger, stage, as_of_ts)
    if not len(cand):
        rep = {"stage": stage, "as_of_ts": as_of_ts, "n_pre": 0, "post_thinning": 0,
               "eligible": False, "counts": None}
    else:
        kept, info = SA.thin(cand, seed)
        ok = counts_ok(kept, stage)
        rep = {"stage": stage, "as_of_ts": as_of_ts, "n_pre": info["n_pre"],
               "cap_size": info["cap_size"], "post_thinning": int(len(kept)),
               "eligible": ok["ok"], "counts": ok["counts"],
               "kept_fixture_ids": sorted(kept["fixture_id"].astype(str))}
    ledger.append("stage_review", rep, now_ts)
    return rep


# ------------------------------------------------------------------ authorized closure
def record_stage_decision(ledger: RN.Ledger, stage: str, seed_artifact: str, as_of_ts: float,
                          blinded_inputs: dict, authorization: str, now_ts: float) -> dict:
    """Owner-authorized closure attempt. Requires an ELIGIBLE review at this as_of and the
    explicitly provided blinded inputs (the four registered variances). The registered blinded
    extension rule applies: effective n below the stage minimum -> stage_extension (whole
    ISO-weeks, blinded payload only), NOT closure. Closure freezes membership immutably.
    Statistical gates are NOT evaluated here under any circumstances."""
    st = stage_state(ledger)
    if stage in st["closed"]:
        raise StageError("%s already closed — finalized membership is immutable" % stage)
    if st["stage"] != stage or st["phase"] not in ("REVIEW", "EXTENDING"):
        raise StageError("premature progression refused: %s is %s/%s (needs an eligible "
                         "boundary review first)" % (stage, st["stage"], st["phase"]))
    if not authorization or not str(authorization).strip():
        raise StageError("missing owner authorization reference — pending")
    need = ("V_clust_H1", "V_iid_H1", "V_clust_H2", "V_iid_H2")
    if blinded_inputs is None or any(k not in blinded_inputs for k in need):
        raise StageError("missing authorized blinded inputs %s — pending" % (need,))
    reviews = [e["payload"] for e in ledger.events("stage_review")
               if e["payload"]["stage"] == stage and e["payload"]["as_of_ts"] == as_of_ts
               and e["payload"]["eligible"]]
    if not reviews:
        raise StageError("no eligible boundary review at this as_of — pending")
    rev = reviews[-1]
    seed = RN.verified_seed(seed_artifact)        # provenance re-verified at every decision
    dec = EV.decide_extension(float(blinded_inputs["V_clust_H1"]),
                              float(blinded_inputs["V_iid_H1"]),
                              float(blinded_inputs["V_clust_H2"]),
                              float(blinded_inputs["V_iid_H2"]),
                              rev["post_thinning"])         # DataIntegrityAbort on degenerate
    eff_min = DEV_EFF if stage == "DEV" else TIER_EFF
    if dec["effective_n"] < eff_min:
        ext = dict(dec, stage=stage, as_of_ts=as_of_ts, eff_min=eff_min,
                   rule="extend by whole ISO-weeks (registered; blinded)")
        ledger.append("stage_extension", ext, now_ts)
        return {"closed": False, "extension": ext}
    closed = {"stage": stage, "as_of_ts": as_of_ts, "n_pre": rev["n_pre"],
              "post_thinning": rev["post_thinning"],
              "membership": rev["kept_fixture_ids"],
              "governing_DE": dec["governing_DE"], "effective_n": dec["effective_n"],
              "seed_verified_sha": RN.REG_SHA256, "authorization": str(authorization),
              "note": ("sample-size closure only — NOT a statistical verdict; gates are "
                       "evaluated and recorded separately under their own authorization")}
    ledger.append("stage_closed", closed, now_ts)
    return {"closed": True, "record": closed}


# ------------------------------------------------------------------ authorized verdicts
def record_verdict(ledger: RN.Ledger, verdict_inputs: dict, authorization: str,
                   verdict_ts: float, now_ts: float) -> dict:
    """RECORD (never compute) the dev+Tier-1 verdict document. Requires DEV and TIER1 closed
    and the authorized gate results provided explicitly; opens TIER2 collection for matches
    starting AFTER verdict_ts (registered rule)."""
    st = stage_state(ledger)
    if "DEV" not in st["closed"] or "TIER1" not in st["closed"]:
        raise StageError("verdict requires DEV and TIER1 closed — pending")
    if st["verdict"] is not None:
        raise StageError("verdict already recorded — immutable")
    need = ("h1_dev_pass", "h2_dev_pass", "h1_tier1_pass", "h2_tier1_pass")
    if not authorization or verdict_inputs is None or any(k not in verdict_inputs
                                                          for k in need):
        raise StageError("missing authorized verdict inputs %s — pending" % (need,))
    p = {"verdict_ts": float(verdict_ts), "inputs": {k: bool(verdict_inputs[k]) for k in need},
         "authorization": str(authorization),
         "note": "recorded from authorized statistical results; never derived here"}
    ledger.append("verdict_recorded", p, now_ts)
    return p


def verdict_ref(ledger: RN.Ledger):
    """The auditable reference to the recorded verdict: the content hash of its ledger event
    (tamper-evident, since the loader recomputes every hash). None when no verdict exists."""
    vs = ledger.events("verdict_recorded")
    return vs[-1]["hash"] if vs else None


def record_final(ledger: RN.Ledger, result: str, authorization: str, now_ts: float,
                 ref: str | None = None) -> dict:
    """Record the authorized final experiment state: COMPLETE or TERMINATED.

    VERDICT PROVENANCE (2026-10-19 hardening): the final event now carries `verdict_ref`, the
    content hash of the `verdict_recorded` event it belongs to, so the gate results behind a
    final state are always reachable and tamper-evident through the append-only ledger. A
    missing, unparseable or non-matching reference is REFUSED rather than recorded.

    COMPLETE MEANS THE REGISTERED STAGES ALL RAN TO CLOSURE. It does NOT mean the predictive
    gates passed, and the event says so explicitly (`means_gates_passed: False`): the gate
    booleans live only in the referenced verdict event, recorded there from authorized inputs
    and never computed by this module.

    TERMINATED needs a reference only if a verdict exists; an early termination before any
    verdict records `verdict_ref: None`."""
    st = stage_state(ledger)
    if result not in ("COMPLETE", "TERMINATED"):
        raise StageError("final result must be COMPLETE or TERMINATED")
    if result == "COMPLETE" and "TIER2" not in st["closed"]:
        raise StageError("COMPLETE requires TIER2 closed — pending")
    if not authorization:
        raise StageError("missing owner authorization — pending")
    have = verdict_ref(ledger)
    if result == "COMPLETE" and have is None:
        raise StageError("COMPLETE requires a recorded verdict to reference — pending")
    if have is not None:
        if not ref or not isinstance(ref, str):
            raise StageError("missing verdict reference — pending (expected the "
                             "verdict_recorded event's content hash)")
        if ref != have:
            raise StageError("inconsistent verdict reference: does not match the recorded "
                             "verdict event — refused, nothing written")
    elif ref:
        raise StageError("verdict reference supplied but no verdict is recorded — refused")
    p = {"result": result, "authorization": str(authorization), "verdict_ref": have,
         "verdict_ts": (st["verdict"] or {}).get("verdict_ts"),
         "means_gates_passed": False,
         "note": ("COMPLETE/TERMINATED is a procedural state: every registered stage closed "
                  "(or the owner stopped the experiment). The statistical gate results are in "
                  "the referenced verdict_recorded event and are not restated here.")}
    ledger.append("experiment_final", p, now_ts)
    return p
