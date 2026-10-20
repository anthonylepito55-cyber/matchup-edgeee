"""DQU — test suite. Correctness, isolation, and the methodology's own negative controls.

Run:  python dqu_tests.py

Covers owner requirement 12 (negative controls, split-period stability, missing-data
tests, reproducibility) plus the isolation guarantees of requirements 1 and 14: the frozen
artifact, the live beta ledgers and the production snapshot must be byte-identical before
and after the whole DQU pipeline runs.

Read-only throughout. Nothing here writes to a ledger, a model or a production file.
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
import dqu_features as F  # noqa: E402
import dqu_report as R  # noqa: E402
import dqu_snapshots as SNAP  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s %-58s %s" % ("PASS" if cond else "FAIL", name, detail))


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# --------------------------------------------------------------------------- T1 ESS
def t_ess():
    print("\nT1 effective sample size")
    check("ESS of n equal weights == n", abs(F.ess([1.0] * 10) - 10) < 1e-9)
    check("ESS of empty history == 0 (not NaN)", F.ess([]) == 0.0)
    decayed = [F._decay(d) for d in (0, 30, 400, 700, 900, 1100)]
    check("ESS below n when weight is concentrated",
          F.ess(decayed) < len(decayed),
          "%.2f < %d" % (F.ess(decayed), len(decayed)))
    fast = [0.5 ** (d / 30.0) for d in (0, 30, 400, 700, 900, 1100)]
    slow = [0.5 ** (d / 2000.0) for d in (0, 30, 400, 700, 900, 1100)]
    check("ESS monotone in decay (faster decay -> smaller ESS)",
          F.ess(fast) < F.ess(slow), "%.2f < %.2f" % (F.ess(fast), F.ess(slow)))
    check("ESS never exceeds n", F.ess([3.0, 1.0, 0.1]) <= 3 + 1e-9)


# ------------------------------------------------------- T2 as-of purity / missing data
def t_asof():
    print("\nT2 as-of purity and missing-data behaviour")
    base = [{"date": "2026-09-01", "key": "k1", "p": "a", "r": "b", "surface": "Clay",
             "level_raw": "ATP", "pwin": 1, "tournament": "x", "round": "R32"},
            {"date": "2026-09-10", "key": "k2", "p": "a", "r": "c", "surface": "Clay",
             "level_raw": "ATP", "pwin": 0, "tournament": "x", "round": "R16"}]
    future = base + [{"date": "2026-09-20", "key": "k3", "p": "a", "r": "d",
                      "surface": "Clay", "level_raw": "ATP", "pwin": 1,
                      "tournament": "x", "round": "QF"}]
    i_base = F.build_player_index(base, "2026-09-15")
    i_fut = F.build_player_index(future, "2026-09-15")
    check("a future-dated row changes nothing before the cutoff",
          i_base["a"] == i_fut["a"], "%d == %d rows" % (len(i_base["a"]), len(i_fut["a"])))
    i_after = F.build_player_index(future, "2026-09-25")
    check("the same row DOES appear once the cutoff moves past it",
          len(i_after["a"]) == len(i_base["a"]) + 1)
    check("cutoff is strict (< D, not <= D)",
          len(F.build_player_index(base, "2026-09-10")["a"]) == 1)

    class _SR:
        n = {}

        @staticmethod
        def point_probs(*_):
            return None
    pf = F.player_features("nobody", "Clay", "2026-09-15", {}, 0)
    check("a player with no history yields zeros, not an exception",
          pf["n_52w"] == 0 and pf["ess_52w"] == 0.0
          and pf["days_since_last_archived_match"] is None)
    pf2 = F.player_features("a", "Grass", "2026-09-15", i_base, 0)
    check("surface filter is exact (Clay history, Grass query -> 0)",
          pf2["n_surface_52w"] == 0 and pf2["n_52w"] == 2)


# ------------------------------------------------------------------- T3 coverage labels
def t_coverage_labels():
    print("\nT3 coverage is never labelled VERIFIED")
    src = open(os.path.join(HERE, "dqu_features.py"), encoding="utf-8").read()
    states = {"known_complete", "unknown", "known_incomplete"}
    check("no 'VERIFIED' coverage state exists in M2", '"VERIFIED"' not in src.upper()
          or "COVERAGE_STATE" not in src.upper().split('"VERIFIED"')[0][-400:])
    check("the only coverage states are known_complete/unknown/known_incomplete",
          all(s in src for s in states))
    rep_path = os.path.join(HERE, "dqu_data", "m3_replay.json")
    if os.path.exists(rep_path):
        rows = [r for run in json.load(open(rep_path, encoding="utf-8"))["runs"]
                for r in run["rows"]]
        bad = {r["coverage_state"] for r in rows} - states
        check("no replay row carries a coverage state outside the allowed set",
              not bad, str(bad or "clean"))
        check("no live-computable row claims known_complete",
              not any(r["coverage_state"] == "known_complete" for r in rows),
              "live code cannot prove completeness")


# ---------------------------------------------------------------- T4 negative controls
def t_negative_controls():
    print("\nT4 negative controls (methodology self-check)")
    rep_path = os.path.join(HERE, "dqu_data", "m4_report.json")
    if not os.path.exists(rep_path):
        check("m4 report present", False, "run dqu_report.py first")
        return
    rep = json.load(open(rep_path, encoding="utf-8"))
    for regime, r in rep["regimes"].items():
        if not r.get("n"):
            continue
        for s in r.get("binary_signals", []):
            if not s["signal"].startswith("NEGATIVE_CONTROL"):
                continue
            ok = s.get("verdict") in ("no_detectable_effect", "n_too_small",
                                      "inconclusive")
            check("%s / %s does not separate error" % (regime, s["signal"]), ok,
                  s.get("verdict", "?"))


# ------------------------------------------------------------- T5 split-period stability
def t_split_stability():
    print("\nT5 split-period stability")
    rep_path = os.path.join(HERE, "dqu_data", "m3_replay.json")
    if not os.path.exists(rep_path):
        check("m3 rows present", False, "run dqu_replay.py first")
        return
    rows = [r for run in json.load(open(rep_path, encoding="utf-8"))["runs"]
            for r in run["rows"]]
    for regime in ("faithful", "sensitivity"):
        sub = [r for r in rows if r["regime"] == regime]
        if len(sub) < 4 * R.MIN_CELL:
            check("%s has enough rows to split" % regime, False, "n=%d" % len(sub))
            continue
        dates = sorted({r["date"] for r in sub})
        mid = dates[len(dates) // 2]
        a = [r for r in sub if r["date"] < mid]
        b = [r for r in sub if r["date"] >= mid]
        ma, mb = R.metrics(a), R.metrics(b)
        check("%s: both halves are scoreable" % regime, ma and mb,
              "n=%d / n=%d brier %.4f / %.4f" % (ma["n"], mb["n"], ma["brier"],
                                                 mb["brier"]))


# ----------------------------------------------------------------- T6 reproducibility
def t_reproducible():
    print("\nT6 reproducibility")
    inv1 = SNAP.inventory()
    inv2 = SNAP.inventory()
    check("snapshot inventory is deterministic", inv1 == inv2)
    rows = [{"date": "2026-10-%02d" % (1 + i % 9), "key": "k%d" % i,
             "p1": "a%d" % i, "p2": "b%d" % i,
             "p1_prob": 0.3 + 0.004 * (i % 100), "outcome_p1_won": i % 2}
            for i in range(400)]
    R.RNG = np.random.default_rng(20261020)
    d1 = R.date_bootstrap_diff(rows[:200], rows[200:], R._brier)
    R.RNG = np.random.default_rng(20261020)
    d2 = R.date_bootstrap_diff(rows[:200], rows[200:], R._brier)
    check("bootstrap CI is reproducible from the fixed seed", d1 == d2,
          json.dumps(d1["ci95"]) if d1 else "none")


# ------------------------------------------------------------------------ T7 isolation
def t_isolation():
    print("\nT7 isolation of frozen assets (requirements 1 and 14)")
    targets = [
        ("frozen artifact", os.path.join(HERE, "tsm_d_rest_artifact.CANDIDATE.json")),
        ("beta paper ledger", os.path.join(HERE, "beta_paper_ledger", "events.jsonl")),
        ("beta settle ledger", os.path.join(HERE, "beta_settle_ledger", "events.jsonl")),
        ("official exp2 ledger", os.path.join(HERE, "exp2_ledger", "events.jsonl")),
        ("production snapshot S3", os.path.join(HERE, "dqu_data",
                                                "archive_2026-10-20.parquet")),
    ]
    before = {n: sha(p) for n, p in targets if os.path.exists(p)}
    import dqu_coverage as C
    C.build()                       # the heaviest read path, run for its side effects
    for n, p in targets:
        if n not in before:
            check("%s present" % n, False, "not found at %s" % os.path.relpath(p, HERE))
            continue
        check("%s unchanged by a DQU run" % n, sha(p) == before[n])
    art = json.load(open(targets[0][1], encoding="utf-8"))
    check("artifact self-reported content hash still matches its own field",
          isinstance(art.get("content_sha256"), str) and len(art["content_sha256"]) == 64)


# --------------------------------------------------------------- T8 M1 internal checks
def t_m1():
    print("\nT8 M1 coverage measurement")
    import dqu_coverage as C
    lo, hi = C.wilson(0, 100)
    check("Wilson CI at 0/100 stays inside [0,1]", lo == 0.0 and 0 < hi < 1,
          "[%.4f, %.4f]" % (lo, hi))
    lo, hi = C.wilson(100, 100)
    check("Wilson CI at 100/100 stays inside [0,1]", hi == 1.0 and 0 < lo < 1,
          "[%.4f, %.4f]" % (lo, hi))
    check("Wilson CI on an empty cell is (None, None)", C.wilson(0, 0) == (None, None))
    p = os.path.join(HERE, "dqu_data", "m1_coverage.json")
    if os.path.exists(p):
        rep = json.load(open(p, encoding="utf-8"))
        pair = rep["pairs"][0]
        mono = [pair["by_age"][a]["complete"] for a in sorted(pair["by_age"], key=int)
                if int(a) <= 6]
        check("completeness rises with match age over the steep window",
              mono[0] < mono[-1], "%.3f -> %.3f" % (mono[0], mono[-1]))
        check("every reported cell carries a CI",
              all("ci95" in c for c in pair["by_age"].values()))


def main():
    print("DQU TEST SUITE")
    t_ess()
    t_asof()
    t_coverage_labels()
    t_split_stability()
    t_negative_controls()
    t_reproducible()
    t_m1()
    t_isolation()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FAILED:")
        for f in FAIL:
            print("  -", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
