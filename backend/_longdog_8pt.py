"""DOGS ABOVE +250 WHERE THE HEADS MOVE THEM 8pt+ (2026-10-13).

User: "if its over +250 but models move the underdog over 8 points then thats still a good dog
bet aka iva jovic vs dayan yastremska". That card is Yastremska +285 with MC2 +17.2pt, MC3
+16.2pt and MC5 +14.1pt over the market on the dog -- and it currently gets no mark at all,
because the brown dog band stops at +250.

WHY THIS NEEDS MEASURING RATHER THAN JUST WIDENING. The existing long-dog cell was measured at
the 10pt margin and the edge did NOT survive past +300: +250..+300 ran +32.11% on 53 while +300
and up ran -24.35% on 107. So "over +250" as an open-ended rule mixes the best slice on the board
with the worst. Yastremska at +285 sits in the good slice. The question is where the rule should
stop, not whether the card is right.

METHOD. MC2 and MC3 are rebuilt on the archive from their own feature tables, WITH the
sample-asymmetry tilt applied (tennis_mc2.asym_tilt), because that tilt is part of the live heads
now and measuring the pre-tilt model would answer the wrong question. MC5 has no archive feature
table, so the archive cell requires MC2 AND MC3 to agree at the threshold and MC5 is reported
separately on the frozen live log.

Reported by dog price band so the rule can be bounded on evidence, with every year shown, and
with the baseline for every dog in the same band as the control -- a cell that only matches the
band's own return is the price band talking, not the heads.
"""
import numpy as np
import pandas as pd

from tennis_mc2 import _NODES, _rnd, asym_tilt
from tennis_mc3 import p_match

COLS = ["year", "p_elo", "pa_pt", "pb_pt", "nS_a", "nS_b", "imp", "won", "score",
        "odd_a", "odd_b", "wom", "lvlg"]


def heads(path):
    F = pd.read_parquet(path, columns=COLS)
    F = F[F["imp"].notna() & F["won"].notna() & F["pa_pt"].notna() & F["pb_pt"].notna()
          & F["p_elo"].notna() & F["odd_a"].notna() & F["odd_b"].notna()
          & (F["odd_a"] > 1.005) & (F["odd_b"] > 1.005)
          & (F["nS_a"] >= 4) & (F["nS_b"] >= 4)].reset_index(drop=True)
    PA, PB = F["pa_pt"].to_numpy(float), F["pb_pt"].to_numpy(float)
    NA, NB = F["nS_a"].to_numpy(float), F["nS_b"].to_numpy(float)
    SGA = 0.10 / np.sqrt(np.maximum(NA, 4.0))
    SGB = 0.10 / np.sqrt(np.maximum(NB, 4.0))

    def sets_won(s):
        if not isinstance(s, str) or not s.strip():
            return 0
        x = y = 0
        for tok in s.split():
            t = tok.split("(")[0]
            if "-" not in t:
                continue
            u, _, v = t.partition("-")
            try:
                u, v = int(u), int(v)
            except ValueError:
                continue
            if u > v:
                x += 1
            elif v > u:
                y += 1
        return max(x, y)

    bo5 = np.array([sets_won(s) >= 3 for s in F["score"]])
    pm = np.zeros(len(F))
    for xi, wi in _NODES:
        for xj, wj in _NODES:
            pm += wi * wj * np.array([p_match(_rnd(x + xi * a), _rnd(y + xj * b), bool(f))
                                      for x, y, a, b, f in zip(PA, PB, SGA, SGB, bo5)])

    def lg(v):
        v = np.clip(v, 1e-6, 1 - 1e-6)
        return np.log(v / (1 - v))

    # the LIVE recipe, tilt included
    tilt = np.array([asym_tilt(a, b) for a, b in zip(NA, NB)])
    p = 1 / (1 + np.exp(-(0.5 * lg(F["p_elo"].to_numpy(float)) + 0.5 * lg(pm) + tilt)))
    return F, p


F2, P2 = heads("data_cache/_mc2_features.parquet")
F3, P3 = heads("data_cache/_mc3_features.parquet")
n = min(len(F2), len(F3))
F, P2, P3 = F3.iloc[:n].reset_index(drop=True), P2[:n], P3[:n]
print("archive rows with both heads: %d" % n)

OA, OB = F["odd_a"].to_numpy(float), F["odd_b"].to_numpy(float)
IMP = F["imp"].to_numpy(float)                     # de-vigged on side A
WON = F["won"].to_numpy(float).astype(bool)
YR = F["year"].to_numpy()
WOM = F["wom"].to_numpy(float).astype(bool) if "wom" in F.columns else np.zeros(n, bool)

dogA = IMP < 0.5
dog_od = np.where(dogA, OA, OB)
dog_am = (dog_od - 1) * 100
mk_dog = np.where(dogA, IMP, 1 - IMP)
g2 = (np.where(dogA, P2, 1 - P2) - mk_dog) * 100    # MC2's margin on the dog, in points
g3 = (np.where(dogA, P3, 1 - P3) - mk_dog) * 100
won_dog = np.where(dogA, WON, ~WON)
pnl = np.where(won_dog, dog_od - 1, -1.0)

BANDS = [(100, 200, "+100..+200"), (200, 250, "+200..+250"), (250, 300, "+250..+300"),
         (300, 400, "+300..+400"), (400, 1e9, "+400 and up")]
BAR = "=" * 102


def line(lab, q, extra=""):
    k = int(q.sum())
    if k < 25:
        return "   %-26s n=%-5d (thin)" % (lab, k)
    return ("   %-26s n=%-5d ROI %+7.2f%%  hit %4.1f%%%s"
            % (lab, k, 100 * pnl[q].mean(), 100 * won_dog[q].mean(), extra))


print("\n" + BAR)
print("THE USER'S RULE: both heads 8pt+ over the market ON THE DOG, by price band")
print("   control line = every dog in the same band, so the band itself is not the story")
print(BAR)
both8 = (g2 >= 8) & (g3 >= 8)
for lo, hi, lab in BANDS:
    inb = (dog_am >= lo) & (dog_am < hi)
    print(line("%s  ALL dogs" % lab, inb))
    print(line("%s  both 8pt+" % lab, inb & both8, "   <- the rule"))
    for y in (2024, 2025, 2026):
        q = inb & both8 & (YR == y)
        if q.sum() >= 15:
            print("      %d  n=%-4d ROI %+7.2f%%" % (y, int(q.sum()), 100 * pnl[q].mean()))
    print()

print(BAR)
print("WHERE DOES IT STOP? the same rule, cumulative from +250 upward")
print(BAR)
for lo in (250, 275, 300, 350, 400):
    q = (dog_am >= lo) & both8
    print(line("dogs >= +%d, both 8pt+" % lo, q))
print()
for lo, hi in ((250, 300), (250, 350), (250, 400), (250, 1e9)):
    q = (dog_am >= lo) & (dog_am < hi) & both8
    print(line("+%d..%s both 8pt+" % (lo, "inf" if hi > 1e8 else "+%d" % hi), q))

print("\n" + BAR)
print("DOES THE MARGIN MATTER ABOVE +250? ladder at 8/10/12/15pt")
print(BAR)
for t in (8, 10, 12, 15, 20):
    q = (dog_am >= 250) & (g2 >= t) & (g3 >= t)
    print(line("dogs >= +250, both %dpt+" % t, q))
print()
for t in (8, 10, 12, 15, 20):
    q = (dog_am >= 250) & (dog_am < 300) & (g2 >= t) & (g3 >= t)
    print(line("+250..+300, both %dpt+" % t, q))

print("\n" + BAR)
print("BY GENDER -- every cell in this project has split by gender")
print(BAR)
for glab, gq in (("men", ~WOM), ("women", WOM)):
    for lo, hi, lab in (("250", 300, "+250..+300"), ("250", 1e9, "+250 and up")):
        q = gq & (dog_am >= 250) & (dog_am < hi) & both8
        print(line("%-6s %s both 8pt+" % (glab, lab), q))

print("\n" + BAR)
print("READ: the rule ships only for the band where it holds in BOTH the pooled number and")
print("every year, and where it beats the all-dogs control for that same band.")
print(BAR)

# ---------------------------------------------------------------- LEVEL, the decisive split
# The archive says -15.5% on 14,327 while the FROZEN LIVE LOG says +44.5% on 51 for the same
# rule. Before calling either one luck, test composition: the archive is dominated by ITF and
# futures, the live board is WTA and challenger, and TOUR has already been measured as the one
# level where dog edges hold (project_level_round_surface). If the archive cell is positive at
# tour level and negative at futures, the forward result is not a fluke -- it is level mix, and
# the rule should ship gated to level rather than refused.
LVL = pd.to_numeric(F["lvlg"], errors="coerce").fillna(-1).to_numpy(float)
print(chr(10) + BAR)
print("LEVEL SPLIT -- is the forward/archive conflict just composition?")
print(BAR)
for llab, lq in (("futures", LVL == 0), ("challenger", LVL == 1), ("tour", LVL == 2),
                 ("slam", LVL == 3)):
    print("   %s" % llab.upper())
    for lo, hi, lab in ((250, 300, "+250..+300"), (300, 1e9, "+300 and up"),
                        (250, 1e9, "+250 and up")):
        inb = lq & (dog_am >= lo) & (dog_am < hi)
        print(line("   %s ALL dogs" % lab, inb))
        print(line("   %s both 8pt+" % lab, inb & both8))
    print()
print(BAR)
print("TOUR + WTA ONLY, by year -- the composition closest to the live board")
print(BAR)
tourish = (LVL >= 2) | ((LVL == 1) & WOM)
for lo, hi, lab in ((250, 300, "+250..+300"), (250, 1e9, "+250 and up")):
    q = tourish & (dog_am >= lo) & (dog_am < hi)
    print(line("%s ALL dogs" % lab, q))
    print(line("%s both 8pt+" % lab, q & both8))
    for y in (2024, 2025, 2026):
        qq = q & both8 & (YR == y)
        if qq.sum() >= 10:
            print("      %d  n=%-4d ROI %+7.2f%%  hit %4.1f%%"
                  % (y, int(qq.sum()), 100 * pnl[qq].mean(), 100 * won_dog[qq].mean()))
    print()
