"""
tennis_context.py — TennisRatio DISPLAY-ONLY context for the tennis tab.

v2 (2026-09-25, after user caught v1 "all stats wrong"): v1 displayed invented blended
composites ("serve 60%") that matched no real tennis stat, and pooled ATP+WTA together for
percentiles. Now serves the REAL stats under their real names — 1st/2nd Serve Points Won,
Service Games Won, Return 1st/2nd Points Won, Return Games Won — over the same 52-week
surface window tennisratio.com uses (verified vs the site: games-won ratios match exactly,
point-%s within ~1pt), with percentile pools split BY TOUR.

CONTEXT, NOT AN EDGE: the 2026-09-25 backtest showed none of this beats the market's
calibration (opponent-adjusted included). It exists so a human can eyeball a matchup next to
the scanner's price edges — the validated tennis edge remains the cross-book price scanner.
"""
import json
import os
import re
import unicodedata

import numpy as np
import pandas as pd

_here = os.path.dirname(os.path.abspath(__file__))
TR_DIR = os.path.join(_here, "data_cache", "tennisratio")
LOGS_PARQUET = os.path.join(TR_DIR, "all_match_logs.parquet")

_cache = {"mtime": None, "profiles": None, "name_index": None}
# AS-OF MEMO (2026-10-11): context_asof is deterministic given (player, surface, asof) and the
# loaded profiles -- it reads only matches strictly BEFORE asof, so a past date's answer never
# changes while the profile cache is unchanged. The history endpoint calls it twice per row
# across 30 days of rows, and adding the L3 window pushed that to ~8s per request. Memoised
# here and invalidated on profile reload (keyed on the same mtime `_load` tracks).
_asof_memo = {"mtime": None, "v": {}}
_ASOF_MEMO_MAX = 20000


def _norm_name(name):
    """Accent-stripped, punctuation-free, token-sorted key so 'Ruud, Casper' == 'Casper Ruud'."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    toks = re.sub(r"[^a-z ]", " ", s.lower().replace(",", " ")).split()
    return " ".join(sorted(toks))



# Tier-5 safety check (2026-10-13). See _patch_tier5.py: tier 5 reduces a name to
# (alphabetically-last token, alphabetically-first token's initial), which collides across
# different people -- "adan freire da silva" and "andrade da lucas silva" both give
# (silva, a). This confirms the candidate is the SAME PERSON before tier 5 is trusted.
_T5_PARTICLES = {"da", "de", "del", "dos", "das", "van", "von", "la", "le", "di", "el",
                 "bin", "al", "ben", "der", "den", "do", "dela"}


def _t5_same_person(query_norm, profile_keys):
    """True when every substantive token of the profile has a partner in the query.

    Partner = identical, a 3+ character shared prefix (caty~catherine), or a close spelling
    (Deigo~Diego, Giorgia~Georgia, which differ at character 2 so a prefix rule misses them).
    Checked in this direction because boards legitimately ADD tokens to a name; requiring
    every QUERY token to match was measured and destroyed four correct resolutions.
    """
    import difflib
    import os as _os
    sub = lambda k: [t for t in k.split() if t not in _T5_PARTICLES]
    qs = sub(query_norm)
    if not qs:
        return False

    def partner(p):
        for t in qs:
            if p == t or len(_os.path.commonprefix([p, t])) >= 3:
                return True
            if difflib.SequenceMatcher(None, p, t).ratio() >= 0.75:
                return True
        return False

    for k in profile_keys:
        ps = sub(k)
        if ps and all(partner(p) for p in ps):
            return True
    return False


def _slug_to_name(slug):
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", slug)


def _fin(v, nd=1):
    v = float(v)
    return round(v, nd) if np.isfinite(v) else None


def _tour_map():
    """slug -> 'atp'|'wta' from the cached today-matches discovery files."""
    tours = {}
    for t in ("atp", "wta"):
        fp = os.path.join(TR_DIR, f"today_{t}.json")
        try:
            for mtc in json.load(open(fp, encoding="utf-8")):
                for k in ("player1_slug", "player2_slug"):
                    s = mtc.get(k)
                    if s:
                        tours[s] = t
        except (OSError, ValueError):
            pass
    return tours


def _pressure_season(sub, year, min_pts=60):
    """SEASON + COURT pressure dials (2026-10-11, user: "I want the pressure point stats
    season and court specific").

    TennisRatio's Compare Players screen reads "This Season / All Levels / <surface>", so the
    window is the CALENDAR SEASON on that court, not a rolling 52 weeks. `sub` arrives already
    filtered to the surface; this cuts it to `year`.

    Early in a season that leaves almost nothing, so when either dial has fewer than `min_pts`
    pressure points the window falls back to the trailing 52 weeks and the returned `win` field
    says which was used -- the card shows the label, so a thin season figure can never be
    mistaken for a full one.
    """
    season = sub[sub["date"].dt.year == year] if year else sub.iloc[0:0]
    svp, rtp, spn, rpn = _pressure(season)
    if spn >= min_pts and rpn >= min_pts:
        return svp, rtp, spn, rpn, "season"
    return None, None, spn, rpn, "thin"


def _pressure(w):
    """SURFACE-SPECIFIC pressure dials (2026-10-11, user: "add surface unique return and serve
    pressure points won on every slip so I can see").

    These are the two circles TennisRatio shows on its Compare Players screen, and until now
    the app computed only their BLEND: `clutch` sums serve and return pressure together over
    the last 25 matches on ANY surface, so the split was never visible and the surface was
    never respected. This returns them separately, over whatever window `w` is -- the caller
    passes the surface-filtered 52-week frame, so the numbers are surface-unique.

        serve  = serve_pressure_won / serve_pressure_all
        return = return_pressure_won / return_pressure_all

    Returns (serve%, return%, serve_pts, return_pts) with the denominators, because a dial off
    30 points is not the same claim as one off 500 and the card should be able to say so.
    None when the window carries no pressure data at all -- coverage is ~46% of archive rows,
    far short of the serve lines.
    """
    try:
        sa = float(w["serve_pressure_all"].fillna(0).sum())
        sw = float(w["serve_pressure_won"].fillna(0).sum())
        ra = float(w["return_pressure_all"].fillna(0).sum())
        rw = float(w["return_pressure_won"].fillna(0).sum())
    except Exception:
        return None, None, 0, 0
    return (_fin(100 * sw / sa) if sa > 0 else None,
            _fin(100 * rw / ra) if ra > 0 else None,
            int(sa), int(ra))


def _load():
    try:
        mtime = os.path.getmtime(LOGS_PARQUET)
    except OSError:
        return None
    if _cache["profiles"] is not None and _cache["mtime"] == mtime:
        return _cache
    df = pd.read_parquet(LOGS_PARQUET)
    df["surface"] = df["surface"].astype(str).str.title()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for c in ("player_odd", "rival_rank", "first_serve_points", "second_serve_points",
              "return_1st_serve_points", "return_2nd_serve_points", "serve_pressure_all",
              "serve_pressure_won", "return_pressure_all", "return_pressure_won"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for col, pre in (("service_games_won", "sg"), ("return_games_won", "rg")):
        parts = df[col].astype(str).str.extract(r"^(\d+)/(\d+)$")
        df[pre + "_won"] = pd.to_numeric(parts[0], errors="coerce")
        df[pre + "_all"] = pd.to_numeric(parts[1], errors="coerce")
    df = df[df["date"].notna()].sort_values(["player_slug", "date"])
    df["won"] = (df["result"] == "Win").astype(int)
    # Model-D context columns for the AS-OF history line (2026-10-20, user ask: show the
    # same per-player line under finished games). Both are vectorised one-off passes over
    # the whole frame, mirroring tennis_model_a._parse so the numbers agree with the board:
    #   lvl      -- tour / challenger / ITF bucket, for the home-platform share
    #   opp_form -- each opponent's OWN last-10 win rate AT THE TIME they played, so
    #               opponent quality is judged by real form and never by ranking
    _lv = df["tournament_level"].astype(str).str.lower()
    df["lvl"] = np.where(_lv.str.contains("challenger"), 1,
                         np.where(_lv.str.contains("futures|itf"), 2, 0))
    _s0 = df.groupby("player_slug", sort=False)["won"].shift(1)
    df["_o10w"] = _s0.groupby(df["player_slug"]).rolling(10, min_periods=4).mean() \
        .reset_index(level=0, drop=True)
    _opp = df[["player_slug", "date", "_o10w"]].rename(
        columns={"player_slug": "rival_slugname", "_o10w": "opp_form"}
    ).drop_duplicates(["rival_slugname", "date"])
    df = df.merge(_opp, on=["rival_slugname", "date"], how="left")
    df = df.sort_values(["player_slug", "date"])
    cutoff = df["date"].max() - pd.Timedelta(weeks=52)
    tours = _tour_map()

    profiles = {}
    for slug, gdf in df.groupby("player_slug"):
        levels = set(gdf["tournament_level"].dropna().unique())
        tour = tours.get(slug) or ("wta" if "WTA" in levels else ("atp" if "ATP" in levels else None))
        p = {"slug": slug, "tour": tour, "surfaces": {},
             "last_date": str(gdf["date"].max().date()), "n_matches": int(len(gdf))}
        for surf in ("Hard", "Clay", "Grass", "All"):
            sub = gdf if surf == "All" else gdf[gdf["surface"] == surf]
            w = sub[sub["date"] >= cutoff]           # the site's 52-week window
            window = "52w"
            if len(w) < 5:                            # thin recent sample -> fall back to last 20 ever
                w, window = sub.tail(20), "L20"
            if len(w) < 5:
                continue
            # sr10: the pre-registered SR-DOG tracker's exact composite -- last 10 matches ON
            # this surface (any date), serve_comp + ret_comp. Kept separate from the display
            # window above so the tracker matches the rule that was actually backtested
            # (2025 +21.2%/90, 2026 +1.2%/89 flat at real odds, dog-priced only).
            t10 = sub.tail(10)
            sr10 = None
            if len(t10) >= 5:
                v = float((0.6 * t10["first_serve_points"] + 0.4 * t10["second_serve_points"]).mean()
                          + (0.5 * t10["return_1st_serve_points"] + 0.5 * t10["return_2nd_serve_points"]).mean())
                sr10 = round(v, 2) if np.isfinite(v) else None
            sga, rga = w["sg_all"].sum(), w["rg_all"].sum()
            # BOTH WINDOWS (2026-10-11, user picked "Option 3" after the season-vs-52w test).
            # Season matches what TennisRatio's Compare Players screen shows, so the card can
            # be cross-checked against the phone. But the archive says 52w is the better READ:
            # where the two disagree about who leads, 52w picks the winner 52.7% of the time on
            # serve-pressure against season's 47.3%, and 51.0% vs 49.0% on return-pressure
            # (EDGE +1.7pt vs -1.7pt). Season only wins Oct-Dec, when its window is finally
            # full -- it is a sample-size effect, not a recency one. So show both and let the
            # divergence be visible rather than picking one and hiding the disagreement.
            _yr = int(gdf["date"].max().year)
            _svp, _rtp, _spn, _rpn, _pwin = _pressure_season(sub, _yr)
            if _pwin == "thin":                       # season too sparse -> no season figure
                _svp = _rtp = None
                _pwin = None
            _svp52, _rtp52, _spn52, _rpn52 = _pressure(w)      # 52w on this surface
            p["surfaces"][surf] = {
                "sr10": sr10,
                "svp": _svp, "rtp": _rtp, "svp_n": _spn, "rtp_n": _rpn, "p_win": _pwin,
                "svp52": _svp52, "rtp52": _rtp52,
                "svp52_n": _spn52, "rtp52_n": _rpn52, "p_win52": window,
                "n": int(len(w)), "window": window,
                "sv1": _fin(w["first_serve_points"].mean()),      # 1st Serve Points Won %
                "sv2": _fin(w["second_serve_points"].mean()),     # 2nd Serve Points Won %
                "sgw": _fin(100 * w["sg_won"].sum() / sga) if sga else None,   # Service Games Won %
                "r1": _fin(w["return_1st_serve_points"].mean()),  # Return 1st Serve Points %
                "r2": _fin(w["return_2nd_serve_points"].mean()),  # Return 2nd Serve Points %
                "rgw": _fin(100 * w["rg_won"].sum() / rga) if rga else None,   # Return Games Won %
                "win": round(float(w["won"].mean()), 3),
            }
            # SHORT WINDOWS ON THIS SURFACE (L10 2026-10-11, then L5 and L3 the same day on
            # "And l5 stats" / "can u add a l3 under the l5 as well"). L3 is exactly three
            # matches whenever it exists, since the floor below is three.
            # Same stat set as the 52w block above and the same surface -- only the window
            # length differs. SGW/RGW are rebuilt from the game SUMS rather than averaged,
            # exactly as the 52w figures are, so every line is directly comparable.
            for _tag, _k in (("l10", 10), ("l5", 5), ("l3", 3)):
                _w = sub.tail(_k)
                if len(_w) < 3:
                    continue
                _sga, _rga = _w["sg_all"].sum(), _w["rg_all"].sum()
                p["surfaces"][surf][_tag] = {
                    "n": int(len(_w)),
                    "sv1": _fin(_w["first_serve_points"].mean()),
                    "sv2": _fin(_w["second_serve_points"].mean()),
                    "sgw": _fin(100 * _w["sg_won"].sum() / _sga) if _sga else None,
                    "r1": _fin(_w["return_1st_serve_points"].mean()),
                    "r2": _fin(_w["return_2nd_serve_points"].mean()),
                    "rgw": _fin(100 * _w["rg_won"].sum() / _rga) if _rga else None,
                    "win": round(float(_w["won"].mean()), 3),
                    "from": str(_w["date"].min().date()),
                }
        recent = gdf.tail(25)
        good = recent[recent["rival_rank"] <= 200]
        p["vs_top200"] = {"w": int(good["won"].sum()), "l": int(len(good) - good["won"].sum())}
        oddsy = recent[recent["player_odd"].notna() & (recent["player_odd"] > 1.005)]
        p["perf_vs_mkt"] = (_fin((oddsy["won"] - 1 / oddsy["player_odd"]).mean(), 3)
                            if len(oddsy) >= 5 else None)
        pr_all = recent["serve_pressure_all"].fillna(0).sum() + recent["return_pressure_all"].fillna(0).sum()
        pr_won = recent["serve_pressure_won"].fillna(0).sum() + recent["return_pressure_won"].fillna(0).sum()
        p["clutch"] = round(float(pr_won / pr_all), 3) if pr_all >= 40 else None
        ranks = gdf.tail(10)["rival_rank"].dropna()
        p["avg_opp_rank"] = int(ranks.median()) if len(ranks) >= 3 else None
        profiles[slug] = p

    # percentiles WITHIN TOUR per surface, on the two summary strengths (SGW = serve, RGW = return)
    for tour in ("atp", "wta"):
        pool = [p for p in profiles.values() if p["tour"] == tour]
        for surf in ("Hard", "Clay", "Grass", "All"):
            for stat in ("sgw", "rgw"):
                vals = sorted(p["surfaces"][surf][stat] for p in pool
                              if surf in p["surfaces"] and p["surfaces"][surf][stat] is not None)
                if len(vals) < 10:
                    continue
                arr = np.array(vals)
                for p in pool:
                    if surf in p["surfaces"] and p["surfaces"][surf][stat] is not None:
                        v = p["surfaces"][surf][stat]
                        p["surfaces"][surf][stat + "_pct"] = int(round(100 * (arr < v).mean()))

    name_index = {_norm_name(_slug_to_name(slug)): slug for slug in profiles}
    # per-player match rows kept for AS-OF stats (results history, 2026-10-09)
    _cache["groups"] = {slug: g for slug, g in df.groupby("player_slug")}
    # tournament -> surface from OUR OWN logs (2026-09-30, Curitiba-clay fix): the old tour
    # metadata misses challengers and defaulted them to Hard; recent 16 months of the 613k-
    # match dataset knows every event's true surface (Curitiba: Clay 100/100).
    tcut = df["date"].max() - pd.Timedelta(days=480)
    tsurf = {}
    for tname, g in df[df["date"] >= tcut].groupby(df["tournament"].astype(str).str.lower()):
        mode = g["surface"].mode()
        if len(mode):
            tsurf[tname] = str(mode.iloc[0])
    _cache.update({"mtime": mtime, "profiles": profiles, "name_index": name_index,
                   "tsurf": tsurf})
    return _cache


def get_tournament_surface(name):
    """Surface for a tournament name ("Curitiba, Brazil") from our own recent logs --
    city-token containment, majority surface. None when unknown."""
    c = _load()
    if not c or not name:
        return None
    city = str(name).split(",")[0].strip().lower()
    if len(city) < 4:
        return None
    hits = [s for t, s in (c.get("tsurf") or {}).items() if city in t]
    if not hits:
        return None
    return max(set(hits), key=hits.count)


def get_context(player_name, surface=None):
    """Compact display context for one player on one surface (or overall). None if the player
    isn't in the ingested TennisRatio pool (e.g. most ITF fields)."""
    c = _load()
    if not c or not player_name:
        return None
    slug = c["name_index"].get(_norm_name(player_name))
    if slug is None:
        # token-subset fallback (2026-09-28, Ayeni case): boards abbreviate long names --
        # "Alafia Ayeni" vs the site's "Olukayode Alafia Damina Ayeni". Match when the
        # board name's tokens are a subset of exactly ONE profile's tokens.
        qt = set(_norm_name(player_name).split())
        if len(qt) >= 2:
            hits = [s for k, s in c["name_index"].items() if qt <= set(k.split())]
            if len(hits) != 1:
                # tier 2: PROFILE tokens subset of QUERY (board adds middle names:
                # "Joel Josef Schwaerzler" vs the site's "Joel Schwaerzler")
                hits = [s for k, s in c["name_index"].items()
                        if len(set(k.split())) >= 2 and set(k.split()) <= qt]
            if len(hits) != 1:
                # tier 3: token decomposition -- a query token may be a FUSION of adjacent
                # profile tokens ("YeXin Ma" vs "Ye Xin Ma"): every query token must be a
                # profile token or a concatenation of them.
                def _covers(ptoks, t):
                    if t in ptoks:
                        return True
                    for i in range(1, len(t)):
                        if t[:i] in ptoks and _covers(ptoks, t[i:]):
                            return True
                    return False
                hits = [s for k, s in c["name_index"].items()
                        if all(_covers(set(k.split()), t) for t in qt)]
            if len(hits) != 1:
                # tier 4: transliteration fuzz (2026-09-30, Starodubtseva case) --
                # feed "Yulia" vs the site's "Yuliia". Keep in lockstep with
                # tennis_model_a.resolve.
                import difflib
                nmq = _norm_name(player_name)
                close = difflib.get_close_matches(nmq, list(c["name_index"]), n=2, cutoff=0.88)
                if len(close) == 1:
                    hits = [c["name_index"][close[0]]]
                elif len(close) == 2:
                    r = [difflib.SequenceMatcher(None, nmq, x).ratio() for x in close]
                    if r[0] - r[1] >= 0.06:
                        hits = [c["name_index"][close[0]]]
            if len(hits) != 1:
                # tier 5: SURNAME + FIRST INITIAL (2026-10-11, Catherine/Caty McNally
                # case). Nickname-vs-formal-name swaps defeat every tier above -- the token
                # sets are not subsets either way and difflib scores below 0.80. Only taken
                # when surname+initial is UNIQUE in the pool (non-unique for 88 of 1,760
                # names, which are therefore left unresolved rather than guessed). Measured
                # on 391 board players: recovers 1 of 47 misses and disagrees with 0 of 344
                # existing resolutions.
                _qt = _norm_name(player_name).split()
                if len(_qt) >= 2:
                    _sur, _ini = _qt[-1], _qt[0][0]
                    hits = [v for k, v in c["name_index"].items()
                            if (lambda p: len(p) >= 2 and p[-1] == _sur
                                and p[0][:1] == _ini)(k.split())]
                    # (silva, a) matches strangers, so confirm it is the same person
                    if len(hits) == 1 and not _t5_same_person(
                            _norm_name(player_name), [k for k, v in c["name_index"].items() if v == hits[0]]):
                        hits = []
            if len(hits) == 1:
                slug = hits[0]
    if not slug:
        return None
    p = c["profiles"][slug]
    surf = (surface or "All").title()
    s = p["surfaces"].get(surf) or p["surfaces"].get("All")
    return {
        "slug": slug, "tour": p["tour"], "surface_used": surf if surf in p["surfaces"] else "All",
        "surface_stats": s,
        "vs_top200": p["vs_top200"], "perf_vs_mkt": p["perf_vs_mkt"],
        "clutch": p["clutch"], "avg_opp_rank": p["avg_opp_rank"],
        "last_date": p["last_date"], "n_matches": p["n_matches"],
    }



def context_asof(player_name, surface, asof):
    """Memoising wrapper around `_context_asof_uncached`.

    Keyed on (name, surface, asof-DAY) and dropped whenever the profile parquet's mtime changes,
    so a re-ingest is picked up but repeated lookups inside one request are free. The day
    granularity is safe because the underlying computation already truncates to `date <  asof`.
    """
    try:
        mtime = os.path.getmtime(LOGS_PARQUET)
    except OSError:
        mtime = None
    if _asof_memo["mtime"] != mtime:
        _asof_memo["mtime"] = mtime
        _asof_memo["v"] = {}
    key = (str(player_name), str(surface), str(asof)[:10])
    memo = _asof_memo["v"]
    if key in memo:
        return memo[key]
    out = _context_asof_uncached(player_name, surface, asof)
    if len(memo) < _ASOF_MEMO_MAX:          # bounded: never let a long-running process grow
        memo[key] = out
    return out


def _context_asof_uncached(player_name, surface, asof):
    """Serve/return context AS IT STOOD BEFORE `asof` (2026-10-09, user "I want to see
    serve/return stats on the previous day page"): same fields as get_context's surface
    stats, computed only from this player's matches strictly before the match date (52-week
    window on the surface, else last 20 on it). No hindsight -- the match itself and anything
    after it are excluded."""
    c = _load()
    if not c or not player_name or asof is None:
        return None
    cur = get_context(player_name, surface)
    if not cur:
        return None
    g = (c.get("groups") or {}).get(cur["slug"])
    if g is None:
        return None
    asof = pd.Timestamp(asof)
    g = g[g["date"] < asof]
    if g.empty:
        return None
    surf = (surface or "All").title()
    sub = g if surf == "All" else g[g["surface"] == surf]
    w, window = sub[sub["date"] >= asof - pd.Timedelta(weeks=52)], "52w"
    if len(w) < 5:
        w, window = sub.tail(20), "L20"
    if len(w) < 5:
        sub, surf = g, "All"
        w, window = g[g["date"] >= asof - pd.Timedelta(weeks=52)], "52w"
        if len(w) < 5:
            w, window = g.tail(20), "L20"
        if len(w) < 5:
            return None
    sga, rga = w["sg_all"].sum(), w["rg_all"].sum()
    # both windows on the replay path too, season taken from the AS-OF date
    _svp, _rtp, _spn, _rpn, _pwin = _pressure_season(sub, int(asof.year))
    if _pwin == "thin":
        _svp = _rtp = None
        _pwin = None
    _svp52, _rtp52, _spn52, _rpn52 = _pressure(w)
    stats = {"n": int(len(w)), "window": window,
             "svp": _svp, "rtp": _rtp, "svp_n": _spn, "rtp_n": _rpn, "p_win": _pwin,
             "svp52": _svp52, "rtp52": _rtp52,
             "svp52_n": _spn52, "rtp52_n": _rpn52, "p_win52": window,
             "sv1": _fin(w["first_serve_points"].mean()), "sv2": _fin(w["second_serve_points"].mean()),
             "sgw": _fin(100 * w["sg_won"].sum() / sga) if sga else None,
             "r1": _fin(w["return_1st_serve_points"].mean()), "r2": _fin(w["return_2nd_serve_points"].mean()),
             "rgw": _fin(100 * w["rg_won"].sum() / rga) if rga else None,
             "win": round(float(w["won"].mean()), 3)}
    # LAST 10 ON THIS SURFACE (2026-10-11, user ask: "below the hard 52w stats can u give
    # hard l10 game stats too"). Same stat set and the same pre-match cut as the 52w block
    # above -- only the window differs -- and SGW/RGW are rebuilt from the game sums rather
    # than averaged so the two lines are directly comparable. `sub` is already filtered to
    # the chosen surface; if the 52w fallback widened to All, this follows it.
    short = {}
    for _tag, _k in (("l10", 10), ("l5", 5), ("l3", 3)):
        _w = sub.tail(_k)
        if len(_w) < 3:
            continue
        _sga, _rga = _w["sg_all"].sum(), _w["rg_all"].sum()
        short[_tag] = {
            "n": int(len(_w)),
            "sv1": _fin(_w["first_serve_points"].mean()),
            "sv2": _fin(_w["second_serve_points"].mean()),
            "sgw": _fin(100 * _w["sg_won"].sum() / _sga) if _sga else None,
            "r1": _fin(_w["return_1st_serve_points"].mean()),
            "r2": _fin(_w["return_2nd_serve_points"].mean()),
            "rgw": _fin(100 * _w["rg_won"].sum() / _rga) if _rga else None,
            "win": round(float(_w["won"].mean()), 3),
            "from": str(_w["date"].min().date()),
        }
    stats_l10, stats_l5, stats_l3 = short.get("l10"), short.get("l5"), short.get("l3")
    recent = g.tail(25)
    good = recent[recent["rival_rank"] <= 200]
    pr_all = recent["serve_pressure_all"].fillna(0).sum() + recent["return_pressure_all"].fillna(0).sum()
    pr_won = recent["serve_pressure_won"].fillna(0).sum() + recent["return_pressure_won"].fillna(0).sum()
    ranks = g.tail(10)["rival_rank"].dropna()
    return {"slug": cur["slug"], "tour": cur.get("tour"), "surface_used": surf, "surface_stats": stats,
            "surface_l10": stats_l10, "surface_l5": stats_l5, "surface_l3": stats_l3,
            "vs_top200": {"w": int(good["won"].sum()), "l": int(len(good) - good["won"].sum())},
            "clutch": round(float(pr_won / pr_all), 3) if pr_all >= 40 else None,
            "avg_opp_rank": int(ranks.median()) if len(ranks) >= 3 else None,
            "asof": str(asof.date()), "last_date": str(g["date"].max().date())}


# ---------------------------------------------------------------- AS-OF Model-D line
_dline_memo = {"mtime": None, "v": {}}


def dline_asof(player_name, surface, asof, level=None):
    """The card's per-player context line AS IT STOOD BEFORE `asof` (2026-10-20 user ask:
    show it under finished games too).

    Same four pieces and the same definitions as the live board line, so a past game reads
    exactly like a current one:
      w52        W-L over the rolling 52 weeks ON THIS COURT, with its win rate
      l10 / form last-10 win rate on this court, and how far that sits above or below the
                 player's OWN 52-week norm on this court
      lvl        share of the past 365 days' matches on this court at TODAY'S level, and
                 the win rate there -- the home-platform check
      fq         the last-10 opponents judged by THEIR OWN form at the time, and the form
                 of the ones actually beaten

    STRICTLY PRE-MATCH: every window is cut at `date < asof`, so the match itself and
    everything after it are excluded. Returns None when the player has no history on the
    court before that date.
    """
    try:
        mtime = os.path.getmtime(LOGS_PARQUET)
    except OSError:
        mtime = None
    if _dline_memo["mtime"] != mtime:
        _dline_memo["mtime"] = mtime
        _dline_memo["v"] = {}
    key = (str(player_name), str(surface), str(asof)[:10], str(level))
    memo = _dline_memo["v"]
    if key in memo:
        return memo[key]
    out = _dline_asof_uncached(player_name, surface, asof, level)
    if len(memo) < _ASOF_MEMO_MAX:
        memo[key] = out
    return out


def _dline_asof_uncached(player_name, surface, asof, level=None):
    c = _load()
    if not c or not player_name or asof is None:
        return None
    cur = get_context(player_name, surface)
    if not cur:
        return None
    g = (c.get("groups") or {}).get(cur["slug"])
    if g is None:
        return None
    asof = pd.Timestamp(asof)
    g = g[g["date"] < asof]
    if g.empty:
        return None
    surf = (surface or "All").title()
    sd = g if surf == "All" else g[g["surface"] == surf]
    if sd.empty:
        return None

    w365 = sd[sd["date"] >= asof - pd.Timedelta(days=365)]
    n52, w52 = int(len(w365)), int(w365["won"].sum())
    win52 = float(w365["won"].mean()) if n52 else None

    t10 = sd.tail(10)
    l10 = float(t10["won"].mean()) if len(t10) >= 3 else None
    form = (l10 - win52) if (l10 is not None and win52 is not None) else None

    lvl_share = lvl_win = lvl_n = None
    if level is not None and n52:
        lv = str(level).lower()
        bk = 1 if "challenger" in lv else (2 if ("itf" in lv or "futures" in lv) else 0)
        lg = w365[w365["lvl"] == bk]
        if len(lg):
            lvl_share = float(len(lg) / n52)
            lvl_win = float(lg["won"].mean())
            lvl_n = int(len(lg))

    fq_faced = fq_beaten = None
    if "opp_form" in sd.columns:
        _of = t10["opp_form"].dropna()
        if len(_of) >= 4:
            fq_faced = float(_of.mean())
        _wf = t10.loc[t10["won"] == 1, "opp_form"].dropna()
        if len(_wf):
            fq_beaten = float(_wf.mean())

    if n52 == 0 and l10 is None:
        return None
    return {"w52": ("%d-%d" % (w52, n52 - w52)) if n52 else None,
            "w52_n": n52, "w52_win": win52,
            "l10": l10, "form": form,
            "lvl_share": lvl_share, "lvl_win": lvl_win, "lvl_n": lvl_n,
            "fq_faced": fq_faced, "fq_beaten": fq_beaten,
            "surface": surf, "asof": str(asof)[:10]}
