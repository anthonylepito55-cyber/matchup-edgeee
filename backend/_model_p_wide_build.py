"""MODEL P, WIDE BAND (2026-10-13, user: "and model p can go over -250 and over +250 now").

WHAT CHANGES. P's universe is market dogs at decimal 2.0-3.5 (+100..+250), with the favourite
side gated separately to 1.5-2.0 (-200..+100). Both of the user's asks are the same widening,
because a dog longer than +250 IS a favourite shorter than -250 on the other side of the match:

    dogs      2.0 .. 6.0 decimal   (+100 .. +500)
    favourites the paired side      (-100 .. -500)

WHY RETRAIN RATHER THAN JUST LIFT THE FILTER. P is an OFFSET model, logit(P) = logit(market) +
b.x, fitted only on +100..+250 dogs. Lifting the runtime band would apply those coefficients to
prices the model has never seen -- extrapolation, and exactly the kind of thing that produces a
good backtest and a dead lane. So the universe is widened at TRAINING time and the walk-forward
is re-run from scratch, with the same two-level discipline: base models C and D are fitted on
years < Y to produce year-Y probabilities, and P for year Y sees only P-rows from years < Y.

WHAT THIS HAS TO BEAT TO SHIP. The measured prior is NOT encouraging and is stated up front so
the result is read honestly:
  * _market_bias_by_price.py found a favourite-longshot bias that runs AGAINST the dog extension.
    +250..+400 is overpriced by -1.7pt and +400+ by -2.2pt, while -400-and-shorter is UNDERpriced
    by +2.1pt. So the dog extension reaches into the market's worst-value region and the
    favourite extension reaches into its best.
  * That predicts the favourite extension should look better than the dog extension. If instead
    the dog extension backtests well, treat it as suspect rather than as a finding.

Reported per band, per gender, per year, so nothing hides inside a pooled average. Two extensions
are judged SEPARATELY and will be registered as separate lanes -- the user asked for both, but
they are different bets and one can pay while the other does not.

Run: ./venv/bin/python _model_p_wide_build.py
"""
import io
import os
import re

import numpy as np
import pandas as pd

SRC = "_model_p250_build.py"
src = io.open(SRC, encoding="utf-8").read()

# ---- widen the training universe -------------------------------------------------------
old = 'base["player_odd"].between(2.0, 3.5)'
assert src.count(old) == 1
src = src.replace(old, 'base["player_odd"].between(2.0, 6.0)')

# ---- keep the live artifacts untouched: different output paths -------------------------
src = src.replace('"data_cache/_model_p250_rows.parquet"', '"data_cache/_model_pwide_rows.parquet"')
src = src.replace('"data_cache/_model_p250_oos.parquet"', '"data_cache/_model_pwide_oos.parquet"')
for bad in ("model_artifacts", "_model_p250_rows.parquet", "_model_p250_oos.parquet"):
    assert bad not in src, "would touch a live Model P artifact: %s" % bad

# ---- stop before its own reporting; this file does the band work -----------------------
cut = 'print("==================== BY PRICE BAND'
assert src.count(cut) == 1
src = src.split(cut)[0]

g = {"__name__": "__pwide__", "__file__": SRC}
exec(compile(src, SRC + "(wide)", "exec"), g)                      # noqa: S102
O = g["O"].copy()
rep = g["rep"]

O["am"] = (O.player_odd - 1) * 100
# the favourite's own price, from the paired side of the same match
O["fav_dec"] = 1.0 / np.clip(1.0 - (1.0 / O.player_odd), 1e-6, 1.0)
O["fav_am"] = -100.0 / np.clip(O.fav_dec - 1.0, 1e-6, None)
# betting the FAVOURITE instead: P's own probability for that side, at the paired price
O["fav_p"] = 1.0 - O.pP
O["fav_ev"] = O.fav_p * O.fav_dec - 1.0

BAR = "=" * 102
print("\n" + BAR)
print("UNIVERSE AFTER WIDENING -- what the extension actually adds")
print(BAR)
for lo, hi, lab in ((100, 200, "+100..+200 (original men)"), (200, 250, "+200..+250 (original W)"),
                    (250, 400, "+250..+400 NEW"), (400, 1e9, "+400 and longer NEW")):
    m = O.am.between(lo, hi)
    print("   %-26s n=%-6d  men %-5d women %-5d  win %4.1f%%"
          % (lab, int(m.sum()), int((m & (O.G == "M")).sum()), int((m & (O.G == "W")).sum()),
             100 * O.won[m].mean() if m.sum() else float("nan")))

print("\n" + BAR)
print("1. THE DOG EXTENSION -- backing the dog above +250, by band, out of sample")
print("   the market measurement says this region is OVERpriced by 1.7-2.2pt, so a good")
print("   number here is suspicious rather than welcome")
print(BAR)
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    print("   %s" % gl)
    for lo, hi, lab in ((100, 250, "+100..+250 (shipped)"), (250, 400, "+250..+400 NEW"),
                        (400, 1e9, "+400+ NEW"), (250, 1e9, "everything above +250 NEW")):
        T = O[(O.G == G) & O.am.between(lo, hi)]
        if len(T) < 30:
            print("      %-28s n=%d (thin)" % (lab, len(T)))
            continue
        print("      %-28s every dog %s" % (lab, rep(T.won.values, T.player_odd.values)))
        for thr in (0.05, 0.10):
            s = T[T.ev > thr]
            print("         P EV > %2d%%%s%s" % (int(thr * 100), " " * 16,
                                                 rep(s.won.values, s.player_odd.values)))
        for y in (2024, 2025, 2026):
            s = T[(T.yr == y) & (T.ev > 0.05)]
            print("            %d EV>5%%        %s" % (y, rep(s.won.values, s.player_odd.values, 15)))

print("\n" + BAR)
print("2. THE FAVOURITE EXTENSION -- backing the FAVOURITE below -250, at the paired price")
print("   shipped gate is 1.5-2.0 decimal (-200..+100) and EV >= 3%. This is the region the")
print("   market measurement says is UNDERpriced, so it is the better-motivated half")
print(BAR)
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    print("   %s" % gl)
    for lo, hi, lab in ((-250, -100, "-100..-250 (shipped zone)"), (-400, -250, "-250..-400 NEW"),
                        (-1e9, -400, "-400 and shorter NEW"), (-1e9, -250, "everything below -250 NEW")):
        T = O[(O.G == G) & O.fav_am.between(lo, hi)]
        if len(T) < 30:
            print("      %-28s n=%d (thin)" % (lab, len(T)))
            continue
        fw = ~T.won.values.astype(bool)          # the favourite wins when the dog loses
        print("      %-28s every fav %s" % (lab, rep(fw, T.fav_dec.values)))
        for thr in (0.03, 0.05):
            s = T[T.fav_ev > thr]
            print("         P fav EV > %d%%%s%s" % (int(thr * 100), " " * 14,
                                                    rep(~s.won.values.astype(bool),
                                                        s.fav_dec.values)))
        for y in (2024, 2025, 2026):
            s = T[(T.yr == y) & (T.fav_ev > 0.03)]
            print("            %d EV>3%%        %s" % (y, rep(~s.won.values.astype(bool),
                                                              s.fav_dec.values, 15)))

print("\n" + BAR)
print("3. DID WIDENING THE TRAINING SET DAMAGE THE ORIGINAL BAND? the question that decides")
print("   whether this can ship as ONE model or has to be a second artifact")
print(BAR)
try:
    OLD = pd.read_parquet("data_cache/_model_p250_oos.parquet")
    OLD["am"] = (OLD.player_odd - 1) * 100
    for G, gl in (("M", "MEN"), ("W", "WOMEN")):
        for lo, hi, lab in ((100, 200, "+100..+200"), (200, 250, "+200..+250")):
            a = OLD[(OLD.G == G) & OLD.am.between(lo, hi)]
            b = O[(O.G == G) & O.am.between(lo, hi)]
            if len(a) < 30 or len(b) < 30:
                continue
            sa, sb = a[a.ev > 0.05], b[b.ev > 0.05]
            print("   %-6s %-12s narrow-trained %s" % (gl, lab,
                                                       rep(sa.won.values, sa.player_odd.values)))
            print("   %-6s %-12s   wide-trained %s" % ("", "",
                                                       rep(sb.won.values, sb.player_odd.values)))
except FileNotFoundError:
    print("   (no saved narrow out-of-sample file to compare against)")

print("\n" + BAR)
print("READ: the dog extension and the favourite extension are separate decisions. Ship only")
print("the half that clears its own bar in BOTH genders it is claimed for and in every year.")
print(BAR)
