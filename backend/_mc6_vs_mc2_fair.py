"""THE FAIR FIGHT: MC2 AND MC6 BOTH RECONSTRUCTED AS-OF (2026-10-16)

The comparison everything else in this thread has been circling. On MC6's 646 reconstructed rows,
MC2 was a genuine forward value on 633 of them -- so MC6 was replaying those matches with correct
as-of ratings while MC2's number came from states up to four days stale. That input-quality gap
is the right size and shape to have manufactured MC6's entire apparent lead:

    MC6-recon rows     MC2 +13.87% /298    MC6 +22.47% /289    lead +8.60pt
    MC6-forward rows   MC2  -9.86% /64     MC6  -8.09% /59     lead +1.76pt

_mc2_asof_for_mc6rows.py re-prices MC2 as-of on exactly those rows. This scores the two heads
against each other on identical matches with identical input quality, under the tab's own rule.

If MC6's lead survives, it is a real difference between the heads and worth acting on with ~300
bets behind it rather than 59. If the lead collapses toward the forward figure, the replay was
the story and MC2 stays -- which is what the forward sample already hints at.

Also reported: MC2 as-of against MC2 forward on the same rows, which measures the staleness
penalty directly and is interesting independently of MC6.

Run: ./venv/bin/python _mc6_vs_mc2_fair.py
"""
import math

import numpy as np
import pandas as pd

import tennis_log

ASOF = "data_cache/_mc2_asof_mc6rows.parquet"
a = pd.read_parquet(ASOF)
log = pd.read_parquet(tennis_log.LOG_PATH)
print("as-of re-priced rows: %d   columns: %s" % (len(a), list(a.columns)))

# the re-pricer stores the log index in "i"
pcol = next((c for c in ("p1_prob", "mc2_p1", "p") if c in a.columns), None)
assert pcol, "no probability column in %s" % ASOF
a = a[a[pcol].notna()]
m = log.loc[a["i"].to_numpy()].copy()
m["mc2_asof"] = a[pcol].to_numpy()
bad = np.zeros(len(m), bool)
for c in ("surface_bad", "resolve_bad", "inplay_suspect", "void"):
    if c in m.columns:
        bad |= m[c].fillna(False).astype(bool).to_numpy()
m = m[~bad]
m = m[m.p1_won.notna() & m.p1_odds.notna() & m.p2_odds.notna()
      & m.mc6_p1.notna() & m.mc2_p1.notna()].reset_index(drop=True)
print("usable rows: %d  (%s .. %s)" % (len(m), str(m.date.min())[:10], str(m.date.max())[:10]))

o1 = pd.to_numeric(m.p1_odds, errors="coerce").to_numpy(float)
o2 = pd.to_numeric(m.p2_odds, errors="coerce").to_numpy(float)
dc = lambda o: np.where(o > 0, 1 + o / 100.0, 1 + 100.0 / np.abs(o))
D1, D2 = dc(o1), dc(o2)
mk1 = (1 / D1) / ((1 / D1) + (1 / D2))
Y1 = m.p1_won.astype(bool).to_numpy()
itfm = (m.league.astype(str).str.lower() == "itf_men").to_numpy()
isw = m.league.astype(str).str.lower().str.contains("wta|itf_women", regex=True).to_numpy()
dog1 = mk1 < 0.5
mkf = np.maximum(mk1, 1 - mk1)
dam = np.where(dog1, o1, o2)
dod = np.where(dog1, D1, D2)
dwon = np.where(dog1, Y1, ~Y1)
dpnl = np.where(dwon, dod - 1, -1.0)
favAm = np.where(dog1, o2, o1)
favDec = np.where(dog1, D2, D1)
favWon = np.where(dog1, ~Y1, Y1)
fpnl = np.where(favWon, favDec - 1, -1.0)
HEADS = {"MC2 live (stale)": m.mc2_p1.to_numpy(float),
         "MC2 as-of (fair)": m.mc2_asof.to_numpy(float),
         "MC6 as-of": m.mc6_p1.to_numpy(float)}
OV = {k: np.where(dog1, 1 - p, p) - mkf for k, p in HEADS.items()}
DOGOK = (dam >= 100) & (dam <= 300) & ~itfm
FAVOK = (favAm <= -100) & (favAm >= -200)
print("mean |MC2 as-of - MC2 live|: %.4f   moved >2pt on %d rows (%.0f%%)"
      % (np.abs(HEADS["MC2 as-of (fair)"] - HEADS["MC2 live (stale)"]).mean(),
         int((np.abs(HEADS["MC2 as-of (fair)"] - HEADS["MC2 live (stale)"]) > 0.02).sum()),
         100 * (np.abs(HEADS["MC2 as-of (fair)"] - HEADS["MC2 live (stale)"]) > 0.02).mean()))


def rep(mask, pnl, won, lab, ind="   "):
    n = int(mask.sum())
    if n == 0:
        print("%s%-20s n=0" % (ind, lab)); return
    w = int(won[mask].sum())
    r = pnl[mask].mean()
    t = ""
    if 0 < w < n:
        g = (r * n + (n - w)) / w
        v = (w * g * g + (n - w)) / n - r * r
        if v > 0:
            t = "  t %5.2f" % (r / (math.sqrt(v) / math.sqrt(n)))
    print("%s%-20s %8s  n=%-4d hit %5.1f%%  ROI %+7.2f%%  $%+8.0f%s"
          % (ind, lab, "%d-%d" % (w, n - w), n, 100 * w / n, 100 * r, 25 * pnl[mask].sum(), t))


BAR = "=" * 92
for th, nm in ((0.04, "4pt"), (0.06, "6pt")):
    print("\n" + BAR)
    print("DOGS at %s over, +100..+300, no ITF men" % nm)
    print(BAR)
    for k in HEADS:
        rep(DOGOK & (OV[k] <= -th), dpnl, dwon, k)
print("\n" + BAR)
print("FAVOURITES at 4pt, -100..-200")
print(BAR)
for k in HEADS:
    rep(FAVOK & (OV[k] >= 0.04), fpnl, favWon, k)
print("\n" + BAR)
print("THE TAB'S RULE: 6pt dogs + 4pt favs")
print(BAR)
for k in HEADS:
    dm = DOGOK & (OV[k] <= -0.06)
    fm = FAVOK & (OV[k] >= 0.04)
    n = int(dm.sum() + fm.sum())
    if not n:
        print("   %-20s n=0" % k); continue
    pl = dpnl[dm].sum() + fpnl[fm].sum()
    w = int(dwon[dm].sum() + favWon[fm].sum())
    r = pl / n
    g = (r * n + (n - w)) / w if w else 0
    v = (w * g * g + (n - w)) / n - r * r if w else 0
    t = "  t %5.2f" % (r / (math.sqrt(v) / math.sqrt(n))) if v > 0 else ""
    print("   %-20s %8s  n=%-4d hit %5.1f%%  ROI %+7.2f%%  $%+8.0f%s"
          % (k, "%d-%d" % (w, n - w), n, 100 * w / n, 100 * r, 25 * pl, t))
print("\n" + BAR)
print("READ: compare 'MC2 as-of (fair)' with 'MC6 as-of'. The gap between them is the only")
print("head-to-head number in this thread free of the input-quality confound. 'MC2 live' is")
print("shown to size the staleness penalty, not to judge MC6.")
print(BAR)
