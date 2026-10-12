"""GOALSERVE INGEST -- same-day challenger stats, and ITF stats derived from point data.

=============================================================================================
THIS IS A FREE TRIAL. IT WILL STOP WORKING. READ THIS BEFORE DEBUGGING ANYTHING.
=============================================================================================
Built 2026-10-12 against a trial key, so the whole thing is deliberately quarantined:

  * ALL Goalserve code lives in THIS FILE. Nothing else imports the feed.
  * It writes to ITS OWN store, `data_cache/goalserve_stats.parquet`. It never touches the
    TennisRatio archive or the prediction log, so a bad feed cannot corrupt the models.
  * Every entry point no-ops cleanly when the key is missing, expired or refusing: `enabled()`
    is false, `ingest()` returns 0, and callers get an empty frame. Nothing raises.
  * The data already collected REMAINS VALID after the trial dies. The feed stops; the parquet
    stays and keeps serving history. That is the point of storing it separately.

  TO REMOVE ENTIRELY: `sudo systemctl disable --now goalserve-ingest.timer`, delete this file
  and `data_cache/goalserve_stats.parquet`, and drop GOALSERVE_KEY from backend/.env. Nothing
  else references it.

=============================================================================================
WHY IT EXISTS
=============================================================================================
Two gaps nothing else fills (measured 2026-10-12):

  1. STAT SPEED. TennisRatio's stat lines lag to 37-55% on the freshest three days, so L5/L3
     windows are often statless on a live card. Goalserve had 134 matches from YESTERDAY
     already populated -- 107 of them CHALLENGER, the level that dominates the board.

  2. ITF STATS. 91% of ITF players have no serve/return context anywhere. Goalserve's
     point-by-point feed carries real point sequences for ~15 ITF matches a day, with
     `@served_player`, `@lost_serve` and per-point `@break_point` flags -- so hold%, break%
     and break-point pressure can be DERIVED for ITF for the first time.

NEW STATS it carries that the TennisRatio archive does not: Winners, Unforced errors, Net
points won, Match points saved, Total/Service/Return points won, Total games won, Last 10
balls. Coverage varies sharply -- UE and Winners are ATP-only (57% of ATP matches, 0% WTA,
0% challenger, 0% ITF) -- so consumers must check per-field coverage, never assume it.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "data_cache", "goalserve_stats.parquet")
BASE = "https://www.goalserve.com/getfeed/%s/tennis_scores/"

# stat names as the feed spells them -> our column names. Anything not listed is ignored, so a
# feed-side rename shows up as a missing column rather than a crash.
STAT_MAP = {
    "aces": "gs_aces",
    "double faults": "gs_df",
    "1st serve percentage": "gs_sv1_pct",
    "1st serve points won": "gs_sv1_won",
    "2nd serve points won": "gs_sv2_won",
    "break points saved": "gs_bp_saved",
    "1st return points won": "gs_r1_won",
    "2nd return points won": "gs_r2_won",
    "break points converted": "gs_bp_conv",
    "service points won": "gs_svpts_won",
    "return points won": "gs_rtpts_won",
    "total points won": "gs_totpts_won",
    "match points saved": "gs_mp_saved",       # NEW
    "service games won": "gs_sgames_won",
    "return games won": "gs_rgames_won",
    "total games won": "gs_totgames_won",      # NEW
    "winners": "gs_winners",                   # NEW
    "unforced errors": "gs_ue",                # NEW (ATP only)
    "net points won": "gs_net_won",            # NEW
    "last 10 balls": "gs_last10",              # NEW
}


def _key() -> str | None:
    k = os.environ.get("GOALSERVE_KEY")
    if k:
        return k.strip()
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        try:
            for ln in open(p, encoding="utf-8", errors="replace"):
                if ln.strip().startswith("GOALSERVE_KEY") and "=" in ln:
                    return ln.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            return None
    return None


def enabled() -> bool:
    return bool(_key())


def _get(feed: str, timeout: int = 120):
    k = _key()
    if not k:
        return None, "no key"
    url = (BASE % k) + feed + "?json=1"
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip",
                                               "User-Agent": "matchup-edge/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            return json.loads(raw.decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %s" % e.code
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, str(e)[:90])


def _L(x):
    """The feed emits a bare object when a list has one element -- normalise everywhere."""
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _level(name: str) -> str:
    s = str(name).lower()
    if "itf" in s or "futures" in s:
        return "itf"
    if "challenger" in s:
        return "challenger"
    if "wta" in s:
        return "wta"
    if "atp" in s:
        return "atp"
    return "other"


def _surface(name: str) -> str | None:
    """Category names look like 'Atp - Singles: Shanghai (China), Hard'."""
    s = str(name).lower()
    for k, v in (("hard", "Hard"), ("clay", "Clay"), ("grass", "Grass"),
                 ("carpet", "Hard")):
        if k in s:
            return v
    return None


def _num(v):
    if v is None:
        return None
    s = str(v).strip().replace("%", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ------------------------------------------------------------------ game stats
def parse_gamestats(d) -> list[dict]:
    rows = []
    for c in _L((d or {}).get("statistics", {}).get("category")):
        cat = str(c.get("@name") or "")
        lvl, surf = _level(cat), _surface(cat)
        for m in _L(c.get("match")):
            mid = str(m.get("@id") or "")
            date = str(m.get("@date") or "")
            for p in _L(m.get("player")):
                r = {"src": "gamestats", "match_id": mid, "date_raw": date,
                     "tournament": cat, "level": lvl, "surface": surf,
                     "player": str(p.get("@name") or ""), "player_id": str(p.get("@id") or "")}
                for per in _L((p.get("stats") or {}).get("period")):
                    # only the whole-match period; per-set rows would double-count
                    if str(per.get("@name") or "").lower() != "match":
                        continue
                    for ty in _L(per.get("type")):
                        for st in _L(ty.get("stat")):
                            col = STAT_MAP.get(str(st.get("@name") or "").lower())
                            if not col:
                                continue
                            r[col] = _num(st.get("@value"))
                            # raw counts are what make a stat re-aggregatable into a 52w
                            # figure; a bare percentage cannot be summed across matches
                            won, tot = _num(st.get("@won")), _num(st.get("@total"))
                            if tot:
                                r[col + "_w"], r[col + "_t"] = won, tot
                if len(r) > 8:
                    rows.append(r)
    return rows


# ------------------------------------------------------------------ point by point
def parse_p2p(d) -> list[dict]:
    """Derive serve/return/pressure counts from point sequences.

    This is the ITF unlock: those matches carry no stat line, but they DO carry points. Only
    unambiguous quantities are derived -- who served each game and whether the server lost it,
    plus how many points were flagged as break/set/match points. Per-point winners would have
    to be inferred from score transitions, which is fragile, so they are deliberately not.
    """
    rows = []
    for c in _L((d or {}).get("scores", {}).get("category")):
        cat = str(c.get("@name") or "")
        lvl, surf = _level(cat), _surface(cat)
        for m in _L(c.get("match")):
            mid = str(m.get("@id") or "")
            date = str(m.get("@date") or "")
            # Parse BOTH players together. The first version derived each player's RETURN
            # numbers from the `@lost_serve` flag on games they did NOT serve, and validating
            # against the official stat line showed that is wrong: hold% matched 96% exactly
            # while break% was out by 53pt on average, because that flag does not mean what it
            # appears to on a non-served game (Dellavedova's 71.4% hold came back as Alkaya's
            # 71.4% "break"). Returns are now taken from the OPPONENT'S service games, which
            # is the half that validated.
            own = {}
            for p in _L(m.get("player")):
                pbp = p.get("pointbypoint")
                if not pbp:
                    continue
                sg = sgw = bp_faced = bp_saves = sp = mp = 0
                for per in _L(pbp.get("period")):
                    for game in _L((per.get("set") or {}).get("game")):
                        if str(game.get("@served_player") or "") != "True":
                            continue                      # only this player's OWN serve
                        lost = str(game.get("@lost_serve") or "") == "True"
                        pts = _L((game.get("points") or {}).get("play"))
                        nbp = sum(1 for x in pts
                                  if str(x.get("@break_point") or "") == "True")
                        sg += 1
                        if not lost:
                            sgw += 1
                        bp_faced += nbp
                        if nbp and not lost:
                            bp_saves += 1
                        sp += sum(1 for x in pts if str(x.get("@set_point") or "") == "True")
                        mp += sum(1 for x in pts if str(x.get("@match_point") or "") == "True")
                if sg:
                    own[str(p.get("@id") or "")] = {
                        "player": str(p.get("@name") or ""), "sg": sg, "sgw": sgw,
                        "bp_faced": bp_faced, "bp_saves": bp_saves, "sp": sp, "mp": mp}
            if len(own) != 2:
                continue                                  # need both halves to derive returns
            ids = list(own.keys())
            for i, pid in enumerate(ids):
                me, opp = own[pid], own[ids[1 - i]]
                rows.append({
                    "src": "p2p", "match_id": mid, "date_raw": date, "tournament": cat,
                    "level": lvl, "surface": surf,
                    "player": me["player"], "player_id": pid,
                    "p2p_sgames": me["sg"], "p2p_sgames_won": me["sgw"],
                    # my return games ARE my opponent's service games
                    "p2p_rgames": opp["sg"], "p2p_rgames_won": opp["sg"] - opp["sgw"],
                    "p2p_hold_pct": 100.0 * me["sgw"] / me["sg"],
                    "p2p_break_pct": 100.0 * (opp["sg"] - opp["sgw"]) / opp["sg"],
                    "p2p_bp_faced": me["bp_faced"], "p2p_bp_game_saves": me["bp_saves"],
                    "p2p_bp_chances": opp["bp_faced"],
                    "p2p_bp_game_convs": opp["sg"] - opp["sgw"],
                    "p2p_set_points": me["sp"], "p2p_match_points": me["mp"],
                })
    return rows


# ------------------------------------------------------------------ store
def ingest(days: int = 1, verbose: bool = True) -> int:
    """Pull d-1..d-N game stats and point-by-point, merge, append. Returns rows added."""
    if not enabled():
        if verbose:
            print("[goalserve] no key -- skipping (this is fine; the trial may have ended)")
        return 0
    got = []
    for i in range(1, max(1, days) + 1):
        for feed, parser in (("d-%d_gamestats" % i, parse_gamestats),
                             ("d-%d_p2p" % i, parse_p2p)):
            d, err = _get(feed)
            if err:
                if verbose:
                    print("[goalserve] %-16s %s" % (feed, err))
                continue
            try:
                rows = parser(d)
            except Exception as e:                     # a feed-shape change must not crash
                print("[goalserve] %-16s parse failed: %s" % (feed, e))
                continue
            if verbose:
                print("[goalserve] %-16s %d rows" % (feed, len(rows)))
            got.extend(rows)
    if not got:
        return 0
    new = pd.DataFrame(got)
    new["date"] = pd.to_datetime(new["date_raw"], format="%d.%m.%Y", errors="coerce")
    new["pulled_at"] = time.time()
    # one row per (match, player, source): re-pulling a day must not duplicate it
    keys = ["match_id", "player_id", "src"]
    if os.path.exists(STORE):
        try:
            old = pd.read_parquet(STORE)
            new = pd.concat([old, new], ignore_index=True)
        except Exception as e:
            print("[goalserve] could not read store (%s); starting fresh" % e)
    before = len(new)
    new = new.drop_duplicates(subset=keys, keep="last").reset_index(drop=True)
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    new.to_parquet(STORE, index=False)
    if verbose:
        print("[goalserve] stored %d rows (%d dropped as duplicates) -> %s"
              % (len(new), before - len(new), os.path.basename(STORE)))
    return len(new)


def load() -> pd.DataFrame:
    """Everything collected so far. Safe to call after the trial ends."""
    if not os.path.exists(STORE):
        return pd.DataFrame()
    try:
        return pd.read_parquet(STORE)
    except Exception:
        return pd.DataFrame()


# --------------------------------------------------------------- player profiles
# Goalserve names players "K. Khachanov"; the board uses "Karen Khachanov". Matching on
# surname + first initial is the same rule the name resolver's tier 5 uses, and it is unique
# enough within a single tournament field.
_PROFILE_CACHE = {"mtime": None, "v": None}


def _pkey(name: str) -> str:
    s = str(name or "").replace(".", " ").replace("-", " ").strip().lower()
    parts = [x for x in s.split() if x]
    if not parts:
        return ""
    surname = max(parts, key=len)
    initial = next((x[0] for x in parts if x is not surname and x), "")
    return "%s|%s" % (surname, initial)


def profiles() -> dict:
    """Per-player aggregates of the NEW stats, keyed by surname|initial, cached on store mtime.

    Only the stats TennisRatio does not already carry are aggregated here -- there is no point
    duplicating hold% and serve numbers the archive has at far greater depth. Coverage is
    sharply uneven (UE / winners / net points are ATP-only, ~57% of ATP matches and nothing
    elsewhere), so each field reports its OWN match count and callers must honour it.
    """
    try:
        mt = os.path.getmtime(STORE)
    except OSError:
        return {}
    if _PROFILE_CACHE["mtime"] == mt and _PROFILE_CACHE["v"] is not None:
        return _PROFILE_CACHE["v"]
    df = load()
    out = {}
    if not df.empty:
        g = df[df.src == "gamestats"] if "src" in df.columns else df
        for name, sub in g.groupby("player"):
            k = _pkey(name)
            if not k:
                continue
            rec = {"name": name, "n": int(len(sub))}
            for col, lab in (("gs_ue", "ue"), ("gs_winners", "win"),
                             ("gs_net_won", "net"), ("gs_mp_saved", "mp")):
                if col in sub.columns:
                    v = pd.to_numeric(sub[col], errors="coerce").dropna()
                    if len(v):
                        rec[lab] = round(float(v.mean()), 1)
                        rec[lab + "_n"] = int(len(v))
            # winners-to-unforced ratio: the shot-quality number neither feed gives directly
            if rec.get("win") and rec.get("ue"):
                rec["w2ue"] = round(rec["win"] / rec["ue"], 2) if rec["ue"] else None
            if len(rec) > 2:
                out[k] = rec
    _PROFILE_CACHE["mtime"], _PROFILE_CACHE["v"] = mt, out
    return out


def profile_for(name: str) -> dict | None:
    """Look up one player. Returns None when the trial store is absent or the player is not
    in it -- which is the common case, so callers must render nothing rather than a blank."""
    try:
        return profiles().get(_pkey(name))
    except Exception:
        return None


def health() -> dict:
    df = load()
    out = {"key_present": enabled(), "rows": len(df), "store": STORE}
    if not df.empty:
        out["dates"] = "%s..%s" % (str(df.date.min())[:10], str(df.date.max())[:10])
        out["by_level"] = df.groupby("level").size().to_dict()
        out["by_src"] = df.groupby("src").size().to_dict()
        out["last_pull"] = datetime.fromtimestamp(
            float(df.pulled_at.max()), timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        for c in ("gs_ue", "gs_winners", "gs_net_won", "p2p_hold_pct"):
            if c in df.columns:
                out["cov_" + c] = int(df[c].notna().sum())
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "health":
        for k, v in health().items():
            print("   %-18s %s" % (k, v))
    else:
        n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
        ingest(days=n)
        print()
        for k, v in health().items():
            print("   %-18s %s" % (k, v))
