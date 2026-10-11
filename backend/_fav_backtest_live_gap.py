"""WHY DO FAVOURITE EDGES BACKTEST WELL AND FAIL LIVE? (2026-10-10, user "Dig into it")

Five favourite cells have now passed an out-of-sample backtest on the TennisRatio archive and
lost money on the frozen live log: CE5 (-30%, n=57), the three pf_*fav_pr cells, fav_value, and
now Ⓟ FAV (-18.5%, n=15, with the whole favourite side of P's universe at -12.4% / -11.3% over
365 settles). On 10-10 I ruled out the two model-side explanations -- the g_C cell is REVERSED
rather than absent, and the g_C distributions of the two samples match almost exactly. So the
suspect is the DATA, not the model.

Five candidate causes, each measured:
  1. BASELINE SHIFT -- what does backing EVERY favourite in the matched universe return in the
     archive vs live? If the archive baseline is ~-4% (normal vig) and live is -12%, then most
     of the "edge" was never model skill, it was a friendlier baseline.
  2. PRICE LEVEL -- the same matches appear in both sources over 09-28..10-08. Compare the
     archive's odds against the frozen live odds match by match. This is the decisive test:
     if the archive's favourite prices are systematically LONGER than what was actually
     available, every favourite backtest is inflated by exactly that much.
  3. OVERROUND -- archive 1/o1 + 1/o2 vs live. A sharp/low-vig archive price makes favourites
     look profitable at a price nobody could bet.
  4. RETIREMENTS AND WALKOVERS -- the archive rows carry full service-stat lines, so matches
     that never produced stats may be missing. Retirements and walkovers are upsets far more
     often than not, and dropping them inflates every favourite win rate.
  5. SAMPLE WINDOW -- the live log is only 09-28..10-10 and ITF-heavy. Check the archive's
     favourite baseline restricted to the same calendar window and the same levels.
"""
import numpy as np
import pandas as pd

BAND_DOG = (2.0, 3.5)
BAND_FAV = (1.5, 2.0)
AR = "data_cache/tennisratio/all_match_logs.parquet"
LOG = "data_cache/tennis_prediction_log.parquet"


def dec_from_american(o):
    o = pd.to_numeric(o, errors="coerce").astype(float)
    return np.where(o > 0, 1 + o / 100.0, 1 + 100.0 / -o)


def roi(won, d):
    won = np.asarray(won, dtype=bool)
    return 100 * np.where(won, np.asarray(d, dtype=float) - 1, -1.0).mean()


def rep(won, d, floor=30):
    n = len(won)
    if n < floor:
        return f"n={n} (thin)"
    w = int(np.sum(np.asarray(won, dtype=bool)))
    return f"{w}-{n - w}  hit {100 * w / n:4.1f}%  ROI {roi(won, d):+6.1f}%  (n={n})"


# ---------------------------------------------------------------------------- archive side
A = pd.read_parquet(AR, columns=["date", "player_slug", "rival_slugname", "player_odd",
                                 "rival_odd", "result", "score", "tournament_level", "surface"])
A["date"] = pd.to_datetime(A["date"], errors="coerce")
for c in ("player_odd", "rival_odd"):
    A[c] = pd.to_numeric(A[c], errors="coerce")
A["won"] = A["result"].eq("Win")
A = A[A.date.notna() & A.player_odd.gt(1.005) & A.rival_odd.gt(1.005)]
A["lvl"] = A["tournament_level"].astype(str).str.lower()
# one row per match, from the FAVOURITE's side
F = A[(A.player_odd >= BAND_FAV[0]) & (A.player_odd <= BAND_FAV[1])
      & (A.rival_odd >= BAND_DOG[0]) & (A.rival_odd <= BAND_DOG[1])].copy()
F = F.drop_duplicates(["date", "player_slug", "rival_slugname"])
F["yr"] = F.date.dt.year
F["ovr"] = 1 / F.player_odd + 1 / F.rival_odd
print("=" * 86)
print("1. BASELINE -- backing EVERY favourite in the matched universe (fav 1.5-2.0, dog 2.0-3.5)")
print("=" * 86)
print(f"   ARCHIVE, all years      {rep(F.won.values, F.player_odd.values)}")
for y in (2024, 2025, 2026):
    s = F[F.yr == y]
    print(f"      {y}                 {rep(s.won.values, s.player_odd.values)}")
print(f"   archive mean overround  {F.ovr.mean():.4f}  (vig {100 * (F.ovr.mean() - 1):.2f}%)")

# ------------------------------------------------------------------------------- live side
L = pd.read_parquet(LOG)
L["date"] = pd.to_datetime(L["date"], errors="coerce")
L["d1"], L["d2"] = dec_from_american(L.p1_odds), dec_from_american(L.p2_odds)
S = L[(L.settled == True) & L.p1_won.notna() & L.d1.notna() & L.d2.notna()].copy()
S["fav1"] = S.d1 < S.d2
S["fdec"] = np.where(S.fav1, S.d1, S.d2)
S["ddec"] = np.where(S.fav1, S.d2, S.d1)
S["fav_won"] = np.where(S.fav1, S.p1_won == 1, S.p1_won == 0)
U = S[(S.fdec >= BAND_FAV[0]) & (S.fdec <= BAND_FAV[1])
      & (S.ddec >= BAND_DOG[0]) & (S.ddec <= BAND_DOG[1])].copy()
U["ovr"] = 1 / U.fdec + 1 / U.ddec
print(f"\n   LIVE log ({U.date.min().date()}..{U.date.max().date()})"
      f"   {rep(U.fav_won.values, U.fdec.values)}")
print(f"   live mean overround     {U.ovr.mean():.4f}  (vig {100 * (U.ovr.mean() - 1):.2f}%)")
print(f"\n   >>> BASELINE GAP: archive {roi(F.won.values, F.player_odd.values):+.1f}%  vs  "
      f"live {roi(U.fav_won.values, U.fdec.values):+.1f}%  = "
      f"{roi(U.fav_won.values, U.fdec.values) - roi(F.won.values, F.player_odd.values):+.1f} pts")

# ----------------------------------------------------- 2+3. the same matches, both sources
print("\n" + "=" * 86)
print("2+3. THE SAME MATCHES IN BOTH SOURCES -- archive price vs the price actually logged")
print("=" * 86)
import tennis_model_a as MA
MA._load()
ov = S[S.date.between(A.date.min(), A.date.max())].copy()
pairs = []
for r in ov.itertuples():
    s1, s2 = MA.resolve(str(r.player_1)), MA.resolve(str(r.player_2))
    if s1 and s2:
        pairs.append((r.date, s1, s2, r.d1, r.d2, bool(r.p1_won == 1), str(r.score or "")))
PR = pd.DataFrame(pairs, columns=["date", "s1", "s2", "live_d1", "live_d2", "p1_won", "score"])
print(f"   live settled rows with both names resolved: {len(PR)}")
AK = A[["date", "player_slug", "rival_slugname", "player_odd", "rival_odd", "score"]].rename(
    columns={"player_slug": "s1", "rival_slugname": "s2", "player_odd": "ar_d1",
             "rival_odd": "ar_d2", "score": "ar_score"})
M = PR.merge(AK, on=["date", "s1", "s2"], how="inner").drop_duplicates(["date", "s1", "s2"])
print(f"   matched into the archive on (date, both slugs): {len(M)}")
if len(M) >= 30:
    M["live_fav1"] = M.live_d1 < M.live_d2
    M["live_f"] = np.where(M.live_fav1, M.live_d1, M.live_d2)
    M["ar_f"] = np.where(M.live_fav1, M.ar_d1, M.ar_d2)
    M["live_d"] = np.where(M.live_fav1, M.live_d2, M.live_d1)
    M["ar_dd"] = np.where(M.live_fav1, M.ar_d2, M.ar_d1)
    M["fw"] = np.where(M.live_fav1, M.p1_won, ~M.p1_won)
    B = M[(M.live_f >= BAND_FAV[0]) & (M.live_f <= BAND_FAV[1])].copy()
    print(f"\n   on the {len(B)} matched favourites in band:")
    print(f"      favourite price   archive {B.ar_f.mean():.4f}   live {B.live_f.mean():.4f}"
          f"   -> archive is {100 * (B.ar_f.mean() / B.live_f.mean() - 1):+.2f}% longer")
    print(f"      dog price         archive {B.ar_dd.mean():.4f}   live {B.live_d.mean():.4f}"
          f"   -> archive is {100 * (B.ar_dd.mean() / B.live_d.mean() - 1):+.2f}% longer")
    print(f"      overround         archive {(1 / B.ar_f + 1 / B.ar_dd).mean():.4f}"
          f"   live {(1 / B.live_f + 1 / B.live_d).mean():.4f}")
    print(f"      median fav diff (archive - live): {(B.ar_f - B.live_f).median():+.4f}"
          f"   | archive longer on {100 * (B.ar_f > B.live_f).mean():.1f}% of matches")
    print(f"\n   SAME GAMES, SAME OUTCOMES, ONLY THE PRICE DIFFERS:")
    print(f"      paid at the ARCHIVE price  {rep(B.fw.values, B.ar_f.values)}")
    print(f"      paid at the LIVE price     {rep(B.fw.values, B.live_f.values)}")
    print(f"      -> price alone is worth "
          f"{roi(B.fw.values, B.ar_f.values) - roi(B.fw.values, B.live_f.values):+.1f} ROI pts")
    # do the two sources even agree on WHO the favourite is?
    dis = B[(B.ar_f > B.ar_dd)]
    print(f"      sources disagree on which player is the favourite: {len(dis)} of {len(B)}")

# ------------------------------------------------------- 4. retirements and walkovers
print("\n" + "=" * 86)
print("4. RETIREMENTS / WALKOVERS -- are the archive's favourite losses incomplete-match losses?")
print("=" * 86)


def odd_flag(s):
    s = s.astype(str).str.lower()
    return s.str.contains("ret|w/o|wo|def|abn|canc", regex=True, na=False)


F["odd_end"] = odd_flag(F["score"])
U["odd_end"] = odd_flag(U["score"].astype(str))
print(f"   ARCHIVE: {100 * F.odd_end.mean():.2f}% of in-band matches end oddly "
      f"({int(F.odd_end.sum())} of {len(F)})")
print(f"   LIVE   : {100 * U.odd_end.mean():.2f}% of in-band matches end oddly "
      f"({int(U.odd_end.sum())} of {len(U)})")
if F.odd_end.sum() > 30:
    print(f"      archive favourites in odd-ending matches "
          f"{rep(F[F.odd_end].won.values, F[F.odd_end].player_odd.values)}")
    print(f"      archive favourites in clean matches       "
          f"{rep(F[~F.odd_end].won.values, F[~F.odd_end].player_odd.values)}")
if U.odd_end.sum() > 10:
    print(f"      live favourites in odd-ending matches "
          f"{rep(U[U.odd_end].fav_won.values, U[U.odd_end].fdec.values, floor=5)}")
    print(f"      live favourites in clean matches      "
          f"{rep(U[~U.odd_end].fav_won.values, U[~U.odd_end].fdec.values)}")

# --------------------------------------------------------------- 5. the calendar window
print("\n" + "=" * 86)
print("5. SAMPLE WINDOW -- the archive restricted to the live log's own window and levels")
print("=" * 86)
lo, hi = U.date.min(), U.date.max()
W = F[(F.date.dt.month == lo.month) & (F.date.dt.day >= 20)]
print(f"   archive, late Sept/Oct of every year  {rep(W.won.values, W.player_odd.values)}")
same = F[(F.date >= lo) & (F.date <= hi)]
print(f"   archive, the SAME dates {lo.date()}..{hi.date()}  "
      f"{rep(same.won.values, same.player_odd.values, floor=10)}")
for tag, mask in (("ITF only", F.lvl.str.contains("itf|futures")),
                  ("challenger", F.lvl.str.contains("chall")),
                  ("tour/slam", ~F.lvl.str.contains("itf|futures|chall"))):
    s = F[mask]
    print(f"   archive {tag:12s} {rep(s.won.values, s.player_odd.values)}")
ulv = U["league"].astype(str).str.lower()
for tag, mask in (("ITF only", ulv.str.contains("itf")),
                  ("tour", ~ulv.str.contains("itf"))):
    s = U[mask]
    print(f"   live    {tag:12s} {rep(s.fav_won.values, s.fdec.values, floor=20)}")
