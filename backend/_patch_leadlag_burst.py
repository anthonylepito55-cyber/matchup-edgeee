"""PHASE 5: add BURST mode to tennis_leadlag.py (approval item 2, verified per item 3).

Why (measured 2026-10-18): the 60s snapshot pipeline cannot observe the venues' 3-6s stale
window (3-day dry run: 0 fills, 65% missed_adjusted), while a 3s poller sees fresh Pinnacle
re-prices in median 1.8s / max 2.9s (probe_1792365461.jsonl, 192 clean cycles). Burst is
therefore the experiment's observation plane, not an optimization. Budget 20 calls/min against
the 8,000/min cap. Socket timeout added because the probe hung on a dead connection (no timeout
in urllib by default). The 60-second scanner remains untouched; burst runs as its own service,
exits every 55 minutes so systemd restarts it with a fresh fixture set.

The FROZEN FILL RULE is unchanged -- burst only changes observation density. Signals are
recorded ONLY when Period A has started AND state.burst_enabled is true; before that the loop
just measures itself (instrumentation prints).
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tennis_leadlag.py")
s = io.open(P, encoding="utf-8").read()
assert "burst_loop" not in s, "already patched"


def rep(old, new):
    global s
    assert s.count(old) == 1, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


# 1. burst parameters join the frozen config (Period A not started; config finalizes at readiness)
rep('''    "pre_match_only": True,
    "period_A_min_fills": 200,   # Period A ends at >=200 valid fills; B = equal DURATION after
}''',
    '''    "pre_match_only": True,
    "period_A_min_fills": 200,   # Period A ends at >=200 valid fills; B = equal DURATION after
    # BURST mode (verified 2026-10-18: Pinnacle availability via 3s poll = median 1.8s, max 2.9s;
    # 20 calls/min vs the 8,000/min cap; socket timeout added after the probe hung on a dead
    # connection). The 60s snapshots cannot see the 3-6s stale window (0 fills in the dry run),
    # so burst is the experiment's observation plane.
    "burst_poll_s": 3.0,
    "burst_fixtures": 8,
    "burst_socket_timeout_s": 10,
    "burst_lookahead_h": 6,
}''')

BURST = '''

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
                pin_two.setdefault((r["fixture_id"], float(r["quote_ts"])), {})[r["selection"]] = \\
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


if __name__ == "__main__":'''
rep("\n\nif __name__ == \"__main__\":", BURST)
rep('''    if "--settle" in sys.argv:''',
    '''    if "--burst" in sys.argv:
        burst_loop()
    elif "--settle" in sys.argv:''')

io.open(P, "w", encoding="utf-8", newline="").write(s)
import py_compile
py_compile.compile(P, doraise=True)
import tennis_leadlag  # noqa: E402  (import check + prints nothing)
print("burst mode added, compiles; CONFIG_SHA now %s" % tennis_leadlag.CONFIG_SHA)
