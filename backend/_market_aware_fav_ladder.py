"""THE MARKET-AWARE HEADS on favourites, full threshold ladder (2026-10-13).

The previous ranking carried only two of these -- C's gray and D's gray -- and left A-MA, B-MA,
G-MA and G2-MA out entirely. They belong in the comparison, because a market-aware head is a
different animal: it takes the market's log-odds as a fixed baseline and only learns where the
price is wrong, so it starts from the right answer and can only add. That is exactly why the two
that were in the table were the only heads above chalk at a loose gate, and it makes the whole
family worth reading together.

One cell: back the market FAVOURITE when the head sits N points over the market's own de-vigged
number, N from 1 to 8. Against backing every favourite on each head's own rows.

A market-aware head sitting far over the market is a strange object -- it was handed the price
and chose to depart from it anyway -- so the tight end of this ladder is the interesting part.
"""
import numpy as np
import pandas as pd

import tennis_log

MA = [("A-MA", "model_ama_p1"), ("B-MA", "model_bma_p1"),
      ("C-MA (gray)", "model_cma_p1"), ("D-MA (gray)", "model_dma_p1"),
      ("G-MA", "model_gma_p1"), ("G2-MA", "model_g2ma_p1")]
RAW = [("A", "model_a_p1"), ("B", "model_b_p1"), ("C", "model_c_p1"),
       ("D", "model_d_p1"), ("G", "model_g_p1"), ("G2", "model_g2_p1")]

L = pd.read_parquet(tennis_log.LOG_PATH)
d = L[(L["settled"] == True) & L["p1_won"].notna()                      # noqa: E712
      & L["p1_odds"].notna() & L["p2_odds"].notna()].copy()
for c in ("surface_bad", "inplay_suspect"):
    if c in d.columns:
        d = d[~d[c].fillna(False).astype(bool)]
print("settled, clean rows: %d  (%s .. %s)"
      % (len(d), str(d["date"].min())[:10], str(d["date"].max())[:10]))
print("market-aware columns present: %s"
      % [lab for lab, c in MA if c in d.columns])


def dec(a):
    a = float(a)
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


d1, d2 = d["p1_odds"].map(dec).to_numpy(), d["p2_odds"].map(dec).to_numpy()
mk1 = (1 / d1) / ((1 / d1) + (1 / d2))
won1 = d["p1_won"].astype(bool).to_numpy()
fav1 = mk1 >= 0.5
mkfav = np.where(fav1, mk1, 1 - mk1)
favodd = np.where(fav1, d1, d2)
favwon = np.where(fav1, won1, ~won1)
favpnl = np.where(favwon, favodd - 1, -1.0)
gend = np.where(d["league"].astype(str).isin(["wta", "itf_women"]), "W", "M")
TH = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08]


def ladder(col):
    pv = pd.to_numeric(d[col], errors="coerce").to_numpy(dtype=float)
    have = ~np.isnan(pv)
    hfav = np.where(fav1, pv, 1 - pv)
    out = []
    for t in TH:
        m = have & ((hfav - mkfav) >= t)
        n = int(m.sum())
        out.append((n, 100 * favpnl[m].mean() if n else None))
    chalk = 100 * favpnl[have].mean() if have.sum() else None
    return out, chalk, int(have.sum())


print("\n" + "=" * 104)
print("MARKET-AWARE HEADS -- favourite, ROI by minimum margin over the market")
print("=" * 104)
hdr = "%-14s" % "head" + "".join("%12s" % ("%.0fpt+" % (100 * t)) for t in TH) + "   chalk"
print(hdr)
for lab, col in MA:
    if col not in d.columns:
        print("%-14s (column absent)" % lab)
        continue
    rows, chalk, cov = ladder(col)
    line = "%-14s" % lab
    for n, roi in rows:
        line += "%12s" % (("%+.1f/%d" % (roi, n)) if roi is not None else "--")
    line += "   %+.2f%% (n=%d)" % (chalk, cov)
    print(line)

print("\nthe same for the RAW heads they are built from, for the contrast:")
for lab, col in RAW:
    if col not in d.columns:
        continue
    rows, chalk, cov = ladder(col)
    line = "%-14s" % lab
    for n, roi in rows:
        line += "%12s" % (("%+.1f/%d" % (roi, n)) if roi is not None else "--")
    line += "   %+.2f%% (n=%d)" % (chalk, cov)
    print(line)

print("\n(cell reads ROI%/n at that threshold)")

# the paired question: on the SAME rows, does the market-aware twin beat its raw parent?
print("\n" + "=" * 104)
print("PAIRED -- market-aware vs its raw parent, 1pt+ gate, on rows where BOTH priced the match")
print("=" * 104)
for (lab, mcol), (rlab, rcol) in zip(MA, RAW):
    if mcol not in d.columns or rcol not in d.columns:
        continue
    pm = pd.to_numeric(d[mcol], errors="coerce").to_numpy(dtype=float)
    pr = pd.to_numeric(d[rcol], errors="coerce").to_numpy(dtype=float)
    both = ~np.isnan(pm) & ~np.isnan(pr)
    hm = np.where(fav1, pm, 1 - pm)
    hr = np.where(fav1, pr, 1 - pr)
    sm = both & ((hm - mkfav) >= 0.01)
    sr = both & ((hr - mkfav) >= 0.01)
    f = lambda m: ("n=%-4d %+7.2f%%" % (int(m.sum()), 100 * favpnl[m].mean())) if m.sum() else "--"
    print("   %-14s MA %-22s raw %-22s chalk %+.2f%% (n=%d)"
          % (lab.split()[0], f(sm), f(sr), 100 * favpnl[both].mean(), int(both.sum())))

print("\n" + "=" * 104)
print("BEST market-aware cell, by gender, at the gate where each peaks")
print("=" * 104)
for lab, col in MA:
    if col not in d.columns:
        continue
    pv = pd.to_numeric(d[col], errors="coerce").to_numpy(dtype=float)
    have = ~np.isnan(pv)
    hfav = np.where(fav1, pv, 1 - pv)
    best = None
    for t in TH:
        m = have & ((hfav - mkfav) >= t)
        if m.sum() >= 40:
            roi = 100 * favpnl[m].mean()
            if best is None or roi > best[1]:
                best = (t, roi, m)
    if not best:
        continue
    t, roi, m = best
    line = "   %-14s peaks at %.0fpt+ : %+.2f%% on %d" % (lab, 100 * t, roi, int(m.sum()))
    for g in ("M", "W"):
        q = m & (gend == g)
        if q.sum():
            line += "   %s %+.1f%%/%d" % (g, 100 * favpnl[q].mean(), int(q.sum()))
    print(line)
