"""WHICH PLAYERS ARE WORTH CHARTING BY HAND, IN ORDER (2026-10-10, user: "anyway to get more
unforced errors info").

The unforced-error edge is a WTA-TOUR edge (+10.8%, n=276, positive all three years, versus
-0.4% ungated at the same level -- `_ue_edge_by_level.py`). On that slice, both players have a
profile on only 435 of 937 2026 dog matches in band. Filling every gap means 195 players and
~975 hand lookups, which nobody is going to do.

But the gaps are concentrated. A handful of tour-fringe players appear as +100..+250 dogs over
and over, and each one unlocks every match they appear in:

    top 10 missing players (  50 lookups) -> 578 of 937 gradeable  (46% -> 62%)
    top 20                 ( 100 lookups) -> 628                   (67%)
    top 40                 ( 200 lookups) -> 689                   (74%)
    top 80                 ( 400 lookups) -> 805                   (86%)
    all 195                ( 975 lookups) -> 937                   (100%)

So this writes the worklist in priority order and pre-seeds the manual CSV with the right player
names and dates, leaving only the numbers to type. Re-run it after each batch: players that have
since gained a profile drop off automatically.

Output:
  data_cache/mcp/manual_ue_worklist.csv   priority list with matches-unlocked per player
  manual_ue_seed.csv                      rows ready to fill (player, opponent, date, blanks)
"""
import collections
import sys

import pandas as pd

import tennis_ue as U

TOP = int(sys.argv[1]) if len(sys.argv) > 1 else 40
KEEP = ["date", "player_slug", "rival_slugname", "player_odd", "rival_odd", "result",
        "tournament_level", "tournament"]

df = pd.read_parquet("data_cache/tennisratio/all_match_logs.parquet", columns=KEEP)
df["date"] = pd.to_datetime(df["date"])
for c in ("player_odd", "rival_odd"):
    df[c] = pd.to_numeric(df[c], errors="coerce")
df["rival_slugname"] = df["rival_slugname"].astype(str)
side = df[["player_slug", "rival_slugname", "date"]].copy()
mir = side.rename(columns={"player_slug": "rival_slugname", "rival_slugname": "player_slug"})
df = df.merge(mir, on=["player_slug", "rival_slugname", "date"], how="inner")
m = df[df["player_slug"].astype(str) < df["rival_slugname"]].drop_duplicates(
    ["player_slug", "rival_slugname", "date"])
i1 = 1 / m["player_odd"].where(m["player_odd"] > 1.005)
i2 = 1 / m["rival_odd"].where(m["rival_odd"] > 1.005)
m["mkt"] = i1 / (i1 + i2)
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
B = m[(m.date.dt.year == 2026) & m.mkt.notna() & (m.mkt < 0.5)
      & m.player_odd.between(2.0, 3.5)].copy()
B["G"] = B.player_slug.astype(str).map(GM)
B = B[(B.G == "W") & B.tournament_level.astype(str).str.lower().isin(["wta", "grand slams"])]

U.load()
blocked, need_dates = collections.Counter(), collections.defaultdict(list)
ok = 0
for r in B.itertuples():
    a = bool(U.profile(r.player_slug, r.date))
    b = bool(U.profile(r.rival_slugname, r.date))
    if a and b:
        ok += 1
        continue
    for nm, has, opp in ((str(r.player_slug), a, str(r.rival_slugname)),
                         (str(r.rival_slugname), b, str(r.player_slug))):
        if not has:
            blocked[nm] += 1
            need_dates[nm].append((r.date.date(), opp, r.tournament))
print(f"2026 WTA-tour/slam women dogs +100..+250: {len(B)}")
print(f"  gradeable now (both players profiled): {ok} ({100 * ok / len(B):.0f}%)")
print(f"  players missing a profile: {len(blocked)}\n")

W = pd.DataFrame([{"rank": i + 1, "player": nm, "matches_unlocked": c,
                   "recent_opponents": "; ".join(f"{d} vs {o}" for d, o, _ in need_dates[nm][:3])}
                  for i, (nm, c) in enumerate(blocked.most_common())])
W.to_parquet if False else W.to_csv("data_cache/mcp/manual_ue_worklist.csv", index=False)
print("priority order (each player unlocks every match they appear in):")
for r in W.head(TOP).itertuples():
    print(f"  {r.rank:3d}. {r.player:28s} unlocks {r.matches_unlocked:3d} matches")

# pre-seed the manual CSV with the right names so only the numbers need typing
seed = ["# Pre-seeded worklist (2026-10-10). Fill `sets` and `unforced` for each row from any",
        "# source you are entitled to read, then run _ue_manual_check.py. FIVE matches per",
        "# player is the minimum for a profile -- the dates below are that player's own recent",
        "# matches, but ANY five of her matches work. Delete rows you do not fill.",
        "match_id,player,opp,Date,Tournament,G,sets,unforced,winners,unforced_fh,unforced_bh,serve_pts,return_pts"]
for nm, _ in blocked.most_common(TOP):
    for d, opp, tn in need_dates[nm][:5]:
        mid = f"{d:%Y%m%d}-{nm[:10]}-{opp[:10]}".replace(" ", "")
        seed.append(f"{mid},{nm},{opp},{d:%Y%m%d},{tn},W,,,,,,,")
with open("../manual_ue_seed.csv", "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(seed) + "\n")
print(f"\nwrote data_cache/mcp/manual_ue_worklist.csv ({len(W)} players)")
print(f"wrote manual_ue_seed.csv ({len(seed) - 5} rows ready to fill, top {TOP} players)")
sys.stdout.flush()
