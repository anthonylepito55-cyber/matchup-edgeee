"""HOW DOES UNFORCED ERRORS DO FOR MEN? (2026-10-12, user ask)

The standing note says men showed no UE edge. But the WOMEN'S edge only appeared after gating
-- tour level, hard court -- so the men's side deserves the same scrutiny rather than a flat
"no". This runs every cut the store supports on `_mcp_ue_rows.parquet`, whose schema is
dog-oriented: `d_ue_set_5` is the dog's unforced errors per set over the last 5 charted
matches, `f_ue_set_5` the favourite's, `won` is whether the DOG won, `dog_odd` the dog's
decimal price.

The cell mirrors the women's lane exactly: back the DOG when it makes FEWER errors per set
than the favourite.
"""
import numpy as np
import pandas as pd

U = pd.read_parquet("data_cache/_mcp_ue_rows.parquet")
M = U[U.G.astype(str).str.upper().str[0] == "M"].copy()
W = U[U.G.astype(str).str.upper().str[0] == "W"].copy()
print("UE rows: %d total | men %d | women %d" % (len(U), len(M), len(W)))


def rep(s, lab, floor=25):
    n = len(s)
    if n < floor:
        print("   %-46s n=%d (thin)" % (lab, n))
        return
    w = s.won.astype(bool)
    pnl = np.where(w, s.dog_odd.astype(float) - 1, -1.0)
    imp = (1 - s.mkt.astype(float)) if s.mkt.mean() > 0.5 else s.mkt.astype(float)
    se = 100 * pnl.std(ddof=1) / np.sqrt(n)
    print("   %-46s %d-%d  dog wins %4.1f%%  no-vig %4.1f%%  EDGE %+5.1fpt  ROI %+6.1f%% ± %4.1f  (n=%d)"
          % (lab, int(w.sum()), n - int(w.sum()), 100 * w.mean(), 100 * imp.mean(),
             100 * (w.mean() - imp.mean()), 100 * pnl.mean(), se, n))


for G, lab in ((M, "MEN"), (W, "WOMEN (the known edge, for comparison)")):
    if G.empty:
        continue
    print("\n" + "=" * 112)
    print("%s -- back the DOG when it makes FEWER unforced errors per set" % lab)
    print("=" * 112)
    rep(G, "every dog with both UE profiles (baseline)")
    for win in (5, 10):
        c = "d_ue_set_%d" % win
        f = "f_ue_set_%d" % win
        if c not in G.columns:
            continue
        gap = G[c].astype(float) - G[f].astype(float)     # negative = dog cleaner
        rep(G[gap < 0], "   dog cleaner, last %d charted" % win)
        rep(G[gap > 0], "   dog MESSIER, last %d (control)" % win)
    gap5 = G["d_ue_set_5"].astype(float) - G["f_ue_set_5"].astype(float)
    S = G[gap5 < 0]
    print("   the cleaner-dog cell, split:")
    for lo, hi, nm in ((2.0, 2.5, "+100..+150"), (2.0, 3.5, "+100..+250"),
                       (3.5, 6.0, "+250..+500"), (6.0, 99, "+500 and longer")):
        rep(S[S.dog_odd.astype(float).between(lo, hi)], "      %s" % nm)
    for y in sorted(set(S.yr.astype(int))):
        rep(S[S.yr.astype(int) == y], "      %d" % y)
    print("   tightened by how much cleaner:")
    for x in (0, 1, 2, 3):
        rep(G[gap5 <= -x], "      at least %d fewer UE per set" % x)
