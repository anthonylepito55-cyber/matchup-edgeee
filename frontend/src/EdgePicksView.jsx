import { useEffect, useState } from 'react'

// EDGE PICKS tab (user call 9/6): every pick from the three live-positive structures on one
// page, so taking them is one glance instead of reading chips across the profit tab.
//   1. ★ winning-profile menu bets — E alone (+26.5% live/30) or 1-2 models agreeing WITH
//      both pitching edges (+29.5%/33)
//   2. other PEN+WHIP ✓ menu bets (+21.0%/55 overall) — the breakeven-cell ones, trim-sized
//   3. ⭐ golden contrarian — the model fades a both-edge team (27-19/+17.3%; DOG wing +32.4%)
// All records shown are LIVE and update as bets settle. HONESTY: these are the best-supported
// live structures, not proven edges — every cell still sits inside a ±25-70pt noise band, and
// the combined record needs ~200+ bets to separate from luck. Co-fired/demoted bets never
// appear here even when their profile looks good.
export default function EdgePicksView({ games }) {
  const [e, setE] = useState(null)
  useEffect(() => {
    fetch('/api/model-e-track-record').then(r => r.json()).then(setE).catch(() => {})
  }, [])
  const bs = (e && e.by_signal) || {}
  const chip = (key, fallback) => {
    const a = bs[key]
    return a && a.flat_roi_pct != null ? `${a.flat_roi_pct > 0 ? '+' : ''}${a.flat_roi_pct.toFixed(1)}% (${a.n})` : fallback
  }
  const pwf = e && e.pen_whip_fade
  const pwfDog = pwf && pwf.dog

  const dv = (h, a) => {
    if (h == null || a == null) return null
    const d = p => (p > 0 ? 1 + p / 100 : 1 + 100 / Math.abs(p))
    const ih = 1 / d(h), ia = 1 / d(a)
    return ih / (ih + ia)
  }

  const bets = (games || []).filter(g => g.model_e_bet && g.model_e_bet.stake_units != null)
    .map(g => ({ g, bet: g.model_e_bet }))
  const demoted = x => x.bet.omega_cofired
  const profileOf = x => {
    const b = x.bet
    if (b.ours_avail !== 3 || b.ours_agree == null) return null
    if (b.ours_agree === 0) return 'e_alone'
    if (b.pen_whip == null) return null
    if (b.ours_agree === 3) return b.pen_whip ? 'consensus_pw' : 'consensus_nopw'
    return b.pen_whip ? 'agree_pw' : 'agree_nopw'
  }
  const winners = bets.filter(x => !demoted(x) && ['e_alone', 'agree_pw'].includes(profileOf(x)))
  const pwOnly = bets.filter(x => !demoted(x) && !winners.includes(x) && x.bet.pen_whip === true)
  const golden = (games || []).map(g => {
    const t = g.pen_whip_team
    const p = g.prediction && g.prediction.home_win_prob
    if (!t || p == null) return null
    const pTeam = t === 'home' ? p : 1 - p
    if (pTeam >= 0.5) return null
    const mkt = g.live_odds ? dv(g.live_odds.home, g.live_odds.away) : null
    const mktTeam = mkt == null ? null : (t === 'home' ? mkt : 1 - mkt)
    return {
      g,
      take: t === 'home' ? g.home_team_abbr : g.away_team_abbr,
      other: t === 'home' ? g.away_team_abbr : g.home_team_abbr,
      pTeam, isDog: mktTeam != null && mktTeam < 0.5,
    }
  }).filter(Boolean).sort((a, b) => (b.isDog ? 1 : 0) - (a.isDog ? 1 : 0))

  const time = g => (['Scheduled', 'Pre-Game', 'Warmup'].includes(g.status)
    ? (g.game_time_utc ? new Date(g.game_time_utc).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : 'pre-game')
    : `${g.status} (frozen)`)

  const section = (title, color, note, rows) => (
    <div style={{ marginTop: 14, padding: '14px 18px', borderRadius: 8, border: `1px solid ${color}`, background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))' }}>
      <div className="mono" style={{ fontSize: 10, color, textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>
        {title} <span style={{ color: 'var(--text-tertiary)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>{note}</span>
      </div>
      {rows.length === 0
        ? <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 6 }}>none on the current slate.</div>
        : rows}
    </div>
  )

  const betRow = ({ g, bet }, color, tag) => (
    <div key={`ep-${g.game_pk}`} className="mono" style={{ display: 'grid', gridTemplateColumns: '1fr 220px 90px 110px', gap: 10, alignItems: 'center', fontSize: 12, padding: '7px 6px', borderBottom: '1px solid var(--line)', borderLeft: `3px solid ${color}`, background: 'rgba(255,255,255,0.02)' }}>
      <span>
        <span style={{ color: 'var(--text-secondary)' }}>{g.away_team_abbr}@{g.home_team_abbr} — </span>
        <b style={{ color }}>{bet.side} {bet.best_price > 0 ? '+' : ''}{bet.best_price}</b>
        {bet.best_book ? <span style={{ color: 'var(--text-tertiary)' }}> @ {bet.best_book}</span> : null}
        <span style={{ color: 'var(--text-tertiary)' }}> · {bet.type}{bet.dog_grade ? ` ${bet.dog_grade}` : ''}</span>
      </span>
      <span style={{ color, fontWeight: 700 }}>{tag}</span>
      <span style={{ fontWeight: 700 }}>{bet.stake_units}u</span>
      <span style={{ color: 'var(--text-tertiary)' }}>{time(g)}</span>
    </div>
  )

  const nWin = winners.length, nPw = pwOnly.length, nGold = golden.length
  return (
    <div>
      <div className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)', margin: '16px 0 4px', lineHeight: 1.5 }}>
        <b style={{ color: 'var(--amber)' }}>EDGE PICKS</b> — every pick from the three structures that are live-positive on real settled bets,
        gathered on one page. These are the best-SUPPORTED patterns, not proven edges: each record below is real and updates as
        bets settle, but all still sit inside their noise bands (~±25-70 pts) and need 200+ bets to separate from luck.
        Stakes shown are the menu&apos;s quarter-Kelly units (1u = 1% of bankroll). Ω-co-fired bets never appear here.
      </div>

      {section(`★ winning-profile bets (${nWin})`, '#3fb950',
        `— E alone ${chip('profile_e_alone', '+26.5% (30)')} or 1-2 models agreeing + both pitching edges ${chip('profile_agree_pw', '+29.5% (33)')} · full menu stake`,
        winners.map(x => betRow(x, '#3fb950', profileOf(x) === 'e_alone' ? `E ALONE ${chip('profile_e_alone', '')}` : `AGREE+EDGES ${chip('profile_agree_pw', '')}`)))}

      {section(`PEN+WHIP ✓, breakeven profile (${nPw})`, 'var(--amber)',
        `— both pitching edges (${chip('pen_whip_yes', '+21.0% (55)')} overall) but full model consensus caps it (${chip('profile_consensus_pw', '-0.9% (9)')}) · trim to ~half size`,
        pwOnly.map(x => betRow(x, '#ffb627', `PEN+WHIP ✓ ${chip('profile_consensus_pw', '')}`)))}

      {/* Excluded-but-close (user challenge 9/6, "shouldn't PIT be under pen+whip"): Ω-co-fired
          bets that DO hold both pitching edges. The shipped co-fire demotion outranks this —
          its live damage concentrates in the no-edges half (omega_same_pw_no), while the
          with-edges half has been near breakeven. Shown grayed with both live records so the
          demotion stays honest and testable; if the with-edges cell turns clearly positive at
          ~25 bets, the demotion rule gets refined. */}
      {(() => {
        const excl = bets.filter(x => demoted(x) && x.bet.pen_whip === true)
        if (!excl.length) return null
        return (
          <div style={{ marginTop: 14, padding: '12px 18px', borderRadius: 8, border: '1px dashed #f85149', opacity: 0.85 }}>
            <div className="mono" style={{ fontSize: 10, color: '#f85149', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}
              title={`These hold both pitching edges but the Omega formula fires the same side, and the shipped co-fire demotion (validated in backtest 7/7 folds and −26.5% live overall) outranks the edges. The honest split it hides: co-fired WITHOUT the edges ${chip('omega_same_pw_no', '−30% (16)')} carries all the damage, co-fired WITH them ${chip('omega_same_pw_yes', '+8.9% (8)')} has been near breakeven — but that cell is single-digit bets, and an 8-bet cell does not overrule a validated rule. It updates live; if it is clearly positive at ~25 bets the demotion gets refined to spare these.`}>
              excluded — Ω-co-fired despite PEN+WHIP ✓ ({excl.length}) <span style={{ color: 'var(--text-tertiary)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>— co-fired with edges: {chip('omega_same_pw_yes', '+8.9% (8)')} · without: {chip('omega_same_pw_no', '−30% (16)')} · the validated demotion wins until the with-edges cell earns ~25 bets — hover</span>
            </div>
            {excl.map(x => betRow(x, '#8b949e', `co-fired · ${chip('omega_same_pw_yes', '')}`))}
          </div>
        )
      })()}

      {section(`⭐ golden contrarian — take AGAINST the model (${nGold})`, '#ffd700',
        `— model fades a both-edge team · live ${pwf ? `${pwf.wins}-${pwf.n - pwf.wins} · ${pwf.flat_roi_pct > 0 ? '+' : ''}${pwf.flat_roi_pct.toFixed(1)}%` : '27-19 · +17.3%'}${pwfDog ? ` · DOG wing ${pwfDog.flat_roi_pct > 0 ? '+' : ''}${pwfDog.flat_roi_pct.toFixed(1)}% (${pwfDog.n})` : ''} · WATCH signal: small flat stakes only, re-judged at 100 games`,
        golden.map(r => (
          <div key={`epg-${r.g.game_pk}`} className="mono" style={{ display: 'grid', gridTemplateColumns: '1fr 220px 90px 110px', gap: 10, alignItems: 'center', fontSize: 12, padding: '7px 6px', borderBottom: '1px solid var(--line)', borderLeft: '3px solid #ffd700', background: r.isDog ? 'rgba(255,215,0,0.12)' : 'rgba(255,215,0,0.05)' }}>
            <span>
              <span style={{ color: 'var(--text-secondary)' }}>{r.g.away_team_abbr}@{r.g.home_team_abbr} — </span>
              <b style={{ color: '#ffd700' }}>TAKE {r.take}</b>
              <span style={{ color: 'var(--text-tertiary)' }}> (model likes {r.other})</span>
              {r.isDog ? <b style={{ color: '#ffd700' }}> · DOG{pwfDog ? ` ${pwfDog.flat_roi_pct > 0 ? '+' : ''}${pwfDog.flat_roi_pct.toFixed(1)}%` : ''}</b> : null}
            </span>
            <span style={{ color: '#ffd700' }}>both edges · model has them {(r.pTeam * 100).toFixed(1)}%</span>
            <span style={{ color: 'var(--text-tertiary)' }}>flat, small</span>
            <span style={{ color: 'var(--text-tertiary)' }}>{time(r.g)}</span>
          </div>
        )))}

      <div className="mono" style={{ fontSize: 9, color: 'var(--text-tertiary)', marginTop: 10, lineHeight: 1.5 }}>
        Not shown here on purpose: losing/breakeven-profile menu bets without the pitching edges, Ω-co-fired bets, F5 (suspended),
        shades, and Kalshi placements (its ~7% fee made the book price better on 96 of 96 logged bets — place these at the listed
        sportsbooks). The full slate with every chip stays on the bet-for-profit tab; this page is the short list.
      </div>
    </div>
  )
}
