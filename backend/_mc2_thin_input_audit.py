"""DOES MC2 LOSE WHEN ITS STAT INPUTS ARE THIN OR STALE? (2026-10-13, v2)

Prompted by Facundo Diaz Acosta on 2026-10-11, where the user spotted the problem by eye:

    hard court, 52 weeks     Diaz Acosta        Mochizuki
    matches                  8                  47
    service points           128                975
    service games won        80.0%              67.1%

His serve reads 13 points better off an eighth of the sample, and MC2 was the only head above
the market on him. MC2's engine is a point-level Markov chain driven by serve/return rates, and
the standard error on a 71% serve-point rate is 4.0pp at 128 points against 1.45pp at 975 -- so
a thin line does not just add noise, it feeds a confident-looking wrong rate into a chain that
amplifies small serve differences.

v1 of this script read sample size off a top-level "n" that does not exist, so its THIN flag
fired on 100% of rows and only the staleness split was readable. The 52-week block is
`surface_stats`, with `n` (matches), `svp_n` (service points) and `rtp_n` (return points).

Nothing about sample size is frozen in the log, so both players' context is RECONSTRUCTED as of
each match date via tennis_context.context_asof -- the same leak-free path the replay engine
uses. Forward rows and the walk-forward backfill are reported separately: forward is the record,
the backfill is there because MC2's forward sample only starts 2026-10-08 and a fix decision
needs more than a few hundred rows.
"""
import sys

import numpy as np
import pandas as pd

import tennis_context as TC
import tennis_log

STALE_D = 540

L = pd.read_parquet(tennis_log.LOG_PATH)
d = L[L["mc2_p1"].notna() & L["p1_odds"].notna() & L["p2_odds"].notna()
      & L["p1_won"].notna() & (L["settled"] == True)].copy()       # noqa: E712
for c in ("surface_bad", "inplay_suspect"):
    if c in d.columns:
        d = d[~d[c].fillna(False).astype(bool)]
d = d.reset_index(drop=True)
rc = (d["mc2_recon"].fillna(False).astype(bool).to_numpy()
      if "mc2_recon" in d.columns else np.zeros(len(d), bool))
FWD = ~rc
print("settled MC2 rows: %d  (forward %d, backfill %d)  %s .. %s"
      % (len(d), int(FWD.sum()), int(rc.sum()),
         str(d["date"].min())[:10], str(d["date"].max())[:10]))
print("reconstructing context for %d player-matches ..." % (2 * len(d)))


def meas(name, surface, asof):
    """-> (matches52, service_points, stretch_days)"""
    try:
        c = TC.context_asof(str(name), surface, asof) or {}
    except Exception:                                              # noqa: BLE001
        return None, None, None
    ss = c.get("surface_stats") or {}
    n52 = ss.get("n")
    svpn = ss.get("svp_n")
    frm = (c.get("surface_l10") or {}).get("from")
    stretch = None
    if frm:
        try:
            stretch = (pd.Timestamp(asof) - pd.Timestamp(frm)).days
        except Exception:                                          # noqa: BLE001
            stretch = None
    return (float(n52) if n52 is not None else None,
            float(svpn) if svpn is not None else None, stretch)


rows = []
for i, r in d.iterrows():
    day = str(r["date"])[:10]
    sf = r.get("surface")
    rows.append(meas(r["player_1"], sf, day) + meas(r["player_2"], sf, day))
    if (i + 1) % 300 == 0:
        print("   %d/%d" % (i + 1, len(d)))
        sys.stdout.flush()
M = pd.DataFrame(rows, columns=["n1", "v1", "s1", "n2", "v2", "s2"])
for c in M.columns:
    d[c] = M[c].to_numpy()

nmin = np.fmin(d["n1"].fillna(0).to_numpy(), d["n2"].fillna(0).to_numpy())
vmin = np.fmin(d["v1"].fillna(0).to_numpy(), d["v2"].fillna(0).to_numpy())
smax = np.fmax(d["s1"].fillna(0).to_numpy(), d["s2"].fillna(0).to_numpy())
have = d["n1"].notna().to_numpy() & d["n2"].notna().to_numpy()
print("\ncoverage: both sides have a 52w surface block on %d of %d rows (%.0f%%)"
      % (int(have.sum()), len(d), 100 * have.mean()))
print("thinner side, 52w matches : median %.0f | p10 %.0f | p25 %.0f"
      % (np.median(nmin[have]), np.percentile(nmin[have], 10), np.percentile(nmin[have], 25)))
print("thinner side, service pts : median %.0f | p10 %.0f | p25 %.0f"
      % (np.median(vmin[have]), np.percentile(vmin[have], 10), np.percentile(vmin[have], 25)))
print("L10 stretch days          : median %.0f | p75 %.0f | p90 %.0f | max %.0f"
      % (np.median(smax), np.percentile(smax, 75), np.percentile(smax, 90), smax.max()))


def dec(a):
    a = float(a)
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


o1 = d["p1_odds"].map(dec).to_numpy()
o2 = d["p2_odds"].map(dec).to_numpy()
mk1 = (1 / o1) / ((1 / o1) + (1 / o2))
pv = d["mc2_p1"].astype(float).to_numpy()
won1 = d["p1_won"].astype(bool).to_numpy()
fav1 = mk1 >= 0.5
mkfav = np.where(fav1, mk1, 1 - mk1)
mcfav = np.where(fav1, pv, 1 - pv)
over = mcfav - mkfav
favodd = np.where(fav1, o1, o2)
dogodd = np.where(fav1, o2, o1)
favwon = np.where(fav1, won1, ~won1)
favpnl = np.where(favwon, favodd - 1, -1.0)
dogpnl = np.where(~favwon, dogodd - 1, -1.0)
side_pnl = np.where(over > 0, favpnl, dogpnl)
side_hit = np.where(over > 0, favwon, ~favwon)
brier = (pv - won1.astype(float)) ** 2
mkbrier = (mk1 - won1.astype(float)) ** 2


def two(lab, m):
    def one(q):
        n = int(q.sum())
        if not n:
            return "%-24s" % "      --"
        p = side_pnl[q]
        se = 100 * p.std() / np.sqrt(n) if n > 1 else float("nan")
        return "n=%-4d %+7.2f%% +/-%4.1f" % (n, 100 * p.mean(), se)
    print("   %-28s %-26s %s" % (lab, one(m), one(m & FWD)))


BAR = "=" * 88
print("\n" + BAR)
print("MC2's OWN SIDE, by the THINNER player's 52-week match count on this surface")
print(BAR)
print("   %-28s %-26s %s" % ("cell", "ALL rows", "FORWARD only"))
for lo, hi in ((0, 10), (10, 15), (15, 20), (20, 30), (30, 10000)):
    two("%d-%d matches" % (lo, hi), have & (nmin >= lo) & (nmin < hi))
two("-- all rows with a block --", have)
print("\n   cumulative, the shape a gate would use:")
for t in (10, 12, 15, 20):
    two("thinner side < %d" % t, have & (nmin < t))
    two("thinner side >= %d" % t, have & (nmin >= t))

print("\n" + BAR)
print("MC2's OWN SIDE, by the THINNER player's SERVICE-POINT count (the Markov denominator)")
print(BAR)
print("   %-28s %-26s %s" % ("cell", "ALL rows", "FORWARD only"))
for lo, hi in ((0, 200), (200, 400), (400, 600), (600, 1000), (1000, 1000000)):
    two("%d-%d svc pts" % (lo, hi), have & (vmin >= lo) & (vmin < hi))
print("\n   cumulative:")
for t in (200, 300, 400, 500):
    two("thinner side < %d pts" % t, have & (vmin < t))
    two("thinner side >= %d pts" % t, have & (vmin >= t))

print("\n" + BAR)
print("MC2's OWN SIDE, by how far the L10 window had to STRETCH (staleness)")
print(BAR)
print("   %-28s %-26s %s" % ("cell", "ALL rows", "FORWARD only"))
for lo, hi in ((0, 180), (180, 365), (365, 540), (540, 730), (730, 100000)):
    two("stretch %d-%dd" % (lo, hi), (smax >= lo) & (smax < hi))
print("\n   cumulative:")
for t in (365, 450, 540, 730):
    two("stretch > %dd" % t, smax > t)
    two("stretch <= %dd" % t, smax <= t)

print("\n" + BAR)
print("ACCURACY -- Brier vs the market on the same rows (lower is better)")
print(BAR)
for lab, m in (("thinner side < 10 matches", have & (nmin < 10)),
               ("thinner side >= 20 matches", have & (nmin >= 20)),
               ("stretch > 540d", smax > 540),
               ("stretch <= 365d", smax <= 365)):
    n = int(m.sum())
    if not n:
        continue
    print("   %-28s n=%-4d MC2 %.4f  market %.4f  gap %+.4f"
          % (lab, n, brier[m].mean(), mkbrier[m].mean(),
             brier[m].mean() - mkbrier[m].mean()))

print("\n" + BAR)
print("OVERCONFIDENCE -- does MC2 depart from the price MORE when its inputs are thin?")
print(BAR)
for lab, m in (("thinner side < 10 matches", have & (nmin < 10)),
               ("thinner side 10-20", have & (nmin >= 10) & (nmin < 20)),
               ("thinner side >= 20", have & (nmin >= 20)),
               ("stretch > 540d", smax > 540),
               ("stretch <= 365d", smax <= 365)):
    n = int(m.sum())
    if not n:
        continue
    print("   %-28s n=%-4d mean |MC2-mkt| %5.2fpt   p90 %5.2fpt"
          % (lab, n, 100 * np.abs(over[m]).mean(), 100 * np.percentile(np.abs(over[m]), 90)))

d[["date", "player_1", "player_2", "surface", "n1", "n2", "v1", "v2", "s1", "s2",
   "mc2_p1", "p1_odds", "p2_odds", "p1_won"]].to_parquet("_mc2_thin_audit_rows.parquet",
                                                         index=False)
print("\nper-row measures saved to _mc2_thin_audit_rows.parquet")
