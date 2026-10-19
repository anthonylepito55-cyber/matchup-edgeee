"""OPP1 v3.5 — eligibility: T*, quote eligibility, freshness, poll-time cutoff, exclusion
taxonomy, and A-O1 timestamp validation.

Registered protocol: OPP1_SPEC_V3_5_PROPOSAL.md (sha256 7539adbb..., t_reg 2026-10-19T08:10:37Z,
commit b0f59fb) + OPP1_IMPLEMENTATION_ADDENDUM.md (ledger entry 1a).

PURE FUNCTIONS ONLY. Every input is a passed-in DataFrame/scalar. This module has NO code path
that opens the snapshot store, the frozen log, or any live/historical data source. Live wiring
is a separate step that is NOT authorized yet.
"""
from __future__ import annotations

import re

import pandas as pd

# ---- registered constants (v3.5 §2) -------------------------------------------------------
TSTAR_LO_S = 6 * 3600          # window opens S-6h
TSTAR_HI_S = 30 * 60           # window closes S-30min
PIN_FRESH_S = 24 * 3600        # Pinnacle pair quote_ts >= S-24h

# ---- addendum A-O1 constants ---------------------------------------------------------------
DEV_CUTOFF_UTC = pd.Timestamp("2026-10-20T00:00:00Z")          # operational dev cutoff
EXPOSURE_DAY_LO = pd.Timestamp("2026-10-11T00:00:00Z")          # registered analyst-exposure
EXPOSURE_DAY_HI = pd.Timestamp("2026-10-19T23:59:59.999999Z")   # exclusion, independent rule

_DATE_ONLY_RE = re.compile(r"^\s*\d{4}-\d{2}-\d{2}\s*$")


def parse_ts(value):
    """A-O1 timestamp parsing. Returns dict(ts, kind) where kind is one of
    'aware' | 'naive_interpreted' | 'date_only' | 'missing' | 'malformed'.
    - offset-aware ISO-8601  -> converted to UTC ('aware')
    - timezone-naive value   -> interpreted as UTC per source convention, COUNTED as such
    - date-only value        -> day marker only; NEVER usable as the eligibility timestamp
    - missing/unparseable    -> flagged; never silently coerced into eligibility
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return {"ts": None, "kind": "missing"}
    s = str(value).strip()
    if s == "" or s.lower() in ("none", "nan", "nat"):
        return {"ts": None, "kind": "missing"}
    if _DATE_ONLY_RE.match(s):
        try:
            d = pd.Timestamp(s).tz_localize("UTC")
        except Exception:
            return {"ts": None, "kind": "malformed"}
        return {"ts": d, "kind": "date_only"}
    try:
        t = pd.Timestamp(s)
    except Exception:
        return {"ts": None, "kind": "malformed"}
    if pd.isna(t):
        return {"ts": None, "kind": "malformed"}
    if t.tzinfo is None:
        return {"ts": t.tz_localize("UTC"), "kind": "naive_interpreted"}
    return {"ts": t.tz_convert("UTC"), "kind": "aware"}


def tstar_for_fixture(quotes: pd.DataFrame, start_s: float):
    """T* = last stored poll in [S-6h, S-30min]; requires a paired two-sided Pinnacle quote
    observed by T* (poll_ts <= T*) whose shared quote_ts >= S-24h.
    `quotes`: columns sportsbook, selection, prob, poll_ts, quote_ts (epoch seconds).
    Returns dict(eligible, reason, tstar, pin_qts, fair)."""
    lo, hi = start_s - TSTAR_LO_S, start_s - TSTAR_HI_S
    w = quotes[(quotes["poll_ts"] >= lo) & (quotes["poll_ts"] <= hi)]
    if not len(w):
        return {"eligible": False, "reason": "no_tstar_poll", "tstar": None}
    tstar = float(w["poll_ts"].max())
    pin = quotes[(quotes["sportsbook"] == "Pinnacle") & (quotes["poll_ts"] <= tstar)]
    pair = None
    for qts, g in sorted(pin.groupby("quote_ts"), key=lambda kv: kv[0], reverse=True):
        if g["selection"].nunique() == 2:
            pair = (float(qts), g)
            break
    if pair is None:
        return {"eligible": False, "reason": "no_pinnacle_pair", "tstar": tstar}
    qts, g = pair
    if qts < start_s - PIN_FRESH_S:
        return {"eligible": False, "reason": "pinnacle_pair_stale", "tstar": tstar}
    p1 = float(g[g["selection"] == "p1"]["prob"].iloc[-1])
    p2 = float(g[g["selection"] == "p2"]["prob"].iloc[-1])
    return {"eligible": True, "reason": "", "tstar": tstar, "pin_qts": qts,
            "fair": p1 / (p1 + p2)}


def feature_input_ok(row_poll_ts: float, tstar: float) -> bool:
    """Leak-safe observation cutoff (v3.5 §2): every feature input needs poll_ts <= T*."""
    return row_poll_ts <= tstar


# ---- registered exclusion taxonomy (v3.5 §2, carried verbatim from v2 §2) ------------------
RESCHEDULE_MAX_S = 6 * 3600
TAXONOMY_EXCLUDING = {"postponed", "void", "status_contradictory", "rescheduled_gt6h",
                      "retirement_unresolved"}


def exclusion_taxonomy(original_start, actual_start=None, status=None,
                       winner=None, advancing=None) -> dict:
    """Registered taxonomy on EXPLICIT inputs only (no live source): reschedules >6h,
    postponed, voids, retirements -> advancing player.

    Missing or contradictory evidence never silently fires or clears a rule:
    - reschedule needs BOTH a recorded original and actual start; otherwise the row is counted
      'reschedule_unverifiable' (reported, NOT excluded — the registered rule fires on a
      MEASURED reschedule, and no new eligibility rule is invented for missing evidence);
    - a void/postponed status alongside a recorded winner is 'status_contradictory' and
      excluded pending documented review;
    - a retirement with no recorded advancing player cannot settle -> excluded as
      'retirement_unresolved'; with one, the row stays eligible and the advancing player is
      the outcome (the registered rule).
    Applied at the ELIGIBILITY stage, i.e. before N_pre and every downstream counter.
    Returns dict(eligible, labels, outcome)."""
    labels = []
    outcome = winner
    st = str(status).strip().lower() if status is not None else ""
    if st == "postponed":
        labels.append("postponed")
    if st in ("void", "cancelled", "canceled"):
        labels.append("void")
    if labels and winner is not None:
        labels.append("status_contradictory")
    if st == "retired":
        if advancing is None:
            labels.append("retirement_unresolved")
        else:
            outcome = advancing
    if actual_start is None:
        labels.append("reschedule_unverifiable")
    else:
        o, a = parse_ts(original_start), parse_ts(actual_start)
        if o["ts"] is None or a["ts"] is None:
            labels.append("reschedule_unverifiable")
        elif abs((a["ts"] - o["ts"]).total_seconds()) > RESCHEDULE_MAX_S:
            labels.append("rescheduled_gt6h")
    eligible = not (set(labels) & TAXONOMY_EXCLUDING)
    return {"eligible": eligible, "labels": labels, "outcome": outcome}


def validate_membership(store_start, linked_start=None, resolution: dict | None = None):
    """A-O1 membership + timestamp validation for one fixture.

    - Eligibility cutoff evaluated on the STORE start_date (the registered field); a documented
      resolution record may adopt the linked source instead (never automatic).
    - A UTC calendar-day disagreement between sources triggers validation/exclusion PENDING
      RESOLUTION (a flag, not proof either source is wrong). Re-admission requires a resolution
      record naming the adopted source and reason. No rule may auto-pick the eligible reading.
    - The registered Oct 11-19 analyst-exposure exclusion is enforced INDEPENDENTLY of the
      Oct 20 cutoff; a row can carry both labels.
    Returns dict(dev_member, labels, ts_kind_store, ts_kind_linked, resolution_used)."""
    labels = []
    sm = parse_ts(store_start)
    lm = parse_ts(linked_start) if linked_start is not None else {"ts": None, "kind": "absent"}

    # --- cross-source UTC calendar-day check (flag, not verdict) ---
    contradiction = (sm["ts"] is not None and lm["ts"] is not None
                     and sm["ts"].strftime("%Y-%m-%d") != lm["ts"].strftime("%Y-%m-%d"))
    resolution_used = None
    eff = sm  # the timestamp that governs membership
    if contradiction:
        if resolution and resolution.get("source") in ("store", "linked") and resolution.get("reason"):
            resolution_used = dict(resolution)
            eff = sm if resolution["source"] == "store" else lm
            labels.append("validation_resolved")
        else:
            labels.append("validation_pending")
            return {"dev_member": False, "labels": labels, "ts_kind_store": sm["kind"],
                    "ts_kind_linked": lm["kind"], "resolution_used": None}

    # --- the governing timestamp must be usable as an eligibility timestamp ---
    if eff["kind"] in ("missing", "malformed"):
        labels.append("ts_%s" % eff["kind"])
        return {"dev_member": False, "labels": labels, "ts_kind_store": sm["kind"],
                "ts_kind_linked": lm["kind"], "resolution_used": resolution_used}
    if eff["kind"] == "date_only":
        labels.append("ts_date_only_not_eligibility")
        return {"dev_member": False, "labels": labels, "ts_kind_store": sm["kind"],
                "ts_kind_linked": lm["kind"], "resolution_used": resolution_used}
    if eff["kind"] == "naive_interpreted":
        labels.append("ts_naive_interpreted")   # counted + reported, never silent

    ts = eff["ts"]
    # --- INDEPENDENT registered exposure exclusion (v3.5 §4) ---
    if EXPOSURE_DAY_LO <= ts <= EXPOSURE_DAY_HI:
        labels.append("analyst_exposure_excluded")
    # --- A-O1 operational dev cutoff ---
    if ts < DEV_CUTOFF_UTC:
        labels.append("before_dev_cutoff")
    dev_member = (ts >= DEV_CUTOFF_UTC) and ("analyst_exposure_excluded" not in labels)
    return {"dev_member": dev_member, "labels": labels, "ts_kind_store": sm["kind"],
            "ts_kind_linked": lm["kind"], "resolution_used": resolution_used}
