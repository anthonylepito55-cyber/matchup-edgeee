"""REAL UNFORCED ERRORS FROM ROLAND GARROS (2026-10-10, user: "yes").

After every feed route closed -- Flashscore and Sofascore refuse automated access, ATP and the
US Open robots-block their stats paths, the WTA API has no such field, and SportsAPI365 returns
null at every level through both RapidAPI and its direct API -- the grand slam sites turned out
to be the one free, permitted source that actually publishes the numbers.

rolandgarros.com/en-us/matches/{year}/{CODE}:
  SD### = women's singles   (Simples Dames)      SM### = men's singles
  SF### = girls' singles                         DD### = women's doubles
Each page is server-rendered Nuxt. Inside it:
  teamA:{players:[{firstName,lastName,...}]}        both players
  dateSchedule:"20260606", status:"FINISHED"        when, and whether it counts
  matchStatisticsSection:{ matchStatistics:{...}, setStatistics1..5:{...} }
and matchStatistics holds the MATCH TOTALS -- unforcedErrors, winners, totalPointsWon, each as
{label:x, teamAValue:"29", teamBValue:"26"}.

robots.txt permits this: it disallows only /admin and /maintenance.

WHY IT IS WORTH THE TROUBLE: a profile needs 5 charted matches, and 163 of the 195 players
blocking 2026 WTA-tour dog matches played a 2026 slam match. Lifting a player's profile with
slam data then lets the LOW-ERROR DOG gate fire on her WTA 250/500 matches too -- leverage well
beyond slam matches themselves.

STRICTNESS: Nuxt dedupes repeated strings into single-letter variables, so a value can appear as
`teamAValue:f` instead of a number. Resolving that variable table is fiddly and getting it wrong
would silently record the WRONG error count, so this accepts ONLY literal numerals and reports
how many matches it skipped for that reason. If the skip rate is high, resolving the table is
the next step -- but a missing row is always better than a wrong one.

Pages are cached under data_cache/slam_html/ so re-runs cost nothing, and requests are paced at
one per second.
"""
import os
import re
import sys
import time

import pandas as pd
import requests

_here = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(_here, "data_cache", "slam_html")
OUT = os.path.join(_here, "data_cache", "mcp", "slam_ue.csv")
BASE = "https://www.rolandgarros.com/en-us/matches"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (matchup-edge research)"}
PAUSE = 1.0
COLS = ["match_id", "player", "opp", "Date", "Tournament", "G", "sets", "unforced",
        "winners", "unforced_fh", "unforced_bh", "serve_pts", "return_pts"]


def _fetch(year, code):
    os.makedirs(CACHE, exist_ok=True)
    fp = os.path.join(CACHE, f"rg{year}_{code}.html")
    if os.path.exists(fp) and os.path.getsize(fp) > 50000:
        with open(fp, encoding="utf-8", errors="ignore") as f:
            return f.read()
    try:
        r = requests.get(f"{BASE}/{year}/{code}", headers=H, timeout=45)
    except requests.exceptions.RequestException:
        return None
    time.sleep(PAUSE)
    if r.status_code != 200 or len(r.text) < 50000:
        return None
    with open(fp, "w", encoding="utf-8") as f:
        f.write(r.text)
    return r.text


def _team(html, which):
    """firstName + lastName of the single player on teamA / teamB (singles only)."""
    m = re.search(which + r':\{players:\[\{id:\d+,firstName:"([^"]*)",lastName:"([^"]*)"', html)
    if not m:
        return None
    first, last = m.group(1).strip(), m.group(2).strip()
    if not last:
        return None
    return f"{first} {last.title()}".strip()


def _names():
    """Minified identifier order: a..z, A..Z, then aa, ab, ... -- how the payload names its
    positional arguments."""
    import string
    base = string.ascii_lowercase + string.ascii_uppercase
    for ch in base:
        yield ch
    for c1 in base:
        for c2 in base:
            yield c1 + c2


def _vars(html):
    """Resolve the payload's variable table.

    The page ends with `}(null,false,true,"","ARTICLE",...,"unforced errors","34",...)` -- a
    positional argument list bound to the minified parameter names in order. Nuxt substitutes a
    name wherever a value repeats, so a stat can read `teamAValue:t` instead of a numeral. Without
    this table those matches are unreadable; with it they resolve exactly. Values are split at
    top-level commas only, so commas inside strings do not break it.
    """
    t = html.rfind("}(")
    if t < 0:
        return {}
    seg = html[t + 2:]
    args, buf, depth, inq, esc = [], [], 0, False, False
    for ch in seg:
        if esc:
            buf.append(ch)
            esc = False
            continue
        if ch == "\\":
            buf.append(ch)
            esc = True
            continue
        if ch == '"':
            inq = not inq
            buf.append(ch)
            continue
        if not inq:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                if depth == 0:          # the closing paren of the call: done
                    break
                depth -= 1
            elif ch == "," and depth == 0:
                args.append("".join(buf).strip())
                buf = []
                continue
        buf.append(ch)
    if buf:
        args.append("".join(buf).strip())
    return {n: v for n, v in zip(_names(), args)}


def _num(tok, table):
    """A stat value -> float, resolving a minified reference through the table. None unless it
    ends up an actual number, so a misread can never masquerade as an error count."""
    tok = (tok or "").strip()
    if re.fullmatch(r'"?-?[\d.]+"?', tok):
        return float(tok.strip('"'))
    v = table.get(tok)
    if v is None:
        return None
    v = str(v).strip().strip('"')
    return float(v) if re.fullmatch(r"-?[\d.]+", v) else None


def _stat(block, name, table=None):
    """(teamA, teamB) for one stat, resolving minified references."""
    table = table or {}
    m = re.search(name + r':\{label:[^,]*,teamAValue:([^,]+),teamBValue:([^},]+)\}', block)
    if not m:
        return None, None
    return _num(m.group(1), table), _num(m.group(2), table)


def parse(html):
    """One RG match page -> two rows (one per player), or [] if unusable."""
    if "matchStatisticsSection" not in html or 'status:"FINISHED"' not in html:
        return [], "not finished / no stats"
    if "DOUBLES" in html.upper()[:4000] and "teamA:{players:[{id" not in html:
        return [], "doubles"
    p1, p2 = _team(html, "teamA"), _team(html, "teamB")
    if not p1 or not p2:
        return [], "no player names"
    # singles only: a doubles team lists two players in the array
    if re.search(r'teamA:\{players:\[\{id:\d+.*?\},\{id:\d+', html[:200000]):
        return [], "doubles"
    d = re.search(r'dateSchedule:"(\d{8})"', html)
    if not d:
        return [], "no date"
    i = html.find("matchStatistics:{")
    j = html.find("setStatistics1:{", i)
    block = html[i: j if j > i else i + 4000]
    tbl = _vars(html)
    ua, ub = _stat(block, "unforcedErrors", tbl)
    if ua is None or ub is None:
        return [], "unforced errors unresolvable"
    wa, wb = _stat(block, "winners", tbl)
    ta, tb = _stat(block, "totalPointsWon", tbl)
    # Sets played = how many setStatistics blocks exist. The page only emits blocks for sets
    # actually played (a two-set match has setStatistics1 and 2 and no setStatistics3), so the
    # count is exact -- no need to inspect their contents, whose values are often minified refs.
    sets = sum(1 for n in range(1, 6) if f"setStatistics{n}:{{" in html)
    if not sets:
        return [], "no set blocks"
    rows = []
    for me, op, u, w, t in ((p1, p2, ua, wa, ta), (p2, p1, ub, wb, tb)):
        rows.append({"match_id": None, "player": me, "opp": op, "Date": d.group(1),
                     "Tournament": "Roland Garros", "G": "W", "sets": sets, "unforced": u,
                     "winners": (w if w is not None else ""), "unforced_fh": "", "unforced_bh": "",
                     "serve_pts": "", "return_pts": ""})
    return rows, None


def scrape(years=(2024, 2025, 2026), prefix="SD", upto=127, verbose=True):
    rows, skips = [], {}
    for y in years:
        got = 0
        for i in range(1, upto + 1):
            code = f"{prefix}{i:03d}"
            html = _fetch(y, code)
            if not html:
                skips["fetch failed"] = skips.get("fetch failed", 0) + 1
                continue
            rs, why = parse(html)
            if rs:
                for r in rs:
                    r["match_id"] = f"RG{y}-{code}"
                rows += rs
                got += 1
            else:
                skips[why] = skips.get(why, 0) + 1
        if verbose:
            print(f"  RG {y} {prefix}: {got} matches parsed", flush=True)
    if verbose:
        print(f"  skipped: {skips}")
    if not rows:
        return {"rows": 0, "skips": skips}
    D = pd.DataFrame(rows)[COLS]
    if os.path.exists(OUT):
        D = pd.concat([pd.read_csv(OUT, dtype=str), D.astype(str)]).drop_duplicates(
            ["match_id", "player"], keep="last")
    D.to_csv(OUT, index=False)
    return {"rows": len(rows), "file_rows": len(D), "skips": skips, "out": OUT}


if __name__ == "__main__":
    yrs = tuple(int(x) for x in sys.argv[1:]) or (2024, 2025, 2026)
    print(scrape(years=yrs))
    sys.stdout.flush()
