"""DQU M2 — per-fixture data-quality features, computed as of a prediction date.

Every feature here is computed from ONE genuine archive snapshot, using only rows dated
strictly before the prediction date. Nothing is imputed from an average curve and nothing
is read from a later capture (owner requirements 7 and 8).

THREE KINDS OF FEATURE, kept apart on purpose (requirement 3). Mixing them is how a
retrospective quantity ends up on a live card:

  measured_asof   A fact about the snapshot in hand. "This snapshot holds 14 clay matches
                  for this player in the last 52 weeks." Always true of that snapshot,
                  and computable live.
  proxy           An INFERENCE about what the snapshot is missing, from draw logic alone.
                  Computable live. Can be wrong.
  truth_only      Computable only by comparing against a later capture. Ground truth for
                  validating the proxies. NEVER a live feature, and never displayed.

COVERAGE IS NEVER "VERIFIED" (requirement 4). `coverage_state` takes one of:
  known_complete    an independent later capture confirms nothing was missing. Only
                    available retrospectively, so live code can never produce it.
  unknown           the honest default. No evidence either way.
  known_incomplete  the draw proxy or a later capture establishes a missing result.

Read-only: no ledger, no model refit, no feed, no production file.
"""
import collections
import datetime as dt
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tsm_proxy as PX  # noqa: E402

W52 = 364
RECENT_WINDOW = 14          # window for "recent matches" missingness
HALF_LIFE_DAYS = 120.0      # recency decay for effective sample size


def _decay(age_days):
    return 0.5 ** (age_days / HALF_LIFE_DAYS)


def ess(weights):
    """Effective sample size, (sum w)^2 / sum w^2.

    Equals n for equal weights and falls below n as weight concentrates, so 20 matches of
    which 18 are two years old counts for far less than 20 recent ones. Returns 0.0 for an
    empty history rather than NaN, so downstream stratification never silently drops rows.
    """
    s1 = sum(weights)
    s2 = sum(w * w for w in weights)
    return (s1 * s1 / s2) if s2 > 0 else 0.0


def build_player_index(matches, through_date):
    """player -> chronological matches dated strictly before through_date.

    Separate from tsm_proxy.build_player_history because that one carries only what the
    draw proxy needs; this keeps surface too.
    """
    by = collections.defaultdict(list)
    for m in matches:
        if m["date"] >= through_date:
            break                              # matches are date-sorted
        for who, won in ((m["p"], m["pwin"]), (m["r"], 1 - m["pwin"])):
            by[who].append({"date": m["date"], "surface": str(m["surface"]),
                            "key": m["key"], "won": bool(won),
                            "level": str(m["level_raw"])})
    return by


def player_features(slug, surface, D, pindex, sr_n):
    """measured_asof facts about one player, from the snapshot in hand."""
    h = pindex.get(slug) or []
    d0 = dt.date.fromisoformat(D)
    n_all = n_surf = 0
    w_all, w_surf = [], []
    for m in h:
        age = (d0 - dt.date.fromisoformat(m["date"])).days
        if age <= 0 or age > W52:
            continue
        w = _decay(age)
        n_all += 1
        w_all.append(w)
        if str(m["surface"]) == str(surface):
            n_surf += 1
            w_surf.append(w)
    last = h[-1]["date"] if h else None
    return {
        "n_52w": n_all,
        "n_surface_52w": n_surf,
        "ess_52w": round(ess(w_all), 3),
        "ess_surface_52w": round(ess(w_surf), 3),
        "days_since_last_archived_match": (
            (d0 - dt.date.fromisoformat(last)).days if last else None),
        "last_archived_match": last,
        "serve_return_rows": int(sr_n),
        "career_rows_in_snapshot": len(h),
    }


def fixture_features(f, D, pindex, state, hist, trounds, archive_watermark):
    """All three kinds of feature for one fixture. `f` needs p, r, surface, tournament."""
    p, r, surf = f["p"], f["r"], f["surface"]
    a = player_features(p, surf, D, pindex, state.SR.n.get(p, 0))
    b = player_features(r, surf, D, pindex, state.SR.n.get(r, 0))

    risk, rdet = PX.fixture_unresolved(f.get("tournament"), D, p, r, hist, trounds)
    pp = state.SR.point_probs(p, r)
    _, meta = state.A.prob({"p": p, "r": r, "surface": surf})
    d0 = dt.date.fromisoformat(D)
    wm = dt.date.fromisoformat(archive_watermark)

    out = {
        # ---- measured_asof: facts about this snapshot
        "n_surface_52w_min": min(a["n_surface_52w"], b["n_surface_52w"]),
        "n_surface_52w_p1": a["n_surface_52w"], "n_surface_52w_p2": b["n_surface_52w"],
        "ess_surface_52w_min": round(min(a["ess_surface_52w"], b["ess_surface_52w"]), 3),
        "ess_surface_52w_p1": a["ess_surface_52w"],
        "ess_surface_52w_p2": b["ess_surface_52w"],
        "n_52w_min": min(a["n_52w"], b["n_52w"]),
        "ess_52w_min": round(min(a["ess_52w"], b["ess_52w"]), 3),
        "days_since_last_max": max(
            [x for x in (a["days_since_last_archived_match"],
                         b["days_since_last_archived_match"]) if x is not None] or [None]),
        "elo_only": pp is None,
        "serve_return_rows_min": min(a["serve_return_rows"], b["serve_return_rows"]),
        "prior_n_min": int(min(meta["n1"], meta["n2"])),
        "cold_start": bool(min(meta["n1"], meta["n2"]) < 5),
        "archive_age_days": (d0 - wm).days,
        # ---- proxy: inference about what is missing, live-computable, can be wrong
        "missing_result_risk": int(risk),
        "missing_result_flag": bool(risk > 0),
        # ---- coverage, never "verified"
        "coverage_state": "known_incomplete" if risk > 0 else "unknown",
        "_detail": {"p1": a, "p2": b, "risk": rdet},
    }
    return out


FEATURE_KIND = {
    "n_surface_52w_min": "measured_asof", "n_surface_52w_p1": "measured_asof",
    "n_surface_52w_p2": "measured_asof", "ess_surface_52w_min": "measured_asof",
    "ess_surface_52w_p1": "measured_asof", "ess_surface_52w_p2": "measured_asof",
    "n_52w_min": "measured_asof", "ess_52w_min": "measured_asof",
    "days_since_last_max": "measured_asof", "elo_only": "measured_asof",
    "serve_return_rows_min": "measured_asof", "prior_n_min": "measured_asof",
    "cold_start": "measured_asof", "archive_age_days": "measured_asof",
    "missing_result_risk": "proxy", "missing_result_flag": "proxy",
    "coverage_state": "proxy",
    "actual_missing_recent": "truth_only", "actual_missing_flag": "truth_only",
}


def actual_missing_recent(f, D, keys_available, recent_by_player):
    """truth_only. How many of each player's matches in the RECENT_WINDOW before D the
    available snapshot did not hold, counted from a later capture. Ground truth for the
    proxy -- never a live feature, never displayed."""
    n = 0
    for who in (f["p"], f["r"]):
        for k in recent_by_player.get(who, ()):
            if k not in keys_available:
                n += 1
    return n
