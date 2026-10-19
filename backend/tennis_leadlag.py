"""PHASE 5: Pinnacle lead-lag PAPER experiment (PHASE5_LEADLAG_EXPERIMENT_PLAN.md).

READ-ONLY throughout: consumes the snapshots oo_feed already stores (the 60-second scanner is
untouched), places no orders, moves no money, and never calls OpticOdds itself. Burst mode is a
separate, instrumented, default-OFF sampler of the venues' own public books (not OpticOdds), and
stays off until the readiness probe passes and it is explicitly enabled in the state file.

TIMESTAMP DISCIPLINE (plan rule: never invent a source timestamp):
  src_move_ts     the venue's OWN stamp on the Pinnacle quote that moved (quote_ts)
  recv_ts         poll_ts of the snapshot row that first carried that quote -- when WE saw it
  decision_ts     recv_ts + LATENCY_BUDGET_S (when a real order could plausibly be sent)
  fill_obs_ts     poll_ts of the first exchange observation at/after decision_ts
  fill_quote_ts   the exchange's OWN stamp on the quote used for the fill (its age is
                  fill_obs_ts - fill_quote_ts); None is recorded as None, never backfilled

FROZEN CONFIG: hashed below; the hash is stamped into the state file when Period A starts and
every signal record carries it. Changing any value changes the hash and the engine refuses to
append to a ledger started under a different hash.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone

import pandas as pd

import oo_feed as F
import oo_steam as ST

HERE = os.path.dirname(os.path.abspath(__file__))
SIGNALS = os.path.join(HERE, "data_cache", "leadlag_signals.parquet")
STATE = os.path.join(HERE, "data_cache", "leadlag_state.json")
BURST_DIR = os.path.join(HERE, "data_cache", "leadlag_burst")

CONFIG = {
    "version": "A1",
    "sharp": "Pinnacle",
    "venues": ["Kalshi", "Polymarket"],
    # the tennis leagues the EXISTING feed already polls (changing the feed is out of scope)
    "leagues": ["atp", "atp_challenger", "itf_men"],
    "min_move_pp": 3.0,          # qualifying Pinnacle de-vigged fair move, in probability points
    "max_quote_gap_s": 900,      # consecutive-quote moves only: a gap longer than this is drift
    "latency_budget_s": 3.0,     # decision + venue ack; nothing faster than the measured lag
    "fill_window_s": 900,        # no exchange observation within this window -> missed_gap
    "stake_usd": 25.0,
    "slippage_pp": 1.0,          # one tick adverse, in probability points, on every fill
    # fees in probability points of effective price; documented rates, deliberately not
    # oo_feed's older zero-fee Polymarket entry (docs.polymarket.com/trading/fees, 2026-10-17)
    "fee_pp": {"Kalshi": "7*p*(1-p)", "Polymarket": "5*p*(1-p)"},
    "pre_match_only": True,
    "period_A_min_fills": 200,   # Period A ends at >=200 valid fills; B = equal DURATION after
    # BURST mode (verified 2026-10-18: Pinnacle availability via 3s poll = median 1.8s, max 2.9s;
    # 20 calls/min vs the 8,000/min cap; socket timeout added after the probe hung on a dead
    # connection). The 60s snapshots cannot see the 3-6s stale window (0 fills in the dry run),
    # so burst is the experiment's observation plane.
    "burst_poll_s": 3.0,
    "burst_fixtures": 8,
    "burst_socket_timeout_s": 10,
    "burst_lookahead_h": 6,
}
CONFIG_SHA = hashlib.sha256(json.dumps(CONFIG, sort_keys=True).encode()).hexdigest()[:16]


def fee_pp(venue: str, prob: float) -> float:
    if not (0 < prob < 1):
        return 0.0
    return {"Kalshi": 7.0, "Polymarket": 5.0}.get(venue, 0.0) * prob * (1 - prob)


# ------------------------------------------------------------------ state / ledger
def load_state() -> dict:
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {"watermark": 0.0, "period_A_start": None, "config_sha": CONFIG_SHA,
            "burst_enabled": False}


def save_state(st: dict):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, STATE)


def load_signals() -> pd.DataFrame:
    if os.path.exists(SIGNALS):
        return pd.read_parquet(SIGNALS)
    return pd.DataFrame()


def append_signals(rows: list[dict]):
    if not rows:
        return
    df = pd.DataFrame(rows)
    old = load_signals()
    if len(old):
        df = pd.concat([old, df], ignore_index=True)
        df = df.drop_duplicates(subset=["signal_id"], keep="first")
    tmp = SIGNALS + ".tmp"
    df.to_parquet(tmp, index=False)
    os.replace(tmp, SIGNALS)


# ------------------------------------------------------------------ the pure evaluator
def evaluate_signal(move: dict, venue: str, vrows: pd.DataFrame, cfg: dict = CONFIG) -> dict:
    """One qualifying Pinnacle move against one venue's observation history for the SAME
    fixture+selection. Pure function of its inputs -- this is what the sim tests exercise.

    `move`: fixture_id, selection, src_move_ts, recv_ts, fair_pre, fair_post, league, matchup,
            start_ts (epoch or None).
    `vrows`: that venue's snapshot rows (price, quote_ts, poll_ts, order_book, top_size),
             any order. Returns the full signal record with outcome in {filled, partial,
             missed_adjusted, missed_no_market, missed_gap, missed_worse_price,
             missed_no_liquidity, mapping_error, skipped_inplay}.
    """
    rec = dict(move)
    rec.update(venue=venue, config_sha=CONFIG_SHA, eval_ts=time.time(),
               outcome=None, fill_prob=None, eff_prob=None, fee_pp=None,
               fill_obs_ts=None, fill_quote_ts=None, quote_age_s=None,
               pre_prob=None, stake_filled=None, venue_adjust_latency_s=None,
               fill_price_am=None, note=None)
    decision_ts = move["recv_ts"] + cfg["latency_budget_s"]
    rec["decision_ts"] = decision_ts

    if cfg["pre_match_only"] and move.get("start_ts") and decision_ts >= move["start_ts"]:
        rec["outcome"] = "skipped_inplay"
        return rec
    if vrows is None or not len(vrows):
        rec["outcome"] = "missed_no_market"
        return rec
    v = vrows.sort_values("quote_ts")
    pre = v[v["quote_ts"] <= move["src_move_ts"]]
    rec["pre_prob"] = F.am_to_prob(pre.iloc[-1]["price"]) if len(pre) else None

    post = v[v["poll_ts"] >= decision_ts].sort_values("poll_ts")
    if not len(post):
        rec["outcome"] = "missed_gap"
        return rec
    first = post.iloc[0]
    if first["poll_ts"] - decision_ts > cfg["fill_window_s"]:
        rec["outcome"] = "missed_gap"
        rec["note"] = "first obs %.0fs after decision" % (first["poll_ts"] - decision_ts)
        return rec
    rec["fill_obs_ts"] = float(first["poll_ts"])
    rec["fill_quote_ts"] = float(first["quote_ts"]) if pd.notna(first["quote_ts"]) else None
    if rec["fill_quote_ts"] is not None:
        rec["quote_age_s"] = rec["fill_obs_ts"] - rec["fill_quote_ts"]
    ask_prob = F.am_to_prob(first["price"])
    if ask_prob is None or pd.isna(ask_prob):
        rec["outcome"] = "mapping_error"
        rec["note"] = "unparseable price"
        return rec
    rec["fill_prob"] = ask_prob
    rec["fill_price_am"] = float(first["price"])

    # venue already re-priced AFTER the move -> the stale quote is gone; conservative miss
    if rec["fill_quote_ts"] is not None and rec["fill_quote_ts"] > move["src_move_ts"]:
        rec["outcome"] = "missed_adjusted"
        rec["venue_adjust_latency_s"] = rec["fill_quote_ts"] - move["src_move_ts"]
        return rec
    # quote must still be the pre-move price or better (plan 2.2); tolerance 0.1pp
    if rec["pre_prob"] is not None and ask_prob > rec["pre_prob"] + 0.001:
        rec["outcome"] = "missed_worse_price"
        return rec
    # theoretical edge must exist at the post-move fair, else there is nothing to capture
    if ask_prob >= move["fair_post"]:
        rec["outcome"] = "missed_worse_price"
        rec["note"] = "ask already at/above post-move fair"
        return rec

    # liquidity: ladder size at this price or better, in units; $ cost ~ units * prob
    size = F.takeable_size(first.get("order_book"), first["price"], first.get("top_size"))
    if size is None:
        rec["outcome"] = "filled"
        rec["note"] = "size_unknown"          # sensitivity bucket, reported separately
        rec["stake_filled"] = cfg["stake_usd"]
    else:
        fillable_usd = float(size) * ask_prob
        if fillable_usd <= 0.5:
            rec["outcome"] = "missed_no_liquidity"
            return rec
        rec["stake_filled"] = min(cfg["stake_usd"], fillable_usd)
        rec["outcome"] = "filled" if fillable_usd >= cfg["stake_usd"] - 1e-9 else "partial"
    f_pp = fee_pp(venue, ask_prob)
    rec["fee_pp"] = f_pp
    rec["eff_prob"] = min(0.999, ask_prob + (f_pp + cfg["slippage_pp"]) / 100.0)
    return rec


# ------------------------------------------------------------------ the run
def _start_ts(sd) -> float | None:
    try:
        return datetime.fromisoformat(str(sd).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def run(days: int = 2, verbose: bool = True) -> dict:
    st = load_state()
    if st.get("config_sha") != CONFIG_SHA:
        raise SystemExit("config hash mismatch (state %s vs code %s) -- refusing to run"
                         % (st.get("config_sha"), CONFIG_SHA))
    if not st.get("period_A_start"):
        if verbose:
            print("[leadlag] Period A not started -- readiness gate first. No signals recorded.")
        return {"started": False}
    df = F.load_snapshots(days=days)
    if df.empty:
        return {"started": True, "new": 0, "note": "no snapshots"}
    df = df[df["league"].isin(CONFIG["leagues"]) & (df["market"].astype(str) == "moneyline")]
    fs = ST.fair_series(df, sharp=CONFIG["sharp"])
    if fs.empty:
        return {"started": True, "new": 0, "note": "no sharp series"}
    mv = ST.detect_moves(fs, min_pp=CONFIG["min_move_pp"])
    if len(mv):
        mv = mv[(mv["quote_ts"] - mv["prev_ts"]) <= CONFIG["max_quote_gap_s"]]
        mv = mv[mv["move_pp"] >= CONFIG["min_move_pp"]]        # take the side whose fair ROSE
        mv = mv[mv["quote_ts"] > max(float(st.get("watermark") or 0), float(st["period_A_start"]))]
        mv = mv[mv["quote_ts"] <= time.time() - 120]           # let venue rows arrive
    out, water = [], float(st.get("watermark") or 0)
    sharp_rows = df[df["sportsbook"] == CONFIG["sharp"]]
    for _, m in (mv.iterrows() if len(mv) else []):
        srow = sharp_rows[(sharp_rows["fixture_id"] == m["fixture_id"])
                          & (sharp_rows["selection"] == m["selection"])
                          & (sharp_rows["quote_ts"] == m["quote_ts"])]
        recv = float(srow["poll_ts"].min()) if len(srow) else None
        if recv is None:
            continue                                            # cannot establish receive time
        move = dict(fixture_id=m["fixture_id"], selection=m["selection"],
                    league=m["league"], matchup=m["matchup"],
                    src_move_ts=float(m["quote_ts"]), recv_ts=recv,
                    fair_pre=float(m["prev_fair"]), fair_post=float(m["fair"]),
                    move_pp=float(m["move_pp"]), start_ts=_start_ts(m["start_date"]),
                    start_date=str(m["start_date"]))
        for venue in CONFIG["venues"]:
            vrows = df[(df["fixture_id"] == m["fixture_id"]) & (df["sportsbook"] == venue)
                       & (df["selection"] == m["selection"])]
            rec = evaluate_signal(move, venue, vrows)
            rec["signal_id"] = "%s|%s|%s|%.0f" % (m["fixture_id"], m["selection"], venue, m["quote_ts"])
            out.append(rec)
        water = max(water, float(m["quote_ts"]))
    append_signals(out)
    if water > float(st.get("watermark") or 0):
        st["watermark"] = water
        save_state(st)
    settled = settle(verbose=False)
    if verbose:
        print("[leadlag] %s new signals, %d settled this pass" % (len(out), settled))
    return {"started": True, "new": len(out), "settled": settled}


# ------------------------------------------------------------------ settlement + CLV
def settle(verbose: bool = True) -> int:
    sig = load_signals()
    if sig.empty:
        return 0
    import tennis_log as T
    from tennis_itf_settle import name_keys
    log = pd.read_parquet(T.LOG_PATH)
    log = log[log["settled"].fillna(False).astype(bool) & log["p1_won"].notna()]
    n = 0
    df = None
    for ix, r in sig.iterrows():
        if r["outcome"] not in ("filled", "partial") or pd.notna(r.get("won")):
            continue
        hit = log[log["fixture_id"] == r["fixture_id"]]
        if not len(hit):
            # name+date fallback (ITF ids differ between sources)
            day = str(r.get("start_date"))[:10]
            cand = log[log["date"].astype(str).str[:10] == day]
            ks = name_keys(str(r["selection"]))
            hit = cand[[bool(ks & name_keys(str(p1))) or bool(ks & name_keys(str(p2)))
                        for p1, p2 in zip(cand["player_1"], cand["player_2"])]]
            if len(hit) != 1:
                continue
        row = hit.iloc[0]
        ks = name_keys(str(r["selection"]))
        if ks & name_keys(str(row["player_1"])):
            won = bool(row["p1_won"])
        elif ks & name_keys(str(row["player_2"])):
            won = not bool(row["p1_won"])
        else:
            sig.loc[ix, "outcome"] = "mapping_error"
            sig.loc[ix, "note"] = "selection matches neither settled player"
            n += 1
            continue
        if bool(row.get("void")) if pd.notna(row.get("void")) else False:
            sig.loc[ix, "won"] = None
            sig.loc[ix, "pnl_usd"] = 0.0
            sig.loc[ix, "note"] = "void"
        else:
            stake = float(r["stake_filled"] or 0)
            eff = float(r["eff_prob"])
            sig.loc[ix, "won"] = won
            sig.loc[ix, "pnl_usd"] = stake * (1 - eff) / eff if won else -stake
        sig.loc[ix, "settle_ts"] = time.time()
        # CLV: Pinnacle's last pre-start de-vigged fair for this side vs our effective price
        if df is None:
            df = F.load_snapshots(days=14)
            df = df[df["league"].isin(CONFIG["leagues"]) & (df["market"].astype(str) == "moneyline")]
            fsx = ST.fair_series(df, sharp=CONFIG["sharp"])
        g = fsx[(fsx["fixture_id"] == r["fixture_id"]) & (fsx["selection"] == r["selection"])]
        if r.get("start_ts") and len(g):
            g = g[g["quote_ts"] <= r["start_ts"]]
        if len(g):
            close_fair = float(g.sort_values("quote_ts").iloc[-1]["fair"])
            sig.loc[ix, "close_fair"] = close_fair
            sig.loc[ix, "clv_pp"] = 100.0 * (close_fair - float(r["eff_prob"]))
        n += 1
    if n:
        tmp = SIGNALS + ".tmp"
        sig.to_parquet(tmp, index=False)
        os.replace(tmp, SIGNALS)
    if verbose:
        print("[leadlag] settled/updated %d" % n)
    return n


# ------------------------------------------------------------------ status
def summary() -> dict:
    st = load_state()
    sig = load_signals()
    out = {"config_sha": CONFIG_SHA, "config": CONFIG, "period_A_start": st.get("period_A_start"),
           "burst_enabled": bool(st.get("burst_enabled")), "signals": 0}
    if sig.empty:
        return out
    out["signals"] = int(len(sig))
    out["by_outcome"] = sig["outcome"].value_counts().to_dict()
    out["moves"] = int(sig["signal_id"].str.rsplit("|", n=2).str[0].nunique()) if "signal_id" in sig.columns else None
    fills = sig[sig["outcome"].isin(["filled", "partial"])]
    out["fills"] = int(len(fills))
    # fill rate over ALL qualifying signals (approval item 3), plus the bettable subset for context
    out["fill_rate_pct"] = round(100 * len(fills) / len(sig), 2) if len(sig) else None
    evaluable = sig[~sig["outcome"].isin(["skipped_inplay", "missed_no_market", "mapping_error"])]
    out["fill_rate_of_evaluable_pct"] = round(100 * len(fills) / len(evaluable), 2) if len(evaluable) else None
    # timestamp-questionable observations: no venue stamp on the fill quote, or negative quote age
    if "fill_quote_ts" in sig.columns:
        obs = sig[sig["fill_obs_ts"].notna()]
        out["ts_questionable"] = {
            "no_venue_stamp": int(obs["fill_quote_ts"].isna().sum()),
            "negative_quote_age": int((obs["quote_age_s"].dropna() < -2).sum()),
        }
    if len(fills) and "fair_post" in fills.columns:
        edge = (fills["fair_post"] - fills["eff_prob"]).dropna()
        if len(edge):
            out["theoretical_edge_pp_mean"] = round(100 * float(edge.mean()), 2)
    out["fills_size_unknown"] = int((fills["note"] == "size_unknown").sum()) if len(fills) else 0
    done = fills[fills.get("won").notna()] if "won" in fills.columns else fills.iloc[0:0]
    out["settled"] = int(len(done))
    out["pending"] = int(len(fills) - len(done) - (fills["note"].eq("void").sum() if "note" in fills else 0))
    if len(done):
        out["wins"] = int(done["won"].sum())
        out["staked_usd"] = round(float(done["stake_filled"].sum()), 2)
        out["pnl_usd"] = round(float(done["pnl_usd"].sum()), 2)
        out["roi_pct"] = round(100 * out["pnl_usd"] / out["staked_usd"], 2) if out["staked_usd"] else None
        clv = done["clv_pp"].dropna() if "clv_pp" in done.columns else pd.Series(dtype=float)
        if len(clv):
            out["clv_mean_pp"] = round(float(clv.mean()), 3)
            out["clv_n"] = int(len(clv))
            out["clv_t"] = round(float(clv.mean() / (clv.std(ddof=1) / len(clv) ** 0.5)), 2) if len(clv) > 2 and clv.std() > 0 else None
    if "venue_adjust_latency_s" in sig.columns:
        lat = sig["venue_adjust_latency_s"].dropna()
        if len(lat):
            out["adjust_latency_s"] = {"n": int(len(lat)), "median": round(float(lat.median()), 1),
                                       "p90": round(float(lat.quantile(0.9)), 1)}
    # full per-signal audit chain for the view (approval item 3): every timestamp separately,
    # prices, fees, slippage-inclusive effective price, settlement and CLV where present
    cols = ["signal_id", "matchup", "league", "selection", "move_pp", "fair_pre", "fair_post",
            "src_move_ts", "recv_ts", "decision_ts", "fill_obs_ts", "quote_age_s",
            "pre_prob", "fill_price_am", "fill_prob", "fee_pp", "eff_prob", "stake_filled",
            "venue", "outcome", "note", "won", "pnl_usd", "clv_pp"]
    have = [c for c in cols if c in sig.columns]
    rec = sig.sort_values("src_move_ts").tail(25)[have]
    out["recent"] = json_safe = rec.where(rec.notna(), None).to_dict("records")
    out["slippage_pp"] = CONFIG["slippage_pp"]
    return out


# ------------------------------------------------------------------ burst mode (default OFF)
def probe_burst(n: int = 5) -> dict:
    """Instrumented capability probe of the venues' PUBLIC books (NOT OpticOdds): RTT, status,
    and whether the venue supplies its own timestamp. Read-only; a handful of requests."""
    import urllib.request
    res = {"polymarket": [], "kalshi": []}
    for _ in range(n):
        t0 = time.time()
        try:
            # a real /book call, same endpoint the paper auto-bettor fills from
            import polymarket_data as _P
            evs = _P._fetch_events(False)
            tok = None
            for _ev in evs[:40]:
                _m = _P._moneyline_market(_ev)
                if _m and _m.get("clobTokenIds"):
                    tok = _P._as_list(_m.get("clobTokenIds"))[0]
                    break
            with urllib.request.urlopen(
                    "https://clob.polymarket.com/book?token_id=%s" % tok, timeout=10) as h:
                code = h.status
        except Exception as e:  # noqa: BLE001
            code = str(e)[:40]
        res["polymarket"].append({"rtt_ms": round(1000 * (time.time() - t0)), "status": code,
                                  "venue_ts": "ms field on /book responses"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(
                    "https://api.elections.kalshi.com/trade-api/v2/exchange/status", timeout=10) as h:
                code = h.status
        except Exception as e:  # noqa: BLE001
            code = str(e)[:40]
        res["kalshi"].append({"rtt_ms": round(1000 * (time.time() - t0)), "status": code,
                              "venue_ts": "none on orderbook -- receive time only"})
        time.sleep(1.0)
    return res


# ------------------------------------------------------------------ burst mode
def _burst_fixture_set():
    """Nearest upcoming tennis fixtures that Pinnacle prices, from the existing snapshots."""
    df = F.load_snapshots(days=1)
    df = df[df["league"].isin(CONFIG["leagues"]) & (df["market"].astype(str) == "moneyline")]
    if df.empty:
        return []
    fx = df.groupby("fixture_id").agg(start=("start_date", "last"),
                                      books=("sportsbook", lambda x: set(x))).reset_index()
    fx["start_ts"] = fx["start"].map(_start_ts)
    now = time.time()
    fx = fx[fx["start_ts"].notna() & (fx["start_ts"] > now - 600)
            & (fx["start_ts"] < now + CONFIG["burst_lookahead_h"] * 3600)]
    fx = fx[[("Pinnacle" in b) for b in fx["books"]]]
    return list(fx.sort_values("start_ts").head(CONFIG["burst_fixtures"])["fixture_id"])


def burst_loop(max_minutes: float = 55.0):
    """The experiment's observation plane: poll Pinnacle+venues every burst_poll_s on the nearest
    fixtures, keep an in-memory quote history, detect qualifying moves the moment they become
    available, and run the SAME frozen evaluate_signal against the denser history. Instrumented
    per cycle; persists its raw stream so results are reproducible; exits after max_minutes so
    systemd restarts it with a fresh fixture set. Records signals only when Period A has started
    AND state.burst_enabled -- before that it only measures itself."""
    import socket
    socket.setdefaulttimeout(CONFIG["burst_socket_timeout_s"])
    st = load_state()
    if st.get("config_sha") != CONFIG_SHA:
        raise SystemExit("config hash mismatch -- refusing")
    armed = bool(st.get("period_A_start")) and bool(st.get("burst_enabled"))
    cli = F.Feed(verbose=False)
    ids = _burst_fixture_set()
    print("[burst] %d fixtures, armed=%s, cadence %.1fs" % (len(ids), armed, CONFIG["burst_poll_s"]))
    if not ids:
        time.sleep(60)
        return
    fixes = [{"id": i} for i in ids]
    hist = {}
    seen = set()
    last_fair = {}
    starts = {}
    cyc = 0
    t_end = time.time() + max_minutes * 60
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stream_path = os.path.join(BURST_DIR, "stream_%s.parquet" % day)
    os.makedirs(BURST_DIR, exist_ok=True)
    new_rows = []
    while time.time() < t_end:
        t0 = time.time()
        try:
            rows = cli.odds(fixes, ["Pinnacle"] + CONFIG["venues"])
        except Exception as e:  # noqa: BLE001
            print("[burst] poll error: %s" % str(e)[:90])
            rows = []
        t1 = time.time()
        cyc += 1
        pin_two = {}
        for r in rows:
            k = (r["fixture_id"], r["sportsbook"], r["selection"], r["quote_ts"])
            starts.setdefault(r["fixture_id"], _start_ts(r.get("start_date")))
            if k in seen:
                continue
            seen.add(k)
            row = dict(price=r["price"],
                       quote_ts=float(r["quote_ts"]) if r["quote_ts"] is not None else None,
                       poll_ts=t1, order_book=r.get("order_book"), top_size=r.get("top_size"))
            hist.setdefault((r["fixture_id"], r["sportsbook"], r["selection"]), []).append(row)
            new_rows.append(dict(row, fixture_id=r["fixture_id"], sportsbook=r["sportsbook"],
                                 selection=r["selection"], league=r.get("league"),
                                 matchup="%s v %s" % (r.get("home"), r.get("away"))))
            if r["sportsbook"] == "Pinnacle" and r["quote_ts"] is not None:
                pin_two.setdefault((r["fixture_id"], float(r["quote_ts"])), {})[r["selection"]] = \
                    (F.am_to_prob(r["price"]), r)
        sigs = []
        for (fid, qts), sides in pin_two.items():
            if len(sides) != 2:
                continue
            (sa, (pa, ra)), (sb, (pb, rb)) = list(sides.items())
            if not pa or not pb:
                continue
            tot = pa + pb
            for sel, fv, rr in ((sa, pa / tot, ra), (sb, pb / tot, rb)):
                prev = last_fair.get((fid, sel))
                last_fair[(fid, sel)] = (fv, qts)
                if prev is None:
                    continue
                pf, pts = prev
                if qts - pts > CONFIG["max_quote_gap_s"]:
                    continue
                if 100.0 * (fv - pf) < CONFIG["min_move_pp"]:
                    continue
                move = dict(fixture_id=fid, selection=sel, league=rr.get("league"),
                            matchup="%s v %s" % (rr.get("home"), rr.get("away")),
                            src_move_ts=qts, recv_ts=t1, fair_pre=pf, fair_post=fv,
                            move_pp=100.0 * (fv - pf), start_ts=starts.get(fid),
                            start_date=str(rr.get("start_date")))
                sigs.append(move)
                print("[burst] MOVE %+.1fpp %s / %s (avail lag %.1fs)"
                      % (move["move_pp"], move["matchup"], sel, t1 - qts))
        if sigs and armed:
            time.sleep(CONFIG["latency_budget_s"])
            try:
                rows2 = cli.odds(fixes, CONFIG["venues"])
            except Exception as e:  # noqa: BLE001
                print("[burst] fill-obs poll error: %s" % str(e)[:90])
                rows2 = []
            t2 = time.time()
            for r in rows2:
                row = dict(price=r["price"],
                           quote_ts=float(r["quote_ts"]) if r["quote_ts"] is not None else None,
                           poll_ts=t2, order_book=r.get("order_book"), top_size=r.get("top_size"))
                hist.setdefault((r["fixture_id"], r["sportsbook"], r["selection"]), []).append(row)
            out = []
            for move in sigs:
                for venue in CONFIG["venues"]:
                    vr = hist.get((move["fixture_id"], venue, move["selection"]), [])
                    rec = evaluate_signal(move, venue, pd.DataFrame(vr) if vr else None)
                    rec["signal_id"] = "%s|%s|%s|%.0f" % (move["fixture_id"], move["selection"],
                                                          venue, move["src_move_ts"])
                    rec["observed_by"] = "burst"
                    out.append(rec)
                    print("[burst]   -> %s: %s @ %s" % (venue, rec["outcome"], rec.get("fill_price_am")))
            append_signals(out)
        if cyc % 20 == 0:
            print("[burst] cycle %d | rtt %.2fs | hist keys %d | quotes %d" % (cyc, t1 - t0, len(hist), len(seen)))
            if new_rows:
                dfn = pd.DataFrame(new_rows)
                if os.path.exists(stream_path):
                    dfn = pd.concat([pd.read_parquet(stream_path), dfn], ignore_index=True)
                tmp = stream_path + ".tmp"
                dfn.to_parquet(tmp, index=False)
                os.replace(tmp, stream_path)
                new_rows = []
        time.sleep(max(0.0, CONFIG["burst_poll_s"] - (time.time() - t0)))
    print("[burst] window over after %d cycles" % cyc)


if __name__ == "__main__":
    import sys
    if "--burst" in sys.argv:
        burst_loop()
    elif "--settle" in sys.argv:
        settle()
    elif "--probe-burst" in sys.argv:
        print(json.dumps(probe_burst(), indent=1))
    else:
        run()
