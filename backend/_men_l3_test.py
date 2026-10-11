"""DOES L3 BEAT L5? (2026-10-11, user: "can u add a l3 under the l5 as well" / "and then test l3")

Four windows on the IDENTICAL men's match set -- L3, L5, L10, seasonal 52w -- so the only thing
varying is window length. Frozen log, as-of context (strictly earlier matches on that surface),
flat 1u at frozen odds, one row per match oriented to the dog.

The L5-vs-L10 result so far: for men, backing the dog who LEADS on L5 hold/break returns +6.7%
while the same bet on L10 returns -30.1%. The reading was that a short window is mostly streak
noise and the market misprices its reaction, while a long window measures real quality that is
already in the line. If that reading is right, L3 -- noisier still -- should either continue the
trend or break it, and which one it does says whether "shorter is better" is a real gradient or
just L5 getting lucky.

Note on L3's floor: the context builder emits a short window only at 3+ matches, so L3 is
exactly three matches whenever it exists.
"""
import numpy as np
import pandas as pd

import tennis_context as TC
import tennis_log as TL

WINDOWS = (("l3", "surface_l3", "LAST 3"), ("l5", "surface_l5", "LAST 5"),
           ("l10", "surface_l10", "LAST 10"), ("s52", "surface_stats", "SEASONAL 52W"))

log = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
log["date"] = pd.to_datetime(log["date"], errors="coerce")
S = log[(log["settled"] == True) & log["p1_won"].notna()      # noqa: E712
        & log["p1_odds"].notna() & log["p2_odds"].notna()].copy()
if "surface_bad" in S.columns:
    S = S[~S["surface_bad"].fillna(False).astype(bool)]
lg = S["league"].astype(str)
S = S[~(lg.str.contains("wta") | lg.str.contains("itf_women"))]      # MEN
print("men's settled rows: %d" % len(S))

cache = {}


def ctx(nm, surf, asof):
    k = (str(nm), str(surf), str(asof)[:10])
    if k not in cache:
        try:
            cache[k] = TC.context_asof(nm, surf, asof)
        except Exception:
            cache[k] = None
    return cache[k]


def pair(c, key):
    b = (c or {}).get(key) or {}
    if b.get("sgw") is None or b.get("rgw") is None:
        return None
    return float(b["sgw"]), float(b["rgw"])


rows = []
for r in S.itertuples():
    ca, cb = ctx(r.player_1, r.surface, r.date), ctx(r.player_2, r.surface, r.date)
    vals, ok = {}, True
    for tag, key, _ in WINDOWS:
        a, b = pair(ca, key), pair(cb, key)
        if a is None or b is None:
            ok = False
            break
        vals["g_" + tag] = (a[0] + a[1]) - (b[0] + b[1])     # the SUM
        vals["h_" + tag] = a[0] - b[0]                        # hold% alone
        vals["r_" + tag] = a[1] - b[1]                        # break% alone
    if not ok:
        continue
    d1, d2 = TL._decimal(r.p1_odds), TL._decimal(r.p2_odds)
    if not d1 or not d2:
        continue
    i1, i2 = 1 / d1, 1 / d2
    rows.append({"won1": bool(r.p1_won), "mk1": i1 / (i1 + i2), "d1": d1, "d2": d2,
                 "lvl": str(r.league), **vals})
D = pd.DataFrame(rows)
print("rows with ALL FOUR windows on BOTH players: %d (%.0f%%) -- identical set per window\n"
      % (len(D), 100 * len(D) / max(len(S), 1)))
if D.empty:
    raise SystemExit("no coverage")


def dogframe(tag):
    f = D.copy()
    p1 = f.mk1 < 0.5                       # player_1 is the market dog
    f["bk_odds"] = np.where(p1, f.d1, f.d2)
    f["bk_won"] = np.where(p1, f.won1, ~f.won1)
    f["bk_imp"] = np.where(p1, f.mk1, 1 - f.mk1)
    f["gs"] = np.where(p1, f["g_" + tag], -f["g_" + tag])    # the DOG's hold+break SUM edge
    f["gh"] = np.where(p1, f["h_" + tag], -f["h_" + tag])    # the DOG's hold% edge
    f["gr"] = np.where(p1, f["r_" + tag], -f["r_" + tag])    # the DOG's break% edge
    return f


def rep(f, lab, floor=25):
    n = len(f)
    if n < floor:
        print("   %-40s n=%d (thin)" % (lab, n))
        return None
    w = f.bk_won.astype(bool)
    pnl = np.where(w, f.bk_odds - 1, -1.0)
    hit, imp = 100 * w.mean(), 100 * f.bk_imp.mean()
    se = 100 * pnl.std(ddof=1) / np.sqrt(n)
    print("   %-40s %d-%d  dog wins %4.1f%%  no-vig %4.1f%%  EDGE %+5.1fpt  "
          "ROI %+6.1f%% +/- %4.1f  (n=%d)"
          % (lab, int(w.sum()), n - int(w.sum()), hit, imp, hit - imp,
             100 * pnl.mean(), se, n))
    return 100 * pnl.mean()


print("=" * 108)
print("MEN -- THE SAME TWO BETS THROUGH FOUR WINDOW LENGTHS")
print("=" * 108)
rep(dogframe("l5"), "every dog (baseline, window-independent)")
print()
for tag, _k, nice in WINDOWS:
    f = dogframe(tag)
    print("   %s:" % nice)
    rep(f[f.gs > 0], "      back the dog who LEADS on hold+break")
    rep(f[f.gs < 0], "      back the dog when the FAV leads")

print("\n" + "=" * 108)
print("THE CELL THE EARLIER L5-vs-L10 CALL USED: better on BOTH hold% AND break% (not the sum)")
print("=" * 108)
for tag, _k, nice in WINDOWS:
    f = dogframe(tag)
    print("   %s:" % nice)
    rep(f[(f.gh > 0) & (f.gr > 0)], "      DOG better on both -> back the dog")
    rep(f[(f.gh < 0) & (f.gr < 0)], "      FAV better on both -> back the dog")
print()
print("   and the SUM version of the same windows, for contrast:")
for tag, _k, nice in WINDOWS:
    f = dogframe(tag)
    rep(f[f.gs > 0], "      %-14s dog leads on the sum" % nice)

print("\n" + "=" * 108)
print("L3 vs L5 HEAD TO HEAD -- where they disagree")
print("=" * 108)
f3, f5 = dogframe("l3"), dogframe("l5")
lead3, lead5 = f3.gs > 0, f5.gs > 0
print("   dog leads on: L3 %d · L5 %d · both %d · L3 only %d · L5 only %d"
      % (int(lead3.sum()), int(lead5.sum()), int((lead3 & lead5).sum()),
         int((lead3 & ~lead5).sum()), int((lead5 & ~lead3).sum())))
rep(f3[lead3 & lead5], "   both windows say the dog leads")
rep(f3[lead3 & ~lead5], "   L3 says lead, L5 does not (hot last 3)")
rep(f5[lead5 & ~lead3], "   L5 says lead, L3 does not (cooling)")

print("\n" + "=" * 108)
print("DOES L3 PICK WINNERS AT ALL? (all games, not just dogs)")
print("=" * 108)
for tag, _k, nice in WINDOWS:
    f = D[D["g_" + tag] != 0]
    sp = f["g_" + tag] > 0
    hit = (sp == f.won1).mean()
    mkt = ((f.mk1 > 0.5) == f.won1).mean()
    imp = np.where(sp, f.mk1, 1 - f.mk1).mean()
    se = np.sqrt(hit * (1 - hit) / len(f))
    print("   %-14s leader wins %5.1f%% +/- %3.1f   market, same rows %5.1f%%   EDGE %+5.1fpt  (n=%d)"
          % (nice, 100 * hit, 100 * se, 100 * mkt, 100 * (hit - imp), len(f)))
