import React, { useEffect, useState } from 'react'

// F5 (first-5-innings) model forward record -- see backend/model_f5.py + /api/model-f5-track-record.
// Top: the model's F5 pick accuracy vs the F5 market's own pick on the same frozen games (the
// honest "is it competitive with its market" read). Middle: graded F5 bets, which only exist once
// the walk-forward validation against real F5 prices showed positive ROI (bets_enabled). Bottom:
// that validation, kept visibly separate from the live record.
export default function ModelF5TrackRecord() {
  const [record, setRecord] = useState(null)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    fetch('/api/model-f5-track-record').then(r => r.json()).then(setRecord).catch(() => {})
  }, [])

  if (!record) return null
  const v = record.validation
  const pct = x => (x == null ? '—' : `${(x * 100).toFixed(1)}%`)
  const signed = (x, suffix = '') => (x == null ? '—' : `${x > 0 ? '+' : ''}${x}${suffix}`)
  const b = record.bets || {}
  const vb = v && v.betting_fair_odds
  const vm = v && v.market_subset

  return (
    <div style={{
      marginTop: 12, padding: '14px 18px', borderRadius: 8,
      background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))',
      border: '1px solid var(--line)', boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
        <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          F5 model — first 5 innings {record.bets_enabled ? '· bets ON' : '· bets off (validation gate)'}
        </span>
        {b.n > 0 && (
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
          no settled F5 predictions yet — graded from the linescore once each game is final (tied after 5 = push).
        </div>
      ) : (
        <div className="mono" style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 8, fontSize: 11 }}>
          <span><span style={{ color: 'var(--text-tertiary)' }}>F5 games graded: </span>{record.total} ({record.decided} decided)</span>
          <span><span style={{ color: 'var(--text-tertiary)' }}>model pick hit: </span>{pct(record.model_hit_rate)}</span>
          <span><span style={{ color: 'var(--text-tertiary)' }}>F5 market pick hit: </span>{pct(record.market_hit_rate)}{record.market_n ? ` (n=${record.market_n})` : ''}</span>
          {b.n > 0 && (
            <span>
              <span style={{ color: 'var(--text-tertiary)' }}>bets: </span>{b.n} · hit {pct(b.hit_rate)} · ROI{' '}
              <span style={{ color: b.roi_pct > 0 ? '#3fb950' : b.roi_pct < 0 ? '#f85149' : undefined }}>{signed(b.roi_pct, '%')}</span>
              {b.pushes ? ` · ${b.pushes} push` : ''}
            </span>
          )}
        </div>
      )}

      {v && (
        <>
          <div className="mono" style={{
            fontSize: 9, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em',
            marginTop: 14, borderTop: '1px dashed var(--line)', paddingTop: 10,
          }}>
            walk-forward validation — {v.n_games} decided-after-5 games (fold-retrained, not the live model)
          </div>
          <div className="mono" style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 6, fontSize: 11 }}>
            <span><span style={{ color: 'var(--text-tertiary)' }}>model AUC / Brier: </span>{v.all.auc.toFixed(3)} / {v.all.brier.toFixed(4)}</span>
            {vm && (
              <span>
                <span style={{ color: 'var(--text-tertiary)' }}>vs F5 market (n={vm.model.n}): </span>
                model {vm.model.auc.toFixed(3)} / {vm.model.brier.toFixed(4)} · market {vm.market.auc.toFixed(3)} / {vm.market.brier.toFixed(4)}
              </span>
            )}
            {vb && ['underdog', 'favorite', 'all'].filter(t => vb[t]).map(t => (
              <span key={t}>
                <span style={{ color: 'var(--text-tertiary)' }}>{t}: </span>
                {pct(vb[t].hit_rate)} vs {pct(vb[t].market_implied)} implied · ROI {signed(vb[t].roi_fair_odds_pct, '%')} (n={vb[t].n})
              </span>
            ))}
          </div>
        </>
      )}

      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 10 }}>
        The F5 line prices the two starters almost directly, which is what this app&apos;s features measure, in a
        thinner market than the full game. Predictions are always shown; bets are only produced once the validation
        above shows positive ROI at fair odds on a real sample, and are then priced at the best available F5 book and
        sized at quarter-Kelly (same layer as Model E). Ties after 5 innings are pushes.
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
              <span style={{ width: 70, color: r.push ? 'var(--text-tertiary)' : r.won ? '#3fb950' : '#f85149' }}>
                {r.push ? 'PUSH' : r.won ? 'WON' : 'LOST'} {r.push ? '' : signed(r.profit_units)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
