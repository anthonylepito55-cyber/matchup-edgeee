"""SETTLE ITF ROWS FROM TENNISEXPLORER (2026-10-10, user: "fix").

THE BUG: all 130 ITF rows in the ledger had never settled -- none, going back to 2026-10-07, all
with score=None. Every ITF pick was therefore permanently pending: absent from every lane record,
never graded, invisible in the forward record used to judge every signal on the board. Non-ITF
rows settle fine (1,166 of 1,236 hex-id rows, 43 of 43 Polymarket rows).

WHY: ITF rows carry fixture ids that no settlement source can match.
  * 93 of them are SYNTHETIC hex ids (date + hash) minted locally for the ITF slate. OpticOdds
    never issued them, so its completed-fixtures lookup can never find them -- and its key is
    dead anyway.
  * 37 are "pm_"+slug ids from the Polymarket ITF scraper. polymarket_data.pm_results() does
    publish results under slug keys (added 2026-10-08 for exactly this), but it returned 470
    keys and ZERO starting "pm_itf" -- ITF events never clear its filters, which need `ended`,
    singles, and a decisively resolved price.

THE FIX: settle ITF by PLAYER NAME AND DATE instead of by fixture id, from TennisExplorer's
results pages -- free, permitted by their robots.txt, already a trusted dependency here
(tennis_surface_check uses the same site for court verification), and it covers ITF thoroughly,
which is the whole problem with every other source.

Matching is deliberately strict, because a wrong winner is far worse than an unsettled row:
both players must match on surname + first initial, the pair must resolve to exactly ONE match
on that date, and the sets won must be decisive. Anything ambiguous is left alone and reported.
"""
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

import tennis_log

BASE = "https://www.tennisexplorer.com/results/"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (matchup-edge research)"}
MAX_AGE = 30          # don't chase rows older than this


def _ascii(s):
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()


def name_key(full):
    """'Georgina Garcia Perez' -> ('garciaperez', 'g'). Kept for callers/tests."""
    t = [x for x in re.split(r"[\s.]+", _ascii(full).lower()) if x]
    if not t:
        return None
    return ("".join(t[1:]) or t[0], t[0][:1])


def name_keys(full):
    """EVERY plausible (surname, initial) for a full name, because we cannot tell a middle name
    from part of a compound surname.

    TennisExplorer writes 'Surname I.', using only the true surname. Taking everything after the
    first token breaks on middle names -- 'Cristiana Nicoleta Todoni' became 'nicoletatodoni'
    against TE's 'todoni' -- while taking only the last token breaks on compound surnames like
    'Garcia Perez' or 'Reasco Gonzalez'. So generate the last-1, last-2 and last-3 token joins
    and accept a match on any of them. Safe because a settlement still requires BOTH players to
    match and the pair to resolve to exactly ONE match on the date.
    """
    t = [x for x in re.split(r"[\s.]+", _ascii(full).lower()) if x]
    if not t:
        return set()
    ini = t[0][:1]
    out = set()
    for k in (1, 2, 3):
        if len(t) > k:
            out.add(("".join(t[-k:]), ini))
    out.add(("".join(t[1:]) or t[0], ini))
    return out


def te_key(disp):
    """TennisExplorer's 'Garcia Perez G.' -> ('garciaperez', 'g'). Initial comes LAST there."""
    t = [x for x in re.split(r"[\s.]+", _ascii(disp).lower()) if x]
    if len(t) < 2:
        return ("".join(t), "") if t else None
    return ("".join(t[:-1]), t[-1][:1])


def fetch_day(d):
    """Every completed singles match TennisExplorer lists for one date.

    Each match is two <tr> rows, one per player: t-name holds the display name, `result` the
    sets won, and the `score` cells the games per set.
    """
    y, m, dd = d.year, d.month, d.day
    try:
        r = requests.get(BASE, params={"type": "all", "year": y, "month": m, "day": dd},
                         headers=H, timeout=60)
        if r.status_code != 200:
            return []
    except requests.exceptions.RequestException:
        return []
    rows = []
    for tr in re.findall(r"<tr[^>]*>.*?</tr>", r.text, re.S):
        nm = re.search(r'class="t-name"[^>]*>\s*(?:<a[^>]*>)?([^<]+)', tr)
        if not nm:
            continue
        res = re.search(r'class="result"[^>]*>\s*([^<\s]*)', tr)
        scores = [s.strip() for s in re.findall(r'class="score"[^>]*>\s*([^<]*)', tr)]
        rows.append({"name": nm.group(1).strip(),
                     "sets": (res.group(1).strip() if res else ""),
                     "games": [s for s in scores if s and s != "&nbsp;"],
                     # TE renders a match as TWO <tr>s and puts the time cell, with
                     # rowspan="2", only on the FIRST. That marker is what identifies where a
                     # match starts: walking rows in steps of one instead invents pairings
                     # between player 2 of one match and player 1 of the next, which is what
                     # produced 33 bogus "2 matches" ambiguities on the first run.
                     "starts": bool(re.search(r'class="first time"', tr))})
    out = []
    for i in range(len(rows) - 1):
        a, b = rows[i], rows[i + 1]
        if not a["starts"] or b["starts"]:
            continue
        if not a["sets"].isdigit() or not b["sets"].isdigit():
            continue
        sa, sb = int(a["sets"]), int(b["sets"])
        if sa == sb:                      # retired/walkover/unfinished -- not decisive
            continue
        ka, kb = te_key(a["name"]), te_key(b["name"])
        if not ka or not kb or ka == kb:
            continue
        sets = " ".join(f"{x}-{y2}" for x, y2 in zip(a["games"], b["games"]) if x and y2)
        # A RETIREMENT still has a winner (TE credits sets won to the player ahead) but its
        # last "set" is unfinished, e.g. "6-3 2-1" or "4-0". Flag it so the caller can see
        # which settlements came from a retirement rather than a completed match.
        ret = bool(sets) and (sa + sb) != len(sets.split())
        out.append({"a": ka, "b": kb, "a_won": sa > sb, "score": sets or None,
                    "retired": ret, "names": (a["name"], b["name"])})
    seen, uniq = set(), []
    for x in out:                       # belt and braces against duplicate listings
        k = frozenset((x["a"], x["b"]))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(x)
    return uniq


def settle(max_age_days=MAX_AGE, dry_run=False, verbose=True):
    log = tennis_log._read_log()
    if log.empty:
        return {"rows": 0}
    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    dates = pd.to_datetime(log["date"].astype(str).str[:10], errors="coerce")
    todo = log[(log["settled"] != True) & log["league"].astype(str).str.startswith("itf")  # noqa: E712
               & (dates >= today - pd.Timedelta(days=max_age_days))
               & (dates <= today)].copy()
    if todo.empty:
        if verbose:
            print("[itf settle] nothing pending")
        return {"rows": 0}
    out = {"pending": int(len(todo)), "settled": 0, "ambiguous": 0, "not_found": 0}
    by_date = {}
    for d in sorted({str(x)[:10] for x in todo["date"]}):
        dt = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        # a match can be listed on the neighbouring day in TE's timezone
        # A match can be listed on the neighbouring day in TE's timezone, so three pages are
        # fetched -- but the SAME match often appears on two of them, and concatenating without
        # a cross-page dedupe made every such match look like two candidates. That, not the row
        # pairing, was the real source of the 33 "2 matches" ambiguities. Offset 0 is fetched
        # first and wins, so the exact-date listing is preferred.
        got, seen = [], set()
        for off in (0, 1, -1):
            for x in fetch_day(dt + timedelta(days=off)):
                k = frozenset((x["a"], x["b"]))
                if k in seen:
                    continue
                seen.add(k)
                got.append(x)
            time.sleep(1.0)
        by_date[d] = got
        if verbose:
            print(f"[itf settle] {d}: {len(got)} completed matches on TennisExplorer", flush=True)
    for i, r in todo.iterrows():
        d = str(r["date"])[:10]
        K1, K2 = name_keys(r["player_1"]), name_keys(r["player_2"])
        if not K1 or not K2:
            out["not_found"] += 1
            continue
        hits = [x for x in by_date.get(d, [])
                if (x["a"] in K1 and x["b"] in K2) or (x["a"] in K2 and x["b"] in K1)]
        if len(hits) != 1:
            out["ambiguous" if len(hits) > 1 else "not_found"] += 1
            if verbose and len(hits) > 1:
                print(f"  AMBIGUOUS {d} {r['player_1']} vs {r['player_2']} -> {len(hits)} matches")
            continue
        h = hits[0]
        a_is_p1 = h["a"] in K1
        p1_won = h["a_won"] if a_is_p1 else (not h["a_won"])
        score = h["score"]
        if score and not a_is_p1:         # TE listed them the other way round
            score = " ".join("-".join(reversed(s.split("-"))) for s in score.split())
        if not dry_run:
            log.at[i, "p1_won"] = bool(p1_won)
            log.at[i, "settled"] = True
            if score:
                log.at[i, "score"] = score
        out["settled"] += 1
        out["retired"] = out.get("retired", 0) + (1 if h.get("retired") else 0)
        if verbose:
            w = r["player_1"] if p1_won else r["player_2"]
            print(f"  {d} {r['player_1']} vs {r['player_2']} -> {w} won  {score or ''}"
                  f"{'  (RET)' if h.get('retired') else ''}")
    if out["settled"] and not dry_run:
        tennis_log._write_log(log)
    if verbose:
        print(f"[itf settle] {out}")
    return out


if __name__ == "__main__":
    print(settle(dry_run="--dry" in sys.argv))
    sys.stdout.flush()
