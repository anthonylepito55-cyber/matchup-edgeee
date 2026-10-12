"""REAL CLV FOR THE BOARD'S TOUR PICKS, AGAINST PINNACLE'S CLOSE (2026-10-11, user: "yes do
that").

The honest test of the whole tennis board, and the one thing we could not do until now. Our own
frozen price is what the card showed; it is NOT a closing line, so comparing picks to it says
nothing about whether we got a good price. The Odds API's subscribed key gives 5-minute
historical snapshots with **Pinnacle in them**, so for a tour match we can reconstruct the
genuine closing fair probability and ask:

    did the price we took beat the sharp market's FINAL estimate?

Positive CLV means the line moved toward us after we bet -- the standard leading indicator of
real edge, and it resolves in ~50-100 bets where ROI needs thousands.

Method:
  * one historical call per match, timed 5 minutes BEFORE its start, so the snapshot returned
    is the last one before the off (the API returns the nearest snapshot at or before the
    requested timestamp)
  * Pinnacle's two-way prices from that snapshot, de-vigged -> closing fair
  * CLV = closing fair of OUR PICK minus the implied probability of the price we logged
  * matched on tournament key + normalised player names, both orientations

Only the tournaments that exist as Odds API keys can be measured -- Shanghai, Beijing (both
tours), Tokyo, Wuhan -- because this API has no challenger or ITF coverage. That is ~22% of the
settled log, and it is tour-only by construction.

Historical calls bill 10 credits each against ~15M remaining, so cost is irrelevant.
Read-only; writes a parquet of results for later reuse.
"""
import json
import os
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

import numpy as np
import pandas as pd

BASE = "https://api.the-odds-api.com/v4"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data_cache", "tour_clv.parquet")

# our tournament string -> The Odds API sport key. Only tour events exist there.
TOURNEY_KEY = {
    ("atp", "Shanghai, China"): "tennis_atp_shanghai_masters",
    ("wta", "Beijing, China"): "tennis_wta_china_open",
    ("atp", "Beijing, China"): "tennis_atp_china_open",
    ("atp", "Tokyo, Japan"): "tennis_atp_japan_open",
    ("wta", "Wuhan, China"): "tennis_wta_wuhan_open",
}
SHARP = "pinnacle"


def load_key():
    k = os.environ.get("ODDS_API_KEY")
    if k:
        return k.strip()
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8", errors="replace"):
            if ln.strip().startswith("ODDS_API_KEY") and "=" in ln:
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return None


KEY = load_key()
CALLS = [0]


def get(path, params):
    p = dict(params)
    p["apiKey"] = KEY
    try:
        with urllib.request.urlopen(BASE + path + "?" + urllib.parse.urlencode(p),
                                    timeout=60) as r:
            CALLS[0] += 1
            return json.loads(r.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %s" % e.code
    except Exception as e:
        return None, str(e)[:80]


def norm(n):
    s = "".join(c for c in unicodedata.normalize("NFKD", str(n))
                if not unicodedata.combining(c)).lower()
    return " ".join(sorted(c for c in s.replace(".", " ").replace("-", " ").split() if c))


def surname_key(n):
    s = "".join(c for c in unicodedata.normalize("NFKD", str(n))
                if not unicodedata.combining(c)).lower()
    parts = [p for p in s.replace(".", " ").replace("-", " ").split() if p]
    if not parts:
        return ""
    return max(parts, key=len)


def am_to_prob(a):
    try:
        a = float(a)
    except (TypeError, ValueError):
        return None
    if a == 0:
        return None
    d = 1.0 + a / 100.0 if a > 0 else 1.0 + 100.0 / abs(a)
    return 1.0 / d


log = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
log["date"] = pd.to_datetime(log["date"], errors="coerce")
log["start"] = pd.to_datetime(log["start_time_utc"], errors="coerce", utc=True)
S = log[(log["settled"] == True) & log["p1_won"].notna()          # noqa: E712
        & log["p1_odds"].notna() & log["p2_odds"].notna() & log["start"].notna()].copy()
for col in ("surface_bad", "inplay_suspect"):
    if col in S.columns:
        S = S[~S[col].fillna(False).astype(bool)]
S["tkey"] = [TOURNEY_KEY.get((str(a), str(b))) for a, b in zip(S.league, S.tournament)]
M = S[S.tkey.notna()].copy()
print("settled rows %d | mappable to an Odds API tournament: %d (%.0f%%)"
      % (len(S), len(M), 100 * len(M) / max(len(S), 1)))
print("   by key: %s\n" % dict(M.tkey.value_counts()))

snap_cache = {}
rows = []
miss_snap = miss_match = miss_sharp = 0
for r in M.itertuples():
    when = (r.start - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ck = (r.tkey, when)
    if ck not in snap_cache:
        d, err = get("/historical/sports/%s/odds" % r.tkey,
                     {"regions": "us,us2,eu,uk", "markets": "h2h",
                      "oddsFormat": "american", "date": when})
        snap_cache[ck] = None if err else d
    d = snap_cache[ck]
    if not d:
        miss_snap += 1
        continue
    data = d.get("data") if isinstance(d, dict) else d
    # find our match in the snapshot, either orientation
    n1, n2 = norm(r.player_1), norm(r.player_2)
    s1, s2 = surname_key(r.player_1), surname_key(r.player_2)
    hit = None
    for ev in (data or []):
        h, a = norm(ev.get("home_team")), norm(ev.get("away_team"))
        if {h, a} == {n1, n2}:
            hit = ev
            break
        hh, aa = surname_key(ev.get("home_team")), surname_key(ev.get("away_team"))
        if {hh, aa} == {s1, s2} and s1 and s2:
            hit = ev
            break
    if hit is None:
        miss_match += 1
        continue
    pin = None
    for b in (hit.get("bookmakers") or []):
        if b.get("key") == SHARP:
            pin = b
            break
    if pin is None:
        miss_sharp += 1
        continue
    prices = {}
    for mk in (pin.get("markets") or []):
        if mk.get("key") != "h2h":
            continue
        for oc in (mk.get("outcomes") or []):
            prices[surname_key(oc.get("name"))] = oc.get("price")
    if len(prices) < 2:
        miss_sharp += 1
        continue
    pa, pb = prices.get(s1), prices.get(s2)
    ia, ib = am_to_prob(pa), am_to_prob(pb)
    if ia is None or ib is None:
        miss_sharp += 1
        continue
    close_p1 = ia / (ia + ib)                      # closing FAIR for player_1
    # our own frozen market, for reference
    oi1, oi2 = am_to_prob(r.p1_odds), am_to_prob(r.p2_odds)
    ours_p1 = oi1 / (oi1 + oi2) if (oi1 and oi2) else None
    rows.append({
        "date": r.date, "tkey": r.tkey, "league": r.league,
        "p1": r.player_1, "p2": r.player_2,
        "p1_won": bool(r.p1_won),
        "our_p1_odds": r.p1_odds, "our_p2_odds": r.p2_odds,
        "our_fair_p1": ours_p1,
        "close_fair_p1": close_p1,
        "snap_ts": d.get("timestamp") if isinstance(d, dict) else None,
        "model_c_p1": getattr(r, "model_c_p1", None),
        "mc_c75_p1": getattr(r, "mc_c75_p1", None),
    })

R = pd.DataFrame(rows)
print("matched with a Pinnacle close: %d   (no snapshot %d, no name match %d, no Pinnacle %d)"
      % (len(R), miss_snap, miss_match, miss_sharp))
print("   API calls: %d (%d credits)\n" % (CALLS[0], CALLS[0] * 10))
if R.empty:
    raise SystemExit("nothing matched")
R.to_parquet(OUT, index=False)

# ---------------------------------------------------------------- the measurements
print("=" * 104)
print("A. IS OUR FROZEN PRICE A CLOSING PRICE? (our implied vs Pinnacle's closing fair)")
print("=" * 104)
R["drift_pp"] = 100.0 * (R.close_fair_p1 - R.our_fair_p1)
print("   n=%d   median |drift| %.2fpp   mean %+0.2fpp   p90 %.1fpp   p99 %.1fpp"
      % (len(R), R.drift_pp.abs().median(), R.drift_pp.mean(),
         R.drift_pp.abs().quantile(.9), R.drift_pp.abs().quantile(.99)))
print("   our price was on the RIGHT side of the close %.0f%% of the time (vs 50%% by chance)"
      % (100 * (R.drift_pp.abs() > 0).mean()))

print("\n" + "=" * 104)
print("B. CLV OF THE DOG SIDE -- the board's actual business")
print("=" * 104)


def clv_block(sel_p1, label, floor=20):
    """sel_p1: boolean Series, True = the pick is player_1."""
    f = R[sel_p1.notna()].copy()
    s = sel_p1[sel_p1.notna()].astype(bool)
    if len(f) < floor:
        print("   %-44s n=%d (thin)" % (label, len(f)))
        return
    our_imp = np.where(s, 100 * f.our_fair_p1, 100 * (1 - f.our_fair_p1))
    close = np.where(s, 100 * f.close_fair_p1, 100 * (1 - f.close_fair_p1))
    clv = close - our_imp
    won = np.where(s, f.p1_won, ~f.p1_won)
    dec = np.where(s, [1 / x if x else np.nan for x in
                       [am_to_prob(v) for v in f.our_p1_odds]],
                   [1 / x if x else np.nan for x in
                    [am_to_prob(v) for v in f.our_p2_odds]])
    pnl = np.where(won, dec - 1, -1.0)
    se = clv.std(ddof=1) / np.sqrt(len(clv))
    print("   %-44s CLV %+5.2fpp +/- %4.2f  beat close %3.0f%%  ROI %+6.1f%%  (n=%d)"
          % (label, clv.mean(), se, 100 * (clv > 0).mean(), 100 * np.nanmean(pnl), len(f)))


mkt_dog_p1 = R.our_fair_p1 < 0.5
clv_block(pd.Series(True, index=R.index), "every match, backing player_1 (control)")
clv_block(mkt_dog_p1, "the market DOG")
clv_block(~mkt_dog_p1, "the market FAVOURITE")
if R.model_c_p1.notna().any():
    c_p1 = R.model_c_p1.astype(float) >= 0.5
    clv_block(c_p1.where(R.model_c_p1.notna()), "Model C's pick")
    clv_block((c_p1 & mkt_dog_p1).where(R.model_c_p1.notna() & mkt_dog_p1),
              "Model C on the DOG")
if R.mc_c75_p1.notna().any():
    c75 = R.mc_c75_p1.astype(float) >= 0.5
    clv_block(c75.where(R.mc_c75_p1.notna()), "c75's pick")
    clv_block((c75 & mkt_dog_p1).where(R.mc_c75_p1.notna() & mkt_dog_p1),
              "c75 on the DOG")

print("\n" + "=" * 104)
print("C. BY TOURNAMENT")
print("=" * 104)
for k, g in R.groupby("tkey"):
    d = 100.0 * (g.close_fair_p1 - g.our_fair_p1)
    print("   %-32s n=%-4d median |drift| %5.2fpp  mean %+5.2fpp"
          % (k, len(g), d.abs().median(), d.mean()))
print("\n   saved -> %s" % OUT)
