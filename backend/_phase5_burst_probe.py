"""PHASE 5 burst VERIFICATION probe (approval item 3): measures the one number that decides
whether any fill window exists -- OpticOdds' AVAILABILITY latency for Pinnacle re-prices
(venue stamp -> first time a fast poller can read it), plus the same for Kalshi/Polymarket.

Design: polls /fixtures/odds for the nearest tennis fixtures every POLL_S seconds for DUR_S
seconds. Read-only; ~DUR_S/POLL_S * ceil(fixtures/5) * 2 calls total (budgeted ~400, vs the
8,000/min cap). Instrumented per approval item 4: every observation records our request time,
response time, and the venue's quote_ts; availability latency = first_seen_recv_ts - quote_ts
for quotes BORN during the probe. Does not touch the 60s scanner, writes only its own JSONL.
"""
import json
import time

import oo_feed as F

POLL_S = 3.0
DUR_S = 600
OUT = "data_cache/leadlag_burst/probe_%d.jsonl" % int(time.time())

import os
os.makedirs("data_cache/leadlag_burst", exist_ok=True)
key = F.load_key()
assert key, "no OpticOdds key"

# nearest upcoming tennis fixtures with a sharp+exchange pair, from the existing snapshots
df = F.load_snapshots(days=1)
df = df[df["league"].isin(["atp", "atp_challenger", "itf_men"])
        & (df["market"].astype(str) == "moneyline")]
now = time.time()
import pandas as pd
fx = df.groupby("fixture_id").agg(start=("start_date", "last"),
                                  books=("sportsbook", lambda s: set(s))).reset_index()


def _ts(sd):
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(sd).replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        return None


fx["start_ts"] = fx["start"].map(_ts)
fx = fx[fx["start_ts"].notna() & (fx["start_ts"] > now - 600) & (fx["start_ts"] < now + 6 * 3600)]
fx = fx[[("Pinnacle" in b) for b in fx["books"]]]
fx = fx.sort_values("start_ts").head(5)
ids = list(fx["fixture_id"])
print("probing %d fixtures for %ds at %.1fs cadence -> %s" % (len(ids), DUR_S, POLL_S, OUT))
assert ids, "no upcoming tennis fixtures to probe"
CLI = F.Feed(key, verbose=False)
FIXES = [{"id": i} for i in ids]

seen = {}
n_req = 0
t_end = time.time() + DUR_S
with open(OUT, "a", encoding="utf-8") as f:
    f.write(json.dumps({"type": "config", "fixtures": ids, "poll_s": POLL_S, "dur_s": DUR_S,
                        "t0": time.time()}) + "\n")
    while time.time() < t_end:
        t_req = time.time()
        try:
            rows = CLI.odds(FIXES, ["Pinnacle", "Kalshi", "Polymarket"])
        except Exception as e:  # noqa: BLE001
            print("poll error:", str(e)[:80])
            rows = []
        t_resp = time.time()
        n_req += 1
        for r in rows or []:
            if r.get("sportsbook") not in ("Pinnacle", "Kalshi", "Polymarket"):
                continue
            k = (r["fixture_id"], r["sportsbook"], r["selection"], r["quote_ts"])
            if k in seen:
                continue
            seen[k] = True
            f.write(json.dumps({"type": "quote", "req_ts": t_req, "resp_ts": t_resp,
                                "sportsbook": r["sportsbook"], "fixture_id": r["fixture_id"],
                                "selection": r["selection"], "price": r["price"],
                                "quote_ts": r["quote_ts"]}) + "\n")
        time.sleep(max(0.0, POLL_S - (time.time() - t_req)))

# ---- analysis: availability latency for quotes born during the probe
import pandas as pd
recs = [json.loads(l) for l in open(OUT, encoding="utf-8") if '"quote"' in l]
d = pd.DataFrame(recs)
print("requests %d, distinct quotes seen %d" % (n_req, len(d)))
if len(d):
    cfg_t0 = json.loads(open(OUT, encoding="utf-8").readline())["t0"]
    born = d[d["quote_ts"] >= cfg_t0]
    born = born.assign(avail_lag=born["resp_ts"] - born["quote_ts"])
    for bk, g in born.groupby("sportsbook"):
        print("  %-11s born-in-probe n=%-4d avail lag: median %6.1fs  p25 %6.1f  p75 %6.1f  min %5.1f"
              % (bk, len(g), g["avail_lag"].median(), g["avail_lag"].quantile(.25),
                 g["avail_lag"].quantile(.75), g["avail_lag"].min()))
    print("VERDICT: a fill window exists only if Pinnacle's availability lag is reliably under")
    print("the venues' ~3.5-6.4s follow latency. Numbers above answer it.")
