import React, { useEffect, useState } from 'react'

export default function TrackRecord() {
  const [record, setRecord] = useState(null)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    fetch('/api/track-record').then(r => r.json()).then(setRecord).catch(() => {})
  }, [])

  if (!record || record.total === 0) return null

  const pct = (record.accuracy * 100).toFixed(1)

  return (
    <div style={{
      marginTop: 12, padding: '14px 18px', borderRadius: 8,
      background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))',
      border: '1px solid var(--line)', boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
        <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          live track record
        </span>
        <Metric label="record" value={`${record.correct}/${record.total}`} />
        <Metric label="accuracy" value={`${pct}%`} />
        <Metric label="brier" value={record.brier?.toFixed(3)} />
        <button onClick={() => setExpanded(e => !e)} style={{
          marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--amber)', fontSize: 10,
          fontFamily: 'var(--font-mono)', textDecoration: 'underline', opacity: 0.8, cursor: 'pointer',
        }}>
          {expanded ? 'hide' : 'show'} recent
        </button>
      </div>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 6 }}>
        Real predictions vs actual final scores — separate from the backtest metrics above. Grows slowly; a handful of games is still mostly noise.
      </div>

      {expanded && (
        <div style={{ marginTop: 12, borderTop: '1px solid var(--line)', paddingTop: 10 }}>
          {record.recent.map((r, i) => (
            <div key={i} className="mono" style={{
              fontSize: 11, display: 'flex', justifyContent: 'space-between',
              padding: '4px 0', color: r.correct ? 'var(--edge-pos)' : 'var(--edge-neg)',
            }}>
              <span>{r.date} {r.matchup}</span>
              <span>{(r.home_win_prob * 100).toFixed(0)}% home &middot; {r.away_score}-{r.home_score} &middot; {r.correct ? 'hit' : 'miss'}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Metric({ label, value }) {
  return (
    <div>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}
      </div>
      <div className="mono" style={{ fontSize: 14, color: 'var(--text-primary)', fontWeight: 600 }}>
        {value ?? '—'}
      </div>
    </div>
  )
}
