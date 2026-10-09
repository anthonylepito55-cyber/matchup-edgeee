"""Authoritative SURFACE per match from TennisExplorer (2026-10-09, user: "u put stefanini
match on clay and it's a hardcourt match ... that is just something we can't get wrong,
need u double checking all courts now").

TE's daily schedule (/matches/?type=...&year&month&day) lists every match under its
tournament header link; each tournament page carries "(prize, SURFACE, gender)". So we map
player PAIR -> tournament -> surface, covering ATP/WTA/Challenger/ITF. Polite: one schedule
page per tour per day + one page per tournament, cached 6h.

surface_for(p1, p2) -> ("Hard"|"Clay"|"Grass", tournament_url) or (None, None).
"""
import html as _html
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone

import requests

BASE = "https://www.tennisexplorer.com"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
TYPES = ("atp-single", "wta-single", "itf-men-single", "itf-women-single")
_TTL = 6 * 3600
_cache = {"at": 0.0, "pairs": {}, "tsurf": {}}
_SURF = {"hard": "Hard", "indoor": "Hard", "indoors": "Hard", "clay": "Clay", "grass": "Grass", "carpet": "Hard"}


def _get(url, params=None):
    for i in range(3):
        try:
            r = requests.get(url, params=params, headers=H, timeout=25)
            if r.status_code == 200:
                return r.text
        except requests.exceptions.RequestException:
            pass
        time.sleep(1.5 * (i + 1))
    return ""


def _key_name(s):
    """Surname-centric key: 'Stefanini L.' / 'Lucrezia Stefanini' -> {'stefanini'} etc."""
    s = unicodedata.normalize("NFKD", _html.unescape(str(s or ""))).encode("ascii", "ignore").decode().lower()
    toks = [t for t in re.sub(r"[^a-z ]", " ", s.replace("-", " ")).split() if len(t) > 1]
    return frozenset(toks)


def _tour_surface(path):
    if path in _cache["tsurf"]:
        return _cache["tsurf"][path]
    t = _get(BASE + path)
    m = re.search(r'<div class="box boxBasic lGray">\(([^)]*)\)</div>', t)
    surf = None
    if m:
        for part in m.group(1).split(","):
            surf = _SURF.get(part.strip().lower()) or surf
    _cache["tsurf"][path] = surf
    time.sleep(0.4)
    return surf


def refresh(days=(0, 1, -1)):
    """Build pair -> (surface, tournament path) for today and the neighbouring days."""
    pairs = {}
    now = datetime.now(timezone.utc)
    for dd in days:
        d = now + timedelta(days=dd)
        for typ in TYPES:
            h = _get(f"{BASE}/matches/", {"type": typ, "year": d.year, "month": d.month, "day": d.day})
            cur = None
            for row in re.findall(r"<tr[^>]*>.*?</tr>", h, re.S):
                if 'class="t-name" colspan="2"' in row:
                    # tournament header. TE lumps MEN'S ITF into one unlinked "Futures 2026"
                    # section (no tournament page) -> mark it so those pairs resolve via the
                    # players' own pages instead of inheriting the previous header.
                    hm = re.search(r'<a href="(/[a-z0-9-]+/\d{4}/[a-z-]+/)"', row)
                    cur = hm.group(1) if hm else "FUTURES"
                    continue
                if cur is None:
                    continue
                for slug, nm in re.findall(r'<a href="/player/([a-z0-9-]+)/"[^>]*>([^<]+)</a>', row):
                    pairs.setdefault("_rows", []).append((cur, nm, slug))
            time.sleep(0.4)
    # TE renders each match over two <tr>s (one per player): pair consecutive names within a tournament
    rows = pairs.pop("_rows", [])
    out = {}
    i = 0
    while i + 1 < len(rows):
        (t1, n1, s1), (t2, n2, s2) = rows[i], rows[i + 1]
        if t1 == t2:
            out[frozenset((_key_name(n1), _key_name(n2)))] = t1 if t1 != "FUTURES" else ("FUTURES", s1, s2)
            i += 2
        else:
            i += 1
    _cache["pairs"] = out
    _cache["at"] = time.time()
    return len(out)


def _match_pair(p1, p2):
    k1, k2 = _key_name(p1), _key_name(p2)
    for key, path in _cache["pairs"].items():
        a, b = tuple(key) if len(key) == 2 else (next(iter(key)), next(iter(key)))
        # TE uses "Surname F." -> require the TE surname tokens be a subset of the board name
        def fits(te, board):
            te_main = {t for t in te if len(t) > 1}
            return bool(te_main) and te_main <= board
        if (fits(a, k1) and fits(b, k2)) or (fits(a, k2) and fits(b, k1)):
            return path
    return None


def _futures_surface(s1, s2):
    """Men's ITF (no tournament page on the daily schedule): read both players' TE pages; if
    their most recent tournament is the SAME event (they're in the same draw this week) take
    its surface, else unknown."""
    try:
        import tennis_explorer_ingest as _te
        d1 = _te.fetch_player_results(s1, max_age_h=12)
        d2 = _te.fetch_player_results(s2, max_age_h=12)
    except Exception:  # noqa: BLE001
        return None, None
    if d1 is None or d2 is None or d1.empty or d2.empty:
        return None, None
    t1, t2 = d1.iloc[0], d2.iloc[0]
    if t1["tournament"] and t1["tournament"] == t2["tournament"] and t1["year"] == t2["year"] and t1["surface"]:
        return t1["surface"], f"/{t1['tournament']}/{t1['year']}/ (via player pages)"
    return None, None


def surface_for(p1, p2):
    if not _cache["pairs"] or time.time() - _cache["at"] > _TTL:
        refresh()
    path = _match_pair(p1, p2)
    if not path:
        return None, None
    if isinstance(path, tuple):
        return _futures_surface(path[1], path[2])
    return _tour_surface(path), path


def surface_for_city(city):
    """Fallback for men's ITF futures (TE gives them no tournament page): the same city's
    women's/other event THIS WEEK on TE's schedule (ITF men's and women's events in one
    city share the club and surface almost always). Returns (surface, path) or (None, None)."""
    if not city:
        return None, None
    if not _cache["pairs"] or time.time() - _cache["at"] > _TTL:
        refresh()
    import re as _re
    c = _re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", str(city)).encode("ascii", "ignore").decode().lower())
    if len(c) < 4:
        return None, None
    for path in set(v for v in _cache["pairs"].values() if isinstance(v, str)):
        slug = _re.sub(r"[^a-z]", "", path.split("/")[1])
        if slug.startswith(c):
            s = _tour_surface(path)
            if s:
                return s, path + " (same city this week)"
    return None, None


def resolve(p1, p2, tournament=None):
    """Best surface for a card: (surface or None, source string). Exact match first, then the
    same-city event this week (men's futures), else None (caller falls back + flags it)."""
    s, path = surface_for(p1, p2)
    if s:
        return s, f"TennisExplorer {path}"
    t = str(tournament or "")
    import re as _re
    city = _re.sub(r"^[MW]\d+\+?H?\s+", "", t.split(",")[0]).strip()
    s, path = surface_for_city(city)
    if s:
        return s, f"TennisExplorer {path}"
    s, path = surface_for_player(p1, p2)
    if s:
        return s, f"TennisExplorer {path}"
    return None, None


def surface_for_player(p1, p2):
    """Last resort (no tournament name on the card): either player's OTHER match on TE's
    schedule in the +-1 day window -> that tournament. Both players must not point to
    DIFFERENT surfaces; a single unambiguous hit is required."""
    hits = set()
    for name in (p1, p2):
        kb = _key_name(name)
        found = set()
        for key, path in _cache["pairs"].items():
            if not isinstance(path, str):
                continue
            for te in key:
                te_main = {t for t in te if len(t) > 1}
                if te_main and te_main <= kb and len(te_main) >= 1 and max(len(t) for t in te_main) >= 4:
                    found.add(path)
        if len(found) == 1:
            hits |= found
    surfs = {(_tour_surface(pth), pth) for pth in hits}
    vals = {sv for sv, _ in surfs if sv}
    if len(vals) == 1:
        sv = vals.pop()
        return sv, next(pth for v2, pth in surfs if v2 == sv) + " (player's event this week)"
    return None, None
