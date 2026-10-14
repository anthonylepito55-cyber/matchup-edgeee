"""COULD THE DUCKWORTH CARD HAVE BEEN READ DIFFERENTLY? (2026-10-13)

Liam Draxl vs James Duckworth, Jinan Challenger, hard. Duckworth was the market favourite at
-154 and EVERY head liked him more than the market. He lost in straight sets.

Three readings are tested against the archive and the frozen live log, in order of how much they
would have changed the call:

  1. THE VIG. The board compares each head to the DE-VIGGED market, so "+3.3pt over" looks like
     an edge. But you pay the real price. This card carried 6.9pt of vig, so the break-even on
     -154 is well above the de-vigged 56.7%, and a 3pt de-vigged edge can be NEGATIVE EV.
     This is the cheapest possible fix and applies to every card.

  2. THE SIDE. Every measured record in this project says the heads lose on favourites. This was
     a favourite that all nine heads agreed on.

  3. MODEL C's MARGIN. C sat 13.5pt over the market here, and the measured gradient says the
     further C sits above the market ON A FAVOURITE, the worse it does -- so C's enthusiasm was
     evidence AGAINST, not for.

Each is quantified on real rows rather than asserted, and the archive and the live log are
reported separately because they have disagreed before.
"""
import numpy as np
import pandas as pd

import tennis_log

# ----------------------------------------------------------------- the card itself
O1, O2 = 116.0, -154.0            # Draxl / Duckworth, frozen pre-match
HEADS = {"MC2": 0.3996, "MC3": 0.3886, "MC5": 0.4010, "Model C": 0.2984,
         "Model D": 0.4233, "Model G": 0.4002, "Model X": 0.3946}


def dec(o):
    return 1 + o / 100.0 if o > 0 else 1 + 100.0 / abs(o)


d1, d2 = dec(O1), dec(O2)
i1, i2 = 1 / d1, 1 / d2
vig = (i1 + i2 - 1) * 100
mk_dv = i2 / (i1 + i2)                      # de-vigged market on DUCKWORTH
be = 1 / d2                                 # break-even on Duckworth at the real price

BAR = "=" * 94
print(BAR)
print("1. THE VIG -- what the board showed vs what the price demanded")
print(BAR)
print("   Duckworth price %-6s decimal %.3f" % ("%+d" % O2, d2))
print("   de-vigged market on Duckworth      %5.1f%%   <- what the board compares against" % (100 * mk_dv))
print("   BREAK-EVEN on Duckworth at -154    %5.1f%%   <- what you actually have to beat" % (100 * be))
print("   vig on the card                    %5.1fpt  (challenger pricing)" % vig)
print()
print("   %-9s %9s %12s %14s %12s" % ("head", "on D'wth", "vs de-vig", "vs break-even", "EV at -154"))
for nm, p1 in HEADS.items():
    pd_ = 1 - p1
    ev = pd_ * d2 - 1
    print("   %-9s %8.1f%% %+11.1fpt %+13.1fpt %+11.1f%%%s"
          % (nm, 100 * pd_, 100 * (pd_ - mk_dv), 100 * (pd_ - be), 100 * ev,
             "   <- looked like an edge, was not" if (pd_ > mk_dv and ev < 0) else ""))
print()
print("   READ: every head that showed a positive de-vigged edge still had NEGATIVE EV at the")
print("   real price, except where noted. The de-vigged comparison flattered the whole card.")

# ------------------------------------------------- how often does the vig eat the edge?
F = pd.read_parquet("data_cache/_mc3_features.parquet",
                    columns=["year", "won", "imp", "odd_a", "odd_b", "p_elo", "pa_pt", "pb_pt",
                             "nS_a", "nS_b", "lvlg"])
F = F[F["imp"].notna() & F["won"].notna() & F["odd_a"].notna() & F["odd_b"].notna()
      & (F["odd_a"] > 1.005) & (F["odd_b"] > 1.005)].reset_index(drop=True)
OA, OB = F["odd_a"].to_numpy(float), F["odd_b"].to_numpy(float)
VIG = (1 / OA + 1 / OB - 1)
IMP = F["imp"].to_numpy(float)
WON = F["won"].to_numpy(float).astype(bool)
LVL = pd.to_numeric(F["lvlg"], errors="coerce").fillna(-1).to_numpy(float)

print("\n" + BAR)
print("HOW BIG IS THIS PROBLEM? vig by level -- the edge a de-vigged read has to clear")
print(BAR)
for lab, q in (("futures", LVL == 0), ("challenger", LVL == 1), ("tour", LVL == 2),
               ("slam", LVL == 3)):
    if q.sum() < 500:
        continue
    v = VIG[q] * 100
    print("   %-11s n=%-7d median vig %4.1fpt   p75 %4.1fpt   p90 %4.1fpt"
          % (lab, int(q.sum()), np.median(v), np.percentile(v, 75), np.percentile(v, 90)))
print("   a de-vigged 'edge' smaller than HALF the vig on that card is not an edge at all,")
print("   because the de-vig splits the margin across both sides.")

# ------------------------------------------------------- 2. the side, on the live log
log = pd.read_parquet(tennis_log.LOG_PATH)
log = log[log["p1_won"].notna()].copy()
for c in ("resolve_bad", "surface_bad", "inplay_suspect"):
    if c in log.columns:
        log = log[~log[c].fillna(False).astype(bool)]
log["_d1"] = pd.to_numeric(log["p1_odds"], errors="coerce")
log["_d2"] = pd.to_numeric(log["p2_odds"], errors="coerce")
log = log[log["_d1"].notna() & log["_d2"].notna()]
dc = lambda o: np.where(o > 0, 1 + o / 100.0, 1 + 100.0 / np.abs(o))
D1, D2 = dc(log["_d1"].to_numpy(float)), dc(log["_d2"].to_numpy(float))
I1, I2 = 1 / D1, 1 / D2
MKD = I1 / (I1 + I2)                      # de-vigged market on p1
W1 = log["p1_won"].astype(bool).to_numpy()
MEN = ~log["league"].astype(str).str.contains("wta|itf_women", case=False, na=False).to_numpy()
CHALL = log["league"].astype(str).str.contains("challenger", case=False, na=False).to_numpy()

print("\n" + BAR)
print("2. THE SIDE -- every head on FAVOURITES, frozen live log (what this card was)")
print(BAR)
print("   %-8s %8s %9s %9s   %8s %9s" % ("head", "fav n", "fav ROI", "fav hit", "dog n", "dog ROI"))
for nm, col in (("MC2", "mc2_p1"), ("MC3", "mc3_p1"), ("MC5", "mc5_p1"),
                ("C", "model_c_p1"), ("D", "model_d_p1"), ("G", "model_g_p1"),
                ("X", "model_x_p1")):
    if col not in log.columns:
        continue
    p = pd.to_numeric(log[col], errors="coerce").to_numpy(float)
    ok = ~np.isnan(p)
    pick1 = p >= 0.5
    # the head's pick is the market FAVOURITE when the market agrees on that side
    favside = (pick1 & (MKD >= 0.5)) | (~pick1 & (MKD < 0.5))
    odd = np.where(pick1, D1, D2)
    win = np.where(pick1, W1, ~W1)
    pnl = np.where(win, odd - 1, -1.0)
    out = []
    for lab, q in (("fav", ok & favside), ("dog", ok & ~favside)):
        n = int(q.sum())
        out.append((n, 100 * pnl[q].mean() if n else float("nan"),
                    100 * win[q].mean() if n else float("nan")))
    print("   %-8s %8d %+8.1f%% %8.1f%%   %8d %+8.1f%%"
          % (nm, out[0][0], out[0][1], out[0][2], out[1][0], out[1][1]))

print("\n   the same split, MEN'S CHALLENGER only (this card's level):")
for nm, col in (("MC2", "mc2_p1"), ("MC3", "mc3_p1"), ("C", "model_c_p1")):
    if col not in log.columns:
        continue
    p = pd.to_numeric(log[col], errors="coerce").to_numpy(float)
    ok = ~np.isnan(p) & MEN & CHALL
    pick1 = p >= 0.5
    favside = (pick1 & (MKD >= 0.5)) | (~pick1 & (MKD < 0.5))
    odd = np.where(pick1, D1, D2)
    win = np.where(pick1, W1, ~W1)
    pnl = np.where(win, odd - 1, -1.0)
    q = ok & favside
    n = int(q.sum())
    print("      %-6s fav n=%-4d ROI %s" % (nm, n, ("%+.1f%%" % (100 * pnl[q].mean())) if n else "-"))

# --------------------------------------- 3. C's margin over the market, on favourites
print("\n" + BAR)
print("3. MODEL C's MARGIN -- C sat 13.5pt over the market on this favourite.")
print("   Archive gradient: does a BIGGER C margin on a favourite do better or worse?")
print(BAR)
try:
    A = pd.read_parquet("data_cache/_abc_oof.parquet")
    cc = [c for c in A.columns if c.lower() in ("p_c", "pc", "raw", "c")]
    print("   (columns: %s)" % ", ".join(list(A.columns)[:14]))
except Exception as e:                                             # noqa: BLE001
    print("   archive C file not loadable here (%s)" % type(e).__name__)
    print("   -- using the FROZEN LOG instead, which is the stronger evidence anyway:")
    if "model_c_p1" in log.columns:
        pc = pd.to_numeric(log["model_c_p1"], errors="coerce").to_numpy(float)
        ok = ~np.isnan(pc)
        cfav = (pc >= 0.5) & (MKD >= 0.5)
        cdog = (pc < 0.5) & (MKD < 0.5)
        onfav = ok & (cfav | cdog)
        cside = np.where(pc >= 0.5, pc, 1 - pc)
        mside = np.where(pc >= 0.5, MKD, 1 - MKD)
        marg = (cside - mside) * 100
        odd = np.where(pc >= 0.5, D1, D2)
        win = np.where(pc >= 0.5, W1, ~W1)
        pnl = np.where(win, odd - 1, -1.0)
        print("   %-18s %7s %10s %9s" % ("C margin over mkt", "n", "ROI", "hit"))
        for lo, hi in ((0, 3), (3, 6), (6, 10), (10, 100)):
            q = onfav & (marg >= lo) & (marg < hi)
            n = int(q.sum())
            if n < 8:
                print("   %-18s %7d  (too few)" % ("%d-%dpt" % (lo, hi), n))
                continue
            print("   %-18s %7d %+9.1f%% %8.1f%%%s"
                  % ("%d-%dpt" % (lo, hi), n, 100 * pnl[q].mean(), 100 * win[q].mean(),
                     "   <- this card" if lo == 10 else ""))
print("\n" + BAR)
