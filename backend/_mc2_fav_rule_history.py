"""THE MC2 FAVOURITE RULE ON THE EARLIER DAYS (2026-10-14).

User: "go back through all our previous days before that and see how it would have done".

The rule: a favourite priced -100..-150 that MC2 rates over the de-vigged market by 4-10pt OR
15pt+ (the 10-15pt rung is carved out -- see the caveat below).

WHY THIS CANNOT SIMPLY BE POOLED WITH THE FORWARD RECORD. Before ~2026-10-08 the log's mc2_p1
values are RECON: walk-forward reconstructions, where the rating state was rebuilt with a date
cutoff and the card re-priced. That is leak-free and is the best available evidence for those
days, but it is NOT a pick that was ever frozen on a board, and for MC2 the two have already
been measured diverging in OPPOSITE directions -- the dog take rule ran -6.17% on 511 recon rows
against +7.68% on 304 forward rows.

There is a known mechanism for that gap, not just noise: the live MC2 state went unrebuilt for
days (project_mc2_state_never_rebuilt), so the probability frozen on a live card was computed
from a stale state while the recon uses a correctly-rebuilt as-of state. They are different
numbers for the same match by construction.

So: forward and recon are reported SEPARATELY and the pooled figure is shown only for
completeness, flagged.

Also reported: the same rule WITHOUT the 10-15pt hole, because the hole was carved out of a
6-bet losing rung in the forward window and is the single most likely thing here to be fitted.
If the hole does not reproduce on the recon days, it was fitted.
"""
import math

import numpy as np
import pandas as pd

import tennis_log

log = pd.read_parquet(tennis_log.LOG_PATH)
log = log[log["p1_won"].notna()].copy()
for c in ("resolve_bad", "surface_bad", "inplay_suspect"):
    if c in log.columns:
        log = log[~log[c].fillna(False).astype(bool).to_numpy()]
log["_o1"] = pd.to_numeric(log["p1_odds"], errors="coerce")
log["_o2"] = pd.to_numeric(log["p2_odds"], errors="coerce")
log = log[log._o1.notna() & log._o2.notna() & log["mc2_p1"].notna()].reset_index(drop=True)

dc = lambda o: np.where(o > 0, 1 + o / 100.0, 1 + 100.0 / np.abs(o))
D1, D2 = dc(log._o1.to_numpy(float)), dc(log._o2.to_numpy(float))
I1, I2 = 1 / D1, 1 / D2
MK1 = I1 / (I1 + I2)
W1 = log.p1_won.astype(bool).to_numpy()
fav1 = MK1 >= 0.5
WOM = log.league.astype(str).str.contains("wta|itf_women", case=False, na=False).to_numpy()
RC = (log["mc2_recon"].fillna(False).astype(bool).to_numpy()
      if "mc2_recon" in log.columns else np.zeros(len(log), bool))
fod = np.where(fav1, D1, D2)
fam = np.where(fod >= 2, (fod - 1) * 100, -100.0 / np.maximum(fod - 1, 1e-9))
wonf = np.where(fav1, W1, ~W1)
pnl = np.where(wonf, fod - 1, -1.0)
mkf = np.where(fav1, MK1, 1 - MK1)
be = 1.0 / fod
p = pd.to_numeric(log["mc2_p1"], errors="coerce").to_numpy(float)
pf = np.where(fav1, p, 1 - p)
over = pf - mkf
dts = log["date"].astype(str).str[:10].to_numpy()

BAND = (fam <= -100) & (fam >= -150)
RULE = BAND & (((over >= 0.04) & (over < 0.10)) | (over >= 0.15))
PLAIN = BAND & (over >= 0.04)
HOLE = BAND & (over >= 0.10) & (over < 0.15)


def rep(m, lab, ind="   "):
    n = int(m.sum())
    if n == 0:
        return "%s%-32s n=0" % (ind, lab)
    w = int(wonf[m].sum())
    roi = 100 * pnl[m].mean()
    prof = 25 * pnl[m].sum()
    r = roi / 100
    t = None
    if w:
        g = (r * n + (n - w)) / w
        v = (w * g * g + (n - w)) / n - r * r
        if v > 0:
            t = r / (math.sqrt(v) / math.sqrt(n))
    ds = sorted(set(dts[m]))
    span = "%s..%s" % (ds[0][5:], ds[-1][5:]) if ds else "-"
    return ("%s%-32s n=%-4d %7s  hit %5.1f%%  needs %5.1f%%  ROI %+7.2f%%  $%+8.2f%s  %2dd %s"
            % (ind, lab, n, "%d-%d" % (w, n - w), 100 * w / n, 100 * be[m].mean(), roi, prof,
               "  t %5.2f" % t if t is not None else "        ", len(ds), span))


BAR = "=" * 126
print(BAR)
print("MC2 FAVOURITE RULE (-100..-150, over by 4-10pt or 15pt+) -- forward vs the earlier days")
print(BAR)
print("   rows with an MC2 number: %d   forward %d   recon %d"
      % (len(log), int((~RC).sum()), int(RC.sum())))
print()
print(rep(RULE & ~RC, "FORWARD (frozen pre-match)"))
print(rep(RULE & RC, "RECON (earlier days, replay)"))
print(rep(RULE, "pooled -- FLAGGED, mixes both"))
print()
print("   the baseline on each, for reference:")
print(rep(BAND & ~RC, "every fav -100..-150, forward"))
print(rep(BAND & RC, "every fav -100..-150, recon"))

print("\n" + BAR)
print("DOES THE 10-15pt HOLE REPRODUCE? if it was fitted, the recon days will not show it")
print(BAR)
for lab, m in (("4-6pt", (over >= 0.04) & (over < 0.06)),
               ("6-8pt", (over >= 0.06) & (over < 0.08)),
               ("8-10pt", (over >= 0.08) & (over < 0.10)),
               ("10-15pt  <- the hole", (over >= 0.10) & (over < 0.15)),
               ("15pt+", over >= 0.15)):
    print("   %s" % lab)
    print(rep(BAND & m & ~RC, "forward", "      "))
    print(rep(BAND & m & RC, "recon", "      "))
print()
print(rep(PLAIN & ~RC, "4pt+ NO hole, forward"))
print(rep(PLAIN & RC, "4pt+ NO hole, recon"))
print(rep(HOLE & ~RC, "the hole alone, forward"))
print(rep(HOLE & RC, "the hole alone, recon"))

print("\n" + BAR)
print("THE RECON DAYS ONE BY ONE -- is it steady or one good week?")
print(BAR)
for d in sorted(set(dts[RULE & RC])):
    print(rep(RULE & RC & (dts == d), d))

print("\n" + BAR)
print("AND BY GENDER on the recon days")
print(BAR)
print(rep(RULE & RC & ~WOM, "men, recon"))
print(rep(RULE & RC & WOM, "women, recon"))
print("\n" + BAR)
