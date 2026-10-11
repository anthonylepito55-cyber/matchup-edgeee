"""THE SAME LIVE TEST ON THE L10 WINDOW (2026-10-11, user: "What about l10").

Identical to _l5_live.py -- frozen log, as-of context (no hindsight), flat 1u at frozen odds --
but reading `surface_l10` instead of `surface_l5`, and printing BOTH windows side by side on the
SAME matches so the comparison is not confounded by coverage differences.

The question the comparison answers: is "fade the player with the better recent hold/break" a
property of the noisy 5-match window (i.e. the market overreacting to a hot streak) or of
recent form in general? If L10 is as strong or stronger, it is the latter.
"""
import numpy as np
import pandas as pd

import tennis_context as TC
import tennis_log as TL

STATS = ("sgw", "rgw")
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


def win(c, tag):
    q = (c or {}).get("surface_" + tag)
    if q and all(q.get(x) is not None for x in STATS):
        return float(q["sgw"]), float(q["rgw"])
    return None


rows = []
for r in S.itertuples():
    ca, cb = ctx(r.player_1, r.surface, r.date), ctx(r.player_2, r.surface, r.date)
    a5, b5 = win(ca, "l5"), win(cb, "l5")
    a10, b10 = win(ca, "l10"), win(cb, "l10")
    if not (a5 and b5 and a10 and b10):     # same matches for both windows
        continue
    d1, d2 = TL._decimal(r.p1_odds), TL._decimal(r.p2_odds)
    if not d1 or not d2:
        continue
    i1, i2 = 1 / d1, 1 / d2
    mk1 = i1 / (i1 + i2)
    lg = str(getattr(r, "league", "") or "")
    rows.append({"dog1": mk1 < 0.5, "mk1": mk1, "d1": d1, "d2": d2, "won1": bool(r.p1_won),
                 "G": "W" if ("wta" in lg or "itf_women" in lg) else "M", "lvl": lg,
                 "gs1_l5": a5[0] - b5[0], "gr1_l5": a5[1] - b5[1],
                 "gs1_l10": a10[0] - b10[0], "gr1_l10": a10[1] - b10[1]})
D = pd.DataFrame(rows)
print(f"settled rows with BOTH windows on BOTH players: {len(D)} of {len(S)} settled "
      f"({100 * len(D) / max(len(S), 1):.0f}%)  -- identical match set for L5 and L10")


def dogframe(tag):
    """One row per match, oriented to BACKING THE DOG; gs/gr = the DOG's edge in window tag."""
    f = D.copy()
    p1 = f.dog1
    f["bk_odds"] = np.where(p1, f.d1, f.d2)
    f["bk_won"] = np.where(p1, f.won1, ~f.won1)
    f["bk_imp"] = np.where(p1, f.mk1, 1 - f.mk1)
    f["gs"] = np.where(p1, f["gs1_" + tag], -f["gs1_" + tag])
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


for tag in ("l5", "l10"):
    f = dogframe(tag)
    print("\n" + "=" * 98)
    print(f"{tag.upper()} — BACKING THE DOG (live frozen log, flat 1u at frozen odds)")
    print("=" * 98)
    rep(f, "every dog (baseline)")
    rep(f[(f.gs > 0) & (f.gr > 0)], "dog better on BOTH")
    rep(f[(f.gs < 0) & (f.gr < 0)], "*** FAV better on BOTH -> back the dog")
    inv = (f.gs < 0) & (f.gr < 0)
    for Gg, gl in (("M", "men"), ("W", "women")):
        rep(f[inv & (f.G == Gg)], f"      {gl}")
    for x in (3, 5, 10):
        rep(f[(f.gs <= -x) & (f.gr <= -x)], f"      fav ahead by >= {x}pt")
    lv = f.lvl.astype(str).str.lower()
    rep(f[inv & ~lv.str.contains("chall|itf")], "      tour")
    rep(f[inv & f.bk_odds.between(2.0, 3.0)], "      priced +100..+200")

# do the two windows even disagree? if they rank the same way, L10 adds nothing
f5, f10 = dogframe("l5"), dogframe("l10")
inv5 = (f5.gs < 0) & (f5.gr < 0)
inv10 = (f10.gs < 0) & (f10.gr < 0)
print("\n" + "=" * 98)
print("DO THE WINDOWS AGREE?")
print("=" * 98)
print(f"   fav-better-on-both fires: L5 {int(inv5.sum())} · L10 {int(inv10.sum())} · "
      f"BOTH {int((inv5 & inv10).sum())} · L5 only {int((inv5 & ~inv10).sum())} · "
      f"L10 only {int((inv10 & ~inv5).sum())}")
rep(f5[inv5 & inv10], "both windows agree (L5 odds)")
rep(f5[inv5 & ~inv10], "L5 fires, L10 does not")
rep(f10[inv10 & ~inv5], "L10 fires, L5 does not")
