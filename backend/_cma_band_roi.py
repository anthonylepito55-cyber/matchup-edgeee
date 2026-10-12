"""THE MARKET-AWARE C (GRAY LINE) BY PRICE BAND (2026-10-11, user: "What's c market aware model
roi on favorites -100 to -250 and underdogs +100 +200").

`model_cma_p1` is the gray line -- Model C blended with the market. Measured on the FROZEN LIVE
LOG only, per the forward-tests-only rule, flat 1u at the odds the card actually showed.

Two cells asked for:
  FAVOURITES  -100 .. -250, where the gray line picks the favourite
  DOGS        +100 .. +200, where the gray line picks the dog

Each is reported against the BASELINE for the same band -- backing every favourite or every dog
in it -- because a cell's ROI means nothing without knowing what the band itself returns. EDGE
is the realised win rate minus the NO-VIG implied probability, which separates "has an edge too
small to clear the vig" from "priced exactly".

Excludes `surface_bad` (models ran on the wrong court) and `inplay_suspect` (price captured
mid-match) rows, the same as every live lane.
"""
import numpy as np
import pandas as pd

LOG = "data_cache/tennis_prediction_log.parquet"


def dec(a):
    a = float(a)
    return 1.0 + a / 100.0 if a > 0 else 1.0 + 100.0 / abs(a)


d = pd.read_parquet(LOG)
d["date"] = pd.to_datetime(d["date"], errors="coerce")
S = d[(d["settled"] == True) & d.p1_won.notna()                  # noqa: E712
      & d.p1_odds.notna() & d.p2_odds.notna() & d.model_cma_p1.notna()].copy()
for c in ("surface_bad", "inplay_suspect"):
    if c in S.columns:
        S = S[~S[c].fillna(False).astype(bool)]
S["d1"] = S.p1_odds.map(dec)
S["d2"] = S.p2_odds.map(dec)
i1, i2 = 1 / S.d1, 1 / S.d2
S["mkt1"] = i1 / (i1 + i2)
S["dog1"] = S.mkt1 < 0.5
S["g1"] = S.model_cma_p1.astype(float) >= 0.5          # gray line prefers player_1
lg = S.league.astype(str)
S["G"] = np.where(lg.str.contains("wta") | lg.str.contains("itf_women"), "W", "M")
print("settled rows with a gray line: %d   %s..%s"
      % (len(S), str(S.date.min())[:10], str(S.date.max())[:10]))


def report(rows, side_is_p1, lab, floor=12):
    """side_is_p1: boolean array -- is the bet on player_1?"""
    n = len(rows)
    if n < floor:
        print("   %-46s n=%d (too thin)" % (lab, n))
        return
    s = np.asarray(side_is_p1, dtype=bool)
    won = np.where(s, rows.p1_won.astype(bool), ~rows.p1_won.astype(bool))
    odds = np.where(s, rows.d1, rows.d2)
    imp = np.where(s, rows.mkt1, 1 - rows.mkt1)
    pnl = np.where(won, odds - 1, -1.0)
    se = 100 * pnl.std(ddof=1) / np.sqrt(n)
    print("   %-46s %d-%d  wins %4.1f%%  no-vig %4.1f%%  EDGE %+5.1fpt  ROI %+6.1f%% ± %4.1f  (n=%d)"
          % (lab, int(won.sum()), n - int(won.sum()), 100 * won.mean(), 100 * imp.mean(),
             100 * (won.mean() - imp.mean()), 100 * pnl.mean(), se, n))


# ---------------------------------------------------------------- FAVOURITES -100..-250
# the favourite's own American price must be between -250 and -100
fav_odds = np.where(S.dog1, S.p2_odds, S.p1_odds).astype(float)
fav_is_p1 = ~S.dog1
band_f = (fav_odds >= -250) & (fav_odds <= -100)
print("\n" + "=" * 110)
print("FAVOURITES -100 .. -250")
print("=" * 110)
F = S[band_f]
report(F, fav_is_p1[band_f], "baseline: back EVERY favourite in the band")
gray_fav = (S.g1 == (~S.dog1))                      # gray picks the favourite
GF = S[band_f & gray_fav]
report(GF, (~GF.dog1), "** gray line picks the FAVOURITE **")
for Gg, nm in (("M", "men"), ("W", "women")):
    sub = S[band_f & gray_fav & (S.G == Gg)]
    report(sub, (~sub.dog1), "      %s" % nm)
GFn = S[band_f & ~gray_fav]
report(GFn, (~GFn.dog1), "control: gray picks the DOG, bet the fav anyway")
print("   tighter sub-bands (gray picks the favourite):")
for lo, hi, nm in ((-150, -100, "-100..-150"), (-200, -150, "-150..-200"),
                   (-250, -200, "-200..-250")):
    m = band_f & gray_fav & (fav_odds >= lo) & (fav_odds <= hi)
    sub = S[m]
    report(sub, (~sub.dog1), "      %s" % nm)

# ---------------------------------------------------------------- DOGS +100..+200
dog_odds = np.where(S.dog1, S.p1_odds, S.p2_odds).astype(float)
band_d = (dog_odds >= 100) & (dog_odds <= 200)
print("\n" + "=" * 110)
print("UNDERDOGS +100 .. +200")
print("=" * 110)
D = S[band_d]
report(D, D.dog1, "baseline: back EVERY dog in the band")
gray_dog = (S.g1 == S.dog1)                         # gray picks the dog
GD = S[band_d & gray_dog]
report(GD, GD.dog1, "** gray line picks the DOG **")
for Gg, nm in (("M", "men"), ("W", "women")):
    sub = S[band_d & gray_dog & (S.G == Gg)]
    report(sub, sub.dog1, "      %s" % nm)
GDn = S[band_d & ~gray_dog]
report(GDn, GDn.dog1, "control: gray picks the FAV, bet the dog anyway")
print("   tighter sub-bands (gray picks the dog):")
for lo, hi, nm in ((100, 150, "+100..+150"), (150, 200, "+150..+200")):
    m = band_d & gray_dog & (dog_odds >= lo) & (dog_odds <= hi)
    sub = S[m]
    report(sub, sub.dog1, "      %s" % nm)

print("\n" + "=" * 110)
print("SIDE SUMMARY -- the gray line everywhere, for context")
print("=" * 110)
allfav = S[S.g1 == (~S.dog1)]
report(allfav, (~allfav.dog1), "gray picks the favourite, ANY price")
alldog = S[S.g1 == S.dog1]
report(alldog, alldog.dog1, "gray picks the dog, ANY price")
