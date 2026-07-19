import React from 'react'

/**
 * The dashboard's signature element: a horizontal tug-of-war bar showing
 * the model's home-team win probability as a fill, with a small tick
 * mark showing where the sportsbook market sits (if odds were entered).
 * The gap between the fill edge and the tick IS the betting edge —
 * made visible, not just stated as a number. Filled in each team's own
 * color rather than a generic app accent, so the bar reads as "these two
 * teams" rather than "a progress bar."
 */
export default function ProbabilityBar({ awayLabel, homeLabel, homeProb, marketHomeProb, awayColor, homeColor }) {
  const homePct = homeProb != null ? homeProb * 100 : 50
  const marketPct = marketHomeProb != null ? marketHomeProb * 100 : null

  return (
    <div>
      <div style={{
        position: 'relative', height: 28, borderRadius: 6, overflow: 'hidden',
        background: 'var(--panel-raised)', border: '1px solid var(--line)',
      }}>
        {/* away portion (left) */}
        <div style={{
          position: 'absolute', left: 0, top: 0, bottom: 0,
          width: `${100 - homePct}%`,
          background: `linear-gradient(90deg, ${awayColor}55, ${awayColor}22)`,
        }} />
        {/* home portion (right) */}
        <div style={{
          position: 'absolute', right: 0, top: 0, bottom: 0,
          width: `${homePct}%`,
          background: `linear-gradient(90deg, ${homeColor}22, ${homeColor}66)`,
        }} />
        {/* center divider at model's split point */}
        <div style={{
          position: 'absolute', left: `${100 - homePct}%`, top: 0, bottom: 0,
          width: 2, background: 'var(--text-primary)', opacity: 0.5,
        }} />
        {/* market tick, if available */}
        {marketPct != null && (
          <div title="Market-implied probability" style={{
            position: 'absolute', left: `${100 - marketPct}%`, top: -3, bottom: -3,
            width: 2, background: 'var(--amber)',
            boxShadow: '0 0 0 1px var(--ink)',
          }} />
        )}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6 }}>
        <span className="mono" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
          <span style={{ display: 'inline-block', width: 7, height: 7, borderRadius: '50%', background: awayColor, marginRight: 5 }} />
          {awayLabel} <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{(100 - homePct).toFixed(0)}%</span>
        </span>
        {marketPct != null && (
          <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
            market: {marketPct.toFixed(0)}% home
          </span>
        )}
        <span className="mono" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
          <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{homePct.toFixed(0)}%</span> {homeLabel}
          <span style={{ display: 'inline-block', width: 7, height: 7, borderRadius: '50%', background: homeColor, marginLeft: 5 }} />
        </span>
      </div>
    </div>
  )
}
