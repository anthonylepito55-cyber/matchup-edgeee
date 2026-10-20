"""Does the player whose recent form is further above his OWN baseline win more?

The card line shows, per player, `L10 70% (+17 vs usual)`: the last-10 win rate on this
court, and how far that sits above or below that player's own 52-week win rate on the same
court. The claim under test is that when those two deltas diverge -- +17 against -12 -- the
player on the better side usually wins, whoever is favourite.

Computed strictly as-of: every window for a match on day D uses only that player's matches
dated before D, on the same surface, taken from a genuine archive capture. The current
match is scored only after both players' numbers are read, so a match never informs its own
features.

Read-only. No ledger, no model, no production file.
"""
import argparse
import collections
import datetime as dt
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

ARCHIVE = os.path.join(HERE, "dqu_captures", "archive_2026-10-20_6197deff194c.parquet")
W52 = 364
L10 = 10
MIN_BASE = 10          # matches on this court in 52 weeks before a baseline means anything


def wilson(k, n, z=1.96):
    if not n:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def load(path, since):
    import pandas as pd
    import tsm_prospective as P
    df = pd.read_parquet(path, columns=["date", "player_slug", "rival_name", "tournament",
                                        "tournament_level", "surface", "round", "result",
                                        "score"])
    ms = [m for m in P._pair(df) if m["date"] >= since]
    ms.sort(key=lambda m: m["date"])
    return ms


def run(since, level_filter=None):
    ms = load(ARCHIVE, since)
    hist = collections.defaultdict(list)      # (slug, surface) -> [(date, won)]
    rows = []
    for m in ms:
        surf = str(m["surface"])
        d = dt.date.fromisoformat(m["date"])
        feats = {}
        ok = True
        for who, won in ((m["p"], m["pwin"]), (m["r"], 1 - m["pwin"])):
            h = hist[(who, surf)]
            recent = [w for (dd, w) in h if 0 < (d - dd).days <= W52]
            if len(recent) < MIN_BASE:
                ok = False
                break
            base = sum(recent) / len(recent)
            last = [w for (dd, w) in h if dd < d][-L10:]
            if len(last) < L10:
                ok = False
                break
            l10 = sum(last) / len(last)
            feats[who] = {"base": base, "l10": l10, "form": l10 - base, "n52": len(recent)}
        # the current result enters history only AFTER both players were read
        for who, won in ((m["p"], m["pwin"]), (m["r"], 1 - m["pwin"])):
            hist[(who, surf)].append((d, won))
        if not ok:
            continue
        if level_filter and str(m["level_raw"]) not in level_filter:
            continue
        a, b = feats[m["p"]], feats[m["r"]]
        rows.append({"date": m["date"], "level": str(m["level_raw"]), "surface": surf,
                     "p": m["p"], "r": m["r"], "pwin": int(m["pwin"]),
                     "form_p": a["form"], "form_r": b["form"],
                     "gap": a["form"] - b["form"],
                     "base_p": a["base"], "base_r": b["base"],
                     "l10_p": a["l10"], "l10_r": b["l10"],
                     "base_gap": a["base"] - b["base"]})
    return rows


def rate(rows, pick):
    """pick(row) -> 1 if it picks player p, 2 if player r, None to skip."""
    n = w = 0
    for x in rows:
        s = pick(x)
        if s is None:
            continue
        n += 1
        w += int((s == 1) == (x["pwin"] == 1))
    lo, hi = wilson(w, n)
    return {"n": n, "wins": w,
            "win_rate": round(w / n, 4) if n else None,
            "ci95": [round(lo, 4), round(hi, 4)] if n else None}


def better_form(x, minimum=0.0):
    if abs(x["gap"]) < minimum:
        return None
    return 1 if x["gap"] > 0 else 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2024-01-01")
    a = ap.parse_args()
    rows = run(a.since)
    print("as-of rows with both players fully measurable, since %s: %d" % (a.since, len(rows)))
    print("date range %s .. %s" % (rows[0]["date"], rows[-1]["date"]))

    print("\nA. BACK THE BETTER FORM DELTA, by how far the two deltas diverge")
    print("   gap        n       win rate   95% CI")
    for lo, hi, lab in ((0.0, 9, "any"), (0.10, 9, ">= 10pt"), (0.20, 9, ">= 20pt"),
                        (0.30, 9, ">= 30pt"), (0.40, 9, ">= 40pt"), (0.50, 9, ">= 50pt")):
        r = rate(rows, lambda x, lo=lo: better_form(x, lo))
        if r["n"] < 50:
            continue
        print("   %-9s %-7d %6.1f%%     [%.1f%%, %.1f%%]"
              % (lab, r["n"], 100 * r["win_rate"], 100 * r["ci95"][0], 100 * r["ci95"][1]))

    print("\nB. CONTROL: back the better 52-WEEK BASELINE instead (class, not form)")
    for lo, lab in ((0.0, "any"), (0.10, ">= 10pt"), (0.20, ">= 20pt")):
        r = rate(rows, lambda x, lo=lo: None if abs(x["base_gap"]) < lo
                 else (1 if x["base_gap"] > 0 else 2))
        if r["n"] < 50:
            continue
        print("   %-9s %-7d %6.1f%%     [%.1f%%, %.1f%%]"
              % (lab, r["n"], 100 * r["win_rate"], 100 * r["ci95"][0], 100 * r["ci95"][1]))

    print("\nC. THE KEY TEST — form delta WHEN THE BASELINE DISAGREES")
    print("   (the better-form player is the WEAKER player on 52-week record)")
    for lo, lab in ((0.20, "gap >= 20pt"), (0.30, "gap >= 30pt"), (0.40, "gap >= 40pt")):
        sub = [x for x in rows if abs(x["gap"]) >= lo
               and (x["gap"] > 0) != (x["base_gap"] > 0)]
        if len(sub) < 50:
            print("   %-13s n=%d (too small)" % (lab, len(sub)))
            continue
        r = rate(sub, lambda x: better_form(x, 0.0))
        print("   %-13s %-6d %6.1f%%     [%.1f%%, %.1f%%]"
              % (lab, r["n"], 100 * r["win_rate"], 100 * r["ci95"][0], 100 * r["ci95"][1]))

    print("\nD. SAME, split by level (gap >= 20pt, any baseline)")
    for lv in sorted({x["level"] for x in rows}):
        sub = [x for x in rows if x["level"] == lv and abs(x["gap"]) >= 0.20]
        if len(sub) < 80:
            continue
        r = rate(sub, lambda x: better_form(x, 0.0))
        print("   %-14s %-6d %6.1f%%     [%.1f%%, %.1f%%]"
              % (lv, r["n"], 100 * r["win_rate"], 100 * r["ci95"][0], 100 * r["ci95"][1]))

    out = os.path.join(HERE, "dqu_data", "form_delta.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"since": a.since, "n": len(rows),
                   "rows": [{k: x[k] for k in ("date", "level", "surface", "gap",
                                               "base_gap", "pwin")} for x in rows]}, fh)
    print("\nwritten", os.path.relpath(out, HERE))


if __name__ == "__main__":
    main()
