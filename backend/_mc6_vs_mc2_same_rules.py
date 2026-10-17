"""MC6 UNDER MC2's EXACT RULES, ON IDENTICAL ROWS (2026-10-16)

User: "so whats the roi on mc6? with the same rules as mc2?"

The lane numbers answer a narrower question than this one. The lanes refuse recon rows, so
mc6_dog4_all has 71 settles against mc2_dog4_all's 459 -- a comparison between a two-day sample
and a six-week one, which says nothing about the heads.

This runs BOTH heads over the SAME rows under the SAME rules, so the only thing that differs is
the head:

    dog 4pt   head >= 4pt over the de-vigged market on the market dog
    dog 6pt   the 6pt version
    fav 4pt   head >= 4pt over on a favourite priced -100..-200, by gender

Reported per gender x price band, because that is how the tab gates, and with the paired
disagreement split -- the only rows that can separate two heads this closely related.

THE CAVEAT THAT CANNOT BE WAVED AWAY: MC6's values on most of these rows are an AS-OF BACKFILL
(721 of 826). The backfill is leak-free -- it takes the ledger's own frozen mc5_p1 and shifts it
by terms built from strictly prior matches -- but it is a REPLAY, not a pick that was shown
before the match. MC2's values on the same rows are mostly genuine forward reads. So this is not
MC6 earning a record; it is MC6's rule applied to history, which is the fairest available read
until its forward sample grows. Both the pooled and forward-only splits are printed.

Run: ./venv/bin/python _mc6_vs_mc2_same_rules.py
"""
import math
import re

import numpy as np
import pandas as pd

import tennis_log

log = pd.read_parquet(tennis_log.LOG_PATH)
bad = np.zeros(len(log), bool)
for c in ("surface_bad", "resolve_bad", "inplay_suspect", "void"):
    if c in log.columns:
        bad |= log[c].fillna(False).astype(bool).to_numpy()
log = log[~bad]
log = log[log.p1_won.notna() & log.p1_odds.notna() & log.p2_odds.notna()]
log = log[log.mc2_p1.notna() & log.mc6_p1.notna()].reset_index(drop=True)

o1 = pd.to_numeric(log.p1_odds, errors="coerce").to_numpy(float)
o2 = pd.to_numeric(log.p2_odds, errors="coerce").to_numpy(float)
dc = lambda o: np.where(o > 0, 1 + o / 100.0, 1 + 100.0 / np.abs(o))
D1, D2 = dc(o1), dc(o2)
mk1 = (1 / D1) / ((1 / D1) + (1 / D2))
Y1 = log.p1_won.astype(bool).to_numpy()
lgs = log.league.astype(str).str.lower()
isw = (lgs.str.contains("wta") | lgs.str.contains("itf_women")).to_numpy()
itfm = (lgs == "itf_men").to_numpy()
m2 = pd.to_numeric(log.mc2_p1, errors="coerce").to_numpy(float)
m6 = pd.to_numeric(log.mc6_p1, errors="coerce").to_numpy(float)
r6 = (log.mc6_recon.fillna(False).astype(bool).to_numpy()
      if "mc6_recon" in log.columns else np.zeros(len(log), bool))
r2 = (log.mc2_recon.fillna(False).astype(bool).to_numpy()
      if "mc2_recon" in log.columns else np.zeros(len(log), bool))
BOTH_FWD = ~r6 & ~r2

dog1 = mk1 < 0.5
dam = np.where(dog1, o1, o2)
dod = np.where(dog1, D1, D2)
dwon = np.where(dog1, Y1, ~Y1)
dpnl = np.where(dwon, dod - 1, -1.0)
mkd = np.where(dog1, mk1, 1 - mk1)
mkFav = np.maximum(mk1, 1 - mk1)
favAm = np.where(dog1, o2, o1)
favDec = np.where(dog1, D2, D1)
favWon = np.where(dog1, ~Y1, Y1)
fpnl = np.where(favWon, favDec - 1, -1.0)
OV = {"mc2": np.where(dog1, 1 - m2, m2) - mkd, "mc6": np.where(dog1, 1 - m6, m6) - mkd}
OVF = {"mc2": np.where(dog1, m2, 1 - m2) - mkFav, "mc6": np.where(dog1, m6, 1 - m6) - mkFav}
print("rows with BOTH heads: %d   (MC6 forward %d, recon %d)   both-forward %d"
      % (len(log), int((~r6).sum()), int(r6.sum()), int(BOTH_FWD.sum())))


def rep(mask, pnl, won, lab, ind="   "):
    n = int(mask.sum())
    if n == 0:
        print("%s%-30s n=0" % (ind, lab)); return None
    w = int(won[mask].sum())
    r = pnl[mask].mean()
    t = ""
    if 0 < w < n:
        g = (r * n + (n - w)) / w
        v = (w * g * g + (n - w)) / n - r * r
        if v > 0:
            t = "  t %5.2f" % (r / (math.sqrt(v) / math.sqrt(n)))
    print("%s%-30s %7s  n=%-4d hit %5.1f%%  ROI %+7.2f%%  $%+7.0f%s"
          % (ind, lab, "%d-%d" % (w, n - w), n, 100 * w / n, 100 * r, 25 * pnl[mask].sum(), t))
    return r


BAR = "=" * 96
BAND = (dam >= 100) & (dam <= 300) & ~itfm
for scope, slab in ((np.ones(len(log), bool), "ALL SHARED ROWS (MC6 mostly as-of replay)"),
                    (BOTH_FWD, "BOTH HEADS FORWARD ONLY")):
    print("\n" + BAR)
    print("SAME RULES, SAME ROWS  --  %s" % slab)
    print(BAR)
    for lab, th in (("DOG 4pt+, +100..+300", 0.04), ("DOG 6pt+, +100..+300", 0.06)):
        print("   %s" % lab)
        for tag in ("mc2", "mc6"):
            rep(scope & BAND & (OV[tag] <= -th), dpnl, dwon, tag.upper(), ind="      ")
    print("   FAV 4pt+, -100..-200")
    fb = (favAm <= -100) & (favAm >= -200)
    for tag in ("mc2", "mc6"):
        for gl, gm in (("women", isw), ("men  ", ~isw)):
            rep(scope & fb & gm & (OVF[tag] >= 0.04), fpnl, favWon,
                "%s %s" % (tag.upper(), gl), ind="      ")

print("\n" + BAR)
print("THE DOG 4pt CELL BY GENDER x BAND  (how the tab gates) -- all shared rows")
print(BAR)
print("   %-14s %-12s %18s %18s" % ("", "", "MC2", "MC6"))
for gl, gm in (("men", ~isw), ("women", isw)):
    for lo, hi in ((100, 150), (150, 200), (200, 250), (250, 300)):
        b = gm & ~itfm & (dam >= lo) & (dam <= hi)
        out = []
        for tag in ("mc2", "mc6"):
            m = b & (OV[tag] <= -0.04)
            n = int(m.sum())
            out.append("%+7.2f%% /%-4d" % (100 * dpnl[m].mean(), n) if n else "      --   ")
        print("   %-14s %-12s %18s %18s" % (gl, "+%d..+%d" % (lo, hi), out[0], out[1]))

print("\n" + BAR)
print("WHERE THEY DISAGREE -- the only rows that separate them (dog 4pt gate, all shared rows)")
print(BAR)
f2, f6 = BAND & (OV["mc2"] <= -0.04), BAND & (OV["mc6"] <= -0.04)
rep(f2 & f6, dpnl, dwon, "BOTH fire")
rep(f2 & ~f6, dpnl, dwon, "MC2 only (MC6 declines)")
rep(f6 & ~f2, dpnl, dwon, "MC6 only (MC2 declines)")
tot = int((f2 | f6).sum())
if tot:
    print("   agreement: %.0f%% of either firing" % (100 * (f2 & f6).sum() / tot))
print("\n" + BAR)
print("READ: the top block is the answer to 'ROI on MC6 under MC2's rules'. The bottom block is")
print("the one that matters for a SWAP -- if MC6-only bets lose and MC2-only bets win, swapping")
print("trades good cards for bad ones regardless of what the headline ROIs look like.")
print(BAR)
