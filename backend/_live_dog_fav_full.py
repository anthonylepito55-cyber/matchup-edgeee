"""EVERY LIVE RECORD, SPLIT DOG VS FAVOURITE (2026-10-10, user ask).

Three sections, deliberately in this order:

  A. THE BASELINE -- backing every favourite, and every dog, on the board. Everything else has
     to be read against this.
  B. EVERY MODEL HEAD, one row per match, no double counting. Each head's OWN side, split by
     whether that side is the market dog or the market favourite. This is the clean view; the
     "604 favourite settles" figure I led with earlier was a sum over overlapping lanes and
     counted the same match many times.
  C. EVERY LANE's dog and favourite halves, for lanes with a usable sample on that side.

All of it is the frozen live log. Model C has only been logged since 2026-09-28, D since
10-01 and P since 10-09, so this is a 13-day window at most -- and because those bets share
tournaments, players and surfaces, the +/- figures (which assume independence) read better
than the evidence really is.
"""
import numpy as np
import pandas as pd
import tennis_log as TL

L = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
L["date"] = pd.to_datetime(L["date"], errors="coerce")


def dec(o):
    o = pd.to_numeric(o, errors="coerce").astype(float)
    return np.where(o > 0, 1 + o / 100.0, 1 + 100.0 / -o)


L["d1"], L["d2"] = dec(L.p1_odds), dec(L.p2_odds)
i1, i2 = 1 / L.d1, 1 / L.d2
L["mk1"] = i1 / (i1 + i2)
S = L[(L.settled == True) & L.p1_won.notna() & L.mk1.notna()
      & (L.d1 > 1.005) & (L.d2 > 1.005)].copy()
S["dog1"] = S.mk1 < 0.5
S["W"] = S.league.astype(str).str.lower().str.contains("women|wta")
S["dog_dec"] = np.where(S.dog1, S.d1, S.d2)
S["fav_dec"] = np.where(S.dog1, S.d2, S.d1)
S["dog_won"] = np.where(S.dog1, S.p1_won == 1, S.p1_won == 0)


def line(won, decs, lab, floor=15):
    n = len(won)
    if n < floor:
        return f"   {lab:32s} n={n} (thin)"
    won = np.asarray(won, bool)
    pnl = np.where(won, np.asarray(decs, float) - 1, -1.0)
    se = 100 * pnl.std(ddof=1) / np.sqrt(n)
    return (f"   {lab:32s} {int(won.sum())}-{n - int(won.sum())}  hit {100 * won.mean():5.1f}%  "
            f"ROI {100 * pnl.mean():+7.1f}% ± {se:4.1f}  (n={n})")


print(f"frozen log: {len(S)} settled with prices, "
      f"{S.date.min().date()}..{S.date.max().date()}")
print("=" * 84)
print("A. THE BASELINE -- the board itself")
print("=" * 84)
print(line(S.dog_won, S.dog_dec, "every DOG"))
print(line(~S.dog_won.astype(bool), S.fav_dec, "every FAVOURITE"))
for g, lab in ((False, "men"), (True, "women")):
    T = S[S.W == g]
    print(line(T.dog_won, T.dog_dec, f"   {lab} dogs"))
    print(line(~T.dog_won.astype(bool), T.fav_dec, f"   {lab} favourites"))

HEADS = [("model_a_p1", "A"), ("model_ama_p1", "A market-aware"),
         ("model_b_p1", "B"), ("model_bma_p1", "B market-aware"),
         ("model_c_p1", "C"), ("model_cma_p1", "C market-aware (gray)"),
         ("model_d_p1", "D"), ("model_dma_p1", "D market-aware"),
         ("mc_p1", "MC (plain)"), ("mc_c_p1", "MC anchored on C (c50)"),
         ("mc_c75_p1", "c75"), ("mc_cutr_p1", "MC C+sUTR"),
         ("mc2_p1", "MC2"), ("model_x_p1", "X")]
print("\n" + "=" * 84)
print("B. EVERY MODEL HEAD -- its own side, one row per match")
print("=" * 84)
print(f"   {'head':24s} {'side':6s} {'record':>9s} {'hit':>7s} {'ROI':>9s} {'se':>5s} {'n':>6s}")
for col, nm in HEADS:
    if col not in S.columns:
        continue
    T = S[S[col].notna()].copy()
    if len(T) < 40:
        continue
    T["side1"] = T[col].astype(float) >= 0.5
    T["dc"] = np.where(T.side1, T.d1, T.d2)
    T["w"] = np.where(T.side1, T.p1_won == 1, T.p1_won == 0)
    T["on_dog"] = T.side1 == T.dog1
    for tag, sub in (("DOG", T[T.on_dog]), ("FAV", T[~T.on_dog])):
        n = len(sub)
        if n < 15:
            print(f"   {nm:24s} {tag:6s} n={n} (thin)")
            continue
        w = sub.w.astype(bool)
        pnl = np.where(w, sub.dc - 1, -1.0)
        print(f"   {nm:24s} {tag:6s} {f'{int(w.sum())}-{n - int(w.sum())}':>9s} "
              f"{100 * w.mean():6.1f}% {100 * pnl.mean():+8.1f}% "
              f"{100 * pnl.std(ddof=1) / np.sqrt(n):5.1f} {n:6d}")
# Model P is dog-side only by construction
if "model_p_prob" in S.columns:
    T = S[S.model_p_prob.notna()].copy()
    if len(T) >= 15:
        T["w"] = np.where(T.dog1, T.p1_won == 1, T.p1_won == 0)
        print(line(T.w, T.dog_dec, "P universe, back every dog"))

print("\n" + "=" * 84)
print("C. EVERY LANE, dog half and favourite half (n>=20 on that side)")
print("=" * 84)
st = (TL.get_ab25_record() or {}).get("study") or {}
rows = []
for k, v in st.items():
    if not isinstance(v, dict):
        continue
    for tag in ("dog", "fav"):
        c = v.get(tag)
        if isinstance(c, dict) and (c.get("n") or 0) >= 20:
            rows.append((k, tag.upper(), c["n"], c.get("wins", 0),
                         c.get("roi_pct", 0.0), c.get("profit_usd", 0.0)))
for tag in ("DOG", "FAV"):
    sel = sorted([r for r in rows if r[1] == tag], key=lambda r: -r[4])
    tot_n = sum(r[2] for r in sel)
    print(f"\n   --- {tag} halves ({len(sel)} lanes) ---")
    print(f"   {'lane':28s} {'record':>10s} {'ROI':>8s} {'profit':>9s} {'n':>6s}")
    for k, _, n, w, roi, pf in sel:
        print(f"   {k:28s} {f'{w}-{n - w}':>10s} {roi:+7.1f}% {pf:+9.0f} {n:6d}")
    print(f"   lanes positive: {sum(1 for r in sel if r[4] > 0)} of {len(sel)}"
          f"   (lane-settles total {tot_n}, which DOUBLE-COUNTS overlapping lanes)")
