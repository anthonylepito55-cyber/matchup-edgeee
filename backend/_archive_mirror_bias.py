"""THE ARCHIVE'S FAVOURITE-SIDE SELECTION BIAS (2026-10-10, user "Dig into it").

The price theory is dead: on 307 matches present in both sources, paying the archive price
returns -5.3% and paying the live price -5.6%. Same games, same outcomes, 0.2 ROI pts apart.

What the overlap DID show is a disagreement about the matches themselves. On the identical
dates 2026-09-06..2026-10-10, in the identical band:
    archive  601-319  65.3% hit  +5.2%  (n=920)
    live     298-236  55.8% hit  -8.1%  (n=534)
    matched into both: 175-132  57.0%  (n=307)
So the archive rows that DO appear live hit 57%, and the archive rows that DON'T hit ~70%.

Hypothesis: the archive is built per tracked player (1,760 of them), so a match appears TWICE
only when BOTH players are tracked, and ONCE when only one is. Selecting "rows whose own price
is in the favourite band" therefore over-samples matches where the FAVOURITE is the tracked
player -- and tracked players are the established, better-documented ones. That is a selection
effect pointing straight at favourite wins, inherited by every favourite backtest cell.

Measured here:
  1. what share of archive matches carry both sides, and does the favourite hit rate differ
  2. the same split restricted to the exact price band the favourite cells use
  3. whether requiring BOTH sides (the mirror-merge some studies already do) removes the gap
  4. the retirement/walkover question, done properly this time -- the earlier regex found 0 of
     84,186, which is not credible and needs checking against the real score strings
"""
import numpy as np
import pandas as pd

AR = "data_cache/tennisratio/all_match_logs.parquet"
FAV = (1.5, 2.0)
DOG = (2.0, 3.5)

A = pd.read_parquet(AR, columns=["date", "player_slug", "rival_slugname", "player_odd",
                                 "rival_odd", "result", "score", "tournament_level"])
A["date"] = pd.to_datetime(A["date"], errors="coerce")
for c in ("player_odd", "rival_odd"):
    A[c] = pd.to_numeric(A[c], errors="coerce")
A = A[A.date.notna() & A.player_odd.gt(1.005) & A.rival_odd.gt(1.005)
      & A.player_slug.notna() & A.rival_slugname.notna()].copy()
A["won"] = A["result"].eq("Win")
A["player_slug"] = A["player_slug"].astype(str)
A["rival_slugname"] = A["rival_slugname"].astype(str)
A = A.drop_duplicates(["date", "player_slug", "rival_slugname"])
print(f"archive rows with both names and two prices: {len(A)}")

# does the mirror row exist? (the same match from the opponent's side)
mir = A[["date", "player_slug", "rival_slugname"]].rename(
    columns={"player_slug": "rival_slugname", "rival_slugname": "player_slug"})
mir["has_mirror"] = True
A = A.merge(mir, on=["date", "player_slug", "rival_slugname"], how="left")
A["has_mirror"] = A["has_mirror"].fillna(False)
print(f"rows whose opponent's side is ALSO in the archive: {100 * A.has_mirror.mean():.1f}%")


def rep(s, col="player_odd", floor=100):
    n = len(s)
    if n < floor:
        return f"n={n} (thin)"
    w = s.won.astype(bool)
    d = s[col].astype(float)
    return (f"{int(w.sum())}-{n - int(w.sum())}  hit {100 * w.mean():4.1f}%  "
            f"ROI {100 * np.where(w, d - 1, -1).mean():+6.1f}%  (n={n})")


print("\n" + "=" * 90)
print("1. THE FAVOURITE SIDE, SPLIT BY WHETHER THE OPPONENT'S ROW EXISTS TOO")
print("=" * 90)
F = A[A.player_odd.between(*FAV) & A.rival_odd.between(*DOG)]
print(f"   ALL favourite-side rows in band            {rep(F)}")
print(f"   ... BOTH sides in the archive (mirrored)   {rep(F[F.has_mirror])}")
print(f"   ... ONLY the favourite's side present      {rep(F[~F.has_mirror])}")
print("\n   the mirror image -- the DOG side in band:")
D = A[A.player_odd.between(*DOG) & A.rival_odd.between(*FAV)]
print(f"   ALL dog-side rows in band                  {rep(D)}")
print(f"   ... BOTH sides present                     {rep(D[D.has_mirror])}")
print(f"   ... ONLY the dog's side present            {rep(D[~D.has_mirror])}")

print("\n" + "=" * 90)
print("2. BY YEAR -- is the one-sided inflation getting worse in recent data?")
print("=" * 90)
F = F.copy()
F["yr"] = F.date.dt.year
for y in (2022, 2023, 2024, 2025, 2026):
    s = F[F.yr == y]
    if len(s) < 200:
        continue
    print(f"   {y}  all {rep(s)}")
    print(f"         mirrored {rep(s[s.has_mirror])}")
    print(f"         one-sided {rep(s[~s.has_mirror], floor=50)}")
    print(f"         -> one-sided share {100 * (~s.has_mirror).mean():4.1f}%")

print("\n" + "=" * 90)
print("3. THE LIVE WINDOW (2026-09-06..2026-10-10), where live said 55.8% / -8.1%")
print("=" * 90)
W = F[(F.date >= "2026-09-06") & (F.date <= "2026-10-10")]
print(f"   archive, all favourite rows   {rep(W, floor=50)}")
print(f"   archive, mirrored only        {rep(W[W.has_mirror], floor=50)}")
print(f"   archive, one-sided only       {rep(W[~W.has_mirror], floor=20)}")
print(f"   one-sided share in this window: {100 * (~W.has_mirror).mean():.1f}%")

print("\n" + "=" * 90)
print("4. RETIREMENTS / WALKOVERS -- what the score strings actually look like")
print("=" * 90)
sc = A["score"].astype(str)
print(f"   distinct score strings: {sc.nunique()}")
print(f"   examples: {list(sc.dropna().unique()[:8])}")
nonstd = sc[~sc.str.match(r"^[\d\-\s\(\)]+$", na=False)]
print(f"   scores containing anything other than digits/dashes/brackets: {len(nonstd)} "
      f"({100 * len(nonstd) / len(sc):.2f}%)")
if len(nonstd):
    print(f"   examples: {list(nonstd.unique()[:10])}")
# an unfinished match is better detected by set count than by text
sets = sc.str.count(r"\d+-\d+")
print(f"   set-count distribution: {sets.value_counts().head(7).to_dict()}")
one_set = A[sets <= 1]
print(f"   matches with 0-1 completed sets (retirement-shaped): {len(one_set)} "
      f"({100 * len(one_set) / len(A):.2f}%)")
if len(one_set) > 50:
    o = one_set[one_set.player_odd.between(*FAV) & one_set.rival_odd.between(*DOG)]
    print(f"      favourites in those matches: {rep(o, floor=20)}")
