"""THE s52 SEASONAL-BAND DOG RULE, BY PRICE BAND x GENDER (2026-10-14).

User: "and do the test +100 to 150 to 150 to 200 to 250 to 300 / 200 to 250".

THE LANE IS PRICE-GATED. tennis_log hard-codes `if not (100 <= dodd <= 200): continue`, so
s52_fav_band_dog has ZERO bets above +200 by construction -- its +19.80% on 183 (t 2.25) is a
+100..+200 number and nothing else. This re-runs the rule with that gate REMOVED so the higher
bands can be measured for the first time.

THE RULE, copied from tennis_log so the two cannot drift:
    * the match has all four frozen seasonal columns (s52_sgw / s52_rgw for both players)
    * take the MARKET DOG
    * orient both seasonal gaps to the dog:
        ds = dog_hold%  - opp_hold%      dr = dog_break% - opp_break%
    * ds < 0 AND dr < 0  -> s52_fav_band_dog  (the FAVOURITE owns both stats; back the dog anyway)
    * ds > 0 AND dr > 0  -> s52_dog_band_dog  (the DOG owns both stats)
    * one each -> unlaned (the negative remainder, deliberately dropped)

Both lanes are reported, because the interesting claim is that the FAVOURITE-owns-both cell is
the profitable one -- i.e. the seasonal stat line is a fade, not a follow
([[project_live_window_fade]]).

Bands are assigned FIRST-MATCH so the edges do not overlap: a dog at exactly +150 belongs to
+100..+150 only. Full lane discipline (surface_bad / resolve_bad / inplay_suspect / void) --
note the shipped lane drops only surface_bad, so its own number is on a slightly wider set; the
run prints both so the difference is visible rather than assumed.

Run on EC2: ./venv/bin/python _s52_band_test.py
"""
import math

import numpy as np
import pandas as pd

import tennis_log

COLS = ("s52_sgw_p1", "s52_rgw_p1", "s52_sgw_p2", "s52_rgw_p2")
BANDS = [("+100..+150", 100, 150), ("+150..+200", 150, 200),
         ("+200..+250", 200, 250), ("+250..+300", 250, 300),
         ("+300..+500", 300, 500)]


def load(strict):
    log = pd.read_parquet(tennis_log.LOG_PATH)
    drop = ("surface_bad", "resolve_bad", "inplay_suspect", "void") if strict else ("surface_bad",)
    bad = np.zeros(len(log), bool)
    for c in drop:
        if c in log.columns:
            bad |= log[c].fillna(False).astype(bool).to_numpy()
    log = log[~bad]
    log = log[log["p1_odds"].notna() & log["p2_odds"].notna()]
    log = log[log[list(COLS)].notna().all(axis=1)]
    return log[log["p1_won"].notna()].reset_index(drop=True)


def build(log):
    o1 = pd.to_numeric(log["p1_odds"], errors="coerce").to_numpy(float)
    o2 = pd.to_numeric(log["p2_odds"], errors="coerce").to_numpy(float)
    dc = lambda o: np.where(o > 0, 1 + o / 100.0, 1 + 100.0 / np.abs(o))
    D1, D2 = dc(o1), dc(o2)
    mk1 = (1 / D1) / ((1 / D1) + (1 / D2))
    dog1 = mk1 < 0.5                                  # player_1 is the market dog
    dam = np.where(dog1, o1, o2)                      # the DOG's american price
    dec = np.where(dog1, D1, D2)
    W1 = log["p1_won"].astype(bool).to_numpy()
    won = np.where(dog1, W1, ~W1)
    pnl = np.where(won, dec - 1.0, -1.0)
    sgn = np.where(dog1, 1.0, -1.0)
    ds = sgn * (pd.to_numeric(log["s52_sgw_p1"]).to_numpy(float)
                - pd.to_numeric(log["s52_sgw_p2"]).to_numpy(float))
    dr = sgn * (pd.to_numeric(log["s52_rgw_p1"]).to_numpy(float)
                - pd.to_numeric(log["s52_rgw_p2"]).to_numpy(float))
    lg = log["league"].astype(str).str.lower()
    isw = (lg.str.contains("wta") | lg.str.contains("itf_women")).to_numpy()
    fav_owns = (ds < 0) & (dr < 0)                    # s52_fav_band_dog
    dog_owns = (ds > 0) & (dr > 0)                    # s52_dog_band_dog
    return dam, pnl, won, isw, fav_owns, dog_owns


def rep(m, pnl, won, lab, ind="   "):
    n = int(m.sum())
    if n == 0:
        return "%s%-26s n=0" % (ind, lab)
    w = int(won[m].sum())
    r = pnl[m].mean()
    t = ""
    if w:
        g = ((r * n) + (n - w)) / w
        v = (w * g * g + (n - w)) / n - r * r
        if v > 0:
            t = "  t %5.2f" % (r / (math.sqrt(v) / math.sqrt(n)))
    return ("%s%-26s n=%-4d %6s  hit %5.1f%%  ROI %+7.2f%%  $%+8.2f%s"
            % (ind, lab, n, "%d-%d" % (w, n - w), 100 * w / n, 100 * r, 25 * pnl[m].sum(), t))


BAR = "=" * 100
for strict, slab in ((False, "lane discipline AS SHIPPED (surface_bad only)"),
                     (True, "FULL discipline (+ resolve_bad / inplay_suspect / void)")):
    log = load(strict)
    dam, pnl, won, isw, fav_owns, dog_owns = build(log)
    print("\n" + BAR)
    print("%s   -- %d qualifying rows" % (slab, len(log)))
    print(BAR)
    for cellmask, cname in ((fav_owns, "s52_fav_band_dog  (FAVOURITE owns both seasonal stats)"),
                            (dog_owns, "s52_dog_band_dog  (DOG owns both)")):
        print("\n  " + cname)
        print(rep(cellmask & (dam >= 100) & (dam <= 200), pnl, won,
                  "AS SHIPPED +100..+200"))
        lower = np.zeros(len(dam), bool)
        for lab, lo, hi in BANDS:
            b = (dam >= lo) & (dam <= hi) & ~lower
            lower |= (dam >= lo) & (dam <= hi)
            m = cellmask & b
            print(rep(m, pnl, won, lab + "  all"))
            print(rep(m & ~isw, pnl, won, lab + "  men", ind="      "))
            print(rep(m & isw, pnl, won, lab + "  women", ind="      "))

print("\n" + BAR)
print("READ: the lane stops at +200 by a hard-coded gate. Anything above that line has never")
print("been bet by it and is being measured here for the first time.")
print(BAR)
