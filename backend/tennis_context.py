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


def _norm_name(name):
    """Accent-stripped, punctuation-free, token-sorted key so 'Ruud, Casper' == 'Casper Ruud'."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    toks = re.sub(r"[^a-z ]", " ", s.lower().replace(",", " ")).split()
    return " ".join(sorted(toks))


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
            p["surfaces"][surf] = {
                "sr10": sr10,
                "n": int(len(w)), "window": window,
                "sv1": _fin(w["first_serve_points"].mean()),      # 1st Serve Points Won %
                "sv2": _fin(w["second_serve_points"].mean()),     # 2nd Serve Points Won %
                "sgw": _fin(100 * w["sg_won"].sum() / sga) if sga else None,   # Service Games Won %
                "r1": _fin(w["return_1st_serve_points"].mean()),  # Return 1st Serve Points %
                "r2": _fin(w["return_2nd_serve_points"].mean()),  # Return 2nd Serve Points %
                "rgw": _fin(100 * w["rg_won"].sum() / rga) if rga else None,   # Return Games Won %
                "win": round(float(w["won"].mean()), 3),
            }
            # LAST 10 ON THIS SURFACE (2026-10-11, user: "below the hard 52w stats can u give
            # hard l10 game stats too"). Same stat set as the 52w block above, same surface,
            # only the window differs; SGW/RGW are rebuilt from the game SUMS rather than
            # averaged, exactly as the 52w figures are, so the two lines are comparable.
            l10 = sub.tail(10)
            if len(l10) >= 3:
                sga10, rga10 = l10["sg_all"].sum(), l10["rg_all"].sum()
                p["surfaces"][surf]["l10"] = {
                    "n": int(len(l10)),
                    "sv1": _fin(l10["first_serve_points"].mean()),
                    "sv2": _fin(l10["second_serve_points"].mean()),
                    "sgw": _fin(100 * l10["sg_won"].sum() / sga10) if sga10 else None,
                    "r1": _fin(l10["return_1st_serve_points"].mean()),
                    "r2": _fin(l10["return_2nd_serve_points"].mean()),
                    "rgw": _fin(100 * l10["rg_won"].sum() / rga10) if rga10 else None,
                    "win": round(float(l10["won"].mean()), 3),
                    "from": str(l10["date"].min().date()),
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
    stats = {"n": int(len(w)), "window": window,
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
    l10 = sub.tail(10)
    sga10, rga10 = l10["sg_all"].sum(), l10["rg_all"].sum()
    stats_l10 = None
    if len(l10) >= 3:
        stats_l10 = {
            "n": int(len(l10)),
            "sv1": _fin(l10["first_serve_points"].mean()),
            "sv2": _fin(l10["second_serve_points"].mean()),
            "sgw": _fin(100 * l10["sg_won"].sum() / sga10) if sga10 else None,
            "r1": _fin(l10["return_1st_serve_points"].mean()),
            "r2": _fin(l10["return_2nd_serve_points"].mean()),
            "rgw": _fin(100 * l10["rg_won"].sum() / rga10) if rga10 else None,
            "win": round(float(l10["won"].mean()), 3),
            "from": str(l10["date"].min().date()),
        }
    recent = g.tail(25)
    good = recent[recent["rival_rank"] <= 200]
    pr_all = recent["serve_pressure_all"].fillna(0).sum() + recent["return_pressure_all"].fillna(0).sum()
    pr_won = recent["serve_pressure_won"].fillna(0).sum() + recent["return_pressure_won"].fillna(0).sum()
    ranks = g.tail(10)["rival_rank"].dropna()
    return {"slug": cur["slug"], "tour": cur.get("tour"), "surface_used": surf, "surface_stats": stats,
            "surface_l10": stats_l10,
            "vs_top200": {"w": int(good["won"].sum()), "l": int(len(good) - good["won"].sum())},
            "clutch": round(float(pr_won / pr_all), 3) if pr_all >= 40 else None,
            "avg_opp_rank": int(ranks.median()) if len(ranks) >= 3 else None,
            "asof": str(asof.date()), "last_date": str(g["date"].max().date())}
