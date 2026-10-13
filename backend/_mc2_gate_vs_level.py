"""IS THE MC2 GATE A SERVICE-POINT GATE OR JUST A LEVEL GATE? (2026-10-13)

The shipped gate withholds MC2 marks when the thinner side has under 400 surface service points.
I justified it as input quality -- then found MC2 never reads the TennisRatio stat line at all
(it uses tennis_context only to resolve a name to a slug; Diaz Acosta's own MC2 sample is nS=285,
not 8). So svp_n cannot be measuring MC2's inputs. It must be a proxy, and the obvious candidate
is LEVEL: ITF and challenger players have fewer tracked points, and that is where MC2 is weakest.

This decides which variable is doing the work, by crossing them:

  * if svp_n adds nothing WITHIN level, the gate should be a level filter instead -- simpler,
    better understood, and it would not silently drop well-covered challenger players
  * if level adds nothing WITHIN svp bucket, the gate is right as built and the wording is all
    that needs fixing
  * if both carry signal, keep both and say so

Scored on MC2's own side (back whichever side it is over the market on), forward rows and
backfill reported separately, same as the audit that produced the gate.
"""
import sys

import numpy as np
import pandas as pd

import tennis_context as TC
import tennis_log

L = pd.read_parquet(tennis_log.LOG_PATH)
d = L[L["mc2_p1"].notna() & L["p1_odds"].notna() & L["p2_odds"].notna()
      & L["p1_won"].notna() & (L["settled"] == True)].copy()       # noqa: E712
for c in ("surface_bad", "inplay_suspect"):
    if c in d.columns:
        d = d[~d[c].fillna(False).astype(bool)]
d = d.reset_index(drop=True)
rc = (d["mc2_recon"].fillna(False).astype(bool).to_numpy()
      if "mc2_recon" in d.columns else np.zeros(len(d), bool))
FWD = ~rc
print("settled MC2 rows: %d (forward %d)" % (len(d), int(FWD.sum())))


def svp(name, surface, asof):
    try:
        c = TC.context_asof(str(name), surface, asof) or {}
    except Exception:                                              # noqa: BLE001
        return None
    v = (c.get("surface_stats") or {}).get("svp_n")
    return float(v) if v is not None else None


vals = []
for i, r in d.iterrows():
    day = str(r["date"])[:10]
    sf = r.get("surface")
    a, b = svp(r["player_1"], sf, day), svp(r["player_2"], sf, day)
    vals.append(min(a, b) if (a is not None and b is not None) else None)
    if (i + 1) % 400 == 0:
        print("   %d/%d" % (i + 1, len(d)))
        sys.stdout.flush()
d["svp_min"] = vals
have = d["svp_min"].notna().to_numpy()
vmin = d["svp_min"].fillna(-1).to_numpy()

lg = d["league"].astype(str)
lvl = np.where(lg.str.startswith("itf"), "itf",
               np.where(lg.str.contains("challenger"), "chall", "tour"))


def dec(a):
    a = float(a)
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


o1 = d["p1_odds"].map(dec).to_numpy()
o2 = d["p2_odds"].map(dec).to_numpy()
mk1 = (1 / o1) / ((1 / o1) + (1 / o2))
pv = d["mc2_p1"].astype(float).to_numpy()
won1 = d["p1_won"].astype(bool).to_numpy()
fav1 = mk1 >= 0.5
over = np.where(fav1, pv, 1 - pv) - np.where(fav1, mk1, 1 - mk1)
favwon = np.where(fav1, won1, ~won1)
favodd = np.where(fav1, o1, o2)
dogodd = np.where(fav1, o2, o1)
pnl = np.where(over > 0,
               np.where(favwon, favodd - 1, -1.0),
               np.where(~favwon, dogodd - 1, -1.0))


def f(m):
    n = int(m.sum())
    if not n:
        return "%-22s" % "      --"
    p = pnl[m]
    se = 100 * p.std() / np.sqrt(n) if n > 1 else float("nan")
    return "n=%-4d %+7.2f%% +/-%4.1f" % (n, 100 * p.mean(), se)


def two(lab, m):
    print("   %-30s %-24s %s" % (lab, f(m), f(m & FWD)))


BAR = "=" * 86
print("\ncoverage: svp on both sides for %d of %d rows" % (int(have.sum()), len(d)))
print("level mix: " + ", ".join("%s %d" % (k, int((lvl == k).sum())) for k in ("tour", "chall", "itf")))

print("\n" + BAR)
print("LEVEL ALONE -- MC2's own side")
print(BAR)
print("   %-30s %-24s %s" % ("cell", "ALL rows", "FORWARD"))
for k in ("tour", "chall", "itf"):
    two(k, lvl == k)
two("everything", np.ones(len(d), bool))

print("\n" + BAR)
print("SERVICE POINTS ALONE -- the shipped gate")
print(BAR)
print("   %-30s %-24s %s" % ("cell", "ALL rows", "FORWARD"))
two("svp < 400 (gated out)", have & (vmin < 400))
two("svp >= 400 (kept)", have & (vmin >= 400))

print("\n" + BAR)
print("CROSSED -- does svp still separate INSIDE each level?")
print(BAR)
print("   %-30s %-24s %s" % ("cell", "ALL rows", "FORWARD"))
for k in ("tour", "chall", "itf"):
    print("   -- %s --" % k)
    two("  svp < 400", have & (vmin < 400) & (lvl == k))
    two("  svp >= 400", have & (vmin >= 400) & (lvl == k))

print("\n" + BAR)
print("CROSSED THE OTHER WAY -- does level still separate INSIDE each svp bucket?")
print(BAR)
print("   %-30s %-24s %s" % ("cell", "ALL rows", "FORWARD"))
for lab, q in (("svp < 400", have & (vmin < 400)), ("svp >= 400", have & (vmin >= 400))):
    print("   -- %s --" % lab)
    for k in ("tour", "chall", "itf"):
        two("  %s" % k, q & (lvl == k))

print("\n" + BAR)
print("HOW CONFOUNDED ARE THEY? median svp by level, and the share each level is gated")
print(BAR)
for k in ("tour", "chall", "itf"):
    m = have & (lvl == k)
    if not m.sum():
        continue
    print("   %-8s median svp %6.0f   gated %3.0f%% of its rows   (n=%d)"
          % (k, np.median(vmin[m]), 100 * (vmin[m] < 400).mean(), int(m.sum())))

print("\n" + BAR)
print("WHAT THE GATE WOULD COST/SAVE vs a plain level filter, on MC2's own side")
print(BAR)
for lab, keep in (("keep all", np.ones(len(d), bool)),
                  ("keep svp >= 400", have & (vmin >= 400)),
                  ("keep tour only", lvl == "tour"),
                  ("keep tour+chall", lvl != "itf"),
                  ("keep svp>=400 AND not itf", have & (vmin >= 400) & (lvl != "itf")),
                  ("keep svp>=400 OR tour", (have & (vmin >= 400)) | (lvl == "tour"))):
    two(lab, keep)
