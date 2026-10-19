"""OPP1 v3.5 — data adapters: existing feed/settlement SCHEMAS -> the committed pure functions.

SCHEMA-LEVEL ONLY. Every function takes PASSED-IN frames/records in the source formats
(oo_feed snapshot rows; tennis_prediction_log rows) and emits exactly what the committed
opp1_* modules expect. No function here opens the snapshot store, the frozen log, or any live
source — real-data wiring and accrual activation remain separately gated.

Discipline: missing or unconvertible source fields are NEVER fabricated or defaulted — the row
is dropped AND counted under an explicit label, or passed through raw so opp1_eligibility's
registered A-O1 validation decides.

Source schemas (inspected read-only 2026-10-19):
- snapshot store (oo_feed.snapshot): fixture_id, league, start_date (ISO str), home, away,
  sportsbook, selection, norm_selection, market, price (AMERICAN odds), limit_max, top_size,
  order_book, quote_ts (epoch s, venue stamp), deep_link, poll_ts (epoch s, oo_feed.py:207/224).
- frozen log: fixture_id, league, tournament, player_1/player_2, start_time_utc (ISO str),
  best_of_5, settled, p1_won, void, score, mc2_p1, mc2_recon, ...
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from oo_feed import am_to_prob          # the project's price->prob conversion (oo_feed.py:279)
import opp1_eligibility as EL
import opp1_link as LK
import opp1_sample as SA

QUOTE_COLS = ["sportsbook", "selection", "prob", "poll_ts", "quote_ts"]


def _norm_name(s) -> str:
    return re.sub(r"[^a-z]+", " ", str(s or "").lower()).strip()


# ---------------------------------------------------------------- store -> quote frame
def quotes_from_store(rows: pd.DataFrame):
    """ONE fixture's snapshot rows -> (quotes frame for opp1_eligibility/opp1_features, drops).
    p1 = the store's HOME slot, p2 = AWAY (the registered fixed deterministic player-1 slot).
    American price -> prob via oo_feed.am_to_prob. Unmappable selections, invalid prices and
    malformed timestamps are dropped and counted — never defaulted."""
    drops = {"non_moneyline": 0, "unmapped_selection": 0, "bad_price": 0, "bad_timestamp": 0}
    g = rows[rows["market"].astype(str) == "moneyline"]
    drops["non_moneyline"] = int(len(rows) - len(g))
    if not len(g):
        return pd.DataFrame(columns=QUOTE_COLS), drops
    home, away = _norm_name(g["home"].iloc[0]), _norm_name(g["away"].iloc[0])
    out = []
    for _, r in g.iterrows():
        side = None
        for cand in (r.get("norm_selection"), r.get("selection")):
            n = _norm_name(cand)
            if n and n == home:
                side = "p1"
                break
            if n and n == away:
                side = "p2"
                break
        if side is None:
            drops["unmapped_selection"] += 1
            continue
        p = am_to_prob(r.get("price"))
        if p is None:
            drops["bad_price"] += 1
            continue
        pts = pd.to_numeric(r.get("poll_ts"), errors="coerce")
        qts = pd.to_numeric(r.get("quote_ts"), errors="coerce")
        if pd.isna(pts) or pd.isna(qts):
            drops["bad_timestamp"] += 1
            continue
        out.append({"sportsbook": r["sportsbook"], "selection": side, "prob": float(p),
                    "poll_ts": float(pts), "quote_ts": float(qts)})
    return pd.DataFrame(out, columns=QUOTE_COLS), drops


# ---------------------------------------------------------------- store -> reschedule evidence
def starts_from_store(rows: pd.DataFrame) -> dict:
    """Observed scheduled-start history from the store (each poll re-records start_date).

    DOCUMENTED POST-REGISTRATION OPERATIONAL INTERPRETATION of observed reschedule evidence
    (not a change to the registered rule): the registered >6h exclusion is evaluated on the
    RANGE of parsed observed starts — range_lo/range_hi (min/max over UTC-parsed values) are
    fed to the committed exclusion_taxonomy, whose registered strict |actual-original| > 6h
    then detects multi-step moves AND A->B->A reversions. An observed range > 6h PROVES a >6h
    reschedule occurred; the converse is NEVER claimed — history before the first listing or
    between polls is unobservable, and any unparseable observed value keeps the ratified
    'reschedule_unverifiable' treatment (counted, not excluded).

    Determinism: rows ordered by parsed poll_ts with start_date as tiebreak, so every output
    is invariant to input row order. A poll batch (one poll_ts) carrying >1 distinct
    start_date is a WITHIN-SOURCE contradiction: start_conflict_within_poll = True (the
    caller excludes pending documented resolution; no timestamp is arbitrarily selected).

    Diagnostics (report-only): n_distinct_starts, unparsed_values_n, max_observed_shift_s,
    first_seen_before_start_s."""
    g = rows.copy()
    g["_pts"] = pd.to_numeric(g["poll_ts"], errors="coerce")
    g = g.dropna(subset=["_pts"])
    g["_sd"] = g["start_date"].astype(str)
    g = g.sort_values(["_pts", "_sd"], kind="mergesort")
    conflict = bool(g.groupby("_pts")["_sd"].nunique().gt(1).any())
    parsed = []
    unparsed = 0
    for v in g["_sd"].drop_duplicates():
        m = EL.parse_ts(v)
        if m["ts"] is not None and m["kind"] in ("aware", "naive_interpreted"):
            parsed.append(m["ts"])
        else:
            unparsed += 1
    shift = (max(parsed) - min(parsed)).total_seconds() if len(parsed) >= 2 else 0.0
    latest_raw = g["start_date"].iloc[-1] if len(g) else None
    lm = EL.parse_ts(latest_raw) if latest_raw is not None else {"ts": None}
    first_seen = (float(lm["ts"].timestamp() - g["_pts"].iloc[0])
                  if (lm["ts"] is not None and len(g)) else None)
    return {"original_start": g["start_date"].iloc[0] if len(g) else None,
            "latest_start": latest_raw,
            "range_lo_iso": min(parsed).isoformat() if parsed else None,
            "range_hi_iso": max(parsed).isoformat() if parsed else None,
            "n_distinct_starts": int(g["_sd"].nunique()),
            "unparsed_values_n": int(unparsed),
            "start_conflict_within_poll": conflict,
            "max_observed_shift_s": float(shift),
            "first_seen_before_start_s": first_seen}


# ---------------------------------------------------------------- log -> linkage frame
def outcomes_from_log(log_df: pd.DataFrame) -> pd.DataFrame:
    """Log-format rows -> the opp1_link outcomes frame (fixture_id, p1, p2, day, tournament).
    day = UTC calendar day of start_time_utc; a row with an unparseable start gets day=None and
    can then only link via fixture_id equality, never via name/day."""
    st = pd.to_datetime(log_df["start_time_utc"], errors="coerce", utc=True)
    return pd.DataFrame({"fixture_id": log_df["fixture_id"].astype(str),
                         "p1": log_df["player_1"], "p2": log_df["player_2"],
                         "day": st.dt.strftime("%Y-%m-%d"),
                         "tournament": log_df["tournament"]})


# ---------------------------------------------------------------- log -> taxonomy inputs
def _set_winners(score) -> tuple:
    """Set winners counting COMPLETED sets only (the settler's discipline,
    tennis_itf_settle.py:133): an unfinished trailing set like '2-1' yields no winner, so
    (sa + sb) < sets flags a retirement mid-set."""
    sa = sb = sets = 0
    for part in str(score or "").replace("(", " ").replace(")", " ").split():
        m = re.match(r"^(\d+)-(\d+)", part)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        sets += 1
        complete = (max(a, b) >= 6 and abs(a - b) >= 2) or (max(a, b) == 7 and min(a, b) >= 5)
        if complete:
            sa += a > b
            sb += b > a
    return sa, sb, sets


def _flag(x):
    """NaN-safe nullable boolean: True, False, or None (missing OR malformed). Bare bool()
    is never used — bool(nan) is True and would fabricate voids and winners."""
    if x is None:
        return None
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, str):
        s = x.strip().lower()
        return True if s in ("true", "1") else (False if s in ("false", "0") else None)
    try:
        if pd.isna(x):
            return None
        f = float(x)
    except (TypeError, ValueError):
        return None
    return True if f == 1.0 else (False if f == 0.0 else None)


def status_from_log(rec) -> dict:
    """Settlement record -> taxonomy inputs, with NaN-safe flag parsing and NO invented facts.
    - void is True  -> status 'void' (the settler voids cancellations).
    - settled is not True -> no status, no winner (the fixture has no outcome; it can never
      become an evaluated row). A present-but-malformed flag gets 'malformed_settlement_flag'.
    - settled is True with missing/malformed p1_won -> 'settled_no_winner': NO winner is
      invented (and missing is never read as player 2); the record cannot be evaluated.
    - an incomplete score on a settled row may be retirement, abandonment, default, or
      incomplete recording — the score alone does not establish the cause. Status 'retired'
      covers all of them; advancing = the RECORDED winner (settler semantics). When the
      completed-set leader disagrees with the recorded winner, the diagnostic
      'retirement_winner_mismatch' is attached — it never overrides the recorded winner,
      never changes the advancing player, and is not an exclusion; it flags the row for
      review if the recorded outcome is ever questioned.
    MAPPING LIMITATION (reported, not papered over): no source carries an explicit
    'postponed' marker; such fixtures never settle and so never become evaluated rows."""
    out = {"status": None, "winner": None, "advancing": None, "labels": []}
    if rec is None:
        return out
    void, settled = _flag(rec.get("void")), _flag(rec.get("settled"))
    pw, bo5 = _flag(rec.get("p1_won")), _flag(rec.get("best_of_5"))
    for name, raw, parsed_v in (("void", rec.get("void"), void),
                                ("settled", rec.get("settled"), settled)):
        if raw is not None and not (isinstance(raw, float) and pd.isna(raw)) and parsed_v is None:
            out["labels"].append("malformed_settlement_flag")
    if void is True:
        out["status"] = "void"
        return out
    if settled is not True:
        return out
    if pw is None:
        out["labels"].append("settled_no_winner")
        return out
    winner = "p1" if pw else "p2"
    sa, sb, sets = _set_winners(rec.get("score"))
    need = (5 if bo5 is True else 3) // 2 + 1   # bo5 missing -> bo3 basis; label-only effect
    if sets and ((sa + sb) != sets or max(sa, sb) < need):
        leader = "p1" if sa > sb else ("p2" if sb > sa else None)
        if leader is not None and leader != winner:
            out["labels"].append("retirement_winner_mismatch")
        out.update({"status": "retired", "winner": winner, "advancing": winner})
        return out
    out["winner"] = winner
    return out


def mc2_from_log(rec) -> tuple:
    """A-O2: the FROZEN pre-match mc2_p1 and its reconstruction flag — never recomputed."""
    v = rec.get("mc2_p1") if rec is not None else None
    return v, bool(rec.get("mc2_recon")) if rec is not None else False


# ---------------------------------------------------------------- end-to-end fixture path
def fixture_to_row(store_rows: pd.DataFrame, log_df: pd.DataFrame,
                   resolution: dict | None = None) -> dict:
    """The full adapter path for ONE fixture (synthetic or, later, real under separate
    authorization): quotes -> T*/eligibility -> linkage -> settlement status -> registered
    taxonomy -> A-O1 membership (store latest start vs linked start, with the registered
    exposure exclusion enforced independently) -> key K + feature inputs.
    `log_df` is in the RAW log schema; the linkage frame is adapted internally and the matched
    record's full raw row supplies status/start/MC2 fields. Returns dict(evaluated_candidate,
    labels, stage results). Nothing is defaulted; every drop/exclusion carries a label."""
    fid = str(store_rows["fixture_id"].iloc[0])
    outcomes_df = outcomes_from_log(log_df)                 # index preserved -> raw row lookup
    labels = []
    quotes, drops = quotes_from_store(store_rows)
    starts = starts_from_store(store_rows)

    # within-source contradiction: conflicting start_dates inside one poll batch -> excluded
    # pending documented resolution; no timestamp is arbitrarily selected
    if starts["start_conflict_within_poll"]:
        labels.append("start_conflict_within_poll")
        return {"fixture_id": fid, "evaluated_candidate": False, "labels": labels,
                "drops": drops, "starts": starts}
    # any unparseable observed start keeps the ratified unverifiable treatment
    # (counted + reported, never an automatic exclusion)
    if starts["unparsed_values_n"] > 0:
        labels.append("reschedule_unverifiable")

    # A-O1 parse of the eligibility timestamp (store latest scheduled start) — raw in, EL rules
    sm = EL.parse_ts(starts["latest_start"])
    if sm["ts"] is None or sm["kind"] == "date_only":
        labels.append("ts_%s" % ("date_only_not_eligibility" if sm["kind"] == "date_only"
                                 else sm["kind"]))
        return {"fixture_id": fid, "evaluated_candidate": False, "labels": labels,
                "drops": drops}
    S = sm["ts"].timestamp()
    elig = EL.tstar_for_fixture(quotes, S)
    if not elig["eligible"]:
        labels.append(elig["reason"])

    link = LK.link_fixture({"fixture_id": fid,
                            "p1": store_rows["home"].iloc[0],
                            "p2": store_rows["away"].iloc[0],
                            "day": sm["ts"].strftime("%Y-%m-%d")}, outcomes_df)
    labels += link["labels"]
    rec = None
    if link["record"] is not None:
        rec = log_df.loc[link["record"].name]               # the full RAW log record
    status = status_from_log(rec if link["status"].startswith("linked") else None)
    labels += status["labels"]

    # the registered >6h rule evaluated on the OBSERVED RANGE: min/max parsed starts are fed
    # to the committed taxonomy, whose |actual - original| > 6h is then exactly the range test
    # (detects reversions and multi-step moves); raw values used when nothing parsed, so the
    # committed unverifiable branch still fires
    orig_arg = starts["range_lo_iso"] if starts["range_lo_iso"] else starts["original_start"]
    act_arg = starts["range_hi_iso"] if starts["range_hi_iso"] else starts["latest_start"]
    tax = EL.exclusion_taxonomy(orig_arg, act_arg,
                                status=status["status"], winner=status["winner"],
                                advancing=status["advancing"])
    labels += tax["labels"]

    linked_start = rec.get("start_time_utc") if (rec is not None and
                                                 "start_time_utc" in rec) else None
    mem = EL.validate_membership(starts["latest_start"], linked_start, resolution)
    labels += mem["labels"]

    mc2_p1, mc2_recon = mc2_from_log(rec if link["status"] == "linked" else None)
    # an evaluated row needs a settled outcome: unsettled or settled_no_winner rows carry
    # outcome None and can never enter the evaluated population
    evaluated = (elig["eligible"] and tax["eligible"] and mem["dev_member"]
                 and link["status"] == "linked" and tax["outcome"] is not None)
    out = {"fixture_id": fid, "evaluated_candidate": evaluated, "labels": labels,
           "drops": drops, "tstar": elig.get("tstar"), "fair": elig.get("fair"),
           "quotes": quotes, "outcome": tax["outcome"], "starts": starts,
           "mc2_p1": mc2_p1, "mc2_recon": mc2_recon,
           "tournament_norm": link["tournament_norm"], "start_ts": sm["ts"]}
    if evaluated:
        out["K"] = SA.key_k(link["tournament_norm"], sm["ts"])
    return out
