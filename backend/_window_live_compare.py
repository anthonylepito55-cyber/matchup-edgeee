"""L5 vs L10 vs THE SEASONAL (52-WEEK) WINDOW, ALL LIVE (2026-10-11, user: "What about seasonal
stat").

Third pass on the same question with the third window the card shows. `surface_stats` from
context_asof IS the seasonal line -- the 52-week-on-surface block (it falls back to the last 20
on the surface when the year is thin). Everything else is unchanged: frozen log, as-of context
so no row sees its own result, flat 1u at the frozen odds, one row per match oriented to the
dog.

All three windows are measured on the IDENTICAL match set (a row is kept only if all three are
defined for both players), so the comparison is about the window and nothing else.

Reading it: if the edge lives in the SHORT window and dies as the window widens, this is the
market overpaying for a hot streak, not a judgement about who is the better player.
"""
import numpy as np
import pandas as pd

import tennis_context as TC
import tennis_log as TL

STATS = ("sgw", "rgw")
WINDOWS = (("l5", "surface_l5", "last 5"), ("l10", "surface_l10", "last 10"),
           ("s52", "surface_stats", "seasonal 52w"))

log = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
log["date"] = pd.to_datetime(log["date"], errors="coerce")
S = log[(log["settled"] == True) & log["p1_won"].notna()      # noqa: E712
        & log["p1_odds"].notna() & log["p2_odds"].notna()].copy()
if "surface_bad" in S.columns:
    S = S[~S["surface_bad"].fillna(False).astype(bool)]

cache = {}


def ctx(nm, surf, asof):
    k = (str(nm), str(surf), str(asof)[:10])
    if k not in cache:
        try:
            cache[k] = TC.context_asof(nm, surf, asof)
        except Exception:
            cache[k] = None
    return cache[k]


def wv(c, key):
    q = (c or {}).get(key)
    if q and all(q.get(x) is not None for x in STATS):
        return float(q["sgw"]), float(q["rgw"]), int(q.get("n") or 0)
    return None


rows = []
for r in S.itertuples():
    ca, cb = ctx(r.player_1, r.surface, r.date), ctx(r.player_2, r.surface, r.date)
    vals = {}
    ok = True
    for tag, key, _ in WINDOWS:
        a, b = wv(ca, key), wv(cb, key)
        if not a or not b:
            ok = False
            break
        vals["gs1_" + tag] = a[0] - b[0]
        vals["gr1_" + tag] = a[1] - b[1]
        vals["n_" + tag] = min(a[2], b[2])
    if not ok:
        continue
    d1, d2 = TL._decimal(r.p1_odds), TL._decimal(r.p2_odds)
    if not d1 or not d2:
        continue
    i1, i2 = 1 / d1, 1 / d2
    mk1 = i1 / (i1 + i2)
    lg = str(getattr(r, "league", "") or "")
    rows.append({"dog1": mk1 < 0.5, "mk1": mk1, "d1": d1, "d2": d2, "won1": bool(r.p1_won),
                 "G": "W" if ("wta" in lg or "itf_women" in lg) else "M", "lvl": lg, **vals})
D = pd.DataFrame(rows)
print(f"settled rows with ALL THREE windows on BOTH players: {len(D)} of {len(S)} "
      f"({100 * len(D) / max(len(S), 1):.0f}%) -- identical match set for every window")
print(f"median window depth: seasonal n={D.n_s52.median():.0f} matches, "
      f"L10 n={D.n_l10.median():.0f}, L5 n={D.n_l5.median():.0f}")


def dogframe(tag):
    f = D.copy()
    p1 = f.dog1
    f["bk_odds"] = np.where(p1, f.d1, f.d2)
    f["bk_won"] = np.where(p1, f.won1, ~f.won1)
    f["bk_imp"] = np.where(p1, f.mk1, 1 - f.mk1)
    f["gs"] = np.where(p1, f["gs1_" + tag], -f["gs1_" + tag])    # the DOG's edge
    f["gr"] = np.where(p1, f["gr1_" + tag], -f["gr1_" + tag])
    return f


def rep(f, lab, floor=10):
    n = len(f)
    if n < floor:
        print(f"   {lab:38s} n={n} (too thin)")
        return
    w = f.bk_won.astype(bool)
    pnl = np.where(w, f.bk_odds - 1, -1.0)
    hit, imp = 100 * w.mean(), 100 * f.bk_imp.mean()
    se = 100 * pnl.std(ddof=1) / np.sqrt(n)
    print(f"   {lab:38s} {int(w.sum())}-{n - int(w.sum())}  dog wins {hit:4.1f}%  "
          f"no-vig {imp:4.1f}%  EDGE {hit - imp:+5.1f}pt  "
          f"ROI {100 * pnl.mean():+6.1f}% ± {se:4.1f}  (n={n})")


for tag, _key, nice in WINDOWS:
    f = dogframe(tag)
    print("\n" + "=" * 98)
    print(f"{nice.upper()} — live frozen log, backing the dog")
    print("=" * 98)
    rep(f, "every dog (baseline)")
    rep(f[(f.gs > 0) & (f.gr > 0)], "dog better on BOTH (back the leader)")
    inv = (f.gs < 0) & (f.gr < 0)
    rep(f[inv], "*** FAV better on BOTH -> back the dog")
    for Gg, gl in (("M", "men"), ("W", "women")):
        rep(f[inv & (f.G == Gg)], f"      {gl}")
    for x in (3, 5, 10):
        rep(f[(f.gs <= -x) & (f.gr <= -x)], f"      fav ahead by >= {x}pt")
    lv = f.lvl.astype(str).str.lower()
    rep(f[inv & ~lv.str.contains("chall|itf")], "      tour")
    rep(f[inv & f.bk_odds.between(2.0, 3.0)], "      priced +100..+200")

F = {t: dogframe(t) for t, _, _ in WINDOWS}
IV = {t: (F[t].gs < 0) & (F[t].gr < 0) for t in F}
print("\n" + "=" * 98)
print("WHICH WINDOW CARRIES IT? (same matches, so these cells are directly comparable)")
print("=" * 98)
print(f"   fires: L5 {int(IV['l5'].sum())} · L10 {int(IV['l10'].sum())} · "
      f"seasonal {int(IV['s52'].sum())} · all three {int((IV['l5'] & IV['l10'] & IV['s52']).sum())}")
rep(F["l5"][IV["l5"] & IV["l10"] & IV["s52"]], "all three windows agree")
rep(F["l5"][IV["l5"] & ~IV["s52"]], "L5 fires, seasonal does NOT")
rep(F["s52"][IV["s52"] & ~IV["l5"]], "seasonal fires, L5 does NOT")
rep(F["l5"][IV["l5"] & ~IV["l10"] & ~IV["s52"]], "L5 ONLY (pure hot streak)")

# ---------------------------------------------------------------------------
# CONTROL (2026-10-11): the seasonal window's standout cell is "+100..+200 dogs where the
# favourite is seasonally better on both" at +25.2%. Before that means anything it has to beat
# the BAND ITSELF -- the +100..+200 dog band is the board's best price band and may already run
# hot in a 5-week log, in which case the seasonal filter is adding nothing.
print("\n" + "=" * 98)
print("CONTROL — is the seasonal +100..+200 cell beating the BAND, or just riding it?")
print("=" * 98)
f = F["s52"]
band = f.bk_odds.between(2.0, 3.0)
rep(f[band], "ALL +100..+200 dogs (the band baseline)")
rep(f[band & IV["s52"]], "   band + fav seasonally better on both")
rep(f[band & ~IV["s52"]], "   band + fav NOT seasonally better")
rep(f[band & (f.gs > 0) & (f.gr > 0)], "   band + DOG seasonally better on both")
for Gg, gl in (("M", "men"), ("W", "women")):
    rep(f[band & IV["s52"] & (f.G == Gg)], f"   band + fav better, {gl}")
print("   same band through the other two windows, for comparison:")
rep(F["l5"][F["l5"].bk_odds.between(2.0, 3.0) & IV["l5"]], "   band + fav better on L5")
rep(F["l10"][F["l10"].bk_odds.between(2.0, 3.0) & IV["l10"]], "   band + fav better on L10")
