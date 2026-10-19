"""PHASE 5 monitoring extension (approval item 3) -- DISPLAY ONLY.

Extends tennis_leadlag.summary() and the Dog-tab view with the requested reporting: fill rate
over ALL qualifying signals, miss reasons, the full per-signal timestamp chain (source stamp,
receive, decision, observation, quote age), prices/fees/slippage/net, CLV and cumulative paper
ROI, and counts of timestamp-questionable observations. Nothing in the signal-recording path,
the fill rule, or CONFIG is touched -- the patch asserts CONFIG_SHA is unchanged afterwards, so
the running Period A (config 3a252d79dd5e1da1) cannot be affected.
"""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, "tennis_leadlag.py")
s = io.open(P, encoding="utf-8").read()
assert "fill_rate_pct" not in s, "already patched"


def rep(old, new):
    global s
    assert s.count(old) == 1, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


rep('''    out["signals"] = int(len(sig))
    out["by_outcome"] = sig["outcome"].value_counts().to_dict()
    fills = sig[sig["outcome"].isin(["filled", "partial"])]
    out["fills"] = int(len(fills))''',
    '''    out["signals"] = int(len(sig))
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
            out["theoretical_edge_pp_mean"] = round(100 * float(edge.mean()), 2)''')

rep('''    out["recent"] = sig.sort_values("src_move_ts").tail(20)[
        ["signal_id", "matchup", "league", "move_pp", "outcome", "fill_price_am",
         "stake_filled", "note"]].to_dict("records")
    return out''',
    '''    # full per-signal audit chain for the view (approval item 3): every timestamp separately,
    # prices, fees, slippage-inclusive effective price, settlement and CLV where present
    cols = ["signal_id", "matchup", "league", "selection", "move_pp", "fair_pre", "fair_post",
            "src_move_ts", "recv_ts", "decision_ts", "fill_obs_ts", "quote_age_s",
            "pre_prob", "fill_price_am", "fill_prob", "fee_pp", "eff_prob", "stake_filled",
            "venue", "outcome", "note", "won", "pnl_usd", "clv_pp"]
    have = [c for c in cols if c in sig.columns]
    rec = sig.sort_values("src_move_ts").tail(25)[have]
    out["recent"] = json_safe = rec.where(rec.notna(), None).to_dict("records")
    out["slippage_pp"] = CONFIG["slippage_pp"]
    return out''')

io.open(P, "w", encoding="utf-8", newline="").write(s)
import py_compile
py_compile.compile(P, doraise=True)
import importlib
import tennis_leadlag as LL
importlib.reload(LL)
assert LL.CONFIG_SHA == "3a252d79dd5e1da1", "CONFIG CHANGED: %s" % LL.CONFIG_SHA
print("summary() extended; CONFIG_SHA unchanged: %s" % LL.CONFIG_SHA)

# ---------------------------------------------------------------- the view
F = os.path.normpath(os.path.join(HERE, "..", "frontend", "src", "DogPicksPanel.jsx"))
t = io.open(F, encoding="utf-8").read()
assert "fill_rate_pct" not in t, "view already patched"
OLDV = '''        {ll.adjust_latency_s ? <> {'\\u00b7'} venue adjust latency median {ll.adjust_latency_s.median}s p90 {ll.adjust_latency_s.p90}s (n{ll.adjust_latency_s.n})</> : null}
      </div>'''
NEWV = '''        {ll.adjust_latency_s ? <> {'\\u00b7'} venue adjust latency median {ll.adjust_latency_s.median}s p90 {ll.adjust_latency_s.p90}s (n{ll.adjust_latency_s.n})</> : null}
        {ll.fill_rate_pct != null ? <> {'\\u00b7'} fill rate <b>{ll.fill_rate_pct}%</b> of all signals ({ll.fill_rate_of_evaluable_pct}% of evaluable)</> : null}
        {ll.theoretical_edge_pp_mean != null ? <> {'\\u00b7'} theoretical edge at fill {ll.theoretical_edge_pp_mean}pp</> : null}
        {ll.ts_questionable ? <> {'\\u00b7'} ts-questionable: no-stamp {ll.ts_questionable.no_venue_stamp}, neg-age {ll.ts_questionable.negative_quote_age}</> : null}
      </div>'''
assert t.count(OLDV) == 1
t = t.replace(OLDV, NEWV)
OLDR = '''      {(ll.recent || []).slice().reverse().map((r, i) => (
        <div key={i} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', padding: '5px 12px', borderRadius: 7, border: '1px solid var(--line)', color: 'var(--text-secondary)' }}>
          <span>{r.matchup}</span><span style={{ color: 'var(--text-tertiary)' }}>{r.league}</span>
          <span>{'+' + Math.round(10 * r.move_pp) / 10}pp move</span>
          <span style={{ marginLeft: 'auto', fontWeight: 700,
            color: r.outcome === 'filled' || r.outcome === 'partial' ? '#3fb950' : 'var(--text-tertiary)' }}>
            {r.outcome}{r.fill_price_am != null && (r.outcome === 'filled' || r.outcome === 'partial') ? ' @ ' + r.fill_price_am : ''}
          </span>
        </div>
      ))}'''
NEWR = '''      {(ll.recent || []).slice().reverse().map((r, i) => {
        const ts = (x) => (x == null ? '\\u2014' : new Date(1000 * x).toISOString().slice(11, 19))
        return (
          <div key={i} style={{ padding: '5px 12px', borderRadius: 7, border: '1px solid var(--line)', color: 'var(--text-secondary)' }}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <span>{r.matchup}</span><span style={{ color: 'var(--text-tertiary)' }}>{r.league} {'\\u00b7'} {r.venue}</span>
              <span>{'+' + Math.round(10 * r.move_pp) / 10}pp ({Math.round(100 * r.fair_pre)}{'\\u2192'}{Math.round(100 * r.fair_post)}%)</span>
              <span style={{ marginLeft: 'auto', fontWeight: 700,
                color: r.outcome === 'filled' || r.outcome === 'partial' ? '#3fb950' : r.won === false ? '#f85149' : 'var(--text-tertiary)' }}>
                {r.outcome}{r.fill_price_am != null && (r.outcome === 'filled' || r.outcome === 'partial') ? ' @ ' + r.fill_price_am : ''}
                {r.pnl_usd != null ? ' \\u00b7 $' + Math.round(100 * r.pnl_usd) / 100 : ''}
              </span>
            </div>
            <div style={{ fontSize: 9.5, color: 'var(--text-tertiary)', marginTop: 2 }}>
              move {ts(r.src_move_ts)} {'\\u2192'} recv {ts(r.recv_ts)} {'\\u2192'} decide {ts(r.decision_ts)} {'\\u2192'} obs {ts(r.fill_obs_ts)}
              {r.quote_age_s != null ? ' \\u00b7 quote age ' + Math.round(10 * r.quote_age_s) / 10 + 's' : ' \\u00b7 quote age \\u2014'}
              {r.pre_prob != null ? ' \\u00b7 pre ' + Math.round(1000 * r.pre_prob) / 10 + '%' : ''}
              {r.eff_prob != null ? ' \\u00b7 eff ' + Math.round(1000 * r.eff_prob) / 10 + '% (fee ' + (Math.round(10 * r.fee_pp) / 10) + 'pp + slip)' : ''}
              {r.clv_pp != null ? ' \\u00b7 CLV ' + Math.round(100 * r.clv_pp) / 100 + 'pp' : ''}
              {r.note ? ' \\u00b7 ' + r.note : ''}
            </div>
          </div>
        )
      })}'''
assert t.count(OLDR) == 1
t = t.replace(OLDR, NEWR)
io.open(F, "w", encoding="utf-8", newline="").write(t)
print("view extended")
print("RESULT: OK")
