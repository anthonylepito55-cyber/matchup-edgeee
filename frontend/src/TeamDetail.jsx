import React, { useEffect, useState } from 'react'

/**
 * Team-level snapshot — opened by clicking a team chip on a game card. Unlike
 * PitcherDetail, this is a single current-season snapshot, not a trend chart:
 * team quality (bullpen, defense, offense) is treated as a season-long
 * constant everywhere else in this app, so there's no per-game history built
 * to chart across time here.
 */
export default function TeamDetail({ teamAbbr, teamColor, onClose }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetch(`/api/team/${teamAbbr}`)
      .then(r => {
        if (!r.ok) throw new Error(`API returned ${r.status}`)
        return r.json()
      })
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [teamAbbr])

  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 100, backdropFilter: 'blur(2px)',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '40px 16px', overflowY: 'auto',
      animation: 'fade-up 0.15s ease-out',
    }}>
      <div className="card-enter" onClick={e => e.stopPropagation()} style={{
        background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12,
        padding: '22px 24px', maxWidth: 520, width: '100%', borderTop: `3px solid ${teamColor || 'var(--amber)'}`,
        boxShadow: '0 16px 48px rgba(0,0,0,0.5)',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>
              {teamAbbr}
            </div>
            {data?.season && (
              <div className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2 }}>
                {data.season} season snapshot
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
            loading team snapshot…
          </div>
        )}
        {error && (
          <div style={{ color: 'var(--edge-neg)', fontSize: 12, marginTop: 16 }}>Couldn't load team data ({error})</div>
        )}

        {data && !loading && (
          <>
            <Section title="Offense">
              <StatRow label="Team wOBA" value={data.batting.woba} />
              <StatRow label="K rate" value={data.batting.k_pct} suffix="%" />
              <StatRow label="wOBA vs LHP" value={data.batting.woba_vs_lhp} />
              <StatRow label="wOBA vs RHP" value={data.batting.woba_vs_rhp} />
            </Section>
            <Section title="Bullpen">
              <StatRow label="Full-pen FIP" value={data.bullpen.fip} />
              <StatRow label="Full-pen ERA" value={data.bullpen.era} />
              <StatRow label="Closer/setup FIP" value={data.bullpen.high_leverage_fip} />
              <StatRow label="Innings, last 3 days" value={data.bullpen.recent_fatigue_ip_last_3d} suffix=" IP" />
            </Section>
            <Section title="Defense & park">
              <StatRow label="BABIP allowed" value={data.defense.babip_against} />
              <StatRow label="Park factor" value={data.park_factor} suffix={data.park_factor > 1 ? ' (hitter-friendly)' : data.park_factor < 1 ? ' (pitcher-friendly)' : ' (neutral)'} />
            </Section>
          </>
        )}
      </div>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div style={{ marginTop: 18 }}>
      <div className="mono" style={{
        fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase',
        letterSpacing: '0.05em', marginBottom: 6, borderBottom: '1px solid var(--line)', paddingBottom: 4,
      }}>
        {title}
      </div>
      {children}
    </div>
  )
}

function StatRow({ label, value, suffix = '' }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
      <span className="mono" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{label}</span>
      <span className="mono" style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 600 }}>
        {value != null ? `${value}${suffix}` : '—'}
      </span>
    </div>
  )
}
