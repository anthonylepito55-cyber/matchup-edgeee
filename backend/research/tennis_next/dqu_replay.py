"""DQU M3 — chronological out-of-sample predictions on GENUINE as-of snapshots.

For a prediction date D the model sees exactly one real archive capture whose watermark
predates D. Nothing is reconstructed, nothing is imputed from M1's curve, and today's
completed archive is used ONLY to supply the outcome and the truth-only diagnostics
(owner requirements 7 and 8).

WHAT THIS CAN AND CANNOT CLAIM, stated here because it bounds every number downstream.
Only two full-breadth capture epochs exist on disk, 21 days apart. So:

  FAITHFUL cells -- the archive's staleness matches what a live pass actually runs with
  (<= 3 days, the live FRESH_DAYS). These are the only rows that justify a statement about
  live behaviour. They are few.

  SENSITIVITY cells -- D is further past the watermark than a live pass would ever be, so
  the archive is artificially stale. Useful for seeing how error moves as data degrades,
  and explicitly NOT evidence about live accuracy. Labelled on every row.

The split is recorded per row as `regime`, and M4 reports the two separately rather than
pooling them.

The frozen artifact is loaded and its estimators rebuilt; no coefficient, calibrator or
threshold is touched, no ledger is written, no feed is contacted.
"""
import collections
import datetime as dt
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dqu_features as F  # noqa: E402
import dqu_snapshots as SNAP  # noqa: E402
import tsm_artifact_probe as A  # noqa: E402
import tsm_prospective as P  # noqa: E402
import tsm_proxy as PX  # noqa: E402
import tsm_state_probe as Q  # noqa: E402
from tsm_c import p_match  # noqa: E402
from tsm_c_v2 import BA, BB, BC  # noqa: E402
from tsm_d import FEATS  # noqa: E402

ARTIFACT = os.path.join(HERE, "tsm_d_rest_artifact.CANDIDATE.json")
OUT = os.path.join(HERE, "dqu_data", "m3_replay.json")
FAITHFUL_MAX_STALE = 3      # matches the live FRESH_DAYS regime


def tier_of(level, tournament):
    t = str(tournament)
    if level == "Futures":
        return "ITF-women" if t[:1].upper() == "W" else "ITF-men"
    if level == "Challengers":
        return "Challenger-women" if t[:1].upper() == "W" else "Challenger"
    return str(level)


def score_one(st, m, mdl, iso, mu, sd):
    """The frozen D_rest probability for player `p` of match m. Pure."""
    d = dt.date.fromisoformat(m["date"])
    pA, _ = st.A.prob({"p": m["p"], "r": m["r"], "surface": m["surface"]})
    f1, f2 = st.FR.feats(m["p"], d), st.FR.feats(m["r"], d)
    feats = {k: f1[k] - f2[k] for k in FEATS}
    pp = st.SR.point_probs(m["p"], m["r"])
    pM = p_match(pp[0], pp[1], False) if pp is not None else None
    pC = pA
    if pM is not None:
        z = BC + BA * np.log(pA / (1 - pA)) + BB * np.log(pM / (1 - pM))
        pC = 1.0 / (1.0 + np.exp(-z))
    X = np.array([[np.log(pC / (1 - pC))]
                  + [(feats[c] - mu[c]) / sd[c] for c in P.REST_COLS]])
    return float(np.clip(iso.predict(mdl.predict_proba(X)[:, 1]), 1e-9, 1 - 1e-9)[0])


def run(available, truth, dates=None, verbose=True):
    art = json.load(open(ARTIFACT, encoding="utf-8"))
    mdl, iso = A.rebuild_estimators(art)
    mu = art["fitted"]["standardization_mu"]
    sd = art["fitted"]["standardization_sd"]

    ma, sa, amax = Q.load_inputs(available["path"])
    mt, _, tmax = Q.load_inputs(truth["path"])
    keys_avail = {m["key"] for m in ma}
    wm = available["watermark"]

    # the model's view: one real snapshot, fully absorbed. Because the snapshot holds
    # nothing after its own watermark, advancing it to D is exactly what a pass holding
    # this capture on day D would have had.
    #
    # The player index and the draw-proxy history are built ONCE over the whole snapshot
    # rather than per date. That is only equivalent to an as-of build while the snapshot
    # contains nothing on or after the earliest prediction date, so assert it rather than
    # trust it -- a snapshot that ever violated this would leak future matches into the
    # proxy without changing a single visible number.
    snap_max = max(m["date"] for m in ma)
    pindex_all = F.build_player_index(ma, "9999-12-31")
    hist, trounds = PX.build_player_history(ma, "9999-12-31")

    if dates is None:
        d0 = dt.date.fromisoformat(wm) + dt.timedelta(days=1)
        d1 = dt.date.fromisoformat(truth["watermark"])
        # inclusive of the truth watermark: matches on that day are real and give the
        # freshest faithful cell available, at the cost of that day being partly unsettled
        dates = [(d0 + dt.timedelta(days=i)).isoformat()
                 for i in range((d1 - d0).days + 1)]

    if dates and snap_max >= min(dates):
        raise SystemExit(
            "as-of purity violated: snapshot %s holds matches up to %s but the earliest "
            "prediction date is %s" % (available["label"], snap_max, min(dates)))

    by_date = collections.defaultdict(list)
    for m in mt:
        by_date[m["date"]].append(m)

    rows = []
    for D in dates:
        pop = [m for m in by_date.get(D, ()) if m["level_raw"] != "Grand Slams"]
        if not pop:
            continue
        st = Q.FwdState().advance(ma, sa, D)
        lo = (dt.date.fromisoformat(D) - dt.timedelta(days=F.RECENT_WINDOW)).isoformat()
        recent = collections.defaultdict(list)
        for m in mt:
            if lo <= m["date"] < D:
                recent[m["p"]].append(m["key"])
                recent[m["r"]].append(m["key"])
        stale = (dt.date.fromisoformat(D) - dt.date.fromisoformat(wm)).days
        for m in pop:
            feats = F.fixture_features(m, D, pindex_all, st, hist, trounds, wm)
            p1 = score_one(st, m, mdl, iso, mu, sd)
            am = F.actual_missing_recent(m, D, keys_avail, recent)
            feats.pop("_detail", None)
            rows.append({
                "date": D, "key": m["key"], "p1": m["p"], "p2": m["r"],
                "surface": str(m["surface"]), "level": str(m["level_raw"]),
                "tier": tier_of(m["level_raw"], m["tournament"]),
                "p1_prob": round(p1, 6),
                "confidence": round(max(p1, 1 - p1), 6),
                "band": P._band(max(p1, 1 - p1)),
                "outcome_p1_won": int(m["pwin"]),
                "correct": int((p1 >= 0.5) == bool(m["pwin"])),
                "archive_stale_days": stale,
                "regime": "faithful" if stale <= FAITHFUL_MAX_STALE else "sensitivity",
                "actual_missing_recent": am,
                "actual_missing_flag": bool(am > 0),
                **feats})
        if verbose:
            print("  %s  n=%-4d stale=%-3dd regime=%s"
                  % (D, len(pop), stale,
                     "faithful" if stale <= FAITHFUL_MAX_STALE else "sensitivity"))
    return {
        "available": {k: available[k] for k in ("label", "watermark", "sha256")},
        "truth": {k: truth[k] for k in ("label", "watermark", "sha256")},
        "artifact_content_sha256": art["content_sha256"],
        "rows": rows}


def main():
    inv = SNAP.inventory()
    byl = {s["label"]: s for s in inv}
    rep = {
        "module": "DQU-M3/chronological-asof-replay",
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "read_only": "frozen artifact loaded and rebuilt, never refit; no ledger written; "
                     "no feed contacted; no production file touched",
        "requirement_7_8": "the model's view is a single GENUINE capture per run; nothing "
                           "is reconstructed from an average completeness curve; the later "
                           "capture supplies outcomes and truth-only diagnostics only",
        "runs": []}
    # S0 -> S3 gives the long window (1..21 days stale, mostly sensitivity).
    # S2 -> S3 gives one genuinely fresh day (1 day stale, faithful).
    for av, tr in (("S0", "S3"), ("S2", "S3")):
        print("\n=== replay %s -> %s ===" % (av, tr))
        rep["runs"].append(run(byl[av], byl[tr]))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rep, fh)
    allr = [r for run_ in rep["runs"] for r in run_["rows"]]
    fa = [r for r in allr if r["regime"] == "faithful"]
    print("\ntotal rows %d  | faithful %d | sensitivity %d"
          % (len(allr), len(fa), len(allr) - len(fa)))
    print("written", os.path.relpath(OUT, HERE))


if __name__ == "__main__":
    main()
