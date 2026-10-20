"""TSM paper beta — result settlement and live performance tracking.

    python tsm_beta_settle.py --dry-run           # read-only: what would settle today
    python tsm_beta_settle.py --settle            # ONE supervised settlement pass
    python tsm_beta_settle.py --report            # performance report from settled records
    python tsm_beta_settle.py --validate <date>   # matcher accuracy vs archive truth

READS the immutable paper prediction ledger and NEVER writes to it. Settlement events go to
a SEPARATE hash-chained ledger, so prediction probabilities, timestamps, identities and
data-quality flags cannot be altered by settlement.

RESULT SOURCE. The permitted TennisRatio schedule pages carry no outcome data at all (no
scores, no statuses), and settling from player pages would need ~154 requests, far above the
authorized cap. So results come from the TennisExplorer daily results page, which the frozen
prospective protocol section 5 already names as the settlement source and whose robots.txt
disallows only /redirect/, /terms-of-use/ and /contact/. One request covers a whole day. No
TennisRatio /api/ endpoint is ever accessed.

NO ODDS. That page carries bookmaker columns (`course`, `coursew`). This module deliberately
does not parse them, and a test asserts no odds value is ever captured.

NEVER GUESS. A winner is recorded only when exactly one result row pair matches the fixture's
two players on that date and the outcome is unambiguous. Everything else is PENDING,
AMBIGUOUS, VOID or UNVERIFIABLE, and is logged as such.
"""
import collections
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
import time

import numpy as np
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from exp2_paper import Ledger  # noqa: E402

PRED_LEDGER = os.path.join(HERE, "beta_paper_ledger")
SETTLE_LEDGER = os.path.join(HERE, "beta_settle_ledger")
RESULT_SNAP = os.path.join(HERE, "settle_result_snapshots")
TE_BASE = "https://www.tennisexplorer.com/results/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept": "text/html"}
MIN_DELAY_S = 2.5
TIMEOUT_S = 30
_last = [0.0]

# frozen final-test benchmarks, for context only -- never a pass/fail criterion
BENCHMARKS = {"ge70": {"expected": 0.8203, "realized": 0.8120},
              "ge80": {"expected": 0.8697, "realized": 0.8557},
              "ge85": {"expected": 0.9016, "realized": 0.8821},
              "ge90": {"expected": 0.9316, "realized": 0.9100},
              "overall": {"logloss": 0.57285, "brier": 0.19466, "accuracy": 0.6998}}

# Result rows carry extra attributes after class (onmouseover/onmouseout), so the pattern
# must not assume '>' immediately follows the class attribute.
ROW_RE = re.compile(
    r'<tr id="r(\d+)"[^>]*>(.*?)</tr>\s*<tr id="r\1b"[^>]*>(.*?)</tr>', re.S)
NAME_RE = re.compile(r'<td class="t-name"><a href="/player/([^/"]+)/">([^<]*)</a>')
RESULT_RE = re.compile(r'<td class="result"[^>]*>([^<]*)</td>')
SCORE_RE = re.compile(r'<td class="score"[^>]*>([^<]*)</td>')
TIME_RE = re.compile(r'<td class="first time"[^>]*>([^<]*)</td>')


def _throttle():
    gap = time.monotonic() - _last[0]
    if gap < MIN_DELAY_S:
        time.sleep(MIN_DELAY_S - gap)
    _last[0] = time.monotonic()


# ------------------------------------------------------------------ name reconciliation
def tr_name_parts(slug_or_name):
    """TennisRatio slug/name -> (first_initial, normalized_surname).

    TR slugs are CamelCase concatenations: 'AlexandraEala' -> Alexandra + Eala,
    'BoticVanDeZandschulp' -> Botic + Van De Zandschulp. The surname is everything after
    the first token, because multi-word surnames are common.
    """
    s = str(slug_or_name or "")
    if " " in s:
        toks = [t for t in re.split(r"\s+", s) if t]
    else:
        toks = [t for t in re.split(r"(?<=[a-z])(?=[A-Z])", s) if t]
    if len(toks) < 2:
        return None, re.sub(r"[^a-z]", "", s.lower())
    return toks[0][:1].lower(), re.sub(r"[^a-z]", "", "".join(toks[1:]).lower())


def te_name_parts(display):
    """TennisExplorer display name -> (first_initial, normalized_surname).
    'Eala A.' -> ('a', 'eala');  'Van de Zandschulp B.' -> ('b', 'vandezandschulp')."""
    s = str(display or "").strip()
    m = re.match(r"^(.*?)\s+([A-Za-z])\.?$", s)
    if not m:
        return None, re.sub(r"[^a-z]", "", s.lower())
    return m.group(2)[:1].lower(), re.sub(r"[^a-z]", "", m.group(1).lower())


def tr_parts(name, slug=None):
    """Prefer the DISPLAY NAME. Resolved slugs are lowercased ('marianonavone'), which
    destroys the word boundary, so a first initial can only be recovered from the name or
    from a CamelCase slug."""
    for cand in (name, slug):
        if not cand:
            continue
        ini, sur = tr_name_parts(cand)
        if ini and sur:
            return ini, sur
    ini, sur = tr_name_parts(name or slug)
    return ini, sur


def pair_key(a, b, from_te=False, a_slug=None, b_slug=None):
    if from_te:
        pa, pb = te_name_parts(a), te_name_parts(b)
    else:
        pa, pb = tr_parts(a, a_slug), tr_parts(b, b_slug)
    return frozenset(((pa[0], pa[1]), (pb[0], pb[1])))


# ------------------------------------------------------------------ result retrieval
def fetch_results(date_iso, tries=3):
    """One request for a whole day's results. Returns (html, provenance)."""
    d = dt.date.fromisoformat(date_iso)
    url = "%s?type=all&year=%d&month=%d&day=%d" % (TE_BASE, d.year, d.month, d.day)
    last = None
    for i in range(tries):
        _throttle()
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT_S)
        except requests.RequestException as e:
            last = "%s: %s" % (type(e).__name__, e)
            time.sleep(1.5 * (i + 1))
            continue
        if r.status_code != 200:
            last = "HTTP %d" % r.status_code
            time.sleep(1.5 * (i + 1))
            continue
        body = r.content
        return r.text, {"result_source": "tennisexplorer_daily_results",
                        "source_url": url, "result_date": date_iso,
                        "http_status": 200,
                        "retrieved_utc": dt.datetime.now(dt.timezone.utc).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"),
                        "bytes": len(body),
                        "body_sha256": hashlib.sha256(body).hexdigest(),
                        "attempt": i + 1}
    raise RuntimeError("result fetch failed after %d tries: %s (%s)" % (tries, url, last))


def snapshot_results(date_iso, html, prov):
    os.makedirs(RESULT_SNAP, exist_ok=True)
    tag = "%s_%s" % (date_iso, prov["retrieved_utc"].replace(":", "").replace("-", ""))
    d = os.path.join(RESULT_SNAP, tag)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "results.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    with open(os.path.join(d, "provenance.json"), "w", encoding="utf-8") as fh:
        json.dump(prov, fh, indent=1)
    return d


def parse_results(html):
    """-> list of result records. Odds columns are deliberately NOT parsed."""
    out = []
    for mid, r1, r2 in ROW_RE.findall(html):
        n1, n2 = NAME_RE.search(r1), NAME_RE.search(r2)
        if not n1 or not n2:
            continue
        res1 = RESULT_RE.findall(r1)
        res2 = RESULT_RE.findall(r2)
        sc1 = [x.strip() for x in SCORE_RE.findall(r1)]
        sc2 = [x.strip() for x in SCORE_RE.findall(r2)]
        tm = TIME_RE.search(r1)
        v1 = (res1[0].strip() if res1 else "")
        v2 = (res2[0].strip() if res2 else "")
        rec = {"te_row_id": mid,
               "te_slug_1": n1.group(1), "te_name_1": n1.group(2).strip(),
               "te_slug_2": n2.group(1), "te_name_2": n2.group(2).strip(),
               "sets_1": v1, "sets_2": v2,
               "score_1": [x for x in sc1 if x and x not in ("\xa0", "&nbsp;")],
               "score_2": [x for x in sc2 if x and x not in ("\xa0", "&nbsp;")],
               "listed_time": tm.group(1).strip() if tm else None}
        rec["outcome"], rec["outcome_note"] = classify(rec)
        out.append(rec)
    return out


def classify(rec):
    """-> (outcome, note). Never guesses: anything unclear is unverifiable."""
    a, b = rec["sets_1"], rec["sets_2"]
    blob = (" ".join(rec["score_1"] + rec["score_2"]) + " " + a + " " + b).lower()
    if "w/o" in blob or "wo." in blob or blob.strip().endswith(" wo"):
        return "void_walkover", "walkover marker in the result row"
    if "ret" in blob:
        # a retirement still has a winner on court, but only if the sets are readable
        if a.isdigit() and b.isdigit() and a != b:
            return ("winner_1" if int(a) > int(b) else "winner_2"), "retirement"
        return "unverifiable", "retirement without readable sets"
    if a.isdigit() and b.isdigit():
        if int(a) == int(b):
            return "unverifiable", "equal set counts (abandoned or in progress)"
        return ("winner_1" if int(a) > int(b) else "winner_2"), "completed"
    if not a and not b:
        return "unverifiable", "no set counts (not started or in progress)"
    return "unverifiable", "unreadable set counts %r/%r" % (a, b)


# ------------------------------------------------------------------ ledger access
def read_invalidated():
    """Fixture identities an appended invalidation event has withdrawn from scoring. The
    prediction records themselves are never altered."""
    if not os.path.exists(os.path.join(PRED_LEDGER, "events.jsonl")):
        return set()
    led = Ledger(PRED_LEDGER)
    try:
        out = set()
        for e in led.events:
            if e["type"] == "beta_invalidation":
                out.update(e.get("fixture_identities") or ())
        return out
    finally:
        led.close()


def read_predictions(include_invalidated=True):
    led = Ledger(PRED_LEDGER)
    try:
        preds = [e for e in led.events if e["type"] == "beta_prediction"]
        bad = set()
        for e in led.events:
            if e["type"] == "beta_invalidation":
                bad.update(e.get("fixture_identities") or ())
        head = led.events[-1]["hash"] if led.events else None
    finally:
        led.close()
    if not include_invalidated:
        preds = [p for p in preds if p["fixture_identity"] not in bad]
    return preds, head


def read_settlements():
    if not os.path.exists(os.path.join(SETTLE_LEDGER, "events.jsonl")):
        return [], None
    led = Ledger(SETTLE_LEDGER)
    try:
        s = [e for e in led.events if e["type"] == "beta_settlement"]
        head = led.events[-1]["hash"] if led.events else None
    finally:
        led.close()
    return s, head


def latest_settlements():
    s, _ = read_settlements()
    out = {}
    for e in s:
        cur = out.get(e["fixture_identity"])
        if cur is None or e["version"] > cur["version"]:
            out[e["fixture_identity"]] = e
    return out


# ------------------------------------------------------------------ matching
def match_predictions(preds, results_by_date, already):
    """-> list of decisions. Pure; writes nothing."""
    index = {}
    for date_iso, recs in results_by_date.items():
        byp = collections.defaultdict(list)
        for r in recs:
            byp[pair_key(r["te_name_1"], r["te_name_2"], from_te=True)].append(r)
        index[date_iso] = byp
    decisions = []
    for p in preds:
        ident = p["fixture_identity"]
        d = {"fixture_identity": ident, "identity_digest": p["identity_digest"],
             "player_1": p["player_1"], "player_2": p["player_2"],
             "slug_1": p["slug_1"], "slug_2": p["slug_2"],
             "tournament": p["tournament"], "scheduled_start_utc":
                 p["scheduled_start_utc"]}
        # NOTE: an already-settled fixture is still re-matched, because a source
        # CORRECTION must be able to reach the writer. It is only reported as
        # already_settled once its outcome is confirmed unchanged.
        want = pair_key(p.get("player_1"), p.get("player_2"),
                        a_slug=p.get("slug_1"), b_slug=p.get("slug_2"))
        # a postponed fixture may land on an adjacent date, so look at D-1..D+2
        base = str(p["scheduled_start_utc"])[:10]
        try:
            b = dt.date.fromisoformat(base)
        except ValueError:
            d["decision"] = "excluded_unparseable_date"
            decisions.append(d)
            continue
        hits = []
        for off in (0, 1, -1, 2):
            di = (b + dt.timedelta(days=off)).isoformat()
            for r in index.get(di, {}).get(want, []):
                hits.append((di, r))
        if not hits:
            d["decision"] = "pending_no_result"
            d["dates_searched"] = [(b + dt.timedelta(days=o)).isoformat()
                                   for o in (0, 1, -1, 2) if
                                   (b + dt.timedelta(days=o)).isoformat() in index]
            decisions.append(d)
            continue
        if len(hits) > 1:
            d["decision"] = "ambiguous_multiple_results"
            d["candidates"] = [{"date": x[0], "te_row_id": x[1]["te_row_id"],
                                "names": [x[1]["te_name_1"], x[1]["te_name_2"]]}
                               for x in hits]
            decisions.append(d)
            continue
        di, r = hits[0]
        d["result_date"] = di
        d["te_row_id"] = r["te_row_id"]
        d["te_names"] = [r["te_name_1"], r["te_name_2"]]
        d["sets"] = [r["sets_1"], r["sets_2"]]
        d["score"] = [r["score_1"], r["score_2"]]
        d["outcome_note"] = r["outcome_note"]
        d["postponed"] = (di != base)
        if r["outcome"] in ("void_walkover",):
            if (already.get(ident) or {}).get("outcome") == "void":
                d["decision"] = "already_settled"
            else:
                d["decision"] = "void"
                d["void_reason"] = r["outcome_note"]
                if ident in already:
                    d["is_correction"] = True
            decisions.append(d)
            continue
        if r["outcome"] == "unverifiable":
            d["decision"] = "unverifiable_result"
            decisions.append(d)
            continue
        # map the TE winner back to the prediction's own player order
        te_win_parts = (te_name_parts(r["te_name_1"]) if r["outcome"] == "winner_1"
                        else te_name_parts(r["te_name_2"]))
        p1_parts = tr_parts(p.get("player_1"), p.get("slug_1"))
        p2_parts = tr_parts(p.get("player_2"), p.get("slug_2"))
        if te_win_parts == p1_parts and te_win_parts != p2_parts:
            d["winner_side"] = 1
        elif te_win_parts == p2_parts and te_win_parts != p1_parts:
            d["winner_side"] = 2
        else:
            d["decision"] = "unverifiable_winner_mapping"
            decisions.append(d)
            continue
        if (already.get(ident) or {}).get("outcome") == d["winner_side"]:
            d["decision"] = "already_settled"
            decisions.append(d)
            continue
        d["decision"] = "settle"
        if ident in already:
            d["is_correction"] = True
            d["previous_outcome"] = already[ident]["outcome"]
        d["winner_slug"] = p["slug_1"] if d["winner_side"] == 1 else p["slug_2"]
        d["winner_name"] = p["player_1"] if d["winner_side"] == 1 else p["player_2"]
        d["predicted_correct"] = bool(
            (p["p1_prob"] >= 0.5 and d["winner_side"] == 1)
            or (p["p1_prob"] < 0.5 and d["winner_side"] == 2))
        decisions.append(d)
    return decisions


# ------------------------------------------------------------------ settlement pass
def run(write=False, dates=None):
    preds, pred_head = read_predictions()
    if not preds:
        return {"status": "NO PREDICTIONS IN THE PAPER LEDGER"}, []
    before = latest_settlements()
    _, settle_head_before = read_settlements()
    want_dates = sorted({str(p["scheduled_start_utc"])[:10] for p in preds})
    today = dt.datetime.now(dt.timezone.utc).date()
    dates = dates or [d for d in want_dates
                      if dt.date.fromisoformat(d) <= today]
    results, provs = {}, []
    for d in dates:
        html, prov = fetch_results(d)
        snap = snapshot_results(d, html, prov)
        recs = parse_results(html)
        prov["parsed_rows"] = len(recs)
        prov["snapshot_dir"] = os.path.basename(snap)
        results[d] = recs
        provs.append(prov)
    decisions = match_predictions(preds, results, before)
    tally = collections.Counter(d["decision"] for d in decisions)
    summary = {
        "pass_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "PAPER SETTLEMENT - read-only on the prediction ledger; no odds, no money",
        "predictions_in_ledger": len(preds),
        "prediction_ledger_chain_head": pred_head,
        "settlement_ledger_chain_head_before": settle_head_before,
        "result_dates_fetched": dates,
        "result_dates_not_yet_reached": [d for d in want_dates if d not in dates],
        "result_provenance": provs,
        "decisions": dict(tally),
        "settleable_now": tally.get("settle", 0),
        "pending": tally.get("pending_no_result", 0),
        "ambiguous": tally.get("ambiguous_multiple_results", 0),
        "void": tally.get("void", 0),
        "unverifiable": (tally.get("unverifiable_result", 0)
                         + tally.get("unverifiable_winner_mapping", 0)),
        "excluded": tally.get("excluded_unparseable_date", 0),
        "already_settled": tally.get("already_settled", 0),
        "postponed_matches_detected": sum(1 for d in decisions if d.get("postponed")),
    }
    if write:
        to_write = [d for d in decisions if d["decision"] in ("settle", "void")]
        if True:
            prov_by_date = {p["result_date"]: p for p in provs}
            led = Ledger(SETTLE_LEDGER)
            try:
                if not [e for e in led.events if e["type"] == "settle_open"]:
                    led.append("settle_open", {
                        "ts": summary["pass_utc"],
                        "prediction_ledger_chain_head": pred_head,
                        "note": "settlement ledger; the prediction ledger is read-only "
                                "and is never modified by settlement"})
                known = {}
                for e in led.events:
                    if e["type"] == "beta_settlement":
                        known[e["fixture_identity"]] = max(
                            known.get(e["fixture_identity"], 0), e["version"])
                new = corr = 0
                for d in to_write:
                    prev = known.get(d["fixture_identity"], 0)
                    outcome = ("void" if d["decision"] == "void"
                               else d["winner_side"])
                    if prev:
                        old = [e for e in led.events if e["type"] == "beta_settlement"
                               and e["fixture_identity"] == d["fixture_identity"]
                               and e["version"] == prev][0]
                        if old["outcome"] == outcome:
                            continue
                        corr += 1
                    else:
                        new += 1
                    pv = prov_by_date.get(d.get("result_date"), {})
                    led.append("beta_settlement", {
                        "ts": summary["pass_utc"],
                        "fixture_identity": d["fixture_identity"],
                        "identity_digest": d["identity_digest"],
                        "outcome": outcome,
                        "winner_slug": d.get("winner_slug"),
                        "winner_name": d.get("winner_name"),
                        "predicted_correct": d.get("predicted_correct"),
                        "postponed": bool(d.get("postponed")),
                        "outcome_note": d.get("outcome_note"),
                        "sets": d.get("sets"), "score": d.get("score"),
                        "version": prev + 1,
                        "result_source": pv.get("result_source"),
                        "source_url": pv.get("source_url"),
                        "result_date": d.get("result_date"),
                        "retrieved_utc": pv.get("retrieved_utc"),
                        "source_body_sha256": pv.get("body_sha256"),
                        "te_row_id": d.get("te_row_id")})
                    known[d["fixture_identity"]] = prev + 1
                led.append("settle_pass_note", {
                    "ts": summary["pass_utc"], "new": new, "corrections": corr,
                    "decisions": dict(tally),
                    "predictions_examined": len(preds),
                    "result_dates_fetched": dates,
                    "result_provenance": [
                        {k: pv.get(k) for k in ("result_source", "source_url",
                                                "result_date", "retrieved_utc",
                                                "body_sha256", "parsed_rows")}
                        for pv in provs],
                    "prediction_ledger_chain_head": pred_head})
                summary["written"] = {"new": new, "corrections": corr}
            finally:
                led.close()
        _, h = read_settlements()
        summary["settlement_ledger_chain_head_after"] = h
        p2, h2 = read_predictions()
        summary["prediction_ledger_unchanged"] = (h2 == pred_head
                                                  and len(p2) == len(preds))
    return summary, decisions


# ------------------------------------------------------------------ performance report
def wilson(k, n, z=1.96):
    if n == 0:
        return (None, None, None)
    ph = k / n
    d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return (ph, c - h, c + h)


def _metrics(rows):
    if not rows:
        return None
    y = np.array([1 if r["won"] else 0 for r in rows])
    conf = np.array([r["conf"] for r in rows])
    p = np.clip(np.array([r["p_pred"] for r in rows]), 1e-9, 1 - 1e-9)
    k = int(y.sum())
    r, lo, hi = wilson(k, len(rows))
    return {"n": len(rows), "correct": k,
            "accuracy": round(float(r), 4),
            "wilson95": [round(lo, 4), round(hi, 4)],
            "mean_predicted": round(float(conf.mean()), 4),
            "predicted_minus_actual_pp": round(100 * (float(conf.mean()) - r), 2),
            "logloss": round(float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), 5),
            "brier": round(float(np.mean((p - y) ** 2)), 5)}


def report():
    preds, pred_head = read_predictions()
    invalid = read_invalidated()
    preds = [p for p in preds if p["fixture_identity"] not in invalid]
    latest = latest_settlements()
    rows, unsettled = [], 0
    for p in preds:
        s = latest.get(p["fixture_identity"])
        if s is None:
            unsettled += 1
            continue
        if s["outcome"] == "void":
            continue
        won_side = s["outcome"]
        conf = p["confidence"]
        pick_side = 1 if p["p1_prob"] >= 0.5 else 2
        rows.append({
            "won": pick_side == won_side,
            "conf": conf,
            "p_pred": conf,                      # probability assigned to the PICK
            "band": p["band"], "tier": p["tier"],
            "dq": p["data_quality"],
            "elo_only": bool(p.get("elo_only")),
            "ceil": bool(p.get("calibrator_saturated")),
            "risk": p.get("missing_result_risk", 0) > 0})
    out = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "invalidated_excluded": len(invalid),
           "PRELIMINARY": "small-sample live results; no claim of improvement or "
                          "deterioration versus the frozen benchmarks, and no claim that "
                          "live predictive accuracy has been established",
           "predictions_in_ledger": len(preds),
           "settled": len(rows) + sum(1 for p in preds
                                      if (latest.get(p["fixture_identity"]) or {}).get(
                                          "outcome") == "void"),
           "scored": len(rows), "unsettled": unsettled,
           "void_excluded_from_rates": sum(
               1 for p in preds
               if (latest.get(p["fixture_identity"]) or {}).get("outcome") == "void"),
           "prediction_ledger_chain_head": pred_head,
           "frozen_benchmarks_for_context_only": BENCHMARKS}
    if not rows:
        out["status"] = "NO SETTLED MATCHES YET - no performance figures can be computed"
        return out
    out["overall"] = _metrics(rows)
    out["cumulative_confidence_bands"] = {}
    for t in (0.70, 0.80, 0.85, 0.90):
        m = _metrics([r for r in rows if r["conf"] >= t])
        key = "ge%d" % round(t * 100)
        out["cumulative_confidence_bands"][key] = (
            dict(m, benchmark=BENCHMARKS.get(key)) if m else
            {"n": 0, "benchmark": BENCHMARKS.get(key)})
    out["exclusive_bands"] = {b: _metrics([r for r in rows if r["band"] == b])
                              for b in sorted({r["band"] for r in rows})}
    out["by_tier"] = {t: _metrics([r for r in rows if r["tier"] == t])
                      for t in sorted({r["tier"] for r in rows})}
    out["by_data_quality"] = {
        "NO_KNOWN_DATA_ISSUE": _metrics([r for r in rows
                                         if r["dq"] == "NO_KNOWN_DATA_ISSUE"]),
        "DATA-QUALITY-UNVERIFIED": _metrics([r for r in rows
                                             if r["dq"] == "DATA-QUALITY-UNVERIFIED"]),
        "elo_only": _metrics([r for r in rows if r["elo_only"]]),
        "calibrator_saturated_CEIL": _metrics([r for r in rows if r["ceil"]]),
        "missing_result_risk": _metrics([r for r in rows if r["risk"]])}
    return out


if __name__ == "__main__":
    if "--report" in sys.argv:
        print(json.dumps(report(), indent=1, default=str))
    elif "--validate" in sys.argv:
        i = sys.argv.index("--validate")
        d = sys.argv[i + 1]
        import tsm_beta_settle_validate as V
        print(json.dumps(V.validate(d), indent=1, default=str))
    elif "--settle" in sys.argv or "--dry-run" in sys.argv:
        w = "--settle" in sys.argv
        s, dec = run(write=w)
        print(json.dumps(s, indent=1, default=str))
        byd = collections.defaultdict(list)
        for x in dec:
            byd[x["decision"]].append(x)
        for k in sorted(byd):
            print("\n%s (%d)" % (k.upper(), len(byd[k])))
            for x in byd[k][:6]:
                print("   %-22s vs %-22s %-16s start %s"
                      % (str(x["player_1"])[:22], str(x["player_2"])[:22],
                         str(x["tournament"])[:16], x["scheduled_start_utc"]))
            if len(byd[k]) > 6:
                print("   ... %d more" % (len(byd[k]) - 6))
        if not w:
            print("\nDRY RUN - nothing written.")
    else:
        print(__doc__)
