import { useEffect, useState } from 'react'

// EDGE PICKS tab, v2 (2026-09-06). v1 grouped bets by the agreement-profile grid — that grid
// FAILED its out-of-sample test the same day it shipped (discovered on live 8/20+ bets, it
// SHUFFLED on the untouched Mar-Aug season: E-alone +26.5% live but −9.1% retro, consensus+
// edges −0.9% live but +25.5% retro; the profile-weighted portfolio made +7.2% vs +12.0% for
// the plain slip). So v2 is the plain validated slip, organized by the ONE signal that points
// the same way in BOTH samples — PEN+WHIP (✓ +21.0% live / +17.8% retro vs ✗ −9.7% / +8.3%)
// — plus the golden fade watch signal (+17.3% live / +4.2% retro, unstaked) and the co-fire
// demotion (validated in fold tests AND live). Profile badges live on as information on the
// bet-for-profit tab; they no longer size anything.
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
  // 2026 season-replay numbers (walk-forward OOF, Mar 25 - Aug 18, close - 3.5% vig; zero
  // overlap with the live record) -- shown in parentheses next to every live ROI so both
  // samples are always visible together. Static: the window is closed.
  const R26 = { pen_whip_yes: '+17.8% (198)', pen_whip_no: '+8.3% (406)', omega_same: '+7.7% (205)', fade: '+4.2% (116)', fade_dog: '+5.8% (62)' }
  const r26 = k => (R26[k] ? ` (26 retro ${R26[k]})` : '')

  const dv = (h, a) => {
    if (h == null || a == null) return null
    const d = p => (p > 0 ? 1 + p / 100 : 1 + 100 / Math.abs(p))
    const ih = 1 / d(h), ia = 1 / d(a)
    return ih / (ih + ia)
  }

  const bets = (games || []).filter(g => g.model_e_bet && g.model_e_bet.stake_units != null)
    .map(g => ({ g, bet: g.model_e_bet }))
  const demoted = x => x.bet.omega_cofired
  const pwYes = bets.filter(x => !demoted(x) && x.bet.pen_whip === true)
  const pwRest = bets.filter(x => !demoted(x) && x.bet.pen_whip !== true)
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

  // HEAVY-FAVORITE half-size rule (9/6, under investigation): the live pipeline generates
  // 3+pt favorite edges on big favorites ~9x more often than the replay pipeline did, the
  // cause is an unresolved serving-feature mismatch, and live -150+ favorites run −7.3%.
  // Until the feature-vector instrumentation identifies the skew, heavy favorites are
  // flagged for half stake.
  const heavyFav = bet => bet.type === 'favorite' && bet.best_price != null && bet.best_price <= -150

  const betRow = ({ g, bet }, color, tag) => (
    <div key={`ep-${g.game_pk}`} className="mono" style={{ display: 'grid', gridTemplateColumns: '1fr 220px 90px 110px', gap: 10, alignItems: 'center', fontSize: 12, padding: '7px 6px', borderBottom: '1px solid var(--line)', borderLeft: `3px solid ${color}`, background: 'rgba(255,255,255,0.02)' }}>
      <span>
        <span style={{ color: 'var(--text-secondary)' }}>{g.away_team_abbr}@{g.home_team_abbr} — </span>
        <b style={{ color }}>{bet.side} {bet.best_price > 0 ? '+' : ''}{bet.best_price}</b>
        {bet.best_book ? <span style={{ color: 'var(--text-tertiary)' }}> @ {bet.best_book}</span> : null}
        <span style={{ color: 'var(--text-tertiary)' }}> · {bet.type}{bet.dog_grade ? ` ${bet.dog_grade}` : ''}</span>
        {heavyFav(bet) ? <b style={{ color: '#f85149' }} title="HEAVY FAVORITE (-150 or shorter), HALF SIZE while under investigation: the live pipeline produces big-favorite edges ~9x more often than the replay pipeline ever did (9/6 diagnostic: live model sits +0.9 pts ABOVE the market on favorites vs −1.8 below under replay conditions — an unresolved serving-feature mismatch, not model drift). Live -150+ favorites run −7.3% (40). Every bet now freezes its full feature vector so the skewed feature identifies itself once the odds backfill catches up (~2 weeks); until then, take these at HALF the listed stake."> · ⚠ HEAVY — half size</b> : null}
      </span>
      <span style={{ color, fontWeight: 700 }}>{tag}</span>
      <span style={{ fontWeight: heavyFav(bet) ? 400 : 700, textDecoration: heavyFav(bet) ? 'line-through' : 'none' }}>{bet.stake_units}u{heavyFav(bet) ? <b style={{ color: '#f85149', textDecoration: 'none' }}> → {(bet.stake_units / 2).toFixed(1)}u</b> : null}</span>
      <span style={{ color: 'var(--text-tertiary)' }}>{time(g)}</span>
    </div>
  )

  return (
    <div>
      <div className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)', margin: '16px 0 4px', lineHeight: 1.5 }}>
        <b style={{ color: 'var(--amber)' }}>EDGE PICKS</b> — the validated slip (every menu bet except the Ω-co-fired demotions), organized by
        the one signal that held up in BOTH the live record and the out-of-sample season replay: <b>PEN+WHIP</b>. The agreement-profile
        grid that briefly organized this page failed its out-of-sample test on 9/6 (cells shuffled sign on the untouched Mar–Aug season;
        the profile-weighted portfolio made +7.2% vs +12.0% for the plain slip) — profile badges remain on the bet-for-profit tab as
        information, but nothing here sizes by them anymore. Stakes are the menu&apos;s quarter-Kelly (1u = 1% of bankroll). Bet at the listed
        books, favorites early — never Kalshi (book price was better on 96 of 96 logged bets).
      </div>

      {section(`★ slip — PEN+WHIP ✓ (${pwYes.length}) · full stake`, '#3fb950',
        `— our side holds both pitching edges · live ${chip('pen_whip_yes', '+21.0% (55)')}${r26('pen_whip_yes')} — the one signal positive in both samples`,
        pwYes.map(x => betRow(x, '#3fb950', `✓ live ${chip('pen_whip_yes', '')}${r26('pen_whip_yes')}`)))}

      {section(`slip — PEN+WHIP ✗ (${pwRest.length}) · standard stake`, '#58a6ff',
        `— still validated menu bets · live ${chip('pen_whip_no', '−9.7% (63)')}${r26('pen_whip_no')} — the samples disagree on these, so take them at listed size and let the record decide`,
        pwRest.map(x => betRow(x, '#58a6ff', `✗ live ${chip('pen_whip_no', '')}${r26('pen_whip_no')}`)))}

      {(() => {
        const excl = bets.filter(x => demoted(x))
        if (!excl.length) return null
        return (
          <div style={{ marginTop: 14, padding: '12px 18px', borderRadius: 8, border: '1px dashed #f85149', opacity: 0.85 }}>
            <div className="mono" style={{ fontSize: 10, color: '#f85149', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}
              title={`The Ω-co-fire demotion is the one exclusion that passed BOTH validation styles: +3.1% vs +14.2% for E-alone in the fold-tested backtest (7/7 folds, two geometries) AND −26.5% live (omega_same). Its pen+whip split: with edges ${chip('omega_same_pw_yes', '−3.2% (9)')}, without ${chip('omega_same_pw_no', '−34.5% (17)')} — if the with-edges cell is clearly positive at ~25 bets the demotion gets refined.`}>
              excluded — Ω-co-fired ({excl.length}) <span style={{ color: 'var(--text-tertiary)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>— the validated demotion · live {chip('omega_same', '−26.5% (27)')}{r26('omega_same')} · shown so nothing is hidden — hover</span>
            </div>
            {excl.map(x => betRow(x, '#8b949e', x.bet.pen_whip === true ? `co-fired · has edges ${chip('omega_same_pw_yes', '')}` : `co-fired ${chip('omega_same_pw_no', '')}`))}
          </div>
        )
      })()}

      {section(`⭐ golden contrarian — take AGAINST the model (${golden.length})`, '#ffd700',
        `— model fades a both-edge team · live ${pwf ? `${pwf.wins}-${pwf.n - pwf.wins} · ${pwf.flat_roi_pct > 0 ? '+' : ''}${pwf.flat_roi_pct.toFixed(1)}%` : '27-19 · +17.3%'}${r26('fade')}${pwfDog ? ` · DOG wing ${pwfDog.flat_roi_pct > 0 ? '+' : ''}${pwfDog.flat_roi_pct.toFixed(1)}% (${pwfDog.n})${r26('fade_dog')}` : ''} — WATCH signal, small flat stakes only, re-judged at 100 games`,
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
        Also not here, still by the record: F5 (suspended, −19.5% live), unflipped-dog shades (−15% live), Kalshi placements, and any
        bet the menu didn&apos;t fire. The full slate with every chip stays on the bet-for-profit tab; this page is the action list.
        Honesty ledger for this page itself: v1 (profile-grouped) lived one day before its own out-of-sample test killed it — the
        badges that organized it are now commentary, not sizing. Signals earn stakes here only by being positive in BOTH the live
        log and an untouched sample; today that list is: the menu, the co-fire demotion, and PEN+WHIP.
      </div>
    </div>
  )
}
