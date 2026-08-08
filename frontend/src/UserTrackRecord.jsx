import React, { useEffect, useState } from 'react'

export default function UserTrackRecord() {
  const [record, setRecord] = useState(null)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    fetch('/api/user-track-record').then(r => r.json()).then(setRecord).catch(() => {})
  }, [])

  if (!record || record.total === 0) return null

  const userPct = (record.user_accuracy * 100).toFixed(1)
  const modelPct = (record.model_accuracy * 100).toFixed(1)
  const userAhead = record.user_accuracy > record.model_accuracy

  return (
    <div style={{
      marginTop: 12, padding: '14px 18px', borderRadius: 8,
      background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))',
      border: '1px solid var(--line)', boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
        <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          your picks vs the model
        </span>
        <Metric label="your record" value={`${record.user_correct}/${record.total}`} highlight={userAhead} />
        <Metric label="your accuracy" value={`${userPct}%`} highlight={userAhead} />
        <Metric label="model, same games" value={`${record.model_correct}/${record.total} (${modelPct}%)`} highlight={!userAhead} />
        <button onClick={() => setExpanded(e => !e)} style={{
          marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--amber)', fontSize: 10,
          fontFamily: 'var(--font-mono)', textDecoration: 'underline', opacity: 0.8, cursor: 'pointer',
        }}>
          {expanded ? 'hide' : 'show'} recent
        </button>
      </div>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 6 }}>
        Your locked-in picks (made before each game started) vs the model's own pick, both graded against
        the same real outcomes on the same games — a genuine forward test, not a backtest reconstruction.
      </div>

      {expanded && (
        <div style={{ marginTop: 12, borderTop: '1px solid var(--line)', paddingTop: 10 }}>
          {record.recent.map((r, i) => (
            <div key={i} className="mono" style={{
              fontSize: 11, display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8,
              padding: '4px 0',
            }}>
              <span style={{ color: 'var(--text-secondary)' }}>{r.date} {r.matchup}</span>
              <span>
                <span style={{ color: r.user_correct ? 'var(--edge-pos)' : 'var(--edge-neg)' }}>you: {r.picked_team} {r.user_correct ? 'hit' : 'miss'}</span>
                {' · '}
                <span style={{ color: r.model_correct ? 'var(--edge-pos)' : 'var(--edge-neg)' }}>model: {r.model_pick} {r.model_correct ? 'hit' : 'miss'}</span>
                {' · '}
                <span style={{ color: 'var(--text-tertiary)' }}>actual: {r.actual_winner}</span>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Metric({ label, value, highlight }) {
  return (
    <div>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}
      </div>
      <div className="mono" style={{ fontSize: 14, color: highlight ? 'var(--edge-pos)' : 'var(--text-primary)', fontWeight: 600 }}>
        {value ?? '—'}
      </div>
    </div>
  )
}
