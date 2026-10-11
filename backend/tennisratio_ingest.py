"""
tennisratio_ingest.py — pull player match logs (with odds) + surface/season stat splits from
tennisratio.com for the tennis tab. (Built 2026-09-25, user ask.)

Data sources discovered on the site:
  - GET /api/today-matches/{atp|wta}/                         -> today's matches (slugs, ranks, surface, level)
  - GET /players/{Slug}.html    (embedded JS "matches": [...]) -> per-match log: player_odd, rival_odd,
        rival_rank, surface, result, score + full serve/return stats + clutch-by-score points
  - GET /api/player/{Slug}/stats-comparison?range={52w|YYYY}&level=all&surface={all|hard|clay|grass}
        -> normalized aggregate stats (value + percentile + rank + total) per surface/season
  - GET /api/player/{Slug}/seasons/                            -> list of seasons available

Politeness: cached to data_cache/tennisratio/, a real UA, a min delay between requests, and a
per-file max-age so a scheduled refresh only re-fetches stale players. This hits one person's
site — keep the delay in place and don't parallelize hard.
"""
import json
import os
import time
import re

import requests
import pandas as pd

BASE = "https://www.tennisratio.com"
_here = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(_here, "data_cache", "tennisratio")
os.makedirs(CACHE_DIR, exist_ok=True)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}
_MIN_DELAY_S = 1.5           # be gentle: at least this long between network calls
_last_call = [0.0]


def _throttle():
    dt = time.monotonic() - _last_call[0]
    if dt < _MIN_DELAY_S:
        time.sleep(_MIN_DELAY_S - dt)
    _last_call[0] = time.monotonic()


def _get(url, as_json=False, tries=3):
    last = None
    for i in range(tries):
        _throttle()
        try:
            r = requests.get(url, headers=_HEADERS, timeout=25)
            if r.status_code == 200:
                return r.json() if as_json else r.text
            last = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last = str(e)
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"GET failed after {tries}: {url} ({last})")


def _extract_json_array(html, key):
    """Pull a balanced JSON array assigned to `key` out of embedded page script, respecting
    strings/escapes so commas or braces inside values don't fool a naive regex."""
    m = re.search(r'["\']?%s["\']?\s*[:=]\s*\[' % re.escape(key), html)
    if not m:
        return None
    i = html.index("[", m.end() - 1)
    depth, in_str, esc = 0, False, False
    for j in range(i, len(html)):
        c = html[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return json.loads(html[i:j + 1])
    return None


# ---------------------------------------------------------------- today's matches
def fetch_today_matches(tour, force=False, max_age_h=2):
    """tour in {'atp','wta'}. Returns list of scheduled matches with player slugs + ranks + surface."""
    tour = tour.lower()
    path = os.path.join(CACHE_DIR, f"today_{tour}.json")
    if not force and os.path.exists(path) and (time.time() - os.path.getmtime(path)) < max_age_h * 3600:
        return json.load(open(path, encoding="utf-8"))
    data = _get(f"{BASE}/api/today-matches/{tour}/", as_json=True)
    json.dump(data, open(path, "w", encoding="utf-8"))
    return data


# ---------------------------------------------------------------- per-player match log (with odds)
def fetch_player_matches(slug, force=False, max_age_h=24):
    """Per-match log embedded in the player page: odds, rank, surface, result, serve/return +
    clutch-by-score. Returns a DataFrame (one row per match). Cached to parquet."""
    path = os.path.join(CACHE_DIR, f"matches_{slug}.parquet")
    if not force and os.path.exists(path) and (time.time() - os.path.getmtime(path)) < max_age_h * 3600:
        return pd.read_parquet(path)
    html = _get(f"{BASE}/players/{slug}.html")
    arr = _extract_json_array(html, "matches")
    if not arr:
        raise RuntimeError(f"no matches blob found for {slug}")
    df = pd.DataFrame(arr)
    df["player_slug"] = slug
    df.to_parquet(path, index=False)
    return df


# ---------------------------------------------------------------- normalized stat splits
def fetch_player_stats(slug, surface="all", rng="52w", level="all", force=False, max_age_h=24):
    """Normalized aggregate stats (value/percentile/rank/total) for a surface + range.
    rng: '52w' or a season year like '2025'. surface: all|hard|clay|grass."""
    path = os.path.join(CACHE_DIR, f"stats_{slug}_{surface}_{rng}.json")
    if not force and os.path.exists(path) and (time.time() - os.path.getmtime(path)) < max_age_h * 3600:
        return json.load(open(path, encoding="utf-8"))
    data = _get(f"{BASE}/api/player/{slug}/stats-comparison?range={rng}&level={level}&surface={surface}", as_json=True)
    json.dump(data, open(path, "w", encoding="utf-8"))
    return data


def fetch_player_seasons(slug):
    return _get(f"{BASE}/api/player/{slug}/seasons/", as_json=True)


# ---------------------------------------------------------------- player universe
#: how far back to chase players whose recent rows never landed, and how many per run
STALE_DAYS = 21
STALE_LIMIT = 350


def discover_active_slugs(tours=("atp", "wta"), include_stale=True):
    """Players in today's/upcoming matches — the ones that matter for betting. Rankings-based
    top-200 enumeration is a separate step (no clean rankings API found yet).

    PLUS (2026-10-10) the players whose RECENT ROWS ARE MISSING. Walking only today's slate is
    winner-biased: a winner advances, is on tomorrow's slate and gets refreshed, so their row
    lands; a loser is out of the draw, never reappears here, and their loss row never lands
    until they enter a new tournament. Measured before this fix, one-sided archive rows aged
    0-7 days were 96.8% wins (78.7% of the priced rows that young had no mirror at all), which
    overstated recent win rates by +0.064 on average for 45% of active players -- straight into
    l10, form_win, sn_win and d_m_won on the live board.

    tennis_archive.stale_slugs() names them exactly: a one-sided row in the window whose
    opponent is TRACKED means that opponent played the match and their own row was never
    fetched. Capped at STALE_LIMIT per run, most recent first, and failure-tolerant -- the
    nightly must never die because this extra pass could not run."""
    slugs = {}
    for t in tours:
        for mt in fetch_today_matches(t):
            for k in ("player1_slug", "player2_slug"):
                s = mt.get(k)
                if s:
                    slugs[s] = {"tour": t.upper(),
                                "name": mt.get(k.replace("_slug", "_name")),
                                "rank": mt.get(k.replace("_slug", "_rank"))}
    if not include_stale:
        return slugs
    try:
        import tennis_archive
        stale = tennis_archive.stale_slugs(days=STALE_DAYS, limit=STALE_LIMIT)
        added = 0
        for s in stale:
            if s and s not in slugs:
                slugs[s] = {"tour": None, "name": None, "rank": None}
                added += 1
        print(f"  [stale] +{added} players whose last {STALE_DAYS}d rows never landed "
              f"(of {len(stale)} found; cap {STALE_LIMIT})")
    except Exception as e:  # noqa: BLE001 -- never let this break the nightly refresh
        print(f"  [stale] skipped: {e}")
    return slugs


def ingest_match_logs(slugs, force=False):
    """Fetch + concat many players' match logs into one DataFrame (deduped on player+date+rival)."""
    frames = []
    for i, s in enumerate(slugs):
        try:
            frames.append(fetch_player_matches(s, force=force))
        except Exception as e:  # noqa: BLE001 -- keep going; report at the end
            print(f"  [skip] {s}: {e}")
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    if {"player_slug", "date", "rival_name"}.issubset(out.columns):
        out = out.drop_duplicates(["player_slug", "date", "rival_name"]).reset_index(drop=True)
    return out


def _rebuild_combined():
    import glob
    frames = []
    for f in glob.glob(os.path.join(CACHE_DIR, "matches_*.parquet")):
        try:
            frames.append(pd.read_parquet(f))
        except Exception:  # noqa: BLE001
            pass
    if not frames:
        return 0
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(["player_slug", "date", "rival_name"]).reset_index(drop=True)
    out.to_parquet(os.path.join(CACHE_DIR, "all_match_logs.parquet"), index=False)
    return len(out)


def _guess_slug(name):
    import unicodedata
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return "".join(w.capitalize() for w in re.sub(r"[^A-Za-z ]", " ", s).split())


def ingest_names(names):
    """Slug-guess player pages for OUR slate's names that aren't in the pool yet (2026-09-26:
    TennisRatio's own today-feed misses whole events -- e.g. WTA 125K Adana had Boisson with a
    page but no feed entry). A page the site doesn't serve gets a 'miss' marker retried after
    3 days (they keep adding pages). Rebuilds the combined log when anything new lands, so
    tennis_context hot-reloads."""
    added = 0
    for nm in set(names):
        slug = _guess_slug(nm)
        if not slug:
            continue
        if os.path.exists(os.path.join(CACHE_DIR, f"matches_{slug}.parquet")):
            continue
        marker = os.path.join(CACHE_DIR, f"miss_{slug}")
        if os.path.exists(marker) and (time.time() - os.path.getmtime(marker)) < 3 * 86400:
            continue
        try:
            fetch_player_matches(slug)
            added += 1
            if os.path.exists(marker):
                os.remove(marker)
        except Exception:  # noqa: BLE001 -- no page (yet): remember and move on
            open(marker, "w").close()
    if added:
        n = _rebuild_combined()
        print(f"[pool] ingest_names: +{added} new players, combined log {n} matches")
    return added


def refresh_daily_pool():
    """Daily pool refresh (2026-09-26, user ask): walk EVERY player on today's ATP + WTA
    slates, fetch/refresh their match log -- including players whose pages the site only
    recently added (unknown slugs are simply attempted; ~1 request each). A player the site
    still doesn't serve is skipped, so their matches carry no context and no SR-DOG flag
    (they're just passed over). Rebuilds all_match_logs.parquet at the end so tennis_context
    hot-reloads it (its cache is keyed on the parquet's mtime)."""
    for t in ("atp", "wta"):
        try:
            fetch_today_matches(t, force=True)
        except Exception as e:  # noqa: BLE001
            print(f"[pool] today-matches {t} failed: {e}")
    slugs = discover_active_slugs()
    ok, missing = [], []
    for s in slugs:
        try:
            fetch_player_matches(s, max_age_h=20)
            ok.append(s)
        except Exception:  # noqa: BLE001 -- page not served (or transient): skip, match gets no flag
            missing.append(s)
    import glob
    frames = []
    for f in glob.glob(os.path.join(CACHE_DIR, "matches_*.parquet")):
        try:
            frames.append(pd.read_parquet(f))
        except Exception:  # noqa: BLE001
            pass
    if frames:
        out = pd.concat(frames, ignore_index=True)
        out = out.drop_duplicates(["player_slug", "date", "rival_name"]).reset_index(drop=True)
        out.to_parquet(os.path.join(CACHE_DIR, "all_match_logs.parquet"), index=False)
        print(f"[pool] refreshed: {len(ok)} players ok, {len(missing)} not on site "
              f"({', '.join(missing[:6])}{'...' if len(missing) > 6 else ''}); "
              f"combined log {len(out)} matches across {out['player_slug'].nunique()} players")
    return len(ok), len(missing)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--refresh-daily":
        refresh_daily_pool()
        sys.exit(0)
    slug = sys.argv[1] if len(sys.argv) > 1 else "CasperRuud"
    print(f"— seasons for {slug}:", fetch_player_seasons(slug))
    dfm = fetch_player_matches(slug, force=True)
    print(f"— {slug} match log: {len(dfm)} matches, {dfm['date'].min()} -> {dfm['date'].max()}")
    cols = ["date", "tournament", "surface", "rival_name", "rival_rank", "result", "player_odd", "rival_odd"]
    print(dfm[[c for c in cols if c in dfm.columns]].head(6).to_string(index=False))
    print("— odds non-null:", int(dfm["player_odd"].notna().sum()), "/", len(dfm),
          "| surfaces:", dfm["surface"].value_counts().to_dict() if "surface" in dfm.columns else "n/a")
    st = fetch_player_stats(slug, surface="clay", rng="52w", force=True)
    comp = (st.get("comparison") or {}).get("clay", {})
    print("— clay 52w serve keys:", list((comp.get("serve") or {}).keys()))
