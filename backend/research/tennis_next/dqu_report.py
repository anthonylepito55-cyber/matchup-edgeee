"""DQU M4 — does any data-quality signal actually predict worse predictions?

Consumes M3's replay rows and answers, per signal: do flagged fixtures have larger error
or worse calibration than unflagged ones, by how much, and with what uncertainty.

RULES OF THE REPORT, all of them owner requirements:

  * Effect sizes with confidence intervals first; a p-value never stands alone (req 6).
  * The two M3 regimes are NEVER pooled. A signal measured on artificially stale data is
    reported as sensitivity evidence, not as live evidence (req 9).
  * Thresholds for continuous signals are chosen on the DEVELOPMENT period only and then
    applied unchanged to a final EVALUATION period that nothing was tuned on (req 11).
  * Negative controls run through the identical pipeline. If a meaningless flag separates
    error, the method is broken and the real results mean nothing (req 12).
  * A signal that fails prediction is reported as failed. It may still be a justified
    OBJECTIVE warning -- "this player has 3 clay matches on record" is true whether or not
    it predicts error -- and the report says which category each one falls in (req 5).

Bootstrap resamples whole DATES, not rows: fixtures on one day share an archive state and
a tournament, so row-level resampling would understate the interval.

Read-only. No ledger, no model, no production file, no feed.
"""
import collections
import datetime as dt
import hashlib
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

IN = os.path.join(HERE, "dqu_data", "m3_replay.json")
OUT = os.path.join(HERE, "dqu_data", "m4_report.json")
B = 2000
RNG = np.random.default_rng(20261020)
MIN_CELL = 30               # below this a cell is reported as "n too small", not as a result


# ----------------------------------------------------------------- scoring primitives
def _p_on_outcome(rows):
    p = np.array([r["p1_prob"] for r in rows], float)
    y = np.array([r["outcome_p1_won"] for r in rows], float)
    return p, y


def metrics(rows):
    if not rows:
        return None
    p, y = _p_on_outcome(rows)
    pc = np.clip(p, 1e-9, 1 - 1e-9)
    return {"n": len(rows),
            "accuracy": round(float((((p >= 0.5) == (y == 1)).mean())), 4),
            "brier": round(float(np.mean((p - y) ** 2)), 5),
            "log_loss": round(float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc))), 5),
            "mae": round(float(np.mean(np.abs(p - y))), 5)}


def calibration(rows):
    """Slope and intercept of outcome on logit(p). Slope 1 / intercept 0 is calibrated;
    slope < 1 means the probabilities are too extreme for how often they come true."""
    if len(rows) < MIN_CELL:
        return None
    p, y = _p_on_outcome(rows)
    if len(set(y.tolist())) < 2:
        return None
    x = np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
    try:
        from sklearn.linear_model import LogisticRegression
        m = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000)
        m.fit(x.reshape(-1, 1), y)
        return {"slope": round(float(m.coef_[0][0]), 4),
                "intercept": round(float(m.intercept_[0]), 4)}
    except Exception:  # noqa: BLE001
        return None


def date_bootstrap_diff(flag_rows, base_rows, stat):
    """CI for stat(flagged) - stat(unflagged), resampling whole dates."""
    if len(flag_rows) < MIN_CELL or len(base_rows) < MIN_CELL:
        return None
    by = collections.defaultdict(lambda: ([], []))
    for r in flag_rows:
        by[r["date"]][0].append(r)
    for r in base_rows:
        by[r["date"]][1].append(r)
    dates = sorted(by)
    if len(dates) < 3:
        return None
    obs = stat(flag_rows) - stat(base_rows)
    out = []
    for _ in range(B):
        pick = RNG.choice(len(dates), len(dates), replace=True)
        f, b = [], []
        for i in pick:
            a, c = by[dates[i]]
            f.extend(a)
            b.extend(c)
        if len(f) < 5 or len(b) < 5:
            continue
        out.append(stat(f) - stat(b))
    if len(out) < 50:
        return None
    lo, hi = np.percentile(out, [2.5, 97.5])
    return {"diff": round(float(obs), 5),
            "ci95": [round(float(lo), 5), round(float(hi), 5)],
            "excludes_zero": bool(lo > 0 or hi < 0),
            "n_flagged": len(flag_rows), "n_unflagged": len(base_rows)}


def _brier(rows):
    p, y = _p_on_outcome(rows)
    return float(np.mean((p - y) ** 2))


def _mae(rows):
    p, y = _p_on_outcome(rows)
    return float(np.mean(np.abs(p - y)))


def _ll(rows):
    p, y = _p_on_outcome(rows)
    pc = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc)))


# ------------------------------------------------------------------------- the signals
def neg_control_parity(r):
    """A deliberately meaningless flag: parity of a hash of the two player slugs. If this
    'predicts' error, the pipeline is broken, not the signal."""
    h = hashlib.sha256((r["p1"] + "|" + r["p2"]).encode()).hexdigest()
    return int(h, 16) % 2 == 0


def neg_control_random(r):
    h = hashlib.sha256(("rand|" + r["key"]).encode()).hexdigest()
    return int(h, 16) % 100 < 37


BINARY_SIGNALS = {
    "missing_result_flag": (lambda r: bool(r["missing_result_flag"]), "proxy"),
    "actual_missing_flag": (lambda r: bool(r["actual_missing_flag"]), "truth_only"),
    "elo_only": (lambda r: bool(r["elo_only"]), "measured_asof"),
    "cold_start": (lambda r: bool(r["cold_start"]), "measured_asof"),
    "NEGATIVE_CONTROL_parity": (neg_control_parity, "negative_control"),
    "NEGATIVE_CONTROL_random37": (neg_control_random, "negative_control"),
}

# continuous signals become binary at a threshold CHOSEN ON THE DEV PERIOD ONLY
CONTINUOUS_SIGNALS = {
    "ess_surface_52w_min": ("low", "measured_asof"),
    "n_surface_52w_min": ("low", "measured_asof"),
    "days_since_last_max": ("high", "measured_asof"),
    "serve_return_rows_min": ("low", "measured_asof"),
    "prior_n_min": ("low", "measured_asof"),
}


def pick_threshold(dev_rows, field, direction):
    """Choose the cut on DEV only: the quantile that maximises the Brier gap, among cuts
    that leave at least MIN_CELL rows on both sides. Returned for use on EVAL unchanged."""
    vals = sorted({r[field] for r in dev_rows if r.get(field) is not None})
    if len(vals) < 4:
        return None
    best = None
    for q in (0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5):
        t = float(np.quantile([r[field] for r in dev_rows
                               if r.get(field) is not None], q if direction == "low"
                              else 1 - q))
        f = [r for r in dev_rows if r.get(field) is not None
             and (r[field] <= t if direction == "low" else r[field] >= t)]
        b = [r for r in dev_rows if r.get(field) is not None
             and not (r[field] <= t if direction == "low" else r[field] >= t)]
        if len(f) < MIN_CELL or len(b) < MIN_CELL:
            continue
        gap = _brier(f) - _brier(b)
        if best is None or gap > best[1]:
            best = (t, gap)
    return None if best is None else {"threshold": round(best[0], 4),
                                      "direction": direction,
                                      "dev_brier_gap": round(best[1], 5)}


NULL_K = 300


def empirical_null(rows, prevalence, stat, K=NULL_K, tag="null"):
    """The distribution of stat(flagged) - stat(unflagged) for MEANINGLESS flags of the
    same prevalence, through the identical pipeline.

    This exists because the date-clustered bootstrap turned out to be too narrow for
    signals that split WITHIN a date: a random 37% flag produced +0.023 Brier, outside its
    own bootstrap interval. Resampling dates adds no variance to a contrast that is
    balanced inside every date, so the interval understated the real spread. The empirical
    null makes no such assumption -- it simply measures how large a difference pure noise
    produces on THIS data -- so it is the criterion a signal has to beat.
    """
    out = []
    for seed in range(K):
        f, b = [], []
        for r in rows:
            h = int(hashlib.sha256(("%s%d|%s" % (tag, seed, r["key"])).encode())
                    .hexdigest(), 16)
            (f if (h % 10000) < int(prevalence * 10000) else b).append(r)
        if len(f) < MIN_CELL or len(b) < MIN_CELL:
            continue
        out.append(stat(f) - stat(b))
    if len(out) < 50:
        return None
    a = np.array(out)
    return {"k": len(out), "mean": round(float(a.mean()), 6),
            "sd": round(float(a.std()), 6),
            "pct2_5": round(float(np.percentile(a, 2.5)), 6),
            "pct97_5": round(float(np.percentile(a, 97.5)), 6),
            "max_abs": round(float(np.abs(a).max()), 6),
            "_draws": a}


def within_stratum_diff(rows, flagger, stat, key="tier"):
    """Pooled difference computed INSIDE each stratum, then n-weighted.

    Needed because the thin-data signals are tier proxies: 72% of ITF-men fixtures are
    Elo-only against 4% of ATP, and ITF is the more predictable tier. A pooled comparison
    therefore measures the tier, not the data quality. Strata with too few rows on either
    side are skipped and reported, never silently merged.
    """
    per, num, den = {}, 0.0, 0
    for g in sorted({str(r[key]) for r in rows}):
        sub = [r for r in rows if str(r[key]) == g]
        f = [r for r in sub if flagger(r)]
        b = [r for r in sub if not flagger(r)]
        if len(f) < MIN_CELL or len(b) < MIN_CELL:
            per[g] = {"n_flagged": len(f), "n_unflagged": len(b),
                      "note": "below MIN_CELL, excluded from the pooled figure"}
            continue
        d = stat(f) - stat(b)
        per[g] = {"n_flagged": len(f), "n_unflagged": len(b), "diff": round(d, 5)}
        num += d * len(sub)
        den += len(sub)
    return {"pooled_within_%s" % key: round(num / den, 5) if den else None,
            "n_used": den, "per_stratum": per}


def evaluate(rows, flagger, label, kind):
    f = [r for r in rows if flagger(r)]
    b = [r for r in rows if not flagger(r)]
    if len(f) < MIN_CELL or len(b) < MIN_CELL:
        return {"signal": label, "kind": kind, "verdict": "n_too_small",
                "n_flagged": len(f), "n_unflagged": len(b),
                "min_cell": MIN_CELL}
    prev = len(f) / float(len(rows))
    nul = empirical_null(rows, prev, _brier)
    obs = _brier(f) - _brier(b)
    res = {"signal": label, "kind": kind, "prevalence": round(prev, 4),
           "flagged": metrics(f), "unflagged": metrics(b),
           "brier_diff": date_bootstrap_diff(f, b, _brier),
           "mae_diff": date_bootstrap_diff(f, b, _mae),
           "log_loss_diff": date_bootstrap_diff(f, b, _ll),
           "calibration_flagged": calibration(f),
           "calibration_unflagged": calibration(b),
           "within_tier": within_stratum_diff(rows, flagger, _brier, "tier")}
    if nul is not None:
        draws = nul.pop("_draws")
        nul["observed"] = round(obs, 6)
        nul["empirical_p_two_sided"] = round(
            float((np.abs(draws) >= abs(obs)).mean()), 5)
        nul["beats_every_null_draw"] = bool(abs(obs) > np.abs(draws).max())
        res["empirical_null"] = nul

    bd = res["brier_diff"]
    en = res.get("empirical_null")
    # A signal must clear BOTH the clustered bootstrap and the empirical null. The null is
    # the stricter of the two and is what a meaningless flag has already been shown to
    # sneak past the bootstrap on.
    # The bar is BEATING EVERY ONE of the 300 null draws, not merely p < 0.05 against
    # them. A null draw scored against its own null is uniform, so 5% of meaningless flags
    # clear a 5% threshold by construction -- and one of this run's two controls did
    # exactly that (+0.0227 Brier, empirical p 0.007). Requiring a signal to exceed the
    # largest effect 300 meaningless flags produced is roughly p < 1/301 and survives the
    # ~22 tests this report runs without a separate multiplicity correction.
    boot_ok = bool(bd and bd["excludes_zero"])
    null_ok = bool(en and en["beats_every_null_draw"])
    wt = res["within_tier"].get("pooled_within_tier")
    res["survives_within_tier"] = (
        None if wt is None else bool(wt * obs > 0 and abs(wt) >= 0.3 * abs(obs)))
    if bd is None:
        res["verdict"] = "inconclusive"
    elif boot_ok and null_ok and obs > 0:
        res["verdict"] = "PREDICTS_WORSE"
    elif boot_ok and null_ok and obs < 0:
        res["verdict"] = "PREDICTS_BETTER_unexpected"
    elif boot_ok and not null_ok:
        res["verdict"] = "fails_empirical_null"
    else:
        res["verdict"] = "no_detectable_effect"
    return res


def strata(rows, key, label):
    out = {}
    for g in sorted({str(r[key]) for r in rows}):
        sub = [r for r in rows if str(r[key]) == g]
        out[g] = metrics(sub) if len(sub) >= MIN_CELL else {
            "n": len(sub), "note": "below MIN_CELL, not reported"}
    return {"stratified_by": label, "cells": out}


def analyse(rows, period_label):
    """Full analysis of one row set. Chronological dev/eval split inside."""
    dates = sorted({r["date"] for r in rows})
    cut = dates[int(len(dates) * 0.7)] if len(dates) >= 4 else None
    dev = [r for r in rows if cut and r["date"] < cut]
    ev = [r for r in rows if cut and r["date"] >= cut]
    rep = {"period": period_label, "n": len(rows),
           "dates": [dates[0], dates[-1]] if dates else [],
           "dev_eval_split": {"cut_date": cut, "n_dev": len(dev), "n_eval": len(ev),
                              "note": "thresholds are chosen on DEV and applied unchanged "
                                      "to EVAL; EVAL is never tuned on"},
           "overall": metrics(rows), "calibration_overall": calibration(rows),
           "binary_signals": [], "continuous_signals": [], "strata": []}
    for name, (fn, kind) in BINARY_SIGNALS.items():
        rep["binary_signals"].append(evaluate(rows, fn, name, kind))
    for field, (direction, kind) in CONTINUOUS_SIGNALS.items():
        th = pick_threshold(dev, field, direction) if len(dev) >= 2 * MIN_CELL else None
        if th is None:
            rep["continuous_signals"].append(
                {"signal": field, "kind": kind, "verdict": "no_usable_threshold_on_dev"})
            continue
        t, d = th["threshold"], th["direction"]

        def fn(r, t=t, d=d, field=field):
            v = r.get(field)
            return v is not None and (v <= t if d == "low" else v >= t)
        on_eval = evaluate(ev, fn, field, kind) if len(ev) >= 2 * MIN_CELL else {
            "signal": field, "kind": kind, "verdict": "eval_period_too_small",
            "n_eval": len(ev)}
        on_eval["threshold_from_dev"] = th
        on_eval["also_on_full_period"] = evaluate(rows, fn, field + "_full", kind)
        rep["continuous_signals"].append(on_eval)
    for key, lab in (("tier", "tour/level"), ("surface", "surface"), ("band", "confidence band")):
        rep["strata"].append(strata(rows, key, lab))
    return rep


def main():
    raw = json.load(open(IN, encoding="utf-8"))
    allr = [r for run in raw["runs"] for r in run["rows"]]
    rep = {"module": "DQU-M4/validation",
           "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "source": {"m3": os.path.basename(IN),
                      "artifact_sha256": raw["runs"][0]["artifact_content_sha256"]},
           "rules": ["effect sizes with CIs, never a bare p-value",
                     "faithful and sensitivity regimes are never pooled",
                     "continuous thresholds chosen on DEV, applied unchanged to EVAL",
                     "negative controls run through the identical pipeline",
                     "a signal that fails prediction may still be a justified objective "
                     "warning; the two verdicts are separate",
                     "a signal must clear BOTH the date-clustered bootstrap AND an "
                     "empirical null built from 300 meaningless flags of the same "
                     "prevalence; the bootstrap alone was shown to pass a random flag",
                     "thin-data signals are tier proxies, so every signal is also "
                     "recomputed WITHIN tier and the pooled within-tier effect reported"],
           "regimes": {}}
    for regime in ("faithful", "sensitivity"):
        sub = [r for r in allr if r["regime"] == regime]
        rep["regimes"][regime] = analyse(sub, regime) if sub else {"n": 0}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)

    for regime, r in rep["regimes"].items():
        print("\n" + "=" * 78)
        print("REGIME: %s   n=%d  %s" % (regime.upper(), r.get("n", 0),
                                         r.get("dates", "")))
        if not r.get("n"):
            continue
        print("overall:", json.dumps(r["overall"]), "| calibration",
              json.dumps(r["calibration_overall"]))
        print("\n  signal                        kind             verdict                n_flag  Brier diff [95% CI]")
        for s in r["binary_signals"] + r["continuous_signals"]:
            bd = s.get("brier_diff")
            cell = ("%+.4f [%+.4f, %+.4f]" % (bd["diff"], bd["ci95"][0], bd["ci95"][1])
                    if bd else "--")
            en = s.get("empirical_null") or {}
            wt = (s.get("within_tier") or {}).get("pooled_within_tier")
            print("  %-26s %-15s %-24s %-6s %-26s nullp=%-7s within-tier=%s"
                  % (s["signal"][:26], s.get("kind", ""), s.get("verdict", ""),
                     (s.get("brier_diff") or {}).get("n_flagged",
                                                     s.get("n_flagged", "-")), cell,
                     en.get("empirical_p_two_sided", "-"),
                     ("%+.4f" % wt) if wt is not None else "-"))
    print("\nwritten", os.path.relpath(OUT, HERE))


if __name__ == "__main__":
    main()
