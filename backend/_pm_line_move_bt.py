"""LINE-MOVEMENT BACKTEST (2026-10-09, user: "follow market line movements and backtest
the hit rate on that for underdogs and favorites"). Data: _pm_tennis_line_backfill.py (v2, full paths)
(settled Polymarket tennis singles, >= $500 traded, real price paths).

For every match the FAVOURITE is the side >= 50% at the close (last sane quote >= 10 min
before the start). Move = favourite's close prob - its open prob (+ = money came in on the
favourite / it shortened; - = it drifted, money on the dog). For each move bucket:
hit rate, the close-implied rate, ROI at the CLOSE price and ROI if you had bet at the
OPEN price, for the favourite and for the dog. Polymarket prices carry almost no vig, so
ROI here is close to "edge vs a fair price"; real fills cost ~1-2c of spread.
"""
import numpy as np
import pandas as pd

import json
D = pd.read_parquet("data_cache/pm_tennis_lines_v2.parquet")
D = D[D["open"].notna() & D["close"].notna() & D["path"].notna()].copy()
# REAL EARLY LINE: Polymarket tennis markets open at a ~50/50 placeholder before anyone
# trades, so the first quote is not a line. "open" here = first quote >= 1h after the
# first quote (trading has formed), and it must sit >= 30 min before the close quote.


def _early(row, lag=3600):
    """First REAL line: find the first trade (price moves >= 2pt off the opening
    placeholder), then take the quote 1h after it; must be >= 30 min before the close."""
    pts = json.loads(row["path"])
    p0 = pts[0][1]
    t_trade = next((t for t, p in pts if abs(p - p0) >= 0.02), None)
    if t_trade is None:
        return np.nan
    c = [p for t, p in pts if t >= t_trade + lag and t <= row["close_t"] - 1800]
    return c[0] if c else np.nan


D["open"] = D.apply(_early, axis=1)
D = D[D["open"].notna()].copy()
slug = D["slug"].astype(str)
D["G"] = np.where(slug.str.startswith("wta"), "W", np.where(slug.str.startswith("atp"), "M",
                  np.where(D["g_title"].isin(["W", "M"]), D["g_title"], "?")))
f1 = D["close"] >= 0.5
D["fav_close"] = np.where(f1, D["close"], 1 - D["close"])
D["fav_open"] = np.where(f1, D["open"], 1 - D["open"])
D["fav_p6"] = np.where(f1, D["p6"], 1 - D["p6"])
D["fav_won"] = np.where(f1, D["p1_won"], ~D["p1_won"].astype(bool)).astype(bool)
D["move"] = D["fav_close"] - D["fav_open"]
D["late"] = D["fav_close"] - D["fav_p6"]
print(f"matches {len(D)} | {D['start'].min():%Y-%m-%d}..{D['start'].max():%Y-%m-%d} | "
      f"men {int((D.G == 'M').sum())} women {int((D.G == 'W').sum())} unknown {int((D.G == '?').sum())} | "
      f"ITF {int((D.lvl == 'itf').sum())} tour {int((D.lvl == 'tour').sum())}")

BK = [(-1, -0.08, "fav DRIFTED 8pt+"), (-0.08, -0.04, "fav drifted 4-8pt"), (-0.04, -0.01, "fav drifted 1-4pt"),
      (-0.01, 0.01, "flat (+-1pt)"), (0.01, 0.04, "fav shortened 1-4pt"), (0.04, 0.08, "fav shortened 4-8pt"),
      (0.08, 1, "fav SHORTENED 8pt+")]


def roi(won, p):
    return 100 * np.where(won, 1 / p - 1, -1).mean()


def table(T, col="move", title=""):
    print(f"\n  {title} (n={len(T)})")
    print(f"  {'move':22s} {'n':>5s} | {'FAV hit':>7s} {'implied':>7s} {'ROI@close':>9s} {'ROI@open':>8s} | {'DOG hit':>7s} {'ROI@close':>9s} {'ROI@open':>8s}")
    fw0 = T.fav_won.values
    print(f"  {'BASELINE (every match)':22s} {len(T):5d} | {100*fw0.mean():6.1f}% {100*T.fav_close.mean():6.1f}% {roi(fw0, T.fav_close.values):+8.1f}% "
          f"{'':>8s} | {100*(~fw0).mean():6.1f}% {roi(~fw0, 1 - T.fav_close.values):+8.1f}%")
    for lo, hi, lab in BK:
        s = T[(T[col] > lo) & (T[col] <= hi)]
        if len(s) < 30:
            print(f"  {lab:22s} {len(s):5d} | thin")
            continue
        fw = s.fav_won.values
        print(f"  {lab:22s} {len(s):5d} | {100*fw.mean():6.1f}% {100*s.fav_close.mean():6.1f}% {roi(fw, s.fav_close.values):+8.1f}% "
              f"{roi(fw, s.fav_open.values):+7.1f}% | {100*(~fw).mean():6.1f}% {roi(~fw, 1 - s.fav_close.values):+8.1f}% "
              f"{roi(~fw, 1 - s.fav_open.values):+7.1f}%")


table(D, title="ALL MATCHES, open -> close")
for G, gl in (("M", "MEN"), ("W", "WOMEN")):
    table(D[D.G == G], title=f"{gl}, open -> close")
for lv in ("itf", "tour"):
    table(D[D.lvl == lv], title=f"{lv.upper()}, open -> close")
L6 = D[D.fav_p6.notna()]
table(L6, col="late", title="LAST 6 HOURS ONLY (T-6h -> close), all")

# within the +100..+200 dog band specifically (where the board lives)
B = D[(1 - D.fav_close).between(1 / 3, 0.5)]
table(B, title="DOG +100..+200 at the close, open -> close")
