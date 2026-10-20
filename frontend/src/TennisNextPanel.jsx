// 🧬 TENNIS NEXT (2026-10-19, user "1" — new tab on the existing site).
//
// READ-ONLY window onto the isolated Experiment 2 paper-trading research project
// (backend/research/tennis_next). Nothing here fires a mark, feeds a lane, changes a pick,
// or places a bet. The data is a snapshot exported from the frozen append-only paper ledger;
// it refreshes only when a supervised scoring/settlement pass runs.
//
// Two independent targets (owner doctrine 2026-10-19):
//   TARGET A — 90%+ high-confidence hit rate (Strategy A).
//   TARGET B — positive net ROI after Kalshi/Polymarket fees + slippage (Strategy B, PRIMARY).
//   Strategy C = both at once. Profitability is never sacrificed for an artificial win rate:
//   high confidence alone can never place a paper bet.
import React, { useEffect, useState } from 'react'

const fmtP = (x) => (x == null ? '—' : (100 * x).toFixed(1) + '%')
const fmtRoi = (x) => (x == null ? '—' : (x >= 0 ? '+' : '') + (100 * x).toFixed(1) + '%')

function Card({ title, big, sub, color }) {
  return (
    <div style={{ flex: '1 1 150px', minWidth: 150, background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 8, padding: '10px 12px' }}>
      <div className="mono" style={{ fontSize: 9.5, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>{title}</div>
      <div className="mono" style={{ fontSize: 20, fontWeight: 900, color: color || 'var(--text-primary)', marginTop: 3 }}>{big}</div>
      <div className="mono" style={{ fontSize: 9.5, color: 'var(--text-tertiary)', marginTop: 2 }}>{sub}</div>
    </div>
  )
}

export default function TennisNextPanel() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(false)
  useEffect(() => {
    fetch('/api/tennis/next').then(r => (r.ok ? r.json() : Promise.reject())).then(setD).catch(() => setErr(true))
  }, [])
  if (err) return <div className="mono" style={{ padding: 16, fontSize: 11, color: 'var(--text-tertiary)' }}>No Tennis-Next snapshot on this server yet.</div>
  if (!d) return <div className="mono" style={{ padding: 16, fontSize: 11, color: 'var(--text-tertiary)' }}>loading…</div>
  const A = d.strategies.A, B = d.strategies.B, C = d.strategies.C
  const statusTxt = (r) => {
    if (r.status === 'pending') return ['pending', 'var(--text-tertiary)']
    if (r.status === 'void') return ['void', '#8b949e']
    const w = r.status === 'p1_won' ? 1 : 2
    if (r.selB) return r.selB.side === w ? ['WON ✓', '#3fb950'] : ['LOST ✗', '#f85149']
    return [(w === 1 ? r.players[0] : r.players[1]).split(' ').slice(-1)[0] + ' won', 'var(--text-secondary)']
  }
  return (
    <div style={{ padding: '10px 4px' }}>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-secondary)', lineHeight: 1.6, maxWidth: 940, marginBottom: 10 }}>
        <b>Experiment 2 — zero-stake prospective paper test of frozen Model E</b> (isolated research;
        view-only; nothing here bets or feeds the board). Predictions freeze ≥30 min pre-match at
        observed Kalshi/Polymarket prices with fees + slippage; selections never change after freezing.
        Snapshot: {d.generated_utc} · protocol {d.protocol_sha8} · model {d.artifact_sha8} · {d.ledger_events} ledger events.
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
        <Card title="Target A · 90% hit (strategy A)" big={A.settled ? fmtP(A.hit) : '—'}
          sub={`${A.settled}/${A.selections} settled · goal ≥90% · conf ≥92% only`}
          color={A.hit == null ? undefined : A.hit >= 0.9 ? '#3fb950' : '#d29922'} />
        <Card title="Target B · net ROI (strategy B, primary)" big={B.settled ? fmtRoi(B.roi) : '—'}
          sub={`${B.settled}/${B.selections} settled · EV≥3pp after fees · goal >0`}
          color={B.roi == null ? undefined : B.roi > 0 ? '#3fb950' : '#f85149'} />
        <Card title="Both · strategy C" big={C.settled ? fmtRoi(C.roi) : C.selections ? 'pending' : '0 picks'}
          sub={`${C.settled}/${C.selections} settled · A ∧ B same side`} />
        <Card title="Cohort" big={`${d.pending} pending`}
          sub={`${d.predictions} frozen predictions · ${d.settled} settled · ${d.days} day(s)`} />
      </div>

      {d.models && d.models.settled_scored ? (
        <div className="mono" style={{ fontSize: 10.5, color: 'var(--text-tertiary)', background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 8, padding: '10px 12px', margin: '2px 0 10px' }}>
          <div style={{ color: 'var(--text-secondary)', fontWeight: 700, marginBottom: 5 }}>
            MODEL ACCURACY ON THE {d.models.settled_scored} SETTLED PREDICTIONS
          </div>
          <table style={{ borderCollapse: 'collapse', fontSize: 10.5 }}>
            <thead><tr style={{ color: 'var(--text-tertiary)' }}>
              {['', 'winners', 'accuracy', 'log loss', 'brier'].map((h) => (
                <th key={h} style={{ textAlign: 'left', padding: '2px 12px 4px 0', fontWeight: 600 }}>{h}</th>))}
            </tr></thead>
            <tbody>
              {[['Model E (cohort model)', d.models.E], ['Model A', d.models.A], ['market price', d.models.market]]
                .filter(([, m]) => m).map(([lab, m]) => (
                <tr key={lab}>
                  <td style={{ padding: '2px 12px 2px 0', color: 'var(--text-secondary)' }}>{lab}</td>
                  <td style={{ padding: '2px 12px 2px 0' }}>{m.correct}/{m.n}</td>
                  <td style={{ padding: '2px 12px 2px 0', fontWeight: 700 }}>{(100 * m.acc).toFixed(1)}%</td>
                  <td style={{ padding: '2px 12px 2px 0' }}>{m.logloss}</td>
                  <td style={{ padding: '2px 12px 2px 0' }}>{m.brier}</td>
                </tr>))}
            </tbody>
          </table>
          <div style={{ marginTop: 6, lineHeight: 1.6 }}>
            E agreed with the price on <b>{d.models.agree_with_market} of {d.models.settled_scored}</b>
            {d.models.disagreements ? <> · on the {d.models.disagreements} disagreement(s) E was right {d.models.E_right_on_disagreements}</> : <> · <b>no disagreements yet</b>, so all three score identically on winners by construction and only calibration separates them</>}.
            <br /><b style={{ color: '#d29922' }}>PRELIMINARY</b> — far too few settled matches to rank these models.
          </div>
        </div>
      ) : null}

      <table className="mono" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
        <thead>
          <tr style={{ color: 'var(--text-tertiary)', textAlign: 'left' }}>
            {['start (UTC)', 'match', 'lg', 'model', 'market', 'picks', 'status'].map(h => (
              <th key={h} style={{ padding: '4px 6px', borderBottom: '1px solid var(--line)', fontWeight: 700 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {d.rows.map((r, i) => {
            const [st, sc] = statusTxt(r)
            return (
              <tr key={i} style={{ borderBottom: '1px solid var(--line)' }}>
                <td style={{ padding: '4px 6px', color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }}>{r.start_utc}</td>
                <td style={{ padding: '4px 6px', color: 'var(--text-primary)' }}>
                  {r.players[0]} <span style={{ color: 'var(--text-tertiary)' }}>v</span> {r.players[1]}
                  {r.tournament ? <span style={{ color: 'var(--text-tertiary)', fontSize: 9 }}> · {r.tournament}</span> : null}
                </td>
                <td style={{ padding: '4px 6px', color: 'var(--text-tertiary)' }}>{r.league}</td>
                <td style={{ padding: '4px 6px' }} title="frozen Model E P1 win probability (shadow in parens)">
                  {fmtP(r.pE)}<span style={{ color: 'var(--text-tertiary)', fontSize: 9 }}> ({fmtP(r.shadow)})</span>
                </td>
                <td style={{ padding: '4px 6px', color: 'var(--text-secondary)' }} title="de-vigged Pinnacle P1 probability at freeze">{fmtP(r.mkt)}</td>
                <td style={{ padding: '4px 6px' }}>
                  {r.selA ? <span title="Strategy A: confidence ≥92%" style={{ color: '#d29922', fontWeight: 700, marginRight: 6 }}>A</span> : null}
                  {r.selB ? (
                    <span title={`Strategy B: +EV at ${r.selB.venue} — side ${r.selB.side}, implied ${(100 * r.selB.implied).toFixed(1)}%, frozen EV ${(100 * r.selB.ev).toFixed(1)}%`}
                      style={{ color: '#3fb950', fontWeight: 700, marginRight: 6 }}>
                      B·{r.selB.venue === 'kalshi' ? 'K' : 'PM'} {fmtRoi(r.selB.ev)}
                    </span>
                  ) : null}
                  {r.selC ? <span title="Strategy C: A and B on the same side" style={{ color: '#58a6ff', fontWeight: 700 }}>C</span> : null}
                  {!r.selA && !r.selB && !r.selC ? <span style={{ color: 'var(--text-tertiary)' }}>no bet</span> : null}
                </td>
                <td style={{ padding: '4px 6px', color: sc, fontWeight: st === 'pending' ? 400 : 700, whiteSpace: 'nowrap' }}>{st}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="mono" style={{ fontSize: 9.5, color: 'var(--text-tertiary)', marginTop: 12, lineHeight: 1.7, maxWidth: 940 }}>
        Market-only control (same rules, de-vigged Pinnacle instead of the model): A {d.controls.A.selections} ·
        B {d.controls.B.selections} · C {d.controls.C.selections} selections. Paper prices are observed
        top-of-book quotes, never guaranteed fills. Descriptive early numbers only — no profitability
        claim before the preregistered checkpoint (≥300 settled B selections across ≥8 weeks).
      </div>
    </div>
  )
}
