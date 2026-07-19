import React, { useEffect, useState } from 'react'

export default function StrikeoutTrackRecord() {
  const [record, setRecord] = useState(null)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    fetch('/api/strikeout-track-record').then(r => r.json()).then(setRecord).catch(() => {})
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
          strikeout props track record
        </span>
        <Metric label="record" value={`${record.correct}/${record.total}`} />
        <Metric label="hit rate" value={`${pct}%`} />
        <Metric label="avg error" value={`${record.mae} K`} />
        {record.pushes > 0 && <Metric label="pushes" value={record.pushes} />}
        <button onClick={() => setExpanded(e => !e)} style={{
          marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--amber)', fontSize: 10,
          fontFamily: 'var(--font-mono)', textDecoration: 'underline', opacity: 0.8, cursor: 'pointer',
        }}>
          {expanded ? 'hide' : 'show'} recent
        </button>
      </div>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 6 }}>
        Real over/under calls vs actual strikeouts once each start is final — a blind forward test, logged before
        the game starts. Grows slowly; a handful of starts is still mostly noise.
      </div>

      {expanded && (
        <div style={{ marginTop: 12, borderTop: '1px solid var(--line)', paddingTop: 10 }}>
          {record.recent.map((r, i) => (
            <div key={i} className="mono" style={{
              fontSize: 11, display: 'flex', justifyContent: 'space-between',
              padding: '4px 0', color: r.correct == null ? 'var(--text-tertiary)' : r.correct ? 'var(--edge-pos)' : 'var(--edge-neg)',
            }}>
              <span>{r.date} {r.pitcher} ({r.matchup})</span>
              <span>
                {r.call} {r.line} &middot; predicted {r.predicted_k} &middot; actual {r.actual_k}
                {' '}&middot; {r.correct == null ? 'push' : r.correct ? 'hit' : 'miss'}
              </span>
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
