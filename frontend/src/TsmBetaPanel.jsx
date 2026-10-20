// 🧪 D_REST BETA (2026-10-20, user "where can i see the new model we built").
//
// READ-ONLY window onto the supervised PAPER-PREDICTION beta for the frozen Tennis
// Strength Model (D_rest). It renders a snapshot exported from the beta's append-only
// hash-chained ledger; nothing here computes, marks a card, feeds a lane, or places a bet.
//
// PAPER ONLY: no money, no wager, no odds, no staking anywhere in this panel.
// NO ACCURACY CLAIM: the model's live accuracy has NOT been established. Everything below
// is preliminary and small-sample until a meaningful number of matches settle.
//
// The panel deliberately leads with DATA QUALITY rather than with confidence, because on
// the first pass only 1 of 22 predictions at 90%+ was free of known data problems — 42 of
// 154 fall back to Elo alone because those players have no serve/return history. Showing a
// "top picks" list without that context would be misleading.
import React, { useEffect, useState } from 'react'

const pct = (x) => (x == null ? '—' : (100 * x).toFixed(1) + '%')
const short = (s, n) => (!s ? '—' : (s.length > n ? s.slice(0, n - 1) + '…' : s))

// Start times in PACIFIC (2026-10-20 user ask), matching the rest of the board. The DATE is
// taken in Pacific too, not sliced off the UTC string: a 02:00 UTC match on the 21st is the
// evening of the 20th in PT, and slicing would date it a day late.
const fmtPT = (utc) => {
  if (!utc) return '—'
  const d = new Date(utc)
  if (isNaN(d)) return '—'
  const opt = { timeZone: 'America/Los_Angeles' }
  const day = d.toLocaleString('en-US', { ...opt, month: '2-digit', day: '2-digit' })
  const tm = d.toLocaleTimeString('en-US', { ...opt, hour: 'numeric', minute: '2-digit' }).replace(' ', '')
  return day + ' ' + tm
}
const ptDay = (utc) => {
  if (!utc) return ''
  const d = new Date(utc)
  if (isNaN(d)) return ''
  return d.toLocaleString('en-US', { timeZone: 'America/Los_Angeles', weekday: 'short', month: 'short', day: 'numeric' })
}

const DQ = {
  NO_KNOWN_DATA_ISSUE: { c: '#3fb950', t: 'no known data issue' },
  'DATA-QUALITY-UNVERIFIED': { c: '#d29922', t: 'data-quality unverified' },
}

function Stat({ label, value, sub, color }) {
  return (
    <div style={{ flex: '1 1 130px', minWidth: 130, background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 8, padding: '10px 12px' }}>
      <div className="mono" style={{ fontSize: 9.5, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '.06em', fontWeight: 700 }}>{label}</div>
      <div className="mono" style={{ fontSize: 20, fontWeight: 900, color: color || 'var(--text-primary)', marginTop: 3 }}>{value}</div>
      {sub ? <div className="mono" style={{ fontSize: 9.5, color: 'var(--text-tertiary)', marginTop: 2 }}>{sub}</div> : null}
    </div>
  )
}

export default function TsmBetaPanel() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const [onlyClean, setOnlyClean] = useState(false)
  useEffect(() => {
    fetch('/api/tennis/drest-beta')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status))))
      .then(setD)
      .catch((e) => setErr(String(e.message || e)))
  }, [])

  if (err) {
    return (
      <div className="mono" style={{ padding: 16, fontSize: 12, color: 'var(--text-tertiary)' }}>
        No D_rest beta snapshot on this server ({err}).<br /><br />
        The beta runs as a supervised manual pass. Its snapshot appears here after
        <span style={{ color: 'var(--text-secondary)' }}> tsm_beta.py --run</span> and
        <span style={{ color: 'var(--text-secondary)' }}> tsm_beta_export.py</span> have been run.
      </div>
    )
  }
  if (!d) return <div className="mono" style={{ padding: 16, fontSize: 12, color: 'var(--text-tertiary)' }}>loading…</div>

  const c = d.counts || {}
  const perf = d.performance || {}
  const noneSettled = !perf.scored
  // soonest start first (user ask). Sorted here as well as in the exporter so the order
  // holds whatever order the snapshot happens to arrive in.
  let rows = [...(d.predictions || [])].sort((a, b) => {
    const ta = Date.parse(a.start_utc || '') || 0
    const tb = Date.parse(b.start_utc || '') || 0
    return ta - tb || (b.confidence - a.confidence)
  })
  if (onlyClean) rows = rows.filter((r) => r.data_quality === 'NO_KNOWN_DATA_ISSUE' && !r.invalidated)

  return (
    <div style={{ padding: '8px 2px 40px' }}>
      <div className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.6, marginBottom: 10 }}>
        <b style={{ color: 'var(--text-secondary)' }}>D_REST PAPER BETA</b> — the frozen Tennis Strength Model, predicting real upcoming
        matches with <b>no money, no wager, no odds and no staking</b>. Predictions are written once, before the match, to an
        append-only hash-chained ledger and are never revised. <b style={{ color: '#d29922' }}>Live accuracy has NOT been
        established</b>; every figure here is preliminary. This is separate from the official 16-week prospective trial,
        which is inactive.
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
        <Stat label="predictions" value={c.total ?? '—'} sub={`${c.pending ?? 0} pending · ${c.settled ?? 0} settled`} />
        <Stat label="no known data issue" value={c.no_known_data_issue ?? '—'} color="#3fb950"
              sub={`${c.data_quality_unverified ?? 0} flagged`} />
        <Stat label="90%+ confidence" value={c.ge90 ?? '—'}
              sub={`only ${c.ge90_clean ?? 0} without data flags`} color={c.ge90_clean ? '#3fb950' : '#d29922'} />
        <Stat label="elo-only" value={c.elo_only ?? '—'} color={c.elo_only ? '#d29922' : '#3fb950'}
              sub="no serve/return history" />
        <Stat label="withdrawn" value={c.invalidated ?? 0} color={c.invalidated ? '#f85149' : 'var(--text-primary)'}
              sub="parser bug — excluded" />
      </div>

      {d.market ? (
        <div className="mono" style={{ fontSize: 10.5, color: 'var(--text-tertiary)', lineHeight: 1.6, marginBottom: 8 }}>
          <b style={{ color: 'var(--text-secondary)' }}>Market column:</b> de-vigged price on the side the model picked, attached
          AFTER the prediction was sealed — <b>the model is market-blind and never saw it</b>. Shown for {d.market.matched} of
          {' '}{(d.market.matched || 0) + (d.market.unmatched || 0)}; the rest have no frozen price (ITF events and dates not yet
          logged). Edge is model minus market, <b>context only, not a bet</b>. Withdrawn rows show no market or edge — their
          probability was produced against a player who does not exist, so an "edge" against it would be meaningless.
        </div>
      ) : null}

      {c.invalidated ? (
        <div className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)', background: 'var(--panel)', border: '1px solid #f8514955', borderRadius: 8, padding: '10px 12px', marginBottom: 10 }}>
          <b style={{ color: '#f85149' }}>{c.invalidated} predictions withdrawn.</b> A bug in the schedule parser read the
          placeholder avatar filename as a player, so those fixtures were priced against a player who does not exist — which is
          also why they looked so confident. The parser is fixed and covered by regression tests. The original records are kept
          in the ledger exactly as written and are marked <i>withdrawn</i> below; they are excluded from every figure above and
          from all performance scoring. Nothing was rewritten.
        </div>
      ) : null}

      {noneSettled ? (
        <div className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)', background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 8, padding: '10px 12px', marginBottom: 10 }}>
          <b style={{ color: '#d29922' }}>No matches have settled yet</b> — accuracy, log loss, Brier and the confidence-band
          table appear here once results arrive. Nothing is computed from an unfinished match.
        </div>
      ) : (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
          <Stat label="winner accuracy" value={pct(perf.overall?.accuracy)}
                sub={`${perf.overall?.correct ?? 0}/${perf.overall?.n ?? 0} · PRELIMINARY`} />
          <Stat label="log loss" value={perf.overall?.logloss ?? '—'} sub={`frozen test ${d.performance?.frozen_benchmarks_for_context_only?.overall?.logloss ?? '—'}`} />
          <Stat label="brier" value={perf.overall?.brier ?? '—'} sub={`frozen test ${d.performance?.frozen_benchmarks_for_context_only?.overall?.brier ?? '—'}`} />
          <Stat label="settled" value={perf.scored ?? 0} sub={`${perf.unsettled ?? 0} still pending`} />
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <button onClick={() => setOnlyClean((v) => !v)} className="mono" style={{
          cursor: 'pointer', borderRadius: 6, padding: '4px 10px', fontSize: 10,
          border: `1px solid ${onlyClean ? '#3fb950' : 'var(--line)'}`,
          background: onlyClean ? 'rgba(63,185,80,.14)' : 'transparent',
          color: onlyClean ? '#3fb950' : 'var(--text-secondary)', fontWeight: 700,
        }}>{onlyClean ? '● no known data issue only' : '○ showing all predictions'}</button>
        <span className="mono" style={{ fontSize: 9.5, color: 'var(--text-tertiary)' }}>{rows.length} shown</span>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table className="mono" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
          <thead>
            <tr style={{ color: 'var(--text-tertiary)', textAlign: 'left' }}>
              {['start (PT)', 'tournament', 'surf', 'match', 'model pick', 'prob', 'market', 'edge', 'data quality', 'result'].map((h) => (
                <th key={h} style={{ padding: '5px 7px', borderBottom: '1px solid var(--line)', whiteSpace: 'nowrap', textTransform: 'uppercase', letterSpacing: '.05em' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const dq = DQ[r.data_quality] || { c: 'var(--text-tertiary)', t: r.data_quality }
              const res = r.result
              return (
                <tr key={r.id} style={{ borderBottom: '1px solid var(--line)', opacity: r.invalidated ? 0.45 : 1 }}>
                  <td style={{ padding: '5px 7px', color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }}
                      title={ptDay(r.start_utc) + ' · ' + (r.start_utc || '') + ' UTC'}>{fmtPT(r.start_utc)}</td>
                  <td style={{ padding: '5px 7px', color: 'var(--text-tertiary)' }}>{short(r.tournament, 18)}</td>
                  <td style={{ padding: '5px 7px', color: 'var(--text-tertiary)' }}>{r.surface}</td>
                  <td style={{ padding: '5px 7px', whiteSpace: 'nowrap' }}>{short(r.p1, 20)} <span style={{ color: 'var(--text-tertiary)' }}>vs</span> {short(r.p2, 20)}</td>
                  <td style={{ padding: '5px 7px', fontWeight: 700 }}>{short(r.pick, 20)}</td>
                  <td style={{ padding: '5px 7px', fontWeight: 700, whiteSpace: 'nowrap' }}
                      title={r.ceil ? 'At the frozen calibrator\'s top bin — a ceiling, not a credible 100%.' : ''}>
                    {r.ceil ? 'CEIL' : pct(r.confidence)}
                  </td>
                  <td style={{ padding: '5px 7px', color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }}
                      title={r.market_on_pick == null
                        ? 'no frozen price for this fixture — ITF and not-yet-logged dates usually have none'
                        : 'de-vigged market probability on the SAME side the model picked' + (r.market_vig_pts != null ? ' · ' + r.market_vig_pts + 'pt vig' : '')}>
                    {r.invalidated || r.market_on_pick == null ? '—' : pct(r.market_on_pick)}
                  </td>
                  <td style={{ padding: '5px 7px', whiteSpace: 'nowrap', fontWeight: 700,
                               color: r.edge_vs_market == null ? 'var(--text-tertiary)' : (r.edge_vs_market > 0 ? '#3fb950' : '#f85149') }}
                      title="model probability minus the de-vigged market, on the model's own side. CONTEXT ONLY — the model never saw the price, and this is not a bet.">
                    {r.invalidated || r.edge_vs_market == null ? '—' : ((r.edge_vs_market >= 0 ? '+' : '') + (100 * r.edge_vs_market).toFixed(1) + 'pt')}
                  </td>
                  <td style={{ padding: '5px 7px', color: r.invalidated ? '#f85149' : dq.c, whiteSpace: 'nowrap' }}
                      title={(r.dq_reasons || []).join(', ') || 'no problem detected — this does NOT prove the history is complete'}>
                    {r.invalidated ? 'withdrawn (parser bug)' : (r.data_quality === 'NO_KNOWN_DATA_ISSUE' ? 'ok' : (r.dq_reasons || []).join(', '))}
                  </td>
                  <td style={{ padding: '5px 7px', whiteSpace: 'nowrap', color: !res ? 'var(--text-tertiary)' : (res.status === 'void' ? 'var(--text-tertiary)' : (res.correct ? '#3fb950' : '#f85149')) }}>
                    {r.invalidated ? 'withdrawn' : (!res ? 'pending' : (res.status === 'void' ? 'void' : (res.correct ? '✓ ' + short(res.winner, 16) : '✗ ' + short(res.winner, 16))))}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="mono" style={{ fontSize: 9.5, color: 'var(--text-tertiary)', marginTop: 10, lineHeight: 1.6 }}>
        all start times are PACIFIC, soonest first · hover a time for the UTC value<br />
        snapshot {d.generated_utc} · model {d.model?.version} · artifact {String(d.model?.artifact_sha256 || '').slice(0, 16)} · refit {String(d.model?.refit)}<br />
        ledger head {String(d.ledger?.prediction_chain_head || '').slice(0, 32)} · {d.ledger?.predictions} immutable prediction records<br />
        "no known data issue" means no problem was DETECTED — it does not prove a player's recent match history is complete.
      </div>
    </div>
  )
}
