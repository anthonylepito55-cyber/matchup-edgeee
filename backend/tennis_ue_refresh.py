"""Daily refresh of unforced-error data (2026-10-09, user: "do it").

1. Re-download the Match Charting Project CSVs from GitHub (Tennis Abstract's published
   dataset, CC BY-NC-SA -- non-commercial use).
2. The tennisabstract.com website is ahead of GitHub (site had matches to ~10-05 when GitHub
   stopped at 09-09). Pull charted matches that are newer than our data from the site's
   charting pages (robots.txt allows /charting/; only /jsfrags/ /jsmatches/ /jsplayers/ are
   disallowed), politely rate-limited, parsing each page's embedded 'overview' table
   (Winners FH/BH, UFE FH/BH, per set + total) and 'serve' table (points served).
   Rows land in data_cache/mcp/ta_extra.csv, which tennis_ue.load() merges.
"""
import html as _html
import os
import re
import time

import pandas as pd
import requests

_here = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(_here, "data_cache", "mcp")
EXTRA = os.path.join(DIR, "ta_extra.csv")
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (matchup-edge research)"}
GH = "https://raw.githubusercontent.com/JeffSackmann/tennis_MatchChartingProject/master/"
FILES = ("charting-m-matches.csv", "charting-w-matches.csv",
         "charting-m-stats-Overview.csv", "charting-w-stats-Overview.csv",
         # detail files (2026-10-10): error breakdown by key point, rally length and shot
         # side. Same matches as Overview, so this is depth not coverage; display only.
         "charting-m-stats-KeyPointsServe.csv", "charting-w-stats-KeyPointsServe.csv",
         "charting-m-stats-Rally.csv", "charting-w-stats-Rally.csv",
         "charting-m-stats-ShotTypes.csv", "charting-w-stats-ShotTypes.csv")


def refresh_github():
    os.makedirs(DIR, exist_ok=True)
    ok = 0
    for f in FILES:
        try:
            r = requests.get(GH + f, headers=H, timeout=120)
            if r.status_code == 200 and len(r.content) > 10000:
                tmp = os.path.join(DIR, f + ".tmp")
                with open(tmp, "wb") as fh:
                    fh.write(r.content)
                os.replace(tmp, os.path.join(DIR, f))
                ok += 1
        except requests.exceptions.RequestException:
            pass
    return ok


def _cells(html_frag):
    t = re.sub(r"<[^>]+>", "|", html_frag)
    return [c.strip() for c in _html.unescape(t).split("|") if c.strip()]


def _num(s):
    m = re.match(r"(\d+)(?:\s*\((\d+)/(\d+)\))?", s or "")
    return (int(m.group(1)), int(m.group(2)) if m.group(2) else None, int(m.group(3)) if m.group(3) else None) if m else (None, None, None)


def parse_match(mid, page):
    ov = re.search(r"var overview = '(.*?)';", page, re.S)
    sv = re.search(r"var serve = '(.*?)';", page, re.S)
    if not ov or not sv:
        return []
    c = _cells(ov.group(1))
    # player names = the cells right after the 9 header labels, total block first
    try:
        start = c.index("UFE (FH/BH)") + 1
    except ValueError:
        return []
    # each player block = name + 9 stat cells (A%, DF%, 1stIn, 1st%, 2nd%, BPSaved, RPW%,
    # Winners (FH/BH), UFE (FH/BH))
    p1, p2 = c[start], c[start + 10]
    tot = {p1: c[start + 1: start + 10], p2: c[start + 11: start + 20]}
    sets = sum(1 for x in c if re.fullmatch(r"SET \d", x))
    s = _cells(sv.group(1))
    tots = [s[i + 1] for i, x in enumerate(s) if x.endswith(" Total") and i + 1 < len(s)]
    if len(tots) < 2:
        return []
    sp = {p1: int(re.match(r"\d+", tots[0]).group()), p2: int(re.match(r"\d+", tots[1]).group())}
    d = mid[:8]
    g = "M" if "-M-" in mid[:12] else "W"
    tourn = mid.split("-")[2].replace("_", " ")
    out = []
    for me, op in ((p1, p2), (p2, p1)):
        w, wfh, wbh = _num(tot[me][7])
        u, ufh, ubh = _num(tot[me][8])
        if u is None:
            continue
        out.append({"match_id": mid, "player": me, "opp": op, "Date": d, "Tournament": tourn, "G": g,
                    "sets": sets or None, "serve_pts": sp[me], "return_pts": sp[op], "winners": w,
                    "winners_fh": wfh, "winners_bh": wbh, "unforced": u, "unforced_fh": ufh, "unforced_bh": ubh})
    return out


def refresh_site(max_new=150, pause=2.0):
    """Fetch charted matches newer than anything we have (GitHub + previous site pulls)."""
    import tennis_ue as U
    have = set()
    latest = "00000000"
    try:
        D = U.load(force=True)
        have = set(D.match_id.astype(str))
        latest = D.date.max().strftime("%Y%m%d")
    except Exception:  # noqa: BLE001
        pass
    meta = requests.get("https://www.tennisabstract.com/charting/meta.html", headers=H, timeout=60).text
    ids = sorted({x[:-5] for x in re.findall(r'href="(\d{8}-[MW]-[^"]+\.html)"', meta)})
    todo = [i for i in ids if i[:8] >= latest and i not in have][-max_new:]
    rows = []
    for mid in todo:
        try:
            p = requests.get(f"https://www.tennisabstract.com/charting/{mid}.html", headers=H, timeout=40).text
            rows += parse_match(mid, p)
        except requests.exceptions.RequestException:
            pass
        time.sleep(pause)
    if rows:
        new = pd.DataFrame(rows)
        if os.path.exists(EXTRA):
            new = pd.concat([pd.read_csv(EXTRA, dtype=str), new.astype(str)]).drop_duplicates(["match_id", "player"])
        new.to_csv(EXTRA, index=False)
    U.load(force=True)
    return {"site_candidates": len(todo), "rows_added": len(rows), "since": latest}


def refresh_all():
    gh = refresh_github()
    site = refresh_site()
    return {"github_files": gh, **site}


if __name__ == "__main__":
    print(refresh_all())
