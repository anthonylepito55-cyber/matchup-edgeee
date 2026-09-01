import React, { useEffect, useState } from 'react'

// Model E's real forward BETTING record (see backend/model_e.py + /api/model-e-track-record):
// every bet that was frozen pre-game with a side, a best book price and a quarter-Kelly stake,
// graded once the game is final. Shows ROI on logged stakes AND flat 1u ROI (so sizing can't
// flatter pick quality), hit rate vs what the market implied, and CLV -- whether the line moved
// toward us between first flag and close, the earliest tell of a real edge. Below it, the
// walk-forward validation the model shipped with, kept visibly separate from the live record.
export default function ModelETrackRecord() {
  const [record, setRecord] = useState(null)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    fetch('/api/model-e-track-record').then(r => r.json()).then(setRecord).catch(() => {})
  }, [])

  if (!record) return null
  const v = record.validation
  const chosen = v && v.candidates && v.candidates[v.chosen]
  const pct = x => (x == null ? '—' : `${(x * 100).toFixed(1)}%`)
  const signed = (x, suffix = '') => (x == null ? '—' : `${x > 0 ? '+' : ''}${x}${suffix}`)
  const order = ['underdog', 'favorite', 'all']

  return (
    <div style={{
      marginTop: 12, padding: '14px 18px', borderRadius: 8,
      background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))',
      border: '1px solid var(--line)', boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
        <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          model E — betting record
        </span>
        {record.total > 0 && (
          <button onClick={() => setExpanded(e => !e)} style={{
            marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--amber)', fontSize: 10,
            fontFamily: 'var(--font-mono)', textDecoration: 'underline', opacity: 0.8, cursor: 'pointer',
          }}>
            {expanded ? 'hide' : 'show'} bets
          </button>
        )}
      </div>

      {record.total === 0 ? (
        <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 8 }}>
          no settled Model E bets yet — bets are frozen pre-game and graded once each game is final.
        </div>
      ) : (
        <>
          <div className="mono" style={{ fontSize: 9, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginTop: 10 }}>
            real forward record — since {record.since} · {record.total} bets
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'auto repeat(6, auto)', gap: '4px 18px', marginTop: 6, fontSize: 11 }} className="mono">
            <span style={{ color: 'var(--text-tertiary)' }}>type</span>
            <span style={{ color: 'var(--text-tertiary)' }}>n</span>
            <span style={{ color: 'var(--text-tertiary)' }}>hit</span>
            <span style={{ color: 'var(--text-tertiary)' }}>mkt implied</span>
            <span style={{ color: 'var(--text-tertiary)' }}>ROI (kelly)</span>
            <span style={{ color: 'var(--text-tertiary)' }}>ROI (flat 1u)</span>
            <span style={{ color: 'var(--text-tertiary)' }}>avg CLV</span>
            {order.filter(t => record.by_type[t]).map(t => {
              const b = record.by_type[t]
              return (
                <React.Fragment key={t}>
                  <span style={{ color: 'var(--text-secondary)' }}>{t}</span>
                  <span>{b.n}</span>
                  <span style={{ color: b.edge_pts > 0 ? '#3fb950' : 'var(--text-secondary)' }}>{pct(b.hit_rate)}</span>
                  <span>{pct(b.market_implied)}</span>
                  <span style={{ color: b.roi_pct > 0 ? '#3fb950' : b.roi_pct < 0 ? '#f85149' : undefined }}>{signed(b.roi_pct, '%')}</span>
                  <span style={{ color: b.flat_roi_pct > 0 ? '#3fb950' : b.flat_roi_pct < 0 ? '#f85149' : undefined }}>{signed(b.flat_roi_pct, '%')}</span>
                  <span>{b.avg_clv_pts == null ? '—' : `${signed(b.avg_clv_pts, 'pts')} (${pct(b.clv_positive_share)} +)`}</span>
                </React.Fragment>
              )
            })}
          </div>
        </>
      )}

      {record.baseball_leg && (
        <div className="mono" style={{ fontSize: 11, marginTop: 10 }}>
          <span style={{ color: 'var(--text-tertiary)' }}>market-blind leg vs Model A (same {record.baseball_leg.n} settled games): </span>
          E-baseball {pct(record.baseball_leg.e_baseball_hit)} · Model A {pct(record.baseball_leg.model_a_hit)}
          {v && v.baseball_leg && (
            <span style={{ color: 'var(--text-tertiary)' }}>
              {' '}· backtest AUC {v.baseball_leg.baseball_leg.auc.toFixed(4)} vs A {v.baseball_leg.model_a_same_folds.auc.toFixed(4)}
            </span>
          )}
        </div>
      )}

      {chosen && (
        <>
          <div className="mono" style={{
            fontSize: 9, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em',
            marginTop: 14, borderTop: '1px dashed var(--line)', paddingTop: 10,
          }}>
            walk-forward validation — {v.n_games} games, calibration "{v.chosen}" (fold-retrained, not the live model, at fair de-vigged odds)
          </div>
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 6 }} className="mono">
            {['underdog', 'favorite', 'all'].filter(t => chosen.betting_fair_odds[t]).map(t => {
              const b = chosen.betting_fair_odds[t]
              return (
                <span key={t} style={{ fontSize: 11 }}>
                  <span style={{ color: 'var(--text-tertiary)' }}>{t}: </span>
                  {pct(b.hit_rate)}{b.market_implied != null ? ` vs ${pct(b.market_implied)} implied` : ''} · ROI {signed(b.roi_fair_odds_pct, '%')} (n={b.n})
                </span>
              )
            })}
          </div>
        </>
      )}

      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 10 }}>
        Model E shares the market-aware model's probabilities (a post-hoc calibration layer was tested on held-out
        folds and did not help, so none is applied). What it adds is the bet: it only fires when it disagrees with
        the market by a validated margin, prices the side at the best available book, sizes at quarter-Kelly, and
        remembers the first price it saw so CLV can be graded. Backtest ROI above is at fair odds — real books
        charge vig, and live edges usually come in smaller than backtests; the top table is the number that counts.
      </div>

      {expanded && record.recent && (
        <div style={{ marginTop: 12, borderTop: '1px solid var(--line)', paddingTop: 10 }}>
          {record.recent.map((r, i) => (
            <div key={i} className="mono" style={{
              fontSize: 11, display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8,
              padding: '3px 0', borderBottom: '1px solid var(--line)',
            }}>
              <span style={{ color: 'var(--text-tertiary)', width: 80 }}>{r.date}</span>
              <span style={{ width: 80 }}>{r.matchup}</span>
              <span style={{ width: 120 }}>{r.type} · {r.side} {r.best_price > 0 ? '+' : ''}{r.best_price}</span>
              <span style={{ width: 60 }}>{r.stake_units}u</span>
              <span style={{ width: 70, color: r.won ? '#3fb950' : '#f85149' }}>{r.won ? 'WON' : 'LOST'} {signed(r.profit_units)}</span>
              <span style={{ width: 90, color: 'var(--text-tertiary)' }}>CLV {r.clv == null ? '—' : signed((r.clv * 100).toFixed(1), 'pts')}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
