"""DQU M1 — how incomplete the archive is at the moment we predict.

Measures, from two genuine captures, what fraction of a day's matches were present in the
earlier capture by the time that capture was taken. This is the empirical object the rest
of the system depends on, and it is a MEASUREMENT, never an imputation: M1 reports what a
snapshot did or did not contain. It is deliberately not used to reconstruct individual
historical matches (owner requirement 8) -- M3 uses real snapshots for that.

Limits of two-snapshot evidence, stated up front because they bound every conclusion:

  * Completeness is measured against a LATER capture, not against truth. A match missing
    from both is invisible here, so every figure is an UPPER bound on completeness.
  * One pair gives one observation of the ingest's behaviour. It is not a distribution
    over weeks, and a tournament-calendar effect cannot be separated from a lag effect.
  * At ages beyond (truth.watermark - available.watermark) the comparison is unavailable,
    so the curve is only defined on that window.
  * The curve is per MATCH-DAY, pooled over players. A player-level lag may differ.

Read-only: loads parquet, writes a JSON report, touches no ledger, model or feed.
"""
import collections
import datetime as dt
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dqu_snapshots as SNAP  # noqa: E402

OUT = os.path.join(HERE, "dqu_data", "m1_coverage.json")
MAX_AGE = 21


def wilson(k, n, z=1.96):
    """Wilson score interval -- correct at the 0% and 100% ends, where this data lives."""
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round(max(0.0, (c - r) / d), 4), round(min(1.0, (c + r) / d), 4))


def match_keys(path):
    """-> {match_key: (date, level, surface)} using the SAME dedup as the replay."""
    import pandas as pd
    sys.path.insert(0, HERE)
    import tsm_prospective as P
    df = pd.read_parquet(path, columns=["date", "player_slug", "rival_name", "tournament",
                                        "tournament_level", "surface", "round", "result",
                                        "score"])
    return {m["key"]: (m["date"], str(m["level_raw"]), str(m["surface"]))
            for m in P._pair(df)}


def curve(avail_path, truth_path, watermark):
    """Completeness of `avail` by match age, measured against `truth`."""
    ka = set(match_keys(avail_path))
    kt = match_keys(truth_path)
    W = dt.date.fromisoformat(watermark)
    have, tot = collections.Counter(), collections.Counter()
    hl = collections.defaultdict(collections.Counter)
    tl = collections.defaultdict(collections.Counter)
    hs = collections.defaultdict(collections.Counter)
    ts = collections.defaultdict(collections.Counter)
    for k, (d, lvl, surf) in kt.items():
        try:
            age = (W - dt.date.fromisoformat(d)).days
        except ValueError:
            continue
        if age < 0 or age > MAX_AGE:
            continue
        tot[age] += 1
        tl[lvl][age] += 1
        ts[surf][age] += 1
        if k in ka:
            have[age] += 1
            hl[lvl][age] += 1
            hs[surf][age] += 1

    def cell(h, t):
        lo, hi = wilson(h, t)
        return {"present": h, "final": t,
                "complete": round(h / t, 4) if t else None,
                "ci95": [lo, hi]}

    def strat(hd, td):
        return {g: {str(a): cell(hd[g][a], td[g][a]) for a in sorted(td[g]) if td[g][a]}
                for g in sorted(td)}

    return {"by_age": {str(a): cell(have[a], tot[a]) for a in sorted(tot) if tot[a]},
            "by_level": strat(hl, tl), "by_surface": strat(hs, ts),
            "totals": {"matches_compared": int(sum(tot.values())),
                       "present": int(sum(have.values()))}}


def build():
    inv = SNAP.inventory()
    rep = {
        "module": "DQU-M1/ingestion-coverage",
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "read_only": "loads archive parquet only; no ledger, model, feed or production "
                     "file is read or written",
        "snapshots": inv,
        "evidence_limits": [
            "completeness is measured against a LATER CAPTURE, not against truth, so every "
            "figure is an upper bound: a match absent from both snapshots is invisible here",
            "each pair is ONE observation of the ingest; it is not a distribution over "
            "weeks, and calendar effects cannot be separated from lag effects",
            "the curve is only defined for ages up to the gap between the two watermarks",
            "ages are pooled over players; a per-player lag may differ from the pooled one",
        ],
        "pairs": [],
    }
    for a, b in SNAP.pairs(inv):
        c = curve(a["path"], b["path"], a["watermark"])
        c["available"] = {"label": a["label"], "watermark": a["watermark"],
                          "sha256": a["sha256"]}
        c["truth"] = {"label": b["label"], "watermark": b["watermark"],
                      "sha256": b["sha256"]}
        c["gap_days"] = (dt.date.fromisoformat(b["watermark"])
                         - dt.date.fromisoformat(a["watermark"])).days
        c["defined_for_ages"] = "0..%d" % min(MAX_AGE, c["gap_days"])
        rep["pairs"].append(c)
    return rep


def main():
    rep = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
    for p in rep["pairs"]:
        print("\n=== %s (%s) measured against %s (%s), gap %dd ==="
              % (p["available"]["label"], p["available"]["watermark"],
                 p["truth"]["label"], p["truth"]["watermark"], p["gap_days"]))
        print(" age   present/final   complete        95% CI")
        for a in sorted(p["by_age"], key=int):
            c = p["by_age"][a]
            if int(a) > min(MAX_AGE, p["gap_days"]):
                continue
            print("  %2sd   %5d/%5d      %6.1f%%     [%.1f%%, %.1f%%]"
                  % (a, c["present"], c["final"], 100 * c["complete"],
                     100 * c["ci95"][0], 100 * c["ci95"][1]))
        print(" by level at age 1/3/5 days:")
        for lvl, d in p["by_level"].items():
            cells = []
            for a in ("1", "3", "5"):
                c = d.get(a)
                cells.append("%sd %s" % (a, ("%5.1f%% (n=%d)" % (100 * c["complete"],
                                                                c["final"]))
                                         if c else "   --   "))
            print("   %-14s %s" % (lvl, " | ".join(cells)))
    print("\nwritten", os.path.relpath(OUT, HERE))


if __name__ == "__main__":
    main()
