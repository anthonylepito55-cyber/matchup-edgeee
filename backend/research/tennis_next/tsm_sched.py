"""TSM prospective trial — TennisRatio schedule adapter (READ-ONLY).

Separate, reviewable component. It does three things and nothing else:
  1. GET the TennisRatio schedule endpoints and snapshot the raw bytes with provenance.
  2. Normalize each row to a fixture dict, preserving every source field untouched and
     translating the FEED's round vocabulary ("1/16-finals", "Round of 32") into the
     ARCHIVE's vocabulary ("R32", "Q1".."Q3") that the registered format rules expect.
  3. Report an eligibility funnel.

It writes only raw snapshots and funnel reports under research/tennis_next/. It creates no
prediction or settlement ledger entry, contacts no betting feed, and does not touch frozen
D_rest coefficients, model logic, format rules or protocol SHA 9eb2e187....

VOCABULARY HAZARD (measured 2026-10-20, the reason for the guard below): the schedule feed
and the match archive are both TennisRatio but use DIFFERENT round vocabularies. The archive
says R128/R64/R32/R16/QF/Semis/Final and Q1/Q2/Q3; the schedule feed says 1/16-finals and
1/8-finals with round_normalized "Round of 32"/"Round of 16". The registered rules detect
Grand Slam qualifying with ^Q\\d on the round string, so a feed round string would never
match it, and a men's slam QUALIFYING match (best-of-three) would fall through to the main
draw rule and be priced best-of-FIVE. That cannot be observed outside a slam fortnight, so
this adapter refuses instead: at Grand Slams level, unless the round maps confidently onto a
known qualifying or main-draw round, the fixture is marked unknown_format and excluded
(protocol section 2: UNKNOWN fixtures are excluded and logged, never guessed). Non-slam
levels are bo3 regardless of round and are unaffected.
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tsm import slug  # noqa: E402

BASE = "https://www.tennisratio.com"
TOURS = ("atp", "wta")
SNAP_DIR = os.path.join(HERE, "sched_snapshots")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept": "application/json"}
MIN_DELAY_S = 2.0          # one person's site: stay gentle, never parallelize
TIMEOUT_S = 25
_last = [0.0]

# Only statuses we have verified mean "not yet played". Anything else is logged, not assumed.
STATUS_OK = {"scheduled"}

# feed `round` -> archive round. Verified against the live feed + archive vocabulary.
ROUND_MAP = {"1/64-finals": "R128", "1/32-finals": "R64", "1/16-finals": "R32",
             "1/8-finals": "R16", "quarterfinals": "QF", "quarterfinal": "QF",
             "semifinals": "Semis", "semifinal": "Semis", "final": "Final",
             "finals": "Final"}
# feed `round_normalized` -> archive round (fallback when `round` is unrecognized)
NORM_MAP = {"round of 128": "R128", "round of 64": "R64", "round of 32": "R32",
            "round of 16": "R16", "quarterfinal": "QF", "quarterfinals": "QF",
            "semifinal": "Semis", "semifinals": "Semis", "final": "Final"}
QUAL_RE = re.compile(r"^q\s*(\d)\b|qualif", re.I)

# Source values that must NEVER become a player identity. slug() stringifies its input,
# so slug(None) == "none" and slug(nan) == "nan" -- indistinguishable from a real slug and
# able to pass a non-empty identity check as a phantom player. Resolve through safe_slug().
UNRESOLVABLE = {"", "none", "nan", "null", "na", "n/a", "undefined", "tbd", "bye",
                "qualifier", "lucky loser",
                # placeholder avatar filename: a missing profile picture must never
                # become a player identity
                "default"}


def safe_slug(*candidates):
    """First candidate that resolves to a real identity, else "". Never invents one."""
    for v in candidates:
        if v is None:
            continue
        raw = str(v).strip().lower()
        if raw in UNRESOLVABLE:
            continue
        sl = slug(v)
        if sl and sl not in UNRESOLVABLE:
            return sl
    return ""


CANON = ("id", "tournament_name", "tournament_level", "surface", "round",
         "round_normalized", "match_date_iso", "match_datetime_utc", "status",
         "player1_slug", "player1_name", "player1_category", "player1_rank",
         "player2_slug", "player2_name", "player2_category", "player2_rank",
         "location_city", "location_country", "ranking_sum", "is_today_utc")


def _throttle():
    gap = time.monotonic() - _last[0]
    if gap < MIN_DELAY_S:
        time.sleep(MIN_DELAY_S - gap)
    _last[0] = time.monotonic()


def fetch_tour(tour, tries=3):
    """One read-only GET. Returns (rows, provenance). Raises on persistent failure."""
    url = "%s/api/today-matches/%s/" % (BASE, tour)
    last = None
    for i in range(tries):
        _throttle()
        t0 = time.time()
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT_S)
        except requests.RequestException as e:
            last = "%s: %s" % (type(e).__name__, e)
            time.sleep(1.5 * (i + 1))
            continue
        if r.status_code != 200:
            last = "HTTP %d" % r.status_code
            time.sleep(1.5 * (i + 1))
            continue
        body = r.content
        prov = {"tour": tour, "url": url, "http_status": 200,
                "server_date": r.headers.get("Date"),
                "cache_control": r.headers.get("Cache-Control"),
                "fetched_utc": dt.datetime.now(dt.timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"),
                "elapsed_s": round(time.time() - t0, 3),
                "bytes": len(body), "body_sha256": hashlib.sha256(body).hexdigest(),
                "attempt": i + 1}
        try:
            rows = r.json()
        except ValueError as e:
            raise RuntimeError("schedule feed returned non-JSON for %s: %s" % (tour, e))
        if not isinstance(rows, list):
            raise RuntimeError("schedule feed for %s is %s, expected a list"
                               % (tour, type(rows).__name__))
        prov["rows"] = len(rows)
        return rows, prov
    raise RuntimeError("schedule GET failed after %d tries: %s (%s)" % (tries, url, last))


def snapshot(rows_by_tour, provs, tag=None):
    """Persist raw payloads + provenance for reproducibility. Writes only under
    research/tennis_next/sched_snapshots/. No ledger involvement."""
    os.makedirs(SNAP_DIR, exist_ok=True)
    tag = tag or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    d = os.path.join(SNAP_DIR, tag)
    os.makedirs(d, exist_ok=True)
    for tour, rows in rows_by_tour.items():
        with open(os.path.join(d, "raw_%s.json" % tour), "w", encoding="utf-8") as fh:
            json.dump(rows, fh)
    with open(os.path.join(d, "provenance.json"), "w", encoding="utf-8") as fh:
        json.dump(provs, fh, indent=1)
    return d


# ------------------------------------------------------------------- round translation
def map_round(row):
    """Feed round vocabulary -> (archive_round, kind, confident, note).

    kind is 'qual', 'main' or None. confident=False means the qualifying-vs-main-draw
    question could not be answered from feed metadata, which only matters at slams.
    """
    raw = str(row.get("round") or "").strip()
    norm = str(row.get("round_normalized") or "").strip()
    for s in (raw, norm):
        m = QUAL_RE.match(s) if s else None
        if m:
            n = m.group(1)
            return (("Q%s" % n) if n else None, "qual", bool(n),
                    "qualifying detected in %r" % s)
    r = ROUND_MAP.get(raw.lower())
    if r:
        return r, "main", True, "round %r" % raw
    r = NORM_MAP.get(norm.lower())
    if r:
        return r, "main", True, "round_normalized %r" % norm
    return None, None, False, "unrecognized round %r / %r" % (raw, norm)


def normalize(row, src_tour):
    """Source row -> fixture dict. Every source field is preserved under `source`."""
    arch_round, kind, confident, note = map_round(row)
    fx = {k: row.get(k) for k in CANON}
    fx["id"] = str(row.get("id"))
    fx["round"] = arch_round                      # ARCHIVE vocabulary, or None
    fx["round_feed"] = row.get("round")
    fx["round_normalized_feed"] = row.get("round_normalized")
    fx["round_kind"] = kind
    fx["round_confident"] = confident
    fx["round_note"] = note
    fx["src_tour"] = src_tour
    # Resolved identities. "" means unresolvable -> the identity gate must reject it.
    fx["slug_1"] = safe_slug(row.get("player1_slug"), row.get("player1_name"))
    fx["slug_2"] = safe_slug(row.get("player2_slug"), row.get("player2_name"))
    fx["source"] = dict(row)                      # untouched source record
    return fx


def dedupe(fixtures):
    """One fixture per source id. Also reports same-pair/different-id collisions."""
    out, seen, dups = [], {}, 0
    for fx in fixtures:
        fid = fx["id"]
        if fid in seen:
            dups += 1
            continue
        seen[fid] = fx
        out.append(fx)
    pairs = {}
    collide = []
    for fx in out:
        s1, s2 = fx.get("slug_1"), fx.get("slug_2")
        if not s1 or not s2:
            continue
        key = (fx.get("match_date_iso"), frozenset((s1, s2)))
        if key in pairs:
            collide.append((pairs[key], fx["id"]))
        else:
            pairs[key] = fx["id"]
    return out, {"duplicate_ids": dups, "same_pair_same_day_different_id": collide}


def format_blocked(fx):
    """Grand Slam fixtures whose round vocabulary is unverified are refused, never guessed.
    Returns a reason string, or None when the registered rules may be applied."""
    if str(fx.get("tournament_level")) != "Grand Slams":
        return None
    if not fx.get("round_confident"):
        return "unverified_round_vocabulary"
    if fx.get("round_kind") == "qual" and "Wimbledon" in str(fx.get("tournament_name")):
        return None      # registered rule 2c handles Wimbledon Q3; Q1/Q2 are bo3
    return None
