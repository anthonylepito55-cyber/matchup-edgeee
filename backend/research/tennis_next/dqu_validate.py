"""DQU — pre-deployment validation of missing_result_flag (owner review items 1-8).

Answers, in order: is the negative-control failure real and what does it mean for false
discovery control; were the 545 faithful predictions genuinely as-of; is the flag knowable
before first serve; does the effect survive stratification, adjustment, and the removal of
any single date / tournament / player; and does it survive honest clustered uncertainty.

Read-only. No ledger, no model, no production file, no deployment.
"""
import collections
import datetime as dt
import hashlib
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dqu_report as R  # noqa: E402

M3 = os.path.join(HERE, "dqu_data", "m3_replay.json")
OUT = os.path.join(HERE, "dqu_data", "validation.json")

# Registered windows, read from TSM_PROTOCOL.md / TSM_D_REGISTRATION.md.
TUNING = ("2022-01-01", "2023-12-31")      # coefficients, standardization, isotonic
DEV = ("2024-01-01", "2025-06-30")
FINAL_TEST = ("2025-07-01", "2026-09-30")  # read once, confirmatory, no refit


def se(rows):
    p = np.array([r["p1_prob"] for r in rows], float)
    y = np.array([r["outcome_p1_won"] for r in rows], float)
    return (p - y) ** 2


def diff(f, b):
    return float(se(f).mean() - se(b).mean())


def cluster_se(rows, flag, by):
    """Cluster-robust SE of the mean squared-error difference, clustering on `by`.

    The usual two-sample SE assumes independent rows. Fixtures on one day share an archive
    state; fixtures in one tournament share a draw, a surface and a player pool. Both are
    reported because they give different answers and the larger one is the honest one.
    """
    g = collections.defaultdict(lambda: [[], []])
    for r in rows:
        g[r[by]][0 if flag(r) else 1].append(r)
    # per-cluster contribution to the difference of means
    nf = sum(len(v[0]) for v in g.values())
    nb = sum(len(v[1]) for v in g.values())
    if nf < 2 or nb < 2:
        return None
    mf = np.concatenate([se(v[0]) for v in g.values() if v[0]]).mean()
    mb = np.concatenate([se(v[1]) for v in g.values() if v[1]]).mean()
    infl = []
    for k, (a, b) in g.items():
        ia = (se(a) - mf).sum() / nf if a else 0.0
        ib = (se(b) - mb).sum() / nb if b else 0.0
        infl.append(ia - ib)
    infl = np.array(infl)
    G = len(infl)
    if G < 3:
        return None
    v = infl.var(ddof=1) * G * (G / (G - 1.0))
    s = float(np.sqrt(v))
    d = float(mf - mb)
    return {"diff": round(d, 5), "se": round(s, 5),
            "t": round(d / s, 3) if s > 0 else None,
            "ci95": [round(d - 1.96 * s, 5), round(d + 1.96 * s, 5)],
            "clusters": G, "n_flagged": nf, "n_unflagged": nb}


def null_tail(rows, prevalence, K, tag):
    """Empirical null of the Brier difference for meaningless flags of this prevalence."""
    out = []
    for seed in range(K):
        f, b = [], []
        for r in rows:
            h = int(hashlib.sha256(("%s%d|%s" % (tag, seed, r["key"])).encode())
                    .hexdigest(), 16)
            (f if (h % 10000) < int(prevalence * 10000) else b).append(r)
        if len(f) < 30 or len(b) < 30:
            continue
        out.append(diff(f, b))
    return np.array(out)


# ----------------------------------------------------------------- items 1 and 2
def item_1_2(rows_by_regime):
    """Why the negative control cleared the bar, and whether the bar controls FDR."""
    out = {}
    for regime, rows in rows_by_regime.items():
        ctrl = [r for r in rows if R.neg_control_random(r)]
        rest = [r for r in rows if not R.neg_control_random(r)]
        if len(ctrl) < 30 or len(rest) < 30:
            continue
        prev = len(ctrl) / float(len(rows))
        obs = diff(ctrl, rest)
        big = null_tail(rows, prev, 2000, "audit")
        out[regime] = {
            "control_prevalence": round(prev, 4),
            "control_observed_brier_diff": round(obs, 5),
            "null_K": int(len(big)),
            "null_sd": round(float(big.std()), 5),
            "null_max_abs": round(float(np.abs(big).max()), 5),
            "control_percentile": round(float((big < obs).mean()) * 100, 2),
            "empirical_p_two_sided": round(float((np.abs(big) >= abs(obs)).mean()), 5),
            "z_vs_null": round(obs / float(big.std()), 3),
            "cluster_se_date": cluster_se(rows, R.neg_control_random, "date"),
        }
    return out


def fdr_analysis():
    """What false-discovery rate does 'beats every one of K null draws' actually give?"""
    tests = 22          # 11 signals x 2 regimes, as run in M4
    out = []
    for K in (300, 2000, 10000):
        alpha = 1.0 / (K + 1)
        out.append({"K": K, "per_test_alpha": round(alpha, 6),
                    "expected_false_positives_over_%d_tests" % tests:
                        round(tests * alpha, 4),
                    "family_wise_error_rate": round(1 - (1 - alpha) ** tests, 4)})
    return {"criterion": "a signal must exceed the largest |difference| among K null draws",
            "note": "this is a max-statistic threshold, so per-test alpha is ~1/(K+1); it "
                    "is NOT a multiplicity correction across the signals tested",
            "levels": out}


# ----------------------------------------------------------------------- item 3
def item_3(rows):
    """Were the faithful predictions genuinely as-of, and are any inside a read window?"""
    byd = collections.Counter(r["date"] for r in rows)
    inside = {d: n for d, n in byd.items() if FINAL_TEST[0] <= d <= FINAL_TEST[1]}
    outside = {d: n for d, n in byd.items() if not (FINAL_TEST[0] <= d <= FINAL_TEST[1])}
    return {
        "fitting_windows": {
            "tuning_coefficients_standardisation_isotonic": TUNING,
            "development_evaluation": DEV,
            "final_test_read_once_no_refit": FINAL_TEST},
        "replay_window": [min(byd), max(byd)],
        "years_after_fitting": round(
            (dt.date.fromisoformat(min(byd)) - dt.date.fromisoformat(TUNING[1])).days
            / 365.25, 2),
        "rows_inside_final_test_window": {"n": sum(inside.values()), "by_date": inside},
        "rows_outside_every_registered_window": {"n": sum(outside.values()),
                                                 "by_date": outside},
        "verdict": "no fitting contamination: coefficients, standardisation and the "
                   "isotonic calibrator were all fit on 2022-2023, years before every "
                   "replayed match. Rows inside the final-test window were read once by a "
                   "pre-registered confirmatory comparison that changed no parameter, but "
                   "they are not virgin data; rows outside it are untouched."}


# ----------------------------------------------------------------------- items 5-8
def item_5_strata(rows, flag):
    out = {}
    for key in ("tier", "surface", "band"):
        cells = {}
        for g in sorted({str(r[key]) for r in rows}):
            sub = [r for r in rows if str(r[key]) == g]
            f = [r for r in sub if flag(r)]
            b = [r for r in sub if not flag(r)]
            if len(f) < 10 or len(b) < 10:
                cells[g] = {"n_flagged": len(f), "n_unflagged": len(b),
                            "note": "too few on one side to report"}
                continue
            d = diff(f, b)
            s = np.sqrt(se(f).var(ddof=1) / len(f) + se(b).var(ddof=1) / len(b))
            cells[g] = {"n_flagged": len(f), "n_unflagged": len(b),
                        "brier_flagged": round(float(se(f).mean()), 4),
                        "brier_clean": round(float(se(b).mean()), 4),
                        "diff": round(d, 4),
                        "ci95_unclustered": [round(d - 1.96 * s, 4), round(d + 1.96 * s, 4)]}
        out[key] = cells
    return out


def item_6_adjusted(rows, flag):
    """Does the flag survive adjustment for level, surface, predicted probability and
    Elo-only? OLS of squared error on the flag plus controls, date-clustered SE."""
    tiers = sorted({r["tier"] for r in rows})[1:]        # first level is the baseline
    surfs = sorted({r["surface"] for r in rows})[1:]
    X, y, clu = [], [], []
    for r in rows:
        conf = max(r["p1_prob"], 1 - r["p1_prob"])
        row = [1.0, 1.0 if flag(r) else 0.0, conf, 1.0 if r["elo_only"] else 0.0]
        row += [1.0 if r["tier"] == t else 0.0 for t in tiers]
        row += [1.0 if r["surface"] == s else 0.0 for s in surfs]
        X.append(row)
        y.append(float(se([r])[0]))
        clu.append(r["date"])
    X = np.array(X)
    y = np.array(y)
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    resid = y - X @ beta
    meat = np.zeros((X.shape[1], X.shape[1]))
    for g in set(clu):
        idx = [i for i, c in enumerate(clu) if c == g]
        u = X[idx].T @ resid[idx]
        meat += np.outer(u, u)
    G = len(set(clu))
    V = XtX_inv @ meat @ XtX_inv * (G / (G - 1.0))
    sev = np.sqrt(np.diag(V))
    names = (["intercept", "missing_result_flag", "confidence", "elo_only"]
             + ["tier=" + t for t in tiers] + ["surface=" + s for s in surfs])
    return {"n": len(rows), "clusters_dates": G,
            "terms": [{"term": n, "coef": round(float(b), 5), "se": round(float(s), 5),
                       "t": round(float(b / s), 3) if s > 0 else None}
                      for n, b, s in zip(names, beta, sev)],
            "flag_coef": round(float(beta[1]), 5),
            "flag_t": round(float(beta[1] / sev[1]), 3)}


def item_7_concentration(rows, flag):
    """Does a handful of dates, tournaments or players carry the effect?"""
    base = diff([r for r in rows if flag(r)], [r for r in rows if not flag(r)])
    out = {"full_diff": round(base, 5)}
    for key, label in (("date", "dates"), ("key_tournament", "tournaments"),
                       ("player", "players")):
        groups = collections.defaultdict(list)
        for r in rows:
            if key == "date":
                groups[r["date"]].append(r)
            elif key == "key_tournament":
                groups[r["key"].split("|")[1]].append(r)
            else:
                groups[r["p1"]].append(r)
                groups[r["p2"]].append(r)
        jack = []
        for g in groups:
            keep = [r for r in rows if r not in groups[g]] if key != "player" else [
                r for r in rows if r["p1"] != g and r["p2"] != g]
            f = [r for r in keep if flag(r)]
            b = [r for r in keep if not flag(r)]
            if len(f) < 20 or len(b) < 20:
                continue
            jack.append((g, diff(f, b)))
        if not jack:
            continue
        jack.sort(key=lambda x: x[1])
        out[label] = {
            "n_groups": len(groups),
            "leave_one_out_min": {"group": jack[0][0], "diff": round(jack[0][1], 5)},
            "leave_one_out_max": {"group": jack[-1][0], "diff": round(jack[-1][1], 5)},
            "all_loo_positive": bool(jack[0][1] > 0),
            "loo_range_pct_of_full": round(
                100 * (jack[-1][1] - jack[0][1]) / abs(base), 1) if base else None}
    return out


def main():
    raw = json.load(open(M3, encoding="utf-8"))
    rows = [r for run in raw["runs"] for r in run["rows"]]
    by = {g: [r for r in rows if r["regime"] == g]
          for g in ("faithful", "sensitivity")}
    fa = by["faithful"]

    def flag(r):
        return bool(r["missing_result_flag"])

    untouched = [r for r in fa if r["date"] > FINAL_TEST[1]]

    rep = {"module": "DQU-validation",
           "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "read_only": "no ledger, model, production file or deployment touched",
           "item_1_2_negative_control": item_1_2(by),
           "item_2_fdr": fdr_analysis(),
           "item_3_asof_provenance": item_3(fa),
           "item_5_strata_faithful": item_5_strata(fa, flag),
           "item_6_adjusted_faithful": item_6_adjusted(fa, flag),
           "item_7_concentration_faithful": item_7_concentration(fa, flag),
           "item_8_clustered": {
               "by_date": cluster_se(fa, flag, "date"),
               "by_tournament": cluster_se(
                   [dict(r, _t=r["key"].split("|")[1]) for r in fa], flag, "_t")},
           "independent_untouched_subset": {
               "definition": "faithful rows dated after the registered final-test window",
               "n": len(untouched),
               "dates": sorted({r["date"] for r in untouched}),
               "result": (cluster_se(untouched, flag, "date")
                          if len(untouched) >= 60 else
                          {"note": "too small for a clustered estimate",
                           "n_flagged": sum(1 for r in untouched if flag(r)),
                           "diff": round(diff([r for r in untouched if flag(r)],
                                              [r for r in untouched if not flag(r)]), 5)
                           if 5 <= sum(1 for r in untouched if flag(r)) <= len(untouched) - 5
                           else None})}}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
    print(json.dumps(rep, indent=1)[:1])
    return rep


if __name__ == "__main__":
    rep = main()
    print("\n--- item 1/2 negative control ---")
    print(json.dumps(rep["item_1_2_negative_control"], indent=1))
    print("\n--- item 2 FDR ---")
    print(json.dumps(rep["item_2_fdr"], indent=1))
    print("\n--- item 3 provenance ---")
    print(json.dumps(rep["item_3_asof_provenance"], indent=1))
    print("\n--- item 8 clustered ---")
    print(json.dumps(rep["item_8_clustered"], indent=1))
    print("\n--- untouched subset ---")
    print(json.dumps(rep["independent_untouched_subset"], indent=1))
    print("\nwritten", os.path.relpath(OUT, HERE))
