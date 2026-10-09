"""Polymarket TENNIS line-movement backfill (2026-10-09, user: "follow market line
movements and backtest the hit rate on that for underdogs and favorites").

For every settled Polymarket tennis singles match (Gamma tag 864) with >= $500 volume:
the hourly/10-min price path from the public CLOB prices-history endpoint, from up to 7
days before the listed start. Per match we keep: open price (first sane quote), prices at
T-24h / T-6h / T-1h, and close = last sane quote >= 10 min before the listed start, plus
the settled winner. "Sane" = 0.03 < p < 0.97 (anything outside is a dead/in-play quote).
Day-windowed pagination, checkpointed to parquet after every day, read-only vs the app.

Usage:  python _pm_tennis_line_backfill.py [START_DATE=2026-05-01] [END_DATE=today]
Output: data_cache/pm_tennis_lines.parquet
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
GAMMA, CLOB = "https://gamma-api.polymarket.com", "https://clob.polymarket.com"
OUT = "data_cache/pm_tennis_lines.parquet"
START = sys.argv[1] if len(sys.argv) > 1 else "2026-05-01"
END = sys.argv[2] if len(sys.argv) > 2 else datetime.now(timezone.utc).strftime("%Y-%m-%d")
MIN_VOL = 500.0


def get(url, params, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=H, timeout=25)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(3 * (i + 1))
                continue
        except requests.exceptions.RequestException:
            time.sleep(2 * (i + 1))
    return None


def ts(s):
    s = str(s).strip().replace(" ", "T")
    if s.endswith("+00"):
        s += ":00"
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def day_events(day):
    lo, hi = day.strftime("%Y-%m-%dT00:00:00Z"), (day + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
    out, off = [], 0
    while True:
        d = get(f"{GAMMA}/events", {"tag_id": 864, "closed": "true", "limit": 100, "offset": off,
                                     "start_date_min": lo, "start_date_max": hi})
        if not isinstance(d, list) or not d:
            break
        out += d
        off += 100
        if len(d) < 100 or off >= 3000:
            break
    return out


def parse(e):
    title = (e.get("title") or "").strip()
    if " vs" not in title or "doubles" in title.lower():
        return None
    mk = next((m for m in (e.get("markets") or []) if m.get("sportsMarketType") == "moneyline"),
              None) or (e.get("markets") or [{}])[0]
    try:
        outs = mk.get("outcomes"); outs = outs if isinstance(outs, list) else json.loads(outs or "[]")
        pr = mk.get("outcomePrices"); pr = pr if isinstance(pr, list) else json.loads(pr or "[]")
        toks = mk.get("clobTokenIds"); toks = toks if isinstance(toks, list) else json.loads(toks or "[]")
    except (ValueError, TypeError):
        return None
    if len(outs) != 2 or len(pr) != 2 or len(toks) != 2 or any("/" in str(o) for o in outs):
        return None
    try:
        p0 = float(pr[0])
    except (ValueError, TypeError):
        return None
    if p0 not in (0.0, 1.0):
        return None                      # not cleanly settled
    vol = float(mk.get("volume") or 0)
    if vol < MIN_VOL:
        return None
    st = e.get("startTime") or mk.get("gameStartTime")
    if not st:
        return None
    lg = "itf" if str(e.get("slug") or "").startswith("itf") else "tour"
    g = "W" if title[:1] == "W" and title[1:2].isdigit() else ("M" if title[:1] == "M" and title[1:2].isdigit() else "?")
    return {"slug": e.get("slug"), "title": title, "p1": outs[0], "p2": outs[1], "tok1": toks[0],
            "p1_won": p0 == 1.0, "start": ts(st), "vol": vol, "lvl": lg, "g_title": g}


def path(row):
    t0 = int(row["start"].timestamp())
    h = get(f"{CLOB}/prices-history", {"market": row["tok1"], "startTs": t0 - 7 * 86400,
                                        "endTs": t0, "fidelity": 10})
    pts = [(int(x["t"]), float(x["p"])) for x in (h or {}).get("history", []) if 0.03 < float(x["p"]) < 0.97]
    pts = [x for x in pts if x[0] <= t0 - 600]
    if len(pts) < 2:
        return None

    def at(sec_before):
        c = [p for t, p in pts if t <= t0 - sec_before]
        return c[-1] if c else None
    return {"open": pts[0][1], "open_t": pts[0][0], "p24": at(86400), "p6": at(6 * 3600),
            "p1h": at(3600), "close": pts[-1][1], "close_t": pts[-1][0], "n_pts": len(pts)}


def main():
    rows = pd.read_parquet(OUT).to_dict("records") if os.path.exists(OUT) else []
    have = {r["slug"] for r in rows}
    day = datetime.strptime(END, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    stop = datetime.strptime(START, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    while day >= stop:
        evs = day_events(day)
        n0 = len(rows)
        for e in evs:
            r = parse(e)
            if not r or r["slug"] in have:
                continue
            pth = path(r)
            time.sleep(0.12)
            if not pth:
                continue
            r.update(pth)
            r.pop("tok1", None)
            rows.append(r)
            have.add(r["slug"])
        pd.DataFrame(rows).to_parquet(OUT)
        print(f"{day:%Y-%m-%d}: events {len(evs)} | kept {len(rows) - n0} | total {len(rows)}", flush=True)
        day -= timedelta(days=1)


if __name__ == "__main__":
    main()
