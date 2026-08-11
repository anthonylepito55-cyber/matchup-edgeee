import React, { useEffect, useState } from 'react'

export default function CLVTrackRecord() {
  const [record, setRecord] = useState(null)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    fetch('/api/clv-track-record').then(r => r.json()).then(setRecord).catch(() => {})
  }, [])

  if (!record || record.total === 0) return null

  const bucketLabel = t => t === 0 ? 'any disagreement' : `edge ≥ ${Math.round(t * 100)}pts`

  return (
    <div style={{
      marginTop: 12, padding: '14px 18px', borderRadius: 8,
      background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))',
      border: '1px solid var(--line)', boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
        <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          model vs market (real CLV)
        </span>
        <button onClick={() => setExpanded(e => !e)} style={{
          marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--amber)', fontSize: 10,
          fontFamily: 'var(--font-mono)', textDecoration: 'underline', opacity: 0.8, cursor: 'pointer',
        }}>
          {expanded ? 'hide' : 'show'} recent
        </button>
      </div>
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 8 }}>
        {record.buckets.map(b => (
          <Metric
            key={b.threshold}
            label={bucketLabel(b.threshold)}
            value={b.accuracy != null ? `${(b.accuracy * 100).toFixed(1)}% (${b.correct}/${b.games})` : '—'}
            highlight={b.accuracy != null && b.accuracy > 0.55}
          />
        ))}
      </div>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 6 }}>
        Real forward record of the model's pick vs the market's own price at prediction time, graded
        against actual outcomes once each game is final — not a backtest. Small buckets (especially the
        higher edge thresholds) grow slowly; treat early reads as noise, not a verdict.
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
                <span style={{ color: 'var(--text-tertiary)' }}>
                  model {(r.model_home_win_prob * 100).toFixed(0)}% vs market {(r.market_home_prob * 100).toFixed(0)}%
                  {' '}(edge {r.edge >= 0 ? '+' : ''}{(r.edge * 100).toFixed(0)}pts)
                </span>
                {' · '}
                <span style={{ color: r.correct ? 'var(--edge-pos)' : 'var(--edge-neg)' }}>
                  {r.correct ? 'hit' : 'miss'}
                </span>
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
        {value}
      </div>
    </div>
  )
}
