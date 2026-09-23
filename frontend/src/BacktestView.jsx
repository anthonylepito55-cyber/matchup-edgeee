import React, { useEffect, useState } from 'react'

// BET FOR BACKTESTED (2026-09-23, user ask): the picks that are VALIDATED by the 2026-season
// walk-forward OOF backtest (both halves positive), not the live-log-sliced marker bands. Each
// of today's menu bets is tagged with the backtest ROI of its cell as the HEADLINE number, and
// the live record of that cell is shown GRAY beside it ("how it's been doing live"). Same bets
// as the slip -- reframed backtest-first, because the backtest is the out-of-sample truth.
// Primary cell = the game's headline (the highest-backtest cell it clears). Grade splits are
// primary for dog flips; agreement filters are shown as secondary tags below.
function classify(g, bt) {
  const bet = g.model_e_bet
  if (!bet || bet.stake_units == null) return null
  const edge = bet.edge || 0
  const mkt = bet.market_prob || 0
  const sh = bet.side_is_home
  const sideOf = v => (v == null ? null : (sh ? v : 1 - v))
  const aSide = sideOf(g.prediction && g.prediction.home_win_prob)
  const hSide = sideOf(g.model_e_baseball_prob)
  const bSide = sideOf(g.market_model_prob)
  const eligible = []
  const tags = []
  if (bet.type === 'underdog' && edge >= 0.06) {
    eligible.push('dog_flip6')
    if (bet.dog_grade === 'A') eligible.push('dog_flipA')
    if (bet.dog_grade === 'B') eligible.push('dog_flipB')
    if (mkt >= 0.40 && mkt < 0.48) tags.push('flip_dog4048')
    if (aSide != null && aSide >= 0.52) { tags.push('flip_A_agree'); if (hSide != null && hSide >= 0.52) tags.push('flip_AH13') }
  }
  if (bet.type === 'favorite' && edge >= 0.03) {
    eligible.push('fav3')
    if (edge >= 0.08) eligible.push('fav8')
    if (mkt >= 0.60 && edge >= 0.06) eligible.push('heavy_fav6')
    if (mkt < 0.60 && edge < 0.06) eligible.push('slim_fav36')
    if (hSide != null && hSide >= 0.5) tags.push('fav3_h13')
    if (bSide != null && bSide >= 0.5) tags.push('fav3_B')
  }
  if (!eligible.length) return null
  const primary = eligible.reduce((best, k) => (bt && bt[k] && (!best || bt[k].roi > bt[best].roi) ? k : best), null) || eligible[0]
  return { cell: primary, tags }
}

export default function BacktestView({ games }) {
  const [bt, setBt] = useState(null)
  useEffect(() => {
    fetch('/api/model-e-track-record').then(r => r.json()).then(d => setBt(d.backtest_menu || null)).catch(() => {})
  }, [])
  const green = '#3fb950'
  const gray = '#8b949e'

  const picks = (games || []).map(g => {
    const cls = classify(g, bt)
    return cls ? { g, bet: g.model_e_bet, cell: cls.cell, tags: cls.tags } : null
  }).filter(Boolean).sort((a, b) => (bt ? (bt[b.cell]?.roi || 0) - (bt[a.cell]?.roi || 0) : 0))

  return (
    <div>
      <div style={{ margin: '16px 0 6px', padding: '12px 18px', borderRadius: 8, border: `1px solid ${green}55`, background: `linear-gradient(180deg, ${green}0d, var(--panel))` }}>
        <div className="mono" style={{ fontSize: 11, color: green, fontWeight: 700, letterSpacing: '0.04em' }}>
          BET FOR BACKTESTED — the validated menu <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>· picks whose 2026-season walk-forward OOF backtest is positive in BOTH halves (the out-of-sample test the live-sliced marker bands fail). Backtest ROI is the headline; <span style={{ color: gray }}>gray = how the cell has done LIVE</span>, for reference only.</span>
        </div>
      </div>

      {/* All validated cells (both-halves-positive season backtest), grouped dog / favorite */}
      {bt && ['dog', 'fav'].map(grp => (
        <div key={grp} style={{ margin: '10px 0 6px' }}>
          <div className="mono" style={{ fontSize: 9, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{grp === 'dog' ? 'dog-flip family' : 'favorite family'}</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {Object.entries(bt).filter(([, c]) => c.group === grp).sort((a, b) => b[1].roi - a[1].roi).map(([k, c]) => (
              <div key={k} className="mono" style={{ padding: '8px 12px', borderRadius: 6, border: `1px solid ${c.primary ? green + '55' : 'var(--line)'}`, background: 'var(--panel)', fontSize: 11, minWidth: 178 }}>
                <div style={{ color: green, fontWeight: 700 }}>{c.label}</div>
                <div style={{ color: 'var(--text-secondary)' }}>backtest {c.roi > 0 ? '+' : ''}{c.roi}% ({c.n}) · {c.halves}</div>
                <div style={{ color: gray }}>live {c.live_roi_pct != null ? `${c.live_roi_pct > 0 ? '+' : ''}${c.live_roi_pct}% (${c.live_n})` : `— (${c.live_n})`}</div>
              </div>
            ))}
          </div>
        </div>
      ))}

      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700, paddingBottom: 4, borderBottom: '1px solid var(--line)' }}>
        today's backtested picks ({picks.length})
      </div>

      {picks.length === 0 ? (
        <div className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)', padding: '14px 0' }}>
          no games clear a validated menu cell today — the honest empty slate, same as the slip.
        </div>
      ) : picks.map(({ g, bet, cell, tags }) => {
        const c = bt && bt[cell]
        const price = bet.best_price > 0 ? `+${bet.best_price}` : `${bet.best_price}`
        const live = g.status && !['Scheduled', 'Pre-Game', 'Warmup'].includes(g.status)
        return (
          <div key={`bt-${g.game_pk}`} className="mono" style={{ display: 'grid', gridTemplateColumns: '1fr 220px 150px 90px', gap: 10, alignItems: 'center', fontSize: 12, padding: '8px 6px', borderBottom: '1px solid var(--line)', background: `${green}0a`, borderLeft: `3px solid ${green}` }}>
            <span>
              <span style={{ color: 'var(--text-secondary)' }}>{g.away_team_abbr}@{g.home_team_abbr} — </span>
              <b style={{ color: green }}>{bet.side} {price}</b>
              {bet.best_book ? <span style={{ color: 'var(--text-tertiary)' }}> @ {bet.best_book}</span> : null}
              <span style={{ color: 'var(--text-tertiary)' }}> · {bet.stake_units}u</span>
              {(tags || []).filter(t => bt && bt[t]).map(t => (
                <span key={t} style={{ color: '#3fb950', opacity: 0.7, fontSize: 10, marginLeft: 5 }} title={`Also clears a validated cell: ${bt[t].label} — backtest ${bt[t].roi > 0 ? '+' : ''}${bt[t].roi}% (${bt[t].n}), live ${bt[t].live_roi_pct != null ? (bt[t].live_roi_pct > 0 ? '+' : '') + bt[t].live_roi_pct + '%' : '—'}. Extra corroboration.`}>✓{bt[t].n}</span>
              ))}
            </span>
            <span style={{ color: green, fontWeight: 700 }} title={c ? `${c.label}: 2026-season OOF backtest ${c.roi > 0 ? '+' : ''}${c.roi}% on ${c.n} (both halves ${c.halves}) — validated out-of-sample.` : ''}>
              {c ? c.label : cell} · BT {c ? `${c.roi > 0 ? '+' : ''}${c.roi}%` : ''}
            </span>
            <span style={{ color: gray }} title="LIVE record of this cell's settled bets so far — reference only; the backtest is the validated number.">
              live {c && c.live_roi_pct != null ? `${c.live_roi_pct > 0 ? '+' : ''}${c.live_roi_pct}% (${c.live_n})` : `— (${c ? c.live_n : 0})`}
            </span>
            <span style={{ color: live ? 'var(--amber)' : 'var(--text-tertiary)' }}>{live ? `${g.status} (frozen)` : (g.game_time_utc ? new Date(g.game_time_utc).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : 'pre-game')}</span>
          </div>
        )
      })}

      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 10, lineHeight: 1.5 }}>
        These are the same bets as the slip on the "bet for profit" tab — reframed to lead with the backtest, which is the
        out-of-sample truth. The colored marker bands over there (purple / green / cyan) look great on live ROI but are NEGATIVE
        in the season backtest because they were sliced from the live log itself; they are excluded here on purpose. Backtest
        numbers are dated 2026-09-23 (2026-season walk-forward OOF); live numbers update as games settle.
      </div>
    </div>
  )
}
