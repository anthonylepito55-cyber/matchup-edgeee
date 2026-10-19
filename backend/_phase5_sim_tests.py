"""PHASE 5 simulator validation: replayed synthetic events through tennis_leadlag.evaluate_signal.

Covers the plan's required edge cases: normal fill, stale-quote (venue already adjusted), missed
updates / suspension gap, partial fill, unavailable liquidity, worse displayed price, mapping
error (unparseable price), in-play exclusion, and unknown size (sensitivity bucket). Asserts the
outcome AND the cost arithmetic (fees + slippage) on the fill path. Exits non-zero on any failure.
"""
import json

import pandas as pd

import tennis_leadlag as LL

T0 = 1_760_000_000.0            # arbitrary epoch base
MOVE = dict(fixture_id="FX1", selection="Player A", league="atp", matchup="A v B",
            src_move_ts=T0, recv_ts=T0 + 20,          # our poller saw it 20s later
            fair_pre=0.50, fair_post=0.56, move_pp=6.0,
            start_ts=T0 + 3600, start_date="2026-10-19T00:00:00Z")


def vrow(price, quote_ts, poll_ts, book=None, top=None):
    return dict(price=price, quote_ts=quote_ts, poll_ts=poll_ts,
                order_book=json.dumps(book) if book else None, top_size=top)


def run(name, move, rows, want, extra=None):
    rec = LL.evaluate_signal(dict(move), "Kalshi", pd.DataFrame(rows) if rows is not None else None)
    ok = rec["outcome"] == want and all(abs((rec.get(k) or 0) - v) < 1e-6 if isinstance(v, float)
                                        else rec.get(k) == v for k, v in (extra or {}).items())
    print("  %-28s -> %-22s %s" % (name, rec["outcome"], "PASS" if ok else "FAIL (want %s %s, got %s)"
                                   % (want, extra or "", {k: rec.get(k) for k in (extra or {})})))
    return ok


ok = True
# 1. normal full fill: stale +105 quote (52.4% -> below post-move fair 56%), deep book
ok &= run("normal fill", MOVE,
          [vrow(105, T0 - 300, T0 - 240), vrow(105, T0 - 300, T0 + 60, book=[[105, 200]])],
          "filled", {"fill_prob": 100 / 205, "stake_filled": 25.0})
# fee arithmetic: Kalshi 7*p*(1-p) pp + 1pp slippage on top of 48.78%
rec = LL.evaluate_signal(dict(MOVE), "Kalshi", pd.DataFrame(
    [vrow(105, T0 - 300, T0 + 60, book=[[105, 200]])]))
p = 100 / 205
want_eff = p + (7 * p * (1 - p) + 1.0) / 100
print("  %-28s -> eff %.4f want %.4f %s" % ("fee+slippage arithmetic", rec["eff_prob"], want_eff,
                                            "PASS" if abs(rec["eff_prob"] - want_eff) < 1e-9 else "FAIL"))
ok &= abs(rec["eff_prob"] - want_eff) < 1e-9
# 2. venue already adjusted (its quote_ts is AFTER the move) -> conservative miss + latency
ok &= run("stale gone / adjusted", MOVE,
          [vrow(105, T0 - 300, T0 - 240), vrow(-130, T0 + 9, T0 + 60, book=[[-130, 500]])],
          "missed_adjusted", {"venue_adjust_latency_s": 9.0})
# 3. suspension / missed updates: nothing observed after the decision time
ok &= run("suspension gap", MOVE, [vrow(105, T0 - 300, T0 - 240)], "missed_gap")
# 3b. an observation exists but far outside the fill window
ok &= run("obs beyond window", MOVE,
          [vrow(105, T0 - 300, T0 - 240), vrow(105, T0 - 300, T0 + 2000)], "missed_gap")
# 4. partial fill: ladder holds only ~$10 at the price
ok &= run("partial fill", MOVE,
          [vrow(105, T0 - 300, T0 + 60, book=[[105, 20]])],
          "partial", {"stake_filled": 20 * (100 / 205)})
# 5. unavailable liquidity: empty ladder
ok &= run("no liquidity", MOVE,
          [vrow(105, T0 - 300, T0 + 60, book=[[105, 0.5]])], "missed_no_liquidity")
# 6. displayed price worse than the pre-move quote. Only constructible when the venue's own
# timestamp is MISSING on the fill observation (otherwise the newest pre-move quote IS the
# reference and the two cannot differ) -- so this doubles as the missing-venue-ts path:
ok &= run("worse price, no venue ts", MOVE,
          [vrow(105, T0 - 300, T0 - 240), vrow(-105, float("nan"), T0 + 60, book=[[-105, 500]])],
          "missed_worse_price")
# 6b. ask already at/above the post-move fair (nothing to capture)
ok &= run("ask >= post fair", MOVE,
          [vrow(-150, T0 - 300, T0 + 60, book=[[-150, 500]])], "missed_worse_price")
# 7. mapping error: unparseable price
ok &= run("mapping error", MOVE, [vrow(float("nan"), T0 - 300, T0 + 60)], "mapping_error")
# 8. in-play exclusion: match already started at decision time
m3 = dict(MOVE, start_ts=T0 + 10)
ok &= run("in-play skip", m3, [vrow(105, T0 - 300, T0 + 60)], "skipped_inplay")
# 9. no market at the venue at all
ok &= run("no market", MOVE, None, "missed_no_market")
# 10. size unknown -> filled but flagged for the sensitivity bucket
ok &= run("size unknown", MOVE, [vrow(105, T0 - 300, T0 + 60)], "filled", {"note": "size_unknown"})

print("\nRESULT: %s" % ("ALL SIM TESTS PASS" if ok else "FAILURES"))
raise SystemExit(0 if ok else 1)
