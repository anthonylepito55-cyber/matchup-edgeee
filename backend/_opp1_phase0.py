"""OPP1 PHASE-0 COVERAGE PROBES (authorized 2026-10-19; spec: OPP1_MARKET_PATH_SPEC.md v2 §6).

Coverage/cost gates ONLY. No model fitting, no feature computation, no outcome inspection, no
full pull. Runs LOCALLY (the EC2 box running Phase 5 Period A is not touched by this script).

Immutable record: every call writes raw/<seq>_<epoch>.json holding {seq, requested_at, path,
params (key redacted), http_status, x-requests-* headers, body}; ledger.jsonl appends one line
per call with the same minus body. Files are never overwritten (seq monotonic, run id in dir).

Budgets (hard): PHASE0_BUDGET = 25,000 credits by header deltas; CEILING: abort if total project
usage since this run's first call would exceed 2,000,000 (tracked from x-requests-remaining).
The run stops itself; it never proceeds to a larger pull.

Probe plan (minimum per gate):
  S1  weekly tennis-key census: /historical/sports?date=<Wed 12:00Z> for every ISO week
      2024-07-01 -> now (cheap; cost measured from headers on the first call).
  S2  weekly snapshot check: for each week with >=1 tennis key, ONE
      /historical/sports/<key>/odds (regions=eu, markets=h2h) at Wed 12:00Z; records snapshot
      ts, events, books per event. Key preference: non-challenger ATP/WTA first, else any.
  S3  Pinnacle T*-window sample: stratified 4 weeks per half-year; for <=2 events in that week's
      S2 snapshot, one eu snapshot at commence_time - 45min; checks a two-way Pinnacle quote
      with last_update within 24h of commence. Plus 5 all-region calls for book-depth readout.
  S4  mapping (no API calls): S2/S3 event records vs the frozen log (read-only copy) via the
      settler's name_keys; and vs the TennisRatio archive for pre-log weeks (supplementary).
Outputs: phase0_summary.json, weekly.csv, events.csv -- the report is written from these.
"""
import glob
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://api.the-odds-api.com/v4"
RUN = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT = os.path.join(HERE, "data_cache", "theoddsapi_hist", "phase0", RUN)
RAW = os.path.join(OUT, "raw")
os.makedirs(RAW, exist_ok=True)
LEDGER = os.path.join(OUT, "ledger.jsonl")
PHASE0_BUDGET = 25000
CEILING = 2_000_000


def load_key():
    k = os.environ.get("ODDS_API_KEY")
    if k:
        return k.strip()
    for ln in open(os.path.join(HERE, ".env"), encoding="utf-8", errors="replace"):
        if ln.startswith("ODDS_API_KEY="):
            return ln.split("=", 1)[1].strip()
    raise SystemExit("no ODDS_API_KEY")


KEY = load_key()
STATE = {"seq": 0, "first_remaining": None, "last_remaining": None, "used_session": 0.0}


def get(path, params):
    if STATE["used_session"] >= PHASE0_BUDGET:
        raise SystemExit("PHASE-0 BUDGET REACHED (%.0f/%d) -- stopping" % (STATE["used_session"], PHASE0_BUDGET))
    if STATE["first_remaining"] is not None and STATE["last_remaining"] is not None \
            and (STATE["first_remaining"] - STATE["last_remaining"]) >= CEILING:
        raise SystemExit("2M CEILING -- aborting")
    STATE["seq"] += 1
    seq = STATE["seq"]
    p = dict(params)
    p["apiKey"] = KEY
    red = {k: v for k, v in params.items()}
    req_at = time.time()
    body, status, err = None, None, None
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(BASE + path + "?" + urllib.parse.urlencode(p), timeout=45) as r:
                hdr = {k.lower(): v for k, v in r.headers.items() if k.lower().startswith("x-requests")}
                status = r.status
                body = json.loads(r.read().decode("utf-8", "replace"))
                break
        except urllib.error.HTTPError as e:
            hdr = {k.lower(): v for k, v in (e.headers or {}).items() if k.lower().startswith("x-requests")}
            status = e.code
            err = e.read().decode("utf-8", "replace")[:200]
            if e.code in (404, 422):
                break
            time.sleep(1.5 * attempt)
        except Exception as e:  # noqa: BLE001
            hdr, status, err = {}, None, str(e)[:160]
            time.sleep(1.5 * attempt)
    rem = hdr.get("x-requests-remaining")
    used_hdr = hdr.get("x-requests-used")
    if rem is not None:
        rem = float(rem)
        if STATE["first_remaining"] is None:
            STATE["first_remaining"] = rem
        if STATE["last_remaining"] is not None and rem < STATE["last_remaining"]:
            STATE["used_session"] += STATE["last_remaining"] - rem
        elif STATE["last_remaining"] is None:
            pass
        STATE["last_remaining"] = rem
    rec = {"seq": seq, "requested_at": req_at, "path": path, "params": red, "status": status,
           "err": err, "x_remaining": rem, "x_used": used_hdr,
           "session_used": round(STATE["used_session"], 1)}
    with open(os.path.join(RAW, "%05d_%d.json" % (seq, int(req_at))), "w", encoding="utf-8") as f:
        json.dump({**rec, "body": body}, f)
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return body, err


def iso_weeks():
    d = datetime(2024, 7, 3, 12, 0, tzinfo=timezone.utc)      # a Wednesday
    out = []
    while d < datetime.now(timezone.utc):
        out.append(d)
        d += timedelta(days=7)
    return out


# ---------------------------------------------------------------- S1 weekly key census
# /historical/sports does NOT exist (404, zero-credit -- verified run 20261019T004520Z), so the
# census is: one current catalog pull, then HISTORICAL EVENTS per tennis key per month -- the
# events' commence_times give the exact covered weeks, at ~1 credit per events call.
weeks = iso_weeks()
months = sorted({w.strftime("%Y-%m") for w in weeks})
cat, err = get("/sports", {"all": "true"})
tkeys = [str(x.get("key")) for x in (cat or []) if str(x.get("key", "")).startswith("tennis_")]
print("S1: catalog tennis keys: %d | months: %d" % (len(tkeys), len(months)))
assert tkeys, "no tennis keys in catalog: %s" % err
# fail-fast shape/cost probe on one key
probe, perr = get("/historical/sports/%s/events" % tkeys[0],
                  {"date": months[-1] + "-15T12:00:00Z"})
print("   events-endpoint probe: err=%s | session credits %.0f" % (perr, STATE["used_session"]))
week_keys = {}
events_all = []
for k in tkeys:
    for m in months:
        body, err = get("/historical/sports/%s/events" % k, {"date": m + "-15T12:00:00Z"})
        data = (body.get("data") if isinstance(body, dict) else body) or []
        for e in data:
            try:
                ct = datetime.fromisoformat(str(e.get("commence_time")).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            wk = ct.strftime("%G-W%V")
            week_keys.setdefault(wk, set()).add(k)
            events_all.append({"week": wk, "sport_key": k, "id": e.get("id"),
                               "commence": e.get("commence_time"),
                               "home": e.get("home_team"), "away": e.get("away_team"),
                               "n_books": None, "has_pin": None, "src": "s1"})
        time.sleep(0.15)
    if STATE["used_session"] > PHASE0_BUDGET * 0.5:
        print("   half budget reached during census -- stopping key loop early at %s" % k)
        break
weekly = []
for w in weeks:
    wk = w.strftime("%G-W%V")
    keys = sorted(week_keys.get(wk, []))
    weekly.append({"week": wk, "wed": w.strftime("%Y-%m-%d"),
                   "tennis_keys": keys, "n_keys": len(keys)})
print("   weeks with >=1 tennis key: %d of %d | session credits %.0f"
      % (sum(1 for x in weekly if x["n_keys"]), len(weekly), STATE["used_session"]))

# ---------------------------------------------------------------- S2 weekly snapshot check
print("S2: one eu odds snapshot per covered week")


def pick_key(keys):
    pri = [k for k in keys if ("atp" in k or "wta" in k) and "challenger" not in k and "itf" not in k]
    return (pri or keys)[0]


for wrec in weekly:
    if not wrec["tennis_keys"]:
        wrec.update(snapshot_ts=None, n_events=0, max_books=0, has_pinnacle=False)
        continue
    k = pick_key(wrec["tennis_keys"])
    when = wrec["wed"] + "T12:00:00Z"
    body, err = get("/historical/sports/%s/odds" % k,
                    {"regions": "eu", "markets": "h2h", "oddsFormat": "american", "date": when})
    ts, evs = None, []
    if isinstance(body, dict):
        ts = body.get("timestamp")
        evs = body.get("data") or []
    nb = 0
    pin = False
    for e in evs:
        bks = e.get("bookmakers") or []
        nb = max(nb, len(bks))
        haspin = any(b.get("key") == "pinnacle" for b in bks)
        pin = pin or haspin
        events_all.append({"week": wrec["week"], "sport_key": k, "id": e.get("id"),
                           "commence": e.get("commence_time"),
                           "home": e.get("home_team"), "away": e.get("away_team"),
                           "n_books": len(bks), "has_pin": haspin, "src": "s2"})
    wrec.update(s2_key=k, snapshot_ts=ts, n_events=len(evs), max_books=nb,
                has_pinnacle=pin, s2_err=err)
    time.sleep(0.3)

# ---------------------------------------------------------------- S3 Pinnacle T*-window sample
print("S3: stratified Pinnacle sample at commence-45min")
halves = {}
for wrec in weekly:
    if wrec["n_events"] > 0:
        h = wrec["wed"][:4] + ("H1" if wrec["wed"][5:7] <= "06" else "H2")
        halves.setdefault(h, []).append(wrec)
sample_rows = []
for h, ws in sorted(halves.items()):
    step = max(1, len(ws) // 4)
    for wrec in ws[::step][:4]:
        evs = [e for e in events_all if e["week"] == wrec["week"] and e["src"] == "s2"][:2]
        for e in evs:
            try:
                ct = datetime.fromisoformat(str(e["commence"]).replace("Z", "+00:00"))
            except ValueError:
                continue
            when = (ct - timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%SZ")
            body, err = get("/historical/sports/%s/odds" % e["sport_key"],
                            {"regions": "eu", "markets": "h2h", "oddsFormat": "american",
                             "date": when})
            found, fresh, last_up = False, False, None
            if isinstance(body, dict):
                for ev in body.get("data") or []:
                    if ev.get("id") != e["id"]:
                        continue
                    for b in ev.get("bookmakers") or []:
                        if b.get("key") == "pinnacle":
                            mk = (b.get("markets") or [{}])[0]
                            oc = mk.get("outcomes") or []
                            found = len(oc) == 2
                            last_up = b.get("last_update")
                            try:
                                lu = datetime.fromisoformat(str(last_up).replace("Z", "+00:00"))
                                fresh = (ct - lu) <= timedelta(hours=24)
                            except ValueError:
                                fresh = False
            sample_rows.append({"half": h, "week": wrec["week"], "sport_key": e["sport_key"],
                                "event": e["id"], "commence": e["commence"],
                                "home": e["home"], "away": e["away"],
                                "t_star_req": when, "pin_two_way": found,
                                "pin_fresh": fresh, "pin_last_update": last_up, "err": err})
            time.sleep(0.35)
# book-depth readout: 5 all-region calls on recent sampled events
for e in [r for r in sample_rows if r["pin_two_way"]][-5:]:
    body, err = get("/historical/sports/%s/odds" % e["sport_key"],
                    {"regions": "us,us2,eu,uk", "markets": "h2h", "oddsFormat": "american",
                     "date": e["t_star_req"]})
    nb = 0
    if isinstance(body, dict):
        for ev in body.get("data") or []:
            if ev.get("id") == e["event"]:
                nb = len(ev.get("bookmakers") or [])
    e["all_region_books"] = nb
    time.sleep(0.35)

# ---------------------------------------------------------------- persist probe tables
pd.DataFrame(weekly).to_csv(os.path.join(OUT, "weekly.csv"), index=False)
pd.DataFrame(events_all).to_csv(os.path.join(OUT, "events.csv"), index=False)
pd.DataFrame(sample_rows).to_csv(os.path.join(OUT, "pinnacle_sample.csv"), index=False)

# ---------------------------------------------------------------- S4 mapping (no API calls)
print("S4: mapping vs frozen log + archive (no API calls)")
import sys
sys.path.insert(0, HERE)
from tennis_itf_settle import name_keys  # noqa: E402

summary = {"run": RUN, "weeks_total": len(weekly),
           "credits_session": round(STATE["used_session"], 1),
           "remaining_end": STATE["last_remaining"]}
logp = os.path.join(HERE, "data_cache", "phase0_frozen_log.parquet")
maps = {"log_rows_in_covered_weeks": None, "log_mapped": None}
if os.path.exists(logp):
    lg = pd.read_parquet(logp)
else:
    lg = None
if lg is not None:
    lg = lg[lg["settled"].fillna(False).astype(bool) & lg["p1_won"].notna()]
    lg = lg[lg["league"].astype(str).isin(["atp", "wta", "atp_challenger"])]
    lg["week"] = pd.to_datetime(lg["date"].astype(str).str[:10]).dt.strftime("%G-W%V")
    covered = {w["week"] for w in weekly if w["n_events"] > 0}
    lgc = lg[lg["week"].isin(covered)]
    ev = pd.DataFrame(events_all)
    if len(ev) == 0:
        ev = pd.DataFrame(columns=["week", "sport_key", "id", "commence", "home", "away"])
    ev["cdt"] = pd.to_datetime(ev.get("commence"), errors="coerce", utc=True)
    mapped = 0
    ambiguous = 0
    for _, r in lgc.iterrows():
        k1, k2 = name_keys(str(r["player_1"])), name_keys(str(r["player_2"]))
        st = pd.to_datetime(r["start_time_utc"], errors="coerce", utc=True)
        cand = ev[(ev["cdt"].notna()) & (abs(ev["cdt"] - st) <= pd.Timedelta(hours=12))] if pd.notna(st) else ev.iloc[0:0]
        hits = 0
        for _, e in cand.iterrows():
            h1, h2 = name_keys(str(e["home"])), name_keys(str(e["away"]))
            if (k1 & h1 and k2 & h2) or (k1 & h2 and k2 & h1):
                hits += 1
        if hits == 1:
            mapped += 1
        elif hits > 1:
            ambiguous += 1
    maps = {"log_rows_in_covered_weeks": int(len(lgc)), "log_mapped": mapped,
            "log_ambiguous": ambiguous,
            "note": "S2 holds ONE snapshot per week, so this UNDERCOUNTS mappability -- a lower bound"}
summary["mapping"] = maps

# archive-based weekly denominator
arch = None
for cand in (os.path.join(HERE, "data_cache", "tennisratio", "all_match_logs.parquet"),
             os.path.join(OUT, "all_match_logs.parquet")):
    if os.path.exists(cand):
        arch = cand
        break
if arch:
    a = pd.read_parquet(arch, columns=["date", "tournament_level"])
    a["d"] = pd.to_datetime(a["date"], errors="coerce")
    a = a[a["d"] >= "2024-07-01"]
    lvl = a["tournament_level"].astype(str).str.lower()
    a = a[lvl.str.contains("atp|wta|challenger|grand|next")]
    wk = a.groupby(a["d"].dt.strftime("%G-W%V")).size()
    denom_weeks = set(wk[wk >= 20].index)
    num_weeks = {w["week"] for w in weekly if w["n_events"] > 0 and w["max_books"] >= 2}
    y25d = [w for w in denom_weeks if w.startswith("2025")]
    y26d = [w for w in denom_weeks if w.startswith("2026")]
    summary["coverage"] = {
        "denom_weeks_total": len(denom_weeks),
        "covered_weeks_total": len(denom_weeks & num_weeks),
        "2025": {"denom": len(y25d), "covered": len([w for w in y25d if w in num_weeks])},
        "2026": {"denom": len(y26d), "covered": len([w for w in y26d if w in num_weeks])},
        "2024H2": {"denom": len([w for w in denom_weeks if w.startswith("2024")]),
                   "covered": len([w for w in denom_weeks if w.startswith("2024") and w in num_weeks])},
    }
else:
    summary["coverage"] = {"error": "archive parquet not found locally"}

sm = pd.DataFrame(sample_rows)
if len(sm):
    summary["pinnacle_sample"] = {
        "n": int(len(sm)), "two_way": int(sm["pin_two_way"].sum()),
        "fresh": int(sm["pin_fresh"].sum()),
        "by_half": {h: {"n": int(len(g)), "fresh": int(g["pin_fresh"].sum())}
                    for h, g in sm.groupby("half")}}
with open(os.path.join(OUT, "phase0_summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=1)
print(json.dumps(summary, indent=1))
print("DONE. credits used this session: %.0f | raw calls: %d | out: %s"
      % (STATE["used_session"], STATE["seq"], OUT))
