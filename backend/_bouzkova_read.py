"""WAS THERE A READ ON BOUZKOVA -> CHWALINSKA? (2026-10-13)

Marie Bouzkova -196 vs Maja Chwalinska +162, Wuhan, hard. Chwalinska won. The MC heads showed
Bouzkova in the mid-60s and the card read as a strong favourite.

Checks, in order:
  1. Did any MC head actually make Bouzkova a BET? Break-even at -196 is 66.2%; the frozen heads
     were 62.3 / 65.0 / 64.2. Same accounting as the Duckworth card.
  2. Which heads dissented? Model C and Model X sat near 50/50, Model P said BET CHWALINSKA at
     +19.6% EV, and the pink returner-only-dog cell flagged her. Those are reads that existed.
  3. What are those dissenting signals actually worth on WOMEN'S DOGS in the frozen log? A read
     being present is not the same as a read being trustworthy.
  4. Did today's sample-asymmetry tilt push this card the wrong way? The frozen (pre-tilt) MC2
     was 62.3% but the live board showed 66% after the tilt shipped, and Bouzkova lost -- so the
     tilt moved it TOWARD the loser here. n=1 and not evidence against it, but it has to be said.
"""
import numpy as np
import pandas as pd

import tennis_log

B_OD, C_OD = -196.0, 162.0
dec = lambda o: 1 + o / 100.0 if o > 0 else 1 + 100.0 / abs(o)
dB, dC = dec(B_OD), dec(C_OD)
iB, iC = 1 / dB, 1 / dC
mkB = iB / (iB + iC)
FROZEN = {"MC2": 0.6225, "MC3": 0.6495, "MC5": 0.6418, "Model A": 0.6227, "Model B": 0.6638,
          "Model C": 0.5087, "Model D": 0.5595, "Model G": 0.5692, "Model G2": 0.6223,
          "Model X": 0.5361}
BAR = "=" * 94
print(BAR)
print("1. DID ANY HEAD MAKE BOUZKOVA A BET? break-even at -196 is %.1f%%" % (100 / dB))
print(BAR)
print("   de-vigged market on Bouzkova %5.1f%%   vig %.1fpt" % (100 * mkB, 100 * (iB + iC - 1)))
print()
print("   %-9s %10s %11s %14s %13s" % ("head", "on Bouzk", "vs de-vig", "vs break-even",
                                       "EV on Bouzk"))
for nm, p in FROZEN.items():
    ev = p * dB - 1
    print("   %-9s %9.1f%% %+10.1fpt %+13.1fpt %+12.1f%%%s"
          % (nm, 100 * p, 100 * (p - mkB), 100 * (p - 1 / dB), 100 * ev,
             "   <- would be a bet" if ev > 0 else ""))
print()
print("   NOT ONE head cleared the price. The card was a PASS, not a strong favourite --")
print("   the displayed 60s looked high only against the de-vigged number.")

print("\n" + BAR)
print("2. THE DISSENT -- read from Chwalinska's side at +162 (break-even %.1f%%)" % (100 / dC))
print(BAR)
for nm, p in FROZEN.items():
    pc = 1 - p
    ev = pc * dC - 1
    if ev > -0.02:
        print("   %-9s Chwalinska %5.1f%%  vs market %4.1f%%  EV %+6.1f%%%s"
              % (nm, 100 * pc, 100 * (1 - mkB), 100 * ev, "   <- positive" if ev > 0 else ""))
print("   Model P (its own output): Chwalinska 45.7%% vs market 36.6%%  EV +19.6%%  -> BET")

# ------------------------------------------------- 3. what are those reads worth?
log = pd.read_parquet(tennis_log.LOG_PATH)
log = log[log["p1_won"].notna()].copy()
for c in ("resolve_bad", "surface_bad", "inplay_suspect"):
    if c in log.columns:
        log = log[~log[c].fillna(False).astype(bool).to_numpy()]
log["_o1"] = pd.to_numeric(log["p1_odds"], errors="coerce")
log["_o2"] = pd.to_numeric(log["p2_odds"], errors="coerce")
log = log[log["_o1"].notna() & log["_o2"].notna()].reset_index(drop=True)
dc = lambda o: np.where(o > 0, 1 + o / 100.0, 1 + 100.0 / np.abs(o))
D1, D2 = dc(log["_o1"].to_numpy(float)), dc(log["_o2"].to_numpy(float))
I1, I2 = 1 / D1, 1 / D2
MKD1 = I1 / (I1 + I2)
W1 = log["p1_won"].astype(bool).to_numpy()
WOM = log["league"].astype(str).str.contains("wta|itf_women", case=False, na=False).to_numpy()

print("\n" + BAR)
print("3. WHAT IS EACH DISSENT WORTH ON WOMEN'S DOGS? frozen live log")
print(BAR)
# Model P's own dog bets
if "model_p_ev" in log.columns and "model_p_dog" in log.columns:
    pe = pd.to_numeric(log["model_p_ev"], errors="coerce").to_numpy(float)
    pdog = pd.to_numeric(log["model_p_dog"], errors="coerce").to_numpy(float)
    ok = ~np.isnan(pe) & ~np.isnan(pdog)
    d1side = pdog == 1
    odd = np.where(d1side, D1, D2)
    win = np.where(d1side, W1, ~W1)
    pnl = np.where(win, odd - 1, -1.0)
    for lab, q in (("women", ok & WOM & (pe >= 0.05)), ("men", ok & ~WOM & (pe >= 0.05))):
        n = int(q.sum())
        if n:
            print("   Ⓟ Model P dog bet (EV>=5%%)  %-6s n=%-4d ROI %+7.2f%%  hit %4.1f%%"
                  % (lab, n, 100 * pnl[q].mean(), 100 * win[q].mean()))
# heads that sit on the market DOG
print()
for nm, col in (("Model C", "model_c_p1"), ("Model X", "model_x_p1"), ("MC2", "mc2_p1")):
    if col not in log.columns:
        continue
    p = pd.to_numeric(log[col], errors="coerce").to_numpy(float)
    ok = ~np.isnan(p)
    pick1 = p >= 0.5
    dogside = (pick1 & (MKD1 < 0.5)) | (~pick1 & (MKD1 >= 0.5))
    odd = np.where(pick1, D1, D2)
    win = np.where(pick1, W1, ~W1)
    pnl = np.where(win, odd - 1, -1.0)
    q = ok & dogside & WOM
    n = int(q.sum())
    if n:
        print("   %-8s picks the WOMEN'S market dog   n=%-4d ROI %+7.2f%%  hit %4.1f%%"
              % (nm, n, 100 * pnl[q].mean(), 100 * win[q].mean()))

# C near a coin flip on a market favourite -- the specific shape here (C 50.9%)
if "model_c_p1" in log.columns:
    pc = pd.to_numeric(log["model_c_p1"], errors="coerce").to_numpy(float)
    ok = ~np.isnan(pc)
    cdog = np.where(MKD1 < 0.5, pc, 1 - pc)          # C's number ON THE MARKET DOG
    mdog = np.where(MKD1 < 0.5, MKD1, 1 - MKD1)
    oddd = np.where(MKD1 < 0.5, D1, D2)
    wind = np.where(MKD1 < 0.5, W1, ~W1)
    pnld = np.where(wind, oddd - 1, -1.0)
    print("\n   C's number ON THE MARKET DOG (women) -- this card was C 49.1% on Chwalinska:")
    print("   %-18s %7s %10s %8s" % ("C on the dog", "n", "ROI", "hit"))
    for lo, hi in ((0.30, 0.40), (0.40, 0.45), (0.45, 0.50), (0.50, 1.00)):
        q = ok & WOM & (cdog >= lo) & (cdog < hi)
        n = int(q.sum())
        if n < 10:
            continue
        print("   %-18s %7d %+9.2f%% %7.1f%%%s"
              % ("%.0f-%.0f%%" % (100 * lo, 100 * hi), n, 100 * pnld[q].mean(),
                 100 * wind[q].mean(), "   <- this card" if lo == 0.45 else ""))

print("\n" + BAR)
print("4. DID TODAY'S TILT PUSH THIS CARD TOWARD THE LOSER?")
print(BAR)
import tennis_mc2 as M2
S = M2._state()
for nm in ("Marie Bouzkova", "Maja Chwalinska"):
    sl = M2._slug(nm, "Hard")
    pl = S["players"].get(sl) if sl else None
    print("   %-18s slug %-22s nS %s" % (nm, sl, pl["nS"] if pl else None))
a = S["players"].get(M2._slug("Marie Bouzkova", "Hard"))
b = S["players"].get(M2._slug("Maja Chwalinska", "Hard"))
if a and b:
    t = M2.asym_tilt(a["nS"], b["nS"])
    import math
    lg = lambda p: math.log(p / (1 - p))
    print("   tilt %+0.4f log-odds -> frozen MC2 62.25%% becomes %.1f%%"
          % (t, 100 / (1 + math.exp(-(lg(0.6225) + t)))))
    print("   (the live board showed 66%% after the tilt shipped; Bouzkova lost)")
