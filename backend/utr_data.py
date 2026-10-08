"""REAL UTR ratings (2026-10-07, user: "get real utr data ... and do tests with it").

Source: UTR's own PUBLIC player-search endpoint (app.utrsports.net/api/v2/search/players)
— verified to return singlesUtr + threeMonthRating with NO login, from server-side too.
Match HISTORIES (/api/v4/player/{id}/results) are login-gated (403), so this module serves
CURRENT ratings only.

HONESTY CONSTRAINT: current-only ratings mean a retro backtest would LEAK (today's rating
already contains yesterday's results). So real UTR ships as a FORWARD tracker exclusively:
frozen into the log at prediction time (utr_edge_p1 / utr_mom_p1), judged on settles.

utr      = singlesUtr        (established level, the real thing our sUTR approximates)
utr3m    = threeMonthRating  (recent-form rating -> utr3m - utr = MOMENTUM, an angle the
                              synthetic sUTR doesn't have; pairs with the form-fade thesis)

Matching is CONSERVATIVE: exact normalized full-name hit, else unique last-name +
first-initial hit. Anything ambiguous -> no rating (a wrong player mapping would poison
the frozen log forever).
"""
import json
import os
import threading
import time
import unicodedata

import requests

API = "https://app.utrsports.net/api/v2/search/players"
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "data_cache", "utr_ratings.json")
TTL_OK = 24 * 3600        # refresh a rating daily
TTL_MISS = 6 * 3600       # retry unknown names every 6h
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept": "application/json",
}
_MIN_GAP = 1.0            # polite: >=1s between network calls, global

_lock = threading.Lock()
_cache = None             # norm_name -> entry dict (with "ts"; miss entries have "miss")
_last_net = [0.0]
_worker_running = [False]
_queue = set()


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _load():
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            _cache = json.load(f)
    except Exception:  # noqa: BLE001
        _cache = {}
    return _cache


def _save():
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        tmp = CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_cache, f)
        os.replace(tmp, CACHE_PATH)
    except Exception:  # noqa: BLE001
        pass


def _pick_hit(name, hits):
    """Best source dict for `name`, or None if ambiguous. Exact normalized display-name
    match first; else a UNIQUE (last name + first initial) match. Prefer Rated singles."""
    nq = _norm(name)
    srcs = [h.get("source") or {} for h in hits or []]
    srcs = [s for s in srcs if s.get("displayName")]
    exact = [s for s in srcs if _norm(s["displayName"]) == nq]
    if not exact:
        # OpticOdds/PM names are "First [Middle] Last"; try last token + first initial
        toks = nq.split()
        if len(toks) >= 2:
            ln, fi = toks[-1], toks[0][0]
            cand = [s for s in srcs
                    if _norm(s.get("playerLastName") or "") == ln
                    and _norm(s.get("playerFirstName") or "")[:1] == fi]
            if len(cand) == 1:
                exact = cand
    if not exact:
        return None
    rated = [s for s in exact if s.get("ratingStatusSingles") == "Rated"]
    return (rated or exact)[0]


def _fetch_one(name: str):
    """Network fetch one name into the cache (throttled). Returns the entry."""
    now = time.time()
    wait = _MIN_GAP - (now - _last_net[0])
    if wait > 0:
        time.sleep(wait)
    _last_net[0] = time.time()
    entry = {"miss": True, "ts": time.time()}
    try:
        r = requests.get(API, params={"query": name}, headers=_HEADERS, timeout=10)
        if r.status_code == 200:
            s = _pick_hit(name, (r.json() or {}).get("hits"))
            if s is not None:
                entry = {"utr": s.get("singlesUtr"), "utr3m": s.get("threeMonthRating"),
                         "status": s.get("ratingStatusSingles"), "utr_id": s.get("id"),
                         "display": s.get("displayName"), "gender": s.get("gender"),
                         "ts": time.time()}
    except Exception:  # noqa: BLE001
        pass
    with _lock:
        _load()[_norm(name)] = entry
    return entry


def get_cached(name: str):
    """Fresh cache entry or None. NEVER hits the network (board latency stays flat)."""
    with _lock:
        e = _load().get(_norm(name))
    if not e:
        return None
    ttl = TTL_MISS if e.get("miss") else TTL_OK
    return e if (time.time() - e.get("ts", 0) < ttl) else None


def queue_fetch(names):
    """Queue names whose rating is missing/stale; one polite background worker drains it."""
    fresh_missing = [n for n in names if n and get_cached(n) is None]
    if not fresh_missing:
        return
    _queue.update(fresh_missing)
    if _worker_running[0]:
        return
    _worker_running[0] = True

    def _run():
        try:
            n_done = 0
            while _queue:
                nm = _queue.pop()
                if get_cached(nm) is None:
                    _fetch_one(nm)
                    n_done += 1
                    if n_done % 20 == 0:
                        with _lock:
                            _save()
            with _lock:
                _save()
        finally:
            _worker_running[0] = False
    threading.Thread(target=_run, daemon=True).start()


def block(p1: str, p2: str):
    """The per-match attach: both players' real UTR or None. Cache-only (non-blocking)."""
    a, b = get_cached(p1), get_cached(p2)
    if (not a or not b or a.get("miss") or b.get("miss")
            or a.get("utr") in (None, 0) or b.get("utr") in (None, 0)):
        return None
    out = {"p1": round(float(a["utr"]), 2), "p2": round(float(b["utr"]), 2),
           "edge": round(float(a["utr"]) - float(b["utr"]), 2)}
    if a.get("utr3m") not in (None, 0) and b.get("utr3m") not in (None, 0):
        m1 = float(a["utr3m"]) - float(a["utr"])
        m2 = float(b["utr3m"]) - float(b["utr"])
        out["p1_mom"] = round(m1, 2)
        out["p2_mom"] = round(m2, 2)
        out["mom"] = round(m1 - m2, 2)       # >0: p1 is the hotter-form side
    return out


if __name__ == "__main__":
    for nm in ("Carlos Alcaraz", "Iga Swiatek", "Renata Zarazua", "Oliver Tarvet"):
        e = _fetch_one(nm)
        print(nm, "->", e)
    _save()
