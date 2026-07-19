import React, { useEffect, useState } from 'react'

export default function ModelStatus() {
  const [status, setStatus] = useState(null)

  useEffect(() => {
    fetch('/api/model/status').then(r => r.json()).then(setStatus).catch(() => {})
  }, [])

  if (!status) return null

  return (
    <div style={{
      marginTop: 24, padding: '16px 20px', borderRadius: 8,
      background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))',
      border: '1px solid var(--line)', boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
      display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap',
    }}>
      <StatusDot trained={status.trained} />
      {status.trained ? (
        <div style={{ display: 'flex', flexWrap: 'wrap' }}>
          <Metric label="brier" value={status.metrics?.brier_score?.toFixed(3)} />
          <Divider />
          <Metric label="log loss" value={status.metrics?.log_loss?.toFixed(3)} />
          <Divider />
          <Metric label="auc" value={status.metrics?.auc?.toFixed(3)} highlight />
          <Divider />
          <Metric label="train rows" value={status.metrics?.n_train} />
        </div>
      ) : (
        <span className="mono" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
          No trained model yet — no predictions available. Run <code style={{ color: 'var(--amber)' }}>python build_training_data.py</code> then train, or POST /api/retrain.
        </span>
      )}
    </div>
  )
}

function StatusDot({ trained }) {
  return (
    <span style={{
      width: 8, height: 8, borderRadius: '50%', marginRight: 14,
      background: trained ? 'var(--edge-pos)' : 'var(--text-tertiary)',
      display: 'inline-block', flexShrink: 0,
      animation: trained ? 'pulse-glow 2.4s ease-in-out infinite' : 'none',
    }} />
  )
}

function Divider() {
  return <span style={{ width: 1, background: 'var(--line)', margin: '2px 20px' }} />
}

function Metric({ label, value, highlight }) {
  return (
    <div>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {label}
      </div>
      <div className="mono" style={{
        fontSize: 16, color: highlight ? 'var(--amber)' : 'var(--text-primary)', fontWeight: 700, marginTop: 2,
      }}>
        {value ?? '—'}
      </div>
    </div>
  )
}
