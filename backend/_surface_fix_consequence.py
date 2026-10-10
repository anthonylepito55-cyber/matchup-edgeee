"""WHAT THE WRONG COURTS COST (2026-10-09, user "so i can see what i would have chosen if it
was the correct court"). Reads the served history payload's surface_fix blocks and scores, flat
1u at the frozen pre-match price, the marks that fired on the court we HAD against the marks
that would have fired on the court the match was really played on.

Read this as an audit of 150 specific mislabelled games, NOT as a validated edge: the sample is
selected (every row is one we got wrong), small, and the right-court marks were never actually
bet. The honest use is to see how often the court changed the pick and whether the corrected
picks were pointing at the winner.
"""
import io
import json
import os
import urllib.request

import pandas as pd

H = {"X-Dashboard-Password": os.environ.get("DASH_PW", "")}
req = urllib.request.Request("http://127.0.0.1/api/tennis/history?limit_dates=60", headers=H)
D = json.loads(urllib.request.urlopen(req, timeout=600).read())
rows = [m for day in D.get("dates", []) for m in day["matches"]]
FX = [m for m in rows if m.get("surface_fix")]
out = io.StringIO()


def w(s=""):
    print(s)
    out.write(s + "\n")


def dec(am):
    if am is None:
        return None
    am = float(am)
    return 1 + (am / 100.0 if am > 0 else 100.0 / abs(am))


w(f"wrong-court rows in the served history: {len(FX)}")
w(f"  the court changed a read on: {sum(1 for m in FX if m['surface_fix']['changed'])}")
w(f"  a pick was actually frozen on: {sum(1 for m in FX if m['surface_fix']['frozen'])}"
  f"  (the rest are September rows from before the model columns were logged)")

# ---- how often each model flipped ---------------------------------------------------------
w("\n=== how often the correct court flipped a model to the other player ===")
for k in ("A", "B", "C", "gray", "D"):
    n = sum(1 for m in FX if m["surface_fix"]["right"]["models"].get(k)
            and m["surface_fix"]["wrong"]["models"].get(k))
    f = sum(1 for m in FX if k in m["surface_fix"]["flips"])
    w(f"  {k:5s} flipped on {f:3d} of {n:3d} rows ({100 * f / n:.0f}%)" if n else f"  {k}: none")

# ---- did the right court point at the winner more often? ----------------------------------
w("\n=== which court's read was actually right (model picked the match winner) ===")
for k in ("A", "B", "C", "gray", "D"):
    rr = [m["surface_fix"]["right"]["models"][k] for m in FX if m["surface_fix"]["right"]["models"].get(k)]
    ww = [m["surface_fix"]["wrong"]["models"][k] for m in FX if m["surface_fix"]["wrong"]["models"].get(k)]
    if not rr or not ww:
        continue
    w(f"  {k:5s} right court {100 * sum(x['hit'] for x in rr) / len(rr):5.1f}% (n={len(rr)})"
      f"   |  wrong court {100 * sum(x['hit'] for x in ww) / len(ww):5.1f}% (n={len(ww)})")

# ---- the marks: flat 1u at the frozen price -----------------------------------------------
w("\n=== the MARKS, flat 1u at the frozen pre-match price ===")
for tag in ("wrong", "right"):
    bets, lbl = [], {}
    for m in FX:
        o1, o2 = m.get("p1_odds"), m.get("p2_odds")
        for g in (m["surface_fix"][tag]["signals"] or []):
            if g.get("watch"):
                continue
            d = dec(o1 if g["side"] == 1 else o2)
            if d is None:
                continue
            v = (d - 1.0) if g["hit"] else -1.0
            bets.append(v)
            lbl.setdefault(g["label"], []).append(v)
    if not bets:
        w(f"  {tag:5s} court: no marks fired at all")
        continue
    hit = sum(1 for m in FX for g in (m["surface_fix"][tag]["signals"] or []) if not g.get("watch") and g["hit"])
    w(f"  {tag:5s} court: {len(bets)} marks | {hit}-{len(bets) - hit} | "
      f"flat ROI {100 * sum(bets) / len(bets):+.1f}% ({sum(bets):+.1f}u)")
    for L, v in sorted(lbl.items(), key=lambda x: -len(x[1]))[:8]:
        w(f"      {L:28s} n={len(v):3d}  ROI {100 * sum(v) / len(v):+6.1f}%")

# ---- the 40 rows where a pick was genuinely on screen -------------------------------------
w("\n=== only the rows where a pick was genuinely frozen on the card that day ===")
FZ = [m for m in FX if m["surface_fix"]["frozen"]]
for tag in ("wrong", "right"):
    bets = []
    for m in FZ:
        o1, o2 = m.get("p1_odds"), m.get("p2_odds")
        src = (m["signals"] or []) if tag == "wrong" else (m["surface_fix"]["right"]["signals"] or [])
        for g in src:
            if g.get("watch"):
                continue
            d = dec(o1 if g["side"] == 1 else o2)
            if d is not None:
                bets.append((d - 1.0) if g["hit"] else -1.0)
    hit = sum(1 for v in bets if v > 0)
    w(f"  {tag:5s} court: {len(bets)} marks | {hit}-{len(bets) - hit} | "
      f"flat ROI {100 * sum(bets) / len(bets):+.1f}% ({sum(bets):+.1f}u)" if bets else f"  {tag}: none")

# ---- biggest individual changes -----------------------------------------------------------
w("\n=== the ten biggest swings (Model C) ===")
sw = []
for m in FX:
    a = m["surface_fix"]["right"]["models"].get("C")
    b = m["surface_fix"]["wrong"]["models"].get("C")
    if a and b:
        sw.append((abs(a["p1_pct"] - b["p1_pct"]), m, a, b))
for d, m, a, b in sorted(sw, key=lambda x: -x[0])[:10]:
    fxs = m["surface_fix"]
    win = m["p1"] if m["p1_won"] else m["p2"]
    w(f"  {m['p1']} vs {m['p2']} ({fxs['logged']}->{fxs['true']}): "
      f"C {b['p1_pct']}% -> {a['p1_pct']}% ({d:.1f}pt"
      f"{', FLIPS' if a['side'] != b['side'] else ''}) | won: {win}")
io.open("_surface_fix_consequence.out", "w", encoding="utf-8").write(out.getvalue())
print("\nwrote _surface_fix_consequence.out")
