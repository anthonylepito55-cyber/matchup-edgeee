import React, { useEffect, useState } from 'react'

/**
 * Full-season start-by-start trend for one pitcher — opened by clicking a
 * pitcher's name on a game card. A hand-rolled FIP line chart (no charting
 * library in this project) plus a per-start table with the Statcast
 * process stats (whiff%/chase%/hard-hit%) the season snapshot elsewhere
 * in the app can't show a trend for.
 */
export default function PitcherDetail({ pitcherId, pitcherName, onClose }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetch(`/api/pitcher/${pitcherId}`)
      .then(r => {
        if (!r.ok) throw new Error(`API returned ${r.status}`)
        return r.json()
      })
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [pitcherId])

  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 100, backdropFilter: 'blur(2px)',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '40px 16px', overflowY: 'auto',
      animation: 'fade-up 0.15s ease-out',
    }}>
      <div className="card-enter" onClick={e => e.stopPropagation()} style={{
        background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12,
        padding: '22px 24px', maxWidth: 640, width: '100%', boxShadow: '0 16px 48px rgba(0,0,0,0.5)',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>
              {data?.name || pitcherName || 'Pitcher'}
            </div>
            {data?.hand && (
              <div className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2 }}>
                throws {data.hand === 'L' ? 'left' : data.hand === 'R' ? 'right' : data.hand} &middot; {data.season} season
              </div>
            )}
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: '1px solid var(--line)', borderRadius: 6,
            color: 'var(--text-secondary)', fontSize: 12, padding: '5px 10px', fontFamily: 'var(--font-mono)',
          }}>
            close
          </button>
        </div>

        {loading && (
          <div className="mono" style={{ color: 'var(--text-tertiary)', padding: '30px 0', textAlign: 'center', fontSize: 12 }}>
            loading season log…
          </div>
        )}
        {error && (
          <div style={{ color: 'var(--edge-neg)', fontSize: 12, marginTop: 16 }}>Couldn't load pitcher data ({error})</div>
        )}

        {data && !loading && (
          <>
            <div style={{ display: 'flex', gap: 20, marginTop: 16 }}>
              <StatBadge label="whiff%" value={data.season_whiff_pct} />
              <StatBadge label="chase%" value={data.season_chase_pct} />
              <StatBadge label="hard-hit%" value={data.season_hard_hit_pct} />
              <StatBadge label="starts" value={data.starts.length} suffix="" />
            </div>

            {data.starts.length > 0 ? (
              <>
                <FipTrendChart starts={data.starts} />
                <StartsTable starts={data.starts} />
              </>
            ) : (
              <div className="mono" style={{ color: 'var(--text-tertiary)', fontSize: 12, marginTop: 20 }}>
                No starts on record this season.
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function StatBadge({ label, value, suffix = '%' }) {
  return (
    <div>
      <div className="mono" style={{ fontSize: 9, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}
      </div>
      <div className="mono" style={{ fontSize: 15, color: 'var(--text-primary)', fontWeight: 600, marginTop: 2 }}>
        {value != null ? `${value}${suffix}` : '—'}
      </div>
    </div>
  )
}

function FipTrendChart({ starts }) {
  const width = 560
  const height = 130
  const padX = 10
  const padY = 16
  const fips = starts.map(s => s.fip).filter(f => f != null)
  if (fips.length < 2) return null

  const maxFip = Math.max(...fips, 4)
  const minFip = Math.min(...fips, 0)
  const range = Math.max(maxFip - minFip, 1)
  const stepX = (width - padX * 2) / (starts.length - 1)

  const points = starts.map((s, i) => {
    const x = padX + i * stepX
    const y = padY + (1 - (s.fip - minFip) / range) * (height - padY * 2)
    return { x, y, fip: s.fip, date: s.date }
  })
  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')

  return (
    <div style={{ marginTop: 20 }}>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
        FIP by start (lower is better)
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
        <path d={linePath} fill="none" stroke="var(--amber)" strokeWidth="2" />
        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r="3" fill="var(--amber)">
            <title>{`${p.date}: ${p.fip.toFixed(2)} FIP`}</title>
          </circle>
        ))}
      </svg>
    </div>
  )
}

function StartsTable({ starts }) {
  const reversed = [...starts].reverse()
  return (
    <div style={{ marginTop: 16, maxHeight: 260, overflowY: 'auto', borderTop: '1px solid var(--line)', paddingTop: 8 }}>
      <div className="mono" style={{
        display: 'grid', gridTemplateColumns: '70px 1fr 50px 40px 40px 50px 60px 60px',
        gap: 6, fontSize: 9, color: 'var(--text-tertiary)', textTransform: 'uppercase',
        letterSpacing: '0.03em', padding: '2px 0', position: 'sticky', top: 0, background: 'var(--panel)',
      }}>
        <span>date</span><span>opp</span><span>IP</span><span>K</span><span>BB</span><span>FIP</span><span>whiff%</span><span>chase%</span>
      </div>
      {reversed.map((s, i) => (
        <div key={i} className="mono" style={{
          display: 'grid', gridTemplateColumns: '70px 1fr 50px 40px 40px 50px 60px 60px',
          gap: 6, fontSize: 11, color: 'var(--text-secondary)', padding: '4px 0',
          borderTop: i > 0 ? '1px solid rgba(255,255,255,0.03)' : 'none',
        }}>
          <span>{s.date?.slice(5)}</span>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.opponent || '—'}</span>
          <span>{s.ip}</span>
          <span style={{ color: 'var(--text-primary)' }}>{s.k}</span>
          <span>{s.bb}</span>
          <span style={{ color: s.fip <= 3.5 ? 'var(--edge-pos)' : s.fip >= 5 ? 'var(--edge-neg)' : 'var(--text-primary)' }}>
            {s.fip.toFixed(2)}
          </span>
          <span>{s.whiff_pct != null ? `${s.whiff_pct}%` : '—'}</span>
          <span>{s.chase_pct != null ? `${s.chase_pct}%` : '—'}</span>
        </div>
      ))}
    </div>
  )
}
