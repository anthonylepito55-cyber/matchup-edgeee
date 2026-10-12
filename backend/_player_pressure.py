"""PRESSURE POINTS FOR ONE PLAYER (2026-10-11, user: "What's the pressure points for sonay
kartel").

The card only ever shows the BLENDED `clutch %` -- serve-pressure and return-pressure points
summed together -- so the two dials TennisRatio displays are not readable anywhere in the app.
This prints them split out, the way the Compare Players screen does:

    PRESSURE POINTS WON ON SERVE   = serve_pressure_won / serve_pressure_all
    PRESSURE POINTS WON ON RETURN  = return_pressure_won / return_pressure_all

Shown season-to-date per surface (what the screenshot's "This Season / All Levels / Hard"
means), plus 52-week and career rows for context, and the blended clutch the card actually
prints so the two can be reconciled.

Usage: _player_pressure.py "Name"
"""
import sys
import unicodedata

import numpy as np
import pandas as pd

import tennis_model_a as MA

NAME = sys.argv[1] if len(sys.argv) > 1 else "Sonay Kartal"
P = "data_cache/tennisratio/all_match_logs.parquet"


def strip_acc(x):
    return "".join(c for c in unicodedata.normalize("NFKD", str(x))
                   if not unicodedata.combining(c)).lower()


MA._load()
slug = MA.resolve(NAME)
print("query: %r  ->  resolved slug: %s" % (NAME, slug))

d = pd.read_parquet(P)
d["date"] = pd.to_datetime(d["date"], errors="coerce")
if slug:
    sub = d[d.player_slug.astype(str) == str(slug)].copy()
else:
    # fall back to a surname match so a near-miss spelling still finds the player
    tgt = strip_acc(NAME).split()
    key = max(tgt, key=len) if tgt else ""
    cand = d[d.player_slug.astype(str).str.lower().str.contains(key, na=False)]
    print("   (name did not resolve; surname fallback on %r -> %s)"
          % (key, sorted(cand.player_slug.astype(str).unique())[:6]))
    sub = cand.copy()
if sub.empty:
    raise SystemExit("no matches found for that player")

for c in ("serve_pressure_all", "serve_pressure_won",
          "return_pressure_all", "return_pressure_won"):
    sub[c] = pd.to_numeric(sub[c], errors="coerce")
sub["surf"] = sub["surface"].astype(str).str.title().replace(
    {"I.Hard": "Hard", "Carpet": "Hard"})
sub["won"] = sub["result"].eq("Win").astype(int)
have = sub[sub.serve_pressure_all.notna() & sub.return_pressure_all.notna()]
print("   matches in the archive: %d   with pressure-point data: %d   latest %s"
      % (len(sub), len(have), str(sub.date.max())[:10]))
if have.empty:
    raise SystemExit("   this player has NO pressure-point rows -- nothing to report")


def block(rows, lab):
    if rows.empty:
        print("   %-26s --" % lab)
        return
    sa, sw = rows.serve_pressure_all.sum(), rows.serve_pressure_won.sum()
    ra, rw = rows.return_pressure_all.sum(), rows.return_pressure_won.sum()
    if sa <= 0 or ra <= 0:
        print("   %-26s --" % lab)
        return
    sp, rp = 100 * sw / sa, 100 * rw / ra
    clutch = 100 * (sw + rw) / (sa + ra)
    print("   %-26s serve %5.1f%%  return %5.1f%%   (clutch %5.1f%%)   "
          "%d matches, %d/%d serve pts, %d/%d return pts"
          % (lab, sp, rp, clutch, len(rows), int(sw), int(sa), int(rw), int(ra)))


now = have.date.max()
yr = now.year
print("\n" + "=" * 104)
print("PRESSURE POINTS WON -- %s" % (slug or NAME))
print("=" * 104)
print("  THIS SEASON (%d), by surface -- what the TennisRatio compare screen shows:" % yr)
season = have[have.date.dt.year == yr]
for s in ("Hard", "Clay", "Grass"):
    block(season[season.surf == s], s)
block(season, "ALL SURFACES")
print("\n  LAST 52 WEEKS, by surface:")
w52 = have[have.date >= now - pd.Timedelta(weeks=52)]
for s in ("Hard", "Clay", "Grass"):
    block(w52[w52.surf == s], s)
block(w52, "ALL SURFACES")
print("\n  LAST 25 MATCHES (the window the card's `clutch` actually uses):")
block(have.sort_values("date").tail(25), "last 25, all surfaces")
print("\n  CAREER:")
block(have, "all time")

print("\n  recent matches with the dials:")
print("   %-12s %-8s %-28s %-6s %s" % ("date", "surface", "opponent", "result", "serve / return"))
for r in have.sort_values("date").tail(10).itertuples():
    sa, sw = r.serve_pressure_all, r.serve_pressure_won
    ra, rw = r.return_pressure_all, r.return_pressure_won
    sp = 100 * sw / sa if sa else float("nan")
    rp = 100 * rw / ra if ra else float("nan")
    print("   %-12s %-8s %-28s %-6s %5.1f%% / %5.1f%%"
          % (str(r.date)[:10], r.surf, str(r.rival_slugname)[:28], r.result, sp, rp))
