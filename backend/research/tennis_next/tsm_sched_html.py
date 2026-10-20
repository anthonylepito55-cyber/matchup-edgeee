"""TSM — PERMITTED-SOURCE schedule adapter (robots-allowed HTML pages only).

Replaces the /api/ adapter for all further coverage work. `robots.txt` on tennisratio.com
reads `Disallow: /api/` for every user agent, so this module never touches /api/. It reads
only `atp-matches.html` and `wta-matches.html`, both listed in `sitemap-static.xml` and not
disallowed by any robots rule, and `/players/{Slug}.html` is likewise allowed (it is the same
path the production archive ingest already uses) though this module does not fetch it.

Page structure (verified 2026-10-20):
    section.matches-date-group[data-date]          -> fixture date
      div.tournament-group[data-level][data-surface]
        span.tournament-title                      -> tournament name
        span.tournament-meta                       -> "Round of 32 - N matches"
        div.match-card[data-match-id][data-level][data-surface]      (featured layout)
        a.compact-row[data-match-id][data-level][data-surface]       (compact layout)
Both layouts carry span[data-utc] for the start time. Featured cards link
/players/{Slug}.html directly; compact rows carry the slug only in the avatar image
filename, so slugs are recovered from either.

TWO MEASURED LIMITATIONS, both reported rather than papered over:
  1. `data-match-id` IS NOT A STABLE FIXTURE IDENTITY. All 56 matchups shared between this
     page and the /api/ response carried DIFFERENT ids (offset ~+187). Fixture identity is
     therefore derived from content -- (fixture date, the two archive slugs) -- and the
     source id is recorded as metadata only.
  2. This source carries NO per-player ATP/WTA category. The page itself declares the tour,
     which is page-level attribution, not the per-player source declaration the registered
     format rules require. Every Grand Slams fixture from this source is therefore left
     UNKNOWN unless the owner authorizes per-player category lookups from the (permitted)
     player pages.
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
from tsm_sched import ROUND_MAP, NORM_MAP, QUAL_RE, UNRESOLVABLE  # noqa: E402

BASE = "https://www.tennisratio.com"
PAGES = {"atp": "/atp-matches.html", "wta": "/wta-matches.html"}
SNAP_DIR = os.path.join(HERE, "sched_html_snapshots")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept": "text/html,application/xhtml+xml"}
MIN_DELAY_S = 2.5
TIMEOUT_S = 30
_last = [0.0]

DATE_GROUP = re.compile(r'<section class="matches-date-group"[^>]*data-date="([^"]+)"')
TGROUP = re.compile(r'<div class="tournament-group[^"]*"\s*'
                    r'data-level="([^"]*)"\s+data-surface="([^"]*)"', re.S)
TTITLE = re.compile(r'class="tournament-title"[^>]*>\s*([^<]+?)\s*<')
TMETA = re.compile(r'class="tournament-meta"[^>]*>\s*([^<]+?)\s*<')
CARD = re.compile(r'<(?:div|a)[^>]*class="(?:match-card|compact-row)"?[^>]*'
                  r'data-match-id="(\d+)"', re.S)
ANYCARD = re.compile(r'<(div|a)\s[^>]*?data-match-id="(\d+)"[^>]*>', re.S)
UTC = re.compile(r'data-utc="([^"]+)"')
PLAYER_HREF = re.compile(r'/players/([A-Za-z0-9\-_]+)\.html')
# Avatars must be read from the src attribute ONLY. Every img also carries
# onerror="this.src='.../profile_pics/default.jpg'", so a naive match picks up "default"
# as if it were a player slug -- and in compact rows, which carry no /players/ link, that
# phantom became player 2's identity on 42 of 154 fixtures.
AVATAR = re.compile(r'src="[^"]*?/profile_pics/([A-Za-z0-9\-_]+)\.jpg"')
NAME_CARD = re.compile(r'class="player-name"[^>]*>\s*([^<]+?)\s*<')
NAME_COMPACT = re.compile(r'class="compact-name"[^>]*>\s*([^<]+?)\s*<')
RANK_CARD = re.compile(r'class="player-rank">Rank:\s*([\d\-]+)')
RANK_COMPACT = re.compile(r'class="compact-rank"[^>]*>\s*([\d\-]+)\s*<')


def _throttle():
    gap = time.monotonic() - _last[0]
    if gap < MIN_DELAY_S:
        time.sleep(MIN_DELAY_S - gap)
    _last[0] = time.monotonic()


def fetch_page(tour, tries=3):
    url = BASE + PAGES[tour]
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
        return r.text, {"tour": tour, "url": url, "http_status": 200,
                        "server_date": r.headers.get("Date"),
                        "fetched_utc": dt.datetime.now(dt.timezone.utc).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"),
                        "elapsed_s": round(time.time() - t0, 3),
                        "bytes": len(body),
                        "body_sha256": hashlib.sha256(body).hexdigest(),
                        "attempt": i + 1,
                        "declared_total": _declared_total(r.text)}
    raise RuntimeError("schedule page GET failed after %d tries: %s (%s)"
                       % (tries, url, last))


def _declared_total(html):
    """The page's own 'All' filter count -- an independent check on parser completeness."""
    m = re.search(r'data-filter-value="all">All<span class="flt-count">(\d+)</span>', html)
    return int(m.group(1)) if m else None


def _safe(*cands):
    for v in cands:
        if v is None:
            continue
        if str(v).strip().lower() in UNRESOLVABLE:
            continue
        s = slug(v)
        if s and s not in UNRESOLVABLE:
            return s
    return ""


def map_round(meta_text):
    """'Round of 32 - 2 matches' -> archive round, with confidence."""
    s = (meta_text or "").split("·")[0].strip()
    if QUAL_RE.match(s):
        m = QUAL_RE.match(s)
        n = m.group(1)
        return (("Q%s" % n) if n else None), "qual", bool(n), "qualifying in %r" % s
    r = NORM_MAP.get(s.lower()) or ROUND_MAP.get(s.lower())
    if r:
        return r, "main", True, "round %r" % s
    return None, None, False, "unrecognized round %r" % s


def parse(html, tour):
    """-> list of fixture dicts. Parses BOTH the featured and compact layouts."""
    out = []
    # index every (date, tournament-group) span so each card inherits its context
    dsecs = [(m.start(), m.group(1)) for m in DATE_GROUP.finditer(html)]
    tsecs = []
    for m in TGROUP.finditer(html):
        seg = html[m.start():m.start() + 1400]
        tt = TTITLE.search(seg)
        tm = TMETA.search(seg)
        tsecs.append((m.start(), m.group(1), m.group(2),
                      tt.group(1) if tt else None, tm.group(1) if tm else None))

    def ctx(pos):
        d = None
        for p, v in dsecs:
            if p <= pos:
                d = v
            else:
                break
        lvl = surf = title = meta = None
        for p, lv, sf, ti, me in tsecs:
            if p <= pos:
                lvl, surf, title, meta = lv, sf, ti, me
            else:
                break
        return d, lvl, surf, title, meta

    marks = [(m.start(), m.group(2)) for m in ANYCARD.finditer(html)]
    for i, (pos, mid) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else min(len(html), pos + 4000)
        body = html[pos:end]
        date, lvl, surf, title, meta = ctx(pos)
        u = UTC.search(body)
        hrefs = PLAYER_HREF.findall(body)
        avs = AVATAR.findall(body)
        names = NAME_CARD.findall(body) or NAME_COMPACT.findall(body)
        ranks = RANK_CARD.findall(body) or RANK_COMPACT.findall(body)
        cand1 = [hrefs[0] if len(hrefs) > 0 else None,
                 avs[0] if len(avs) > 0 else None,
                 names[0] if len(names) > 0 else None]
        cand2 = [hrefs[1] if len(hrefs) > 1 else None,
                 avs[1] if len(avs) > 1 else None,
                 names[1] if len(names) > 1 else None]
        s1, s2 = _safe(*cand1), _safe(*cand2)
        ar, kind, conf, note = map_round(meta)
        start = u.group(1) if u else None
        fdate = (start[:10] if start else date)
        out.append({
            "source_match_id": mid,                 # metadata ONLY: ids are not stable
            "fixture_key": ("%s|%s" % (fdate, "|".join(sorted((s1, s2)))))
            if (s1 and s2) else None,
            "match_date_iso": fdate, "match_datetime_utc": start,
            "tournament_level": lvl, "tournament_name": title, "surface": surf,
            "round": ar, "round_feed": (meta or "").split("·")[0].strip(),
            "round_kind": kind, "round_confident": conf, "round_note": note,
            "slug_1": s1, "slug_2": s2,
            "player1_name": names[0].strip() if len(names) > 0 else None,
            "player2_name": names[1].strip() if len(names) > 1 else None,
            "player1_rank": ranks[0] if len(ranks) > 0 else None,
            "player2_rank": ranks[1] if len(ranks) > 1 else None,
            "player1_category": None,               # NOT available from this source
            "player2_category": None,
            "category_source": "page-level only (%s page); per-player category "
                               "unavailable from the permitted HTML source" % tour.upper(),
            "status": "scheduled" if start else None,
            "src_tour": tour})
    return out


def dedupe(fixtures):
    """One fixture per CONTENT key. Source ids are unstable, so they are not the key."""
    out, seen, dup, nokey = [], set(), 0, 0
    id_conflicts = []
    by_key = {}
    for f in fixtures:
        k = f.get("fixture_key")
        if not k:
            nokey += 1
            continue
        if k in seen:
            dup += 1
            if by_key[k]["source_match_id"] != f["source_match_id"]:
                id_conflicts.append((k, by_key[k]["source_match_id"],
                                     f["source_match_id"]))
            continue
        seen.add(k)
        by_key[k] = f
        out.append(f)
    return out, {"duplicate_keys": dup, "unresolvable_identity": nokey,
                 "same_key_different_source_id": id_conflicts}


def snapshot(pages, provs, tag=None):
    os.makedirs(SNAP_DIR, exist_ok=True)
    tag = tag or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    d = os.path.join(SNAP_DIR, tag)
    os.makedirs(d, exist_ok=True)
    for tour, html in pages.items():
        with open(os.path.join(d, "%s-matches.html" % tour), "w",
                  encoding="utf-8") as fh:
            fh.write(html)
    with open(os.path.join(d, "provenance.json"), "w", encoding="utf-8") as fh:
        json.dump(provs, fh, indent=1)
    return d


def observe():
    pages, provs, fixtures = {}, [], []
    for tour in ("atp", "wta"):
        html, prov = fetch_page(tour)
        pages[tour] = html
        provs.append(prov)
        got = parse(html, tour)
        prov["parsed"] = len(got)
        prov["parse_complete"] = (prov["declared_total"] is None
                                  or len(got) == prov["declared_total"])
        fixtures += got
    return pages, provs, fixtures


if __name__ == "__main__":
    import collections
    pages, provs, fx = observe()
    d = snapshot(pages, provs)
    uniq, info = dedupe(fx)
    print(json.dumps({
        "snapshot": os.path.basename(d),
        "provenance": [{k: p[k] for k in ("tour", "http_status", "server_date", "bytes",
                                          "declared_total", "parsed", "parse_complete")}
                       for p in provs],
        "parsed_total": len(fx), "unique_by_content_key": len(uniq),
        "dedupe": {k: (v if not isinstance(v, list) else len(v))
                   for k, v in info.items()},
        "dates": dict(sorted(collections.Counter(f["match_date_iso"]
                                                 for f in uniq).items())),
        "levels": dict(collections.Counter(str(f["tournament_level"]) for f in uniq)),
        "rounds": dict(collections.Counter(str(f["round"]) for f in uniq)),
        "round_unconfident": sum(1 for f in uniq if not f["round_confident"]),
        "identity_resolved": sum(1 for f in uniq if f["slug_1"] and f["slug_2"]),
        "tournament_name_present": sum(1 for f in uniq if f["tournament_name"]),
        "start_time_present": sum(1 for f in uniq if f["match_datetime_utc"]),
        "per_player_category_present": sum(1 for f in uniq if f["player1_category"]),
    }, indent=1))
