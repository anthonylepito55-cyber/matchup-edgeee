"""Validate the point-derived stats against Goalserve's own stat line (2026-10-12).

The first pass had hold% at 96% exact but break% out by 53pt, which exposed a wrong reading of
`@lost_serve` on games the player did not serve. Returns are now taken from the OPPONENT'S
service games. This re-checks both halves, then prints the ITF rows -- the ones that have no
official stat line anywhere and are the entire reason for parsing point data.
"""
import goalserve_ingest as G

d = G.load()
if d.empty:
    raise SystemExit("store is empty")
gs = d[d.src == "gamestats"].set_index(["match_id", "player_id"])
pp = d[d.src == "p2p"].set_index(["match_id", "player_id"])
both = gs.index.intersection(pp.index)
print("player-matches with BOTH an official line and derived point data: %d" % len(both))
a, q = gs.loc[both], pp.loc[both]
for nm, off, der in (("hold%", 100 * a.gs_sgames_won_w / a.gs_sgames_won_t, q.p2p_hold_pct),
                     ("break%", 100 * a.gs_rgames_won_w / a.gs_rgames_won_t, q.p2p_break_pct)):
    m = off.notna() & der.notna()
    diff = (der[m] - off[m]).abs()
    print("   %-7s n=%-4d mean |diff| %5.2fpt  exact %3.0f%%  within 1pt %3.0f%%"
          % (nm, int(m.sum()), diff.mean(), 100 * (diff < 0.01).mean(),
             100 * (diff <= 1).mean()))

itf = d[(d.src == "p2p") & (d.level == "itf")]
print("\nITF rows derived from point data: %d   (official ITF stat lines: %d)"
      % (len(itf), int(((d.src == "gamestats") & (d.level == "itf")).sum())))
for r in itf.head(8).itertuples():
    print("   %-24s hold %5.1f%%  break %5.1f%%  BPfaced %2d  BPchances %2d"
          % (str(r.player)[:24], r.p2p_hold_pct, r.p2p_break_pct,
             r.p2p_bp_faced, r.p2p_bp_chances))
if len(itf):
    print("\n   sanity: across a match the two players' hold%% and break%% must mirror, so the"
          "\n   means should sum to ~100 -- hold %.1f%% + break %.1f%% = %.1f%%"
          % (itf.p2p_hold_pct.mean(), itf.p2p_break_pct.mean(),
             itf.p2p_hold_pct.mean() + itf.p2p_break_pct.mean()))
