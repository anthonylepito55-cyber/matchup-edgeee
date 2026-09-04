import React, { useEffect, useState } from 'react'

// Daily profit tab (user request 2026-09-04): day-by-day P&L at a flat dollar stake per bet
// (default $20), green or red, with a running cumulative — real settled bets only, graded at
// each bet's logged best price. Primary series = bets the CURRENT ruleset keeps (post-9/4
// thresholds + omega-co-fire filter, retro-applied server-side); the as-placed series is shown
// muted beside it so nothing is hidden.
export default function DailyProfitView() {
  const [data, setData] = useState(null)
  const [stake, setStake] = useState(() => {
    try { const v = localStorage.getItem('dp_stake'); return v == null ? 20 : (Number(v) || 20) } catch { return 20 }
  })
  useEffect(() => { try { localStorage.setItem('dp_stake', String(stake || 0)) } catch {} }, [stake])
  useEffect(() => {
    fetch('/api/daily-profit').then(r => r.json()).then(setData).catch(() => {})
  }, [])

  if (!data) return <div className="mono" style={{ marginTop: 20, fontSize: 12, color: 'var(--text-tertiary)' }}>loading daily record…</div>
  const days = data.days || []
  if (!days.length) return <div className="mono" style={{ marginTop: 20, fontSize: 12, color: 'var(--text-tertiary)' }}>no settled bets yet.</div>

  const usd = u => `${u < 0 ? '−' : '+'}$${Math.abs(u * stake).toFixed(0)}`
  let cum = 0
  const rows = days.map(d => { cum += d.flat_cur; return { ...d, cum } })
  const maxAbs = Math.max(...rows.map(r => Math.abs(r.flat_cur)), 0.001)
  const green = rows.filter(r => r.flat_cur > 0).length
  const red = rows.filter(r => r.flat_cur < 0).length
  const totCur = rows.length ? rows[rows.length - 1].cum : 0
  const totAll = days.reduce((s, d) => s + d.flat_all, 0)
  const nCur = days.reduce((s, d) => s + d.n_cur, 0)
  const nAll = days.reduce((s, d) => s + d.n_all, 0)

  return (
    <div style={{ marginTop: 16, padding: '16px 20px', borderRadius: 8, border: '1px solid var(--line)', background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, flexWrap: 'wrap' }}>
        <span className="mono" style={{ fontSize: 13, color: 'var(--amber)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700 }}>
          daily profit <span style={{ fontSize: 10, color: 'var(--text-tertiary)', letterSpacing: 0, textTransform: 'none', fontWeight: 400 }}>· real settled bets at a flat stake · current-rules series (as-placed shown muted)</span>
        </span>
        <span className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)', marginLeft: 'auto' }}>
          $ per bet <input value={stake || ''} inputMode="numeric"
            onChange={ev => setStake(Number(String(ev.target.value).replace(/[^0-9]/g, '')) || 0)}
            style={{ width: 48, background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 4, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: 11, padding: '2px 6px' }} />
        </span>
      </div>

      <div className="mono" style={{ display: 'flex', gap: 24, flexWrap: 'wrap', margin: '10px 0 4px', fontSize: 12 }}>
        <span><span style={{ color: 'var(--text-tertiary)' }}>total (current rules): </span><b style={{ color: totCur >= 0 ? '#3fb950' : '#f85149' }}>{usd(totCur)}</b> on {nCur} bets</span>
        <span><span style={{ color: 'var(--text-tertiary)' }}>days: </span><b style={{ color: '#3fb950' }}>{green} green</b> · <b style={{ color: '#f85149' }}>{red} red</b>{rows.length - green - red ? ` · ${rows.length - green - red} flat` : ''}</span>
        <span style={{ color: 'var(--text-tertiary)' }}>as placed (old rules incl. filtered bets): <b style={{ color: totAll >= 0 ? '#3fb950' : '#f85149' }}>{usd(totAll)}</b> on {nAll}</span>
      </div>

      <div className="mono" style={{ display: 'grid', gridTemplateColumns: '90px 60px 70px 90px 1fr 100px', gap: 10, fontSize: 9, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', padding: '8px 6px 4px', borderBottom: '1px solid var(--line)' }}>
        <span>date</span><span>bets</span><span>record</span><span>day P&amp;L</span><span></span><span>cumulative</span>
      </div>
      {[...rows].reverse().map(r => (
        <div key={r.date} className="mono" style={{ display: 'grid', gridTemplateColumns: '90px 60px 70px 90px 1fr 100px', gap: 10, alignItems: 'center', fontSize: 12, padding: '5px 6px', borderBottom: '1px solid var(--line)' }}>
          <span style={{ color: 'var(--text-secondary)' }}>{r.date.slice(5)}</span>
          <span style={{ color: 'var(--text-tertiary)' }}>{r.n_cur}{r.n_all !== r.n_cur ? <span style={{ opacity: 0.5 }}> /{r.n_all}</span> : ''}</span>
          <span style={{ color: 'var(--text-tertiary)' }}>{r.w_cur}-{r.n_cur - r.w_cur}</span>
          <span style={{ color: r.flat_cur > 0 ? '#3fb950' : r.flat_cur < 0 ? '#f85149' : 'var(--text-tertiary)', fontWeight: 700 }}>{r.n_cur ? usd(r.flat_cur) : '—'}</span>
          <span style={{ display: 'flex', alignItems: 'center' }}>
            <span style={{ height: 8, borderRadius: 2, width: `${Math.max(2, 100 * Math.abs(r.flat_cur) / maxAbs)}%`, maxWidth: '100%', background: r.flat_cur >= 0 ? 'rgba(63,185,80,0.55)' : 'rgba(248,81,73,0.55)' }} />
          </span>
          <span style={{ color: r.cum >= 0 ? '#3fb950' : '#f85149' }}>{usd(r.cum)}</span>
        </div>
      ))}

      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 10, lineHeight: 1.5 }}>
        Every row is real settled bets graded at their logged best prices, ${stake || 0} flat per bet. The primary series applies
        TODAY&apos;S ruleset (fav ≥3 pts, dog flip ≥6 pts, Ω-co-fire filter) to the whole history so the line tracks what following
        the current slip would have done; the muted as-placed figure includes the bets those filters have since removed. Days swing
        hard at this stake — a 7-bet day at $20 routinely lands anywhere between −$140 and +$150 — so judge the cumulative line,
        not any single day. Updates automatically as bets settle.
      </div>
    </div>
  )
}
