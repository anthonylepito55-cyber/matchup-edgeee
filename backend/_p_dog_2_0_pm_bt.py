"""P DOG TO WIN 2-0, vs REAL Polymarket set prices (2026-10-09, user: "test it").

1. Model P's out-of-sample dog rows (2026, through the archive end) with P's prob and the
   actual set score (archive).
2. Matched to Polymarket tennis events (pm_tennis_lines_v2.parquet from the line backfill)
   by date (+-1 day) and both player names (TennisRatio slugs vs PM names, letters only).
3. For each matched event: the 'Set Handicap: DOG (-1.5) vs FAV (+1.5)' market = dog wins
   2-0; its last sane CLOB quote >= 10 min before the listed start.
4. Bet dog 2-0 at that price when P likes the dog (EV >= 5%) vs every matched dog, and by
   P's own 2-0 edge (P-implied 2-0 from P's match prob vs the PM price).
Polymarket prices carry little vig; real fills cost ~1-2c of spread.
"""
import json
import re
import time
import unicodedata
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def get(url, params, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=H, timeout=25)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(3 * (i + 1))
        except requests.exceptions.RequestException:
            time.sleep(2 * (i + 1))
    return None


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


def tokset(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return "".join(sorted(re.sub(r"[^a-z ]", " ", s).split()))


# ---------- P rows (2026) + set scores
O = pd.read_parquet("data_cache/_model_p250_oos.parquet")
O = O[(O.yr == 2026) & ((O.G == "W") | (O.player_odd <= 3.0))].copy()
ns = {}
src = open("_tennis_model_c_build.py", encoding="utf-8").read()
exec(compile(src.split("from sklearn.linear_model")[0], "_c_prep", "exec"), ns)
mC = ns["m"]
sc = mC[["date", "player_slug", "rival_slugname", "score", "rival_name"]].drop_duplicates(["date", "player_slug", "rival_slugname"])
O = O.merge(sc, on=["date", "player_slug", "rival_slugname"], how="left")


def sets(score):
    try:
        w = l = 0
        for t in str(score).split():
            g = t.split("(")[0].split("-")
            x, y = int(g[0]), int(g[1])
            w += x > y
            l += y > x
        return w, l
    except (ValueError, IndexError):
        return None


ss = O.score.map(sets)
O["sw"] = [x[0] if x else np.nan for x in ss]
O["sl"] = [x[1] if x else np.nan for x in ss]
O = O[O.sw.notna() & (((O.sw == 2) & (O.sl <= 1)) | ((O.sl == 2) & (O.sw <= 1)))]
O = O[(O.sw == 2) == O.won.astype(bool)].copy()
O["dog20"] = (O.sw == 2) & (O.sl == 0)
# P-implied 2-0 (iid sets): solve s from m = s^2(3-2s)
m = O.pP.clip(1e-4, 1 - 1e-4).values
lo, hi = np.zeros_like(m), np.ones_like(m)
for _ in range(50):
    mid = (lo + hi) / 2
    f = mid * mid * (3 - 2 * mid)
    lo, hi = np.where(f < m, mid, lo), np.where(f >= m, mid, hi)
O["p20_P"] = ((lo + hi) / 2) ** 2
O["dk"] = O.player_slug.astype(str).map(norm)
O["rk"] = O.rival_slugname.astype(str).map(norm)
print(f"P 2026 dog rows with a clean best-of-3 score: {len(O)}", flush=True)

# ---------- Polymarket events from the line backfill
L = pd.read_parquet("data_cache/pm_tennis_lines_v2.parquet")
L["k1"], L["k2"] = L.p1.map(norm), L.p2.map(norm)
L["d"] = pd.to_datetime(L.start).dt.tz_convert(None).dt.normalize()
idx = {}
for r in L.itertuples():
    for dd in (-1, 0, 1):
        idx.setdefault((r.d + pd.Timedelta(days=dd), frozenset((r.k1, r.k2))), r)
O["d"] = pd.to_datetime(O.date).dt.normalize()
hits = []
for r in O.itertuples():
    e = idx.get((r.d, frozenset((r.dk, r.rk))))
    if e is not None:
        hits.append((r.Index, e.slug, e.p1, e.p2, e.start))
print(f"matched to a Polymarket event: {len(hits)} (PM coverage starts {L.start.min():%Y-%m-%d})", flush=True)

rows = []
for i, slug, p1, p2, start in hits:
    r = O.loc[i]
    ev = get("https://gamma-api.polymarket.com/events", {"slug": slug})
    if not ev:
        continue
    ev = ev[0] if isinstance(ev, list) else ev
    dog_pm = p1 if norm(p1) == r.dk else p2
    tgt = None
    for mk in ev.get("markets") or []:
        if mk.get("sportsMarketType") != "tennis_set_handicap":
            continue
        q = mk.get("question") or ""
        mm = re.search(r"Set Handicap:\s*(.+?)\s*\(-1\.5\)", q)
        if mm and norm(mm.group(1)) == norm(dog_pm):
            tgt = mk
            break
    if tgt is None:
        continue
    try:
        outs = json.loads(tgt["outcomes"]) if isinstance(tgt["outcomes"], str) else tgt["outcomes"]
        toks = json.loads(tgt["clobTokenIds"]) if isinstance(tgt["clobTokenIds"], str) else tgt["clobTokenIds"]
    except (KeyError, ValueError, TypeError):
        continue
    j = 0 if norm(outs[0]) == norm(dog_pm) else 1
    t0 = int(pd.Timestamp(start).timestamp())
    h = get("https://clob.polymarket.com/prices-history", {"market": toks[j], "startTs": t0 - 7 * 86400, "endTs": t0, "fidelity": 10})
    pts = [(int(x["t"]), float(x["p"])) for x in (h or {}).get("history", []) if 0.02 < float(x["p"]) < 0.98 and int(x["t"]) <= t0 - 600]
    time.sleep(0.12)
    if not pts:
        continue
    rows.append({"G": r.G, "pP": r.pP, "ev": r.ev, "mkt": r.mkt, "p20_P": r.p20_P, "dog20": bool(r.dog20),
                 "price20": pts[-1][1], "n_pts": len(pts), "dog_odd": r.player_odd})
R = pd.DataFrame(rows)
R.to_parquet("data_cache/_p_dog20_pm_rows.parquet")
print(f"with a priced 'dog -1.5 sets' market: {len(R)}\n")


def rep(s, f=20):
    n = len(s)
    if n < f:
        return f"n={n} (thin)"
    w = s.dog20.values
    return (f"{int(w.sum())}-{n-int(w.sum())} hit {100*w.mean():4.1f}% vs PM price {100*s.price20.mean():4.1f}% "
            f"| ROI {100*np.where(w, 1/s.price20 - 1, -1).mean():+6.1f}% (n={n})")


for G, gl in (("M", "MEN"), ("W", "WOMEN"), (None, "ALL")):
    T = R if G is None else R[R.G == G]
    if not len(T):
        continue
    print(f"{gl}: every matched dog, back 2-0      {rep(T)}")
    print(f"   P dog bets (EV>=5%), back 2-0      {rep(T[T.ev >= .05])}")
    print(f"   P 2-0 edge >= 5pt over PM price    {rep(T[T.p20_P - T.price20 >= .05])}")
    print(f"   P bets AND 2-0 edge >= 5pt         {rep(T[(T.ev >= .05) & (T.p20_P - T.price20 >= .05)])}\n")
