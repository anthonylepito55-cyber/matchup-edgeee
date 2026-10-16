"""HOW MANY ARCHIVE MATCHES NEVER FINISHED, AND WHAT THEY DO TO MC6 (2026-10-16)

User: "if we added last 5 on the court and saw which games were walkovers and stuff what does it
help mc6".

TennisRatio does NOT mark retirements. Zero rows contain "ret", "w/o" or "def" -- the marker is
stripped and the ROW IS KEPT, so an unfinished match is indistinguishable from a finished one
unless the SCORE SHAPE is inspected. That is why this has gone unnoticed.

An unfinished match is identified structurally, not by a label:
  * zero sets recorded            -> walkover, no tennis played at all
  * a final set that cannot be a completed set. A legitimate set ends 6-0..6-4, 7-5 or 7-6 (or
    the mirror). A match whose LAST set reads 4-1, 3-0 or 2-1 stopped mid-set, which only
    happens on a retirement.
  * a one-set match. Best-of-three has no one-set outcome, so every single-set row is unfinished
    even when that set is legitimate (7-6 then retired).

WHY IT MATTERS TO MC6 SPECIFICALLY -- both of MC6's own terms read these rows:

  h2h margin   35% of MC6's head-to-head term is a games differential. A retirement at 6-1 2-0
               scores +7, i.e. "beat them easily", for one and a bit sets of tennis. This is the
               exact term the user asked for when they said "if the h2h is recent and they beat
               them easily".
  sform        the surface-form residual is (result - what Elo expected). A walkover is a free
               win with no tennis in it and registers as over-performance.

And below MC6: MC3's margin-aware Elo scales K by games margin, MC5's surface L5 and
season-on-surface count the result, and MC2's Elo counts the win.

This script only MEASURES. It changes nothing.

Run: ./venv/bin/python _unfinished_match_audit.py
"""
import re

import numpy as np
import pandas as pd

SRC = "data_cache/tennisratio/all_match_logs.parquet"
F = pd.read_parquet(SRC, columns=["date", "score", "result", "surface", "player_slug",
                                  "rival_slugname"])
s = F["score"].astype(str).fillna("")
print("raw archive rows: %d" % len(F))

SET_RE = re.compile(r"(\d+)\s*-\s*(\d+)")


def legit_set(a, b):
    """A completed set: 6-0..6-4, 7-5, 7-6 (or mirrored)."""
    hi, lo = max(a, b), min(a, b)
    return (hi == 6 and lo <= 4) or (hi == 7 and lo in (5, 6))


def classify(x):
    sets = [(int(a), int(b)) for a, b in SET_RE.findall(str(x))
            if int(a) <= 30 and int(b) <= 30]
    if not sets:
        return "walkover", 0
    if not legit_set(*sets[-1]):
        return "retired_midset", len(sets)
    if len(sets) == 1:
        return "retired_after_set", 1
    return "complete", len(sets)


cls, nsets = zip(*s.map(classify))
F["cls"] = cls
F["nsets"] = nsets
BAR = "=" * 92
print("\n" + BAR)
print("MATCH COMPLETION, by score shape (the source carries no ret/walkover marker)")
print(BAR)
vc = F["cls"].value_counts()
for k in ("complete", "retired_midset", "retired_after_set", "walkover"):
    n = int(vc.get(k, 0))
    print("   %-20s %7d  (%.2f%%)" % (k, n, 100 * n / len(F)))
unf = F["cls"] != "complete"
print("   %-20s %7d  (%.2f%%)" % ("UNFINISHED total", int(unf.sum()), 100 * unf.mean()))

print("\n   examples of each:")
for k in ("walkover", "retired_midset", "retired_after_set"):
    g = F[F["cls"] == k].head(3)
    for _, r in g.iterrows():
        print("      %-18s %-14s %s" % (k, repr(str(r["score"]))[:14], r["result"]))

# ---- what the margin term reads on these rows ----
def margin(x):
    d = 0
    for a, b in SET_RE.findall(str(x)):
        a, b = int(a), int(b)
        if a > 30 or b > 30:
            continue
        d += a - b
    return float(d)


F["mg"] = s.map(margin)
F["won"] = (F["result"].astype(str) == "Win")
# margin from the WINNER's side, which is what the h2h term ends up weighting
F["mg_w"] = np.where(F["won"], F["mg"], -F["mg"])
print("\n" + BAR)
print("WHAT THE 'BEAT THEM EASILY' MARGIN READS, by completion")
print(BAR)
print("   %-20s %7s %10s %10s %10s" % ("", "n", "mean mg", "median", ">= +4 games"))
for k in ("complete", "retired_midset", "retired_after_set", "walkover"):
    g = F[F["cls"] == k]
    if not len(g):
        continue
    print("   %-20s %7d %10.2f %10.1f %9.0f%%"
          % (k, len(g), g["mg_w"].mean(), g["mg_w"].median(), 100 * (g["mg_w"] >= 4).mean()))

print("\n" + BAR)
print("HOW OFTEN AN UNFINISHED MATCH IS READ AS A DOMINANT WIN")
print(BAR)
dom = F[(F["mg_w"] >= 4) & F["won"]]
print("   matches the margin term calls dominant (winner +4 games or more): %d" % len(dom))
bad = dom[dom["cls"] != "complete"]
print("   of those, UNFINISHED: %d (%.2f%%)" % (len(bad), 100 * len(bad) / max(len(dom), 1)))
print("   i.e. roughly 1 in %d 'easy wins' never actually finished"
      % round(max(len(dom), 1) / max(len(bad), 1)))

# ---- recency: are they spread evenly, or concentrated where MC6 looks? ----
F["yr"] = pd.to_datetime(F["date"], errors="coerce").dt.year
print("\n" + BAR)
print("UNFINISHED RATE BY YEAR (MC6's h2h half-life is 365 days, so recent rows weigh most)")
print(BAR)
g = F.dropna(subset=["yr"]).groupby("yr")["cls"].apply(lambda c: 100 * (c != "complete").mean())
for y, v in g.tail(8).items():
    print("   %d   %.2f%% unfinished" % (int(y), v))

# ---- and the ITF question, since that is where the board's dogs live ----
if "tournament_level" in pd.read_parquet(SRC, columns=["tournament_level"]).columns:
    L = pd.read_parquet(SRC, columns=["tournament_level"])["tournament_level"].astype(str).str.lower()
    F["lvl"] = np.where(L.str.contains("challenger"), "challenger",
                        np.where(L.str.contains("future") | L.str.contains("itf"), "itf", "tour"))
    print("\n" + BAR)
    print("UNFINISHED RATE BY LEVEL")
    print(BAR)
    for lv, g2 in F.groupby("lvl"):
        print("   %-12s %7d rows   %.2f%% unfinished" % (lv, len(g2), 100 * (g2["cls"] != "complete").mean()))
print("\n" + BAR)
print("READ: these rows are not labelled anywhere, so every term that reads a score or a result")
print("currently treats them as ordinary matches. The margin column is the one MC6 owns.")
print(BAR)
