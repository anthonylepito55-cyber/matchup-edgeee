import React, { useEffect, useState } from 'react'
import BetBoard, { betScore, betTier, betPriority, corroboration, f5Confirms } from './BetBoard.jsx'

// "BET FOR PROFIT" tab: nothing but the bets and the money. Today's slip (the same Model E / F5
// bets the board shows, BEST first), what to risk in total, and the running P&L of every bet the
// two models have ever placed (from /api/model-e-track-record + /api/model-f5-track-record --
// real forward records, graded after each game, never recomputed).
const FEATURE_LABELS = {
  bullpen_fip_diff: 'bullpen quality (FIP)', high_leverage_bullpen_fip_diff: 'closer/setup quality',
  opp_platoon_woba_diff: 'lineup vs this hand', opp_lineup_woba_diff: 'lineup quality',
  opp_power_diff: 'lineup power (ISO)', lineup_xwoba_diff: 'lineup contact quality (xwOBA)',
  lineup_chase_percentile_diff: 'lineup chase rate', defense_oaa_diff: 'team defense (OAA)',
  recent_bb9_diff: 'starter walks, last 5', recent_hr9_diff: 'starter HR/9, last 5',
  fip_trend_diff: 'starter FIP trend', season_ip_per_start_diff: 'starter innings depth',
  pitches_per_start_diff: 'starter pitch efficiency', travel_fatigue_diff: 'travel fatigue',
  consensus_prob_diff: 'MARKET: consensus price', consensus_median_diff: 'MARKET: median price',
  line_movement_diff: 'MARKET: line movement', market_divergence_diff: 'MARKET: sharp vs public',
  book_disagreement: 'MARKET: book spread', book_prob_std: 'MARKET: book disagreement',
  book_favor_diff: 'MARKET: books favoring', book_movement_agreement: 'MARKET: books moving together',
  prediction_market_diff: 'MARKET: Kalshi/Polymarket', team_total_diff: 'MARKET: team totals',
  market_total_runs: 'MARKET: game total', market_outs_line_diff: 'MARKET: outs line',
  market_er_line_diff: 'MARKET: ER line', market_hits_allowed_line_diff: 'MARKET: hits line',
}

function WhyRow({ game, bet }) {
  const [open, setOpen] = useState(false)
  const ex = game.model_e_explain
  if (!ex || !ex.length) return null
  const homeAbbr = game.home_team_abbr, awayAbbr = game.away_team_abbr
  const max = Math.max(...ex.map(e => Math.abs(e.contribution))) || 1
  return (
    <div style={{ gridColumn: '1 / -1' }}>
      <button onClick={() => setOpen(o => !o)} className="mono" style={{
        background: 'none', border: 'none', color: 'var(--amber)', fontSize: 10,
        fontFamily: 'var(--font-mono)', textDecoration: 'underline', opacity: 0.75, cursor: 'pointer', padding: '2px 0',
      }}>{open ? 'hide' : 'why this bet?'}</button>
      {open && (
        <div style={{ padding: '6px 0 10px 12px' }}>
          {ex.map(e => {
            const towardBet = (e.favors === 'home') === !!bet.side_is_home
            const w = Math.round((Math.abs(e.contribution) / max) * 100)
            return (
              <div key={e.feature} className="mono" style={{ display: 'grid', gridTemplateColumns: '210px 1fr 120px 70px', gap: 8, alignItems: 'center', fontSize: 10, padding: '2px 0' }}>
                <span style={{ color: 'var(--text-secondary)' }}>{FEATURE_LABELS[e.feature] || e.feature}</span>
                <span style={{ background: 'var(--line)', height: 6, borderRadius: 3, position: 'relative' }}>
                  <span style={{ position: 'absolute', left: 0, top: 0, height: 6, width: `${w}%`, borderRadius: 3, background: towardBet ? '#3fb950' : '#f85149' }} />
                </span>
                <span style={{ color: towardBet ? '#3fb950' : '#f85149' }}>
                  {towardBet ? 'toward' : 'against'} {bet.side}
                </span>
                <span style={{ color: 'var(--text-tertiary)' }}>{e.value == null ? '—' : e.value}</span>
              </div>
            )
          })}
          <div className="mono" style={{ fontSize: 9, color: 'var(--text-tertiary)', marginTop: 6 }}>
            XGBoost contributions in log-odds, averaged over all 5 seeds and their calibration folds — the actual drivers of the
            served number, biggest first. Bars are relative size; green pushes toward {bet.side}, red against. Rows marked MARKET
            are the market-derived features (the model knows the price); the rest are baseball.
          </div>
        </div>
      )}
    </div>
  )
}

const pct = x => (x == null ? '—' : `${(x * 100).toFixed(1)}%`)
const signed = (x, d = 2, suffix = '') => (x == null ? '—' : `${x > 0 ? '+' : ''}${Number(x).toFixed(d)}${suffix}`)

// Shade dogs split hard by price (2026-08-21 study, disjoint windows). Shown per row so the
// evidence sits next to the bet; nothing is filtered out -- the user asked for all of them.
const shadePriceNote = mp => {
  if (mp == null) return null
  if (mp >= 0.425) return { label: '+100..+135', color: '#3fb950', title: 'best shade bucket: +12.1% early / +2.0% recent — the only one positive in both windows (dogs here win ~2.9 pts MORE than their price implies)' }
  if (mp >= 0.357) return { label: '+135..+180', color: '#8b949e', title: 'mixed: -1.4% early / +9.2% recent — roughly break-even' }
  if (mp >= 0.25) return { label: '+180..+300', color: '#f85149', title: 'WORST bucket: -32.7% on 152 early bets. Dogs here won 21.1% vs 31.3% implied — the model overrates long dogs by ~5-7 pts' }
  return { label: '+300 and up', color: '#f85149', title: 'worst of all: -53.6% (small sample). Model overrates long dogs badly' }
}

// Kalshi chip, shared by every bet section. EV = model probability vs (contract price + Kalshi's
// ~7% * p * (1-p) per-contract trading fee). Purple + bold when positive; the rule everywhere is
// the same: bet a row on Kalshi only while this number is positive.
const kalshiChip = (g, sideIsHome, modelProb, compact = false) => {
  const k = g && g.live_odds && g.live_odds.kalshi
  if (!k || modelProb == null) return null
  const c = sideIsHome ? k.home_cents : k.away_cents
  if (c == null) return null
  const cp = c / 100
  const fee = 0.07 * cp * (1 - cp)
  const ev = (modelProb / (cp + fee) - 1) * 100
  return (
    <span className="mono" style={{ color: ev > 0 ? '#a371f7' : 'var(--text-tertiary)', fontWeight: ev > 0 ? 700 : 400, fontSize: compact ? 9 : 11 }}
      title={`Kalshi ${c}¢ + ~${(fee * 100).toFixed(1)}¢ trading fee → effective ${((cp + fee) * 100).toFixed(1)}¢. EV compares the model's probability to that effective cost. Bet on Kalshi only while this is positive.`}>
      {' '}· Kalshi {c}¢ <b>{ev > 0 ? '+' : ''}{ev.toFixed(1)}%</b>
    </span>
  )
}

export default function ProfitView({ games, date, marketAge }) {
  const [e, setE] = useState(null)
  const [f5, setF5] = useState(null)
  const [retro, setRetro] = useState(null)
  const [book, setBook] = useState(null)
  useEffect(() => {
    fetch('/api/model-e-track-record').then(r => r.json()).then(setE).catch(() => {})
    fetch('/api/model-f5-track-record').then(r => r.json()).then(setF5).catch(() => {})
    fetch('/api/model-e-retro-record').then(r => r.json()).then(setRetro).catch(() => {})
    fetch('/api/omega-book').then(r => r.json()).then(setBook).catch(() => {})
  }, [])
  // Bankroll for compounding: stakes are a % of the CURRENT bankroll (1u = 1%), so keeping this
  // number current as the roll grows/shrinks is what turns +ROI into geometric growth. Stored
  // only in this browser, never sent anywhere.
  // try/catch: browsers set to block site data make localStorage.getItem itself throw, which
  // would crash the whole tab inside a render. A stored "0" is an explicit user choice (they
  // cleared the field), not a missing value — `Number(...) || 10000` silently resurrected a
  // $10,000 default over it and priced every stake off money the user zeroed out.
  const [bank, setBank] = useState(() => {
    try {
      const v = localStorage.getItem('me_bankroll')
      if (v == null) return 10000
      const n = Number(v)
      return Number.isFinite(n) ? n : 10000
    } catch { return 10000 }
  })
  useEffect(() => { try { localStorage.setItem('me_bankroll', String(bank || 0)) } catch {} }, [bank])
  const usd = u => (u == null || !bank ? '' : `$${Math.round((u * bank) / 100).toLocaleString()}`)

  // Model E (full-game moneyline) only -- F5 stays on the today tab and its own panel.
  const slip = (games || []).filter(g => g.model_e_bet && g.model_e_bet.stake_units != null)
    .map(g => ({ g, bet: g.model_e_bet, market: 'Full game ML' }))
    .sort((a, b) => betPriority(b.bet, b.g) - betPriority(a.bet, a.g))
  // F5-less favorites — the weakest measured still-positive class (+1.8% full-sample on 336
  // bets, +6.5% last-1,000) — are demoted to a red section at the bottom and excluded from the
  // headline risk total (user sizing call, 2026-09-03: the menu without them measured ~+13.8%
  // full-sample / +18.1% recent vs ~+10.7% / +15.5% with them). Demoted, not censored: they are
  // still positive, and hard-gating them never survived a clean test.
  // Demoted out of the recommended slip + headline risk total (both user calls, both measured):
  //   - F5-less favorites: +1.8% full-sample / +6.5% last-1,000 -- weakest still-positive class
  //   - Ω-co-fired bets (SHIPPED 9/4): E bets the Omega formula also fires -- +3.1% vs +14.2%
  //     E-alone in backtest (7/7 folds, two geometries), -20.6% on 25 live bets
  const isWeakFav = x => (x.bet.type === 'favorite' && f5Confirms(x.g, x.bet) === false) || x.bet.omega_cofired
  const mainSlip = slip.filter(x => !isWeakFav(x))
  const weakFavs = slip.filter(isWeakFav)
  const totalUnits = mainSlip.reduce((s, x) => s + (x.bet.stake_units || 0), 0)
  const weakUnits = weakFavs.reduce((s, x) => s + (x.bet.stake_units || 0), 0)
  const shades = (games || []).filter(g => g.model_e_shade && g.model_e_shade.stake_units != null)
    .sort((a, b) => (b.model_e_shade.edge || 0) - (a.model_e_shade.edge || 0))
  const shadeUnits = shades.reduce((t, g) => t + (g.model_e_shade.stake_units || 0), 0)
  const dogsA = slip.filter(x => x.bet.type === 'underdog' && x.bet.dog_grade === 'A').length
  const pending = (games || []).filter(g => ['Scheduled', 'Pre-Game', 'Warmup'].includes(g.status)).length

  // F5 (first-5-innings) bets -- back on the profit tab 2026-08-23. The F5 model is the only one
  // that beats its own market outright (+12.3% fair / +9.4% at real prices, positive in all four
  // validation windows), so leaving it off the slip was leaving the largest validated edge unused.
  const f5slip = (games || []).filter(g => g.model_f5_bet && g.model_f5_bet.stake_units != null)
    .map(g => ({ g, bet: g.model_f5_bet }))
    .sort((a, b) => (b.bet.edge || 0) - (a.bet.edge || 0))
  const f5Units = f5slip.reduce((t, x) => t + (x.bet.stake_units || 0), 0)

  const eAll = e && e.by_type && e.by_type.all
  const f5Bets = f5 && f5.bets && f5.bets.n > 0 ? f5.bets : null
  const totalProfit = (eAll ? eAll.units_profit : 0) + (f5Bets ? f5Bets.units_profit : 0)
  const totalStaked = (eAll ? eAll.units_staked : 0) + (f5Bets ? f5Bets.units_staked : 0)
  const totalBets = (eAll ? eAll.n : 0) + (f5Bets ? f5Bets.n : 0)

  return (
    <div>
      {/* ---- CONFLUENCE: slip bets ranked by LIVE-record signal ROIs (real bets only) ---- */}
      {(() => {
        const bs = (e && e.by_signal) || {}
        const chipOf = (label, agg, extra) => agg && agg.n > 0 && agg.flat_roi_pct != null
          ? { t: label, roi: agg.flat_roi_pct, n: agg.n, extra: extra || '' } : null
        const scored = mainSlip.map(({ g, bet }) => {
          const sigs = []
          // class signal from the LIVE by_class/by_type record (same source as the yellow chips)
          const key = bet.type === 'underdog' ? (bet.dog_grade === 'A' ? 'dog_a' : 'dog_b')
            : (f5Confirms(g, bet) === true ? 'fav_f5yes' : f5Confirms(g, bet) === false ? 'fav_f5no' : 'fav_nof5')
          let cls = e && e.by_class && e.by_class[key]
          let clsLabel = { dog_a: 'grade-A dogs', dog_b: 'grade-B dogs', fav_f5yes: 'F5-backed favs', fav_f5no: 'F5-less favs', fav_nof5: 'favs (no F5 read)' }[key]
          if (!cls || !(cls.n > 0)) {
            cls = e && e.by_type && e.by_type[bet.type === 'underdog' ? 'underdog' : 'favorite']
            clsLabel = bet.type === 'underdog' ? 'all dogs' : 'all favs'
          }
          const c1 = cls && cls.n > 0 && cls.flat_roi_pct != null ? { t: clsLabel, roi: cls.flat_roi_pct, n: cls.n, extra: 'live class record' } : null
          if (c1) sigs.push(c1)
          const ob = g.model_omega_bet
          const alone = !ob || ob.side !== bet.side
          const c2 = chipOf(alone ? 'E-alone' : 'Ω fires too', alone ? bs.e_alone : bs.omega_same, 'live split of real bets')
          if (c2) sigs.push(c2)
          const lm = g.line_move
          if (lm && lm.move_pts != null && lm.move_pts >= 1) {
            const c3 = chipOf('line toward us', bs.line_toward, 'live')
            if (c3) sigs.push(c3)
          } else if (lm && lm.move_pts != null && lm.move_pts <= -1) {
            const c3 = chipOf('line against', bs.line_against, 'live')
            if (c3) sigs.push(c3)
          }
          const hrs = bet.first_seen_at ? (Date.now() - new Date(bet.first_seen_at).getTime()) / 3.6e6 : 0
          const flatStale = lm && lm.move_pts != null && Math.abs(lm.move_pts) < 1 && hrs >= 3
          if (flatStale) {
            const c4 = chipOf('line flat 3h+', bs.line_flat, 'live — the bleed bucket')
            if (c4) sigs.push(c4)
          }
          const pos = sigs.filter(s => s.roi > 0).length
          const neg = sigs.filter(s => s.roi <= 0).length
          const sum = sigs.reduce((s, x) => s + x.roi, 0)
          return { g, bet, sigs, pos, neg, sum }
        }).filter(x => x.sigs.length >= 2 && x.pos >= 2 && x.neg === 0)
          .sort((a, b2) => b2.pos - a.pos || b2.sum - a.sum)
        if (!scored.length) return null
        return (
          <div style={{
            marginTop: 12, padding: '14px 18px', borderRadius: 8, border: '2px solid var(--amber)',
            background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))',
          }}>
            <div className="mono" style={{ fontSize: 10, color: 'var(--amber)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}
              title="Slip bets whose applicable LIVE signals are ALL positive in the real record so far — the class's live ROI (same feed as the yellow chips), the E-alone/Ω-fires split measured on real settled bets, and the line-movement split (+ live when the market has come toward us; a bet drops off this list entirely if any applicable live signal is negative, e.g. grade-A dogs at −59.8% on 10, or a 3h+ flat line at −22.4%). Every number updates automatically as bets settle. HONESTY: these are real-bet ROIs but tiny samples (±15–30 pt noise under 100 bets) — this ranks recent reality, which is not the same as truth. Bets are already in the slip and risk total; this adds no stake.">
              ⭐ confluence — every applicable LIVE signal positive ({scored.length}) <span style={{ color: 'var(--text-tertiary)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>— real-bet ROIs only, auto-updating · small samples · hover for the honesty note</span>
            </div>
            {scored.map(({ g, bet, sigs, pos }) => (
              <div key={`conf-${g.game_pk}`} className="mono" style={{ display: 'grid', gridTemplateColumns: '150px 60px 1fr 120px', gap: 10, alignItems: 'center', fontSize: 12, padding: '7px 6px', borderBottom: '1px solid var(--line)' }}>
                <span><span style={{ color: 'var(--text-secondary)' }}>{g.away_team_abbr}@{g.home_team_abbr} — </span><b style={{ color: 'var(--amber)' }}>{bet.side}</b> {bet.best_price > 0 ? '+' : ''}{bet.best_price}</span>
                <span style={{ color: pos >= 3 ? '#3fb950' : 'var(--amber)', fontWeight: 700 }}>{pos} live</span>
                <span>{sigs.map((s, i) => (
                  <span key={i} className="mono" style={{ fontSize: 10, border: `1px solid ${s.roi > 0 ? 'var(--line)' : '#f85149'}`, borderRadius: 4, padding: '1px 5px', marginRight: 5, color: s.roi > 0 ? 'var(--text-secondary)' : '#f85149' }}
                    title={`${s.t}: ${s.roi > 0 ? '+' : ''}${s.roi}% flat ROI on ${s.n} real settled bets (${s.extra}). Live record, not backtest — and n=${s.n} means a ±${Math.round(200 / Math.sqrt(s.n))}pt noise band.`}>
                    {s.t} <b style={{ color: s.roi > 0 ? '#3fb950' : '#f85149' }}>{s.roi > 0 ? '+' : ''}{s.roi}% ({s.n})</b>
                  </span>
                ))}</span>
                <span style={{ fontWeight: 700 }}>{bet.stake_units}u{bank ? <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}> {usd(bet.stake_units)}</span> : null}</span>
              </div>
            ))}
          </div>
        )
      })()}

      {/* ---- the slip ---- */}
      <div style={{
        marginTop: 16, padding: '16px 20px', borderRadius: 8, border: '1px solid var(--amber)',
        background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))',
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, flexWrap: 'wrap' }}>
          <span className="mono" style={{ fontSize: 13, color: 'var(--amber)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700 }}>
            bet for profit{date ? ` · ${date}` : ''} <span style={{ fontSize: 10, color: 'var(--text-tertiary)', letterSpacing: 0, textTransform: 'none', fontWeight: 400 }}>· full-game moneyline, Model E</span>
          </span>
          <span className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
            {mainSlip.length} bet{mainSlip.length === 1 ? '' : 's'}{dogsA ? <span style={{ color: '#3fb950' }}> · {dogsA} grade-A dog{dogsA === 1 ? '' : 's'} ◆</span> : null} · risk <b>{totalUnits.toFixed(2)}u</b>{bank ? <> = <b>{usd(totalUnits)}</b></> : null} (1u = 1% of bankroll){weakFavs.length ? <span style={{ color: '#f85149' }}> · {weakFavs.length} demoted below</span> : null}
            {marketAge != null && (
              <span
                title="How old the live moneyline prices behind these bets are. The server re-prices every minute inside 20 min of first pitch, every 3 min within 2 hours, and force-refreshes the odds cache first — so a frozen bet is priced from current market data, not an hour-old snapshot."
                style={{ marginLeft: 10, color: marketAge > 600 ? '#f85149' : marketAge > 300 ? '#8b949e' : '#3fb950' }}>
                · odds {marketAge < 90 ? `${marketAge}s` : `${Math.round(marketAge / 60)}m`} old
              </span>
            )}
            {pending ? ` · ${pending} game${pending === 1 ? '' : 's'} still pre-game, slip can change until first pitch` : ''}
          </span>
          <span className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)', marginLeft: 'auto' }}>
            bankroll $<input value={bank || ''} inputMode="numeric"
              onChange={ev => setBank(Number(String(ev.target.value).replace(/[^0-9]/g, '')) || 0)}
              title="Your current bankroll in dollars. Stakes are a % of THIS number (1u = 1%), so updating it as the roll grows or shrinks is what makes the sizing compound. Saved only in this browser."
              style={{ width: 72, background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 4, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: 11, padding: '2px 6px' }} />
            <span style={{ color: 'var(--text-tertiary)' }}> · 1u = ${Math.round((bank || 0) / 100).toLocaleString()}</span>
          </span>
        </div>

        {/* LIVE current-rules record + pace-based month estimate — all numbers from real settled
            bets under the ruleset that is live right now (post-9/4 thresholds + co-fire filter),
            retro-applied server-side and refreshed as bets settle. No backtest figures here. */}
        {e && e.current_rules && e.current_rules.roi_pct != null ? (() => {
          const cr = e.current_rules
          const perDay = cr.days > 0 ? cr.units_staked / cr.days : 0
          const estU = perDay * 30 * (cr.roi_pct / 100)
          const noise = Math.round(200 / Math.sqrt(cr.n))
          return (
            <div className="mono" style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 8 }}
              title={`The CURRENT ruleset (fav >= 3 pts, dog flip >= 6 pts, omega-co-fire filter) retro-applied to every real settled bet: ${cr.n} bets over ${cr.days} slate days, hit ${(100 * cr.hit_rate).toFixed(1)}%, ${cr.units_profit > 0 ? '+' : ''}${cr.units_profit}u on ${cr.units_staked}u staked. The monthly figure is simple arithmetic — this ROI at this staking pace over 30 slate days — NOT a guarantee: at n=${cr.n} the ROI itself carries a ±${noise}-point noise band, so the true pace could be anywhere in that range. This line updates automatically as bets settle. For reference, ALL bets ever placed under the old rules sit at −2.0%.`}>
              <span style={{ color: 'var(--text-tertiary)' }}>LIVE record of current rules: </span>
              <b style={{ color: cr.roi_pct > 0 ? '#3fb950' : '#f85149' }}>{cr.roi_pct > 0 ? '+' : ''}{cr.roi_pct}%</b> on {cr.n} real bets ({cr.days} days)
              {' '}· {cr.units_profit > 0 ? '+' : ''}{cr.units_profit}u
              {bank ? <> · at this pace ≈ <b style={{ color: estU > 0 ? '#3fb950' : '#f85149' }}>{estU > 0 ? '+' : ''}{usd(Math.abs(estU)).replace('$', '$') && (estU > 0 ? '' : '−') + usd(Math.abs(estU))}</b>/month</> : null}
              {' '}· ±{noise}pt noise at this sample — hover
            </div>
          )
        })() : null}

        {/* SKIP rows are included in `slip` — sorted last by betPriority, flagged red, and left out of the risk total */}
        {slip.length === 0 ? (
          <div className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 12 }}>
            No bets right now. That is a normal, profitable outcome: neither model disagrees with the market by a validated
            margin on any game, so the market&apos;s price is better than ours and the right play is not to pay the vig.
          </div>
        ) : (
          <div style={{ marginTop: 12 }}>
            <div className="mono" style={{ display: 'grid', gridTemplateColumns: '60px 110px 1fr 150px 70px 90px 110px', gap: 10, fontSize: 9, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', paddingBottom: 4, borderBottom: '1px solid var(--line)' }}>
              <span>tier</span><span>market</span><span>bet</span><span>model vs market</span><span>risk</span><span>EV</span><span>status</span>
            </div>
            {[...mainSlip, ...(weakFavs.length ? [{ divider: true }] : []), ...weakFavs].map((item) => {
              if (item.divider) return (
                <div key="weak-divider" className="mono" style={{ fontSize: 10, color: '#f85149', fontWeight: 700, padding: '12px 6px 4px', borderBottom: '1px solid var(--line)', textTransform: 'uppercase', letterSpacing: '0.06em' }}
                  title="Two demoted classes, both measured: (1) favorites the F5 model does not back — +1.8% ROI full-sample on 336 bets, the weakest still-positive class; (2) Ω-co-fired bets (filter shipped 9/4) — E bets the Omega formula also fires on the same side, +3.1% vs +14.2% for E-alone in backtest, reproduced in 7 of 7 folds across two independent fold geometries, and −20.6% on the 25 live co-fired bets. Kept visible and still logged/settled so the classes stay measured, but excluded from the recommended slip and the headline risk total. Each row's chips show which reason applies (red F5 ✗, or 'Ω fires too').">
                  ⚠ demoted — F5-less favorites (+1.8%) &amp; Ω-co-fired (−20.6% live) ({weakFavs.length}, {weakUnits.toFixed(2)}u{bank ? ` = ${usd(weakUnits)}` : ''}) · not in the risk total
                </div>
              )
              const { g, bet, market } = item
              const tier = betTier(bet, g)
              const tcolor = tier === 'BEST' ? '#ffb627' : tier === 'GOOD' ? '#3fb950' : 'var(--text-tertiary)'
              const topDog = bet.type === 'underdog' && bet.dog_grade === 'A'
              const f5c = f5Confirms(g, bet)
              const cor = corroboration(g, bet)
              const scolor = bet.type === 'underdog' ? '#3fb950' : '#58a6ff'
              const live = g.status && !['Scheduled', 'Pre-Game', 'Warmup'].includes(g.status)
              return (
                <div key={`${market}-${g.game_pk}`} className="mono" style={{
                  display: 'grid', gridTemplateColumns: '60px 110px 1fr 150px 70px 90px 110px', gap: 10, alignItems: 'center',
                  fontSize: 12, padding: '8px 6px', borderBottom: '1px solid var(--line)',
                  background: topDog ? 'rgba(63,185,80,0.10)' : ((bet.type === 'favorite' && f5c === false) || bet.omega_cofired) ? 'rgba(248,81,73,0.08)' : 'transparent',
                  borderLeft: `3px solid ${topDog ? '#3fb950' : ((bet.type === 'favorite' && f5c === false) || bet.omega_cofired) ? '#f85149' : 'transparent'}`,
                }}>
                  <span style={{ color: tcolor, fontWeight: 700, fontSize: 10 }} title={tier === 'LOW' ? 'no other model corroborates this side — unproven (+6.9% on the full 2,111-bet replay, CI -5.4% to +19.1%); shown, not excluded' : ''}>{tier}</span>
                  <span style={{ color: 'var(--text-tertiary)' }}>{market}</span>
                  <span>
                    <span style={{ color: 'var(--text-secondary)' }}>{g.away_team_abbr}@{g.home_team_abbr} — </span>
                    <span style={{ color: scolor, fontWeight: 700 }}>{bet.side} {bet.best_price > 0 ? '+' : ''}{bet.best_price}</span>
                    {bet.best_book ? <span style={{ color: 'var(--text-tertiary)' }}> @ {bet.best_book}</span> : null}
                    <span style={{ color: 'var(--text-tertiary)' }}> · {bet.type}{bet.dog_grade ? ` ${bet.dog_grade}` : ''}{bet.strength === 'strong' ? ' ★' : ''}</span>
                    {topDog ? <span style={{ color: '#3fb950', fontWeight: 700 }} title="grade-A underdog flip: the best-performing group in every window tested (+37.9% on the last 1,000 games, +21-35% on the full sample)"> ◆ TOP</span> : null}
                    {(() => {
                      // Kalshi chip: the user's actual venue. EV uses the model probability against
                      // the contract price PLUS Kalshi's ~7% * p * (1-p) per-contract trading fee --
                      // the quoted cents alone overstate the value.
                      const k = g.live_odds && g.live_odds.kalshi
                      if (!k) return <span className="mono" style={{ color: 'var(--text-tertiary)', fontSize: 10 }}> · Kalshi —</span>
                      const c = bet.side_is_home ? k.home_cents : k.away_cents
                      if (c == null) return null
                      const cp = c / 100
                      const fee = 0.07 * cp * (1 - cp)
                      const ev = ((bet.model_prob || 0) / (cp + fee) - 1) * 100
                      return (
                        <span className="mono" style={{ color: ev > 0 ? '#a371f7' : 'var(--text-tertiary)', fontWeight: ev > 0 ? 700 : 400, fontSize: 11 }}
                          title={`Kalshi has ${bet.side} at ${c}¢. Trading fee ≈ ${(fee * 100).toFixed(1)}¢/contract, so effective cost ${((cp + fee) * 100).toFixed(1)}¢. EV shown is the model probability vs that effective cost — positive means the Kalshi price still beats fair AFTER fees. Compare with the sportsbook EV column; take whichever venue's EV is higher.`}>
                          {' '}· Kalshi {c}¢ <b>{ev > 0 ? '+' : ''}{ev.toFixed(1)}%</b>
                        </span>
                      )
                    })()}
                    {bet.type === 'favorite' && !live ? <span style={{ color: '#58a6ff', opacity: 0.85, fontSize: 10 }} title="Favorites: bet as early as you can. In the timing study their lines drift TOWARD the model side by first pitch (worth ~+3 pts of ROI vs betting at close). Underdog timing was neutral — bet dogs whenever the price is right."> ⏱ bet early</span> : null}
                  </span>
                  <span style={{ color: 'var(--text-tertiary)' }}>{pct(bet.model_prob)} vs {pct(bet.market_prob)} (+{((bet.edge || 0) * 100).toFixed(1)} pts){(() => {
                    // One-signal flag: the top feature pushes TOWARD the bet side while every
                    // other listed feature COMBINED nets against it — one signal overruling the
                    // rest of the model. Seen live 2026-09-01 (CWS@HOU: market_divergence_diff
                    // +0.86 toward HOU vs −0.27 net from everything else, model 69% vs a 49%
                    // market with A/C at 44%). Direction-aware on purpose: a bet whose loudest
                    // feature merely OUTWEIGHS agreeing teammates (MIA@KC same night: bullpen
                    // −0.29 toward MIA with the rest also netting toward MIA) is corroborated,
                    // not one-signal — the first magnitude-only version wrongly flagged it.
                    // Information, never a gate.
                    // The explain payload is the TOP 8 of ~27 features by |contribution|, so
                    // "the rest" here means the 7 next-largest — the truncated tail is bounded
                    // by the smallest visible row but could still sum to a few tenths. Hence:
                    // (a) restToward must be strictly negative (a 0.00 tie proves nothing),
                    // (b) topToward must clear a 0.25 loudness floor so no plausible tail sum
                    // could flip the picture, and (c) the tooltip claims exactly what was
                    // measured (seven next-largest), not "every other feature in the model".
                    const ex = g.model_e_explain
                    if (!ex || ex.length < 2) return null
                    const sideSign = bet.side_is_home ? 1 : -1
                    const topToward = (ex[0].contribution || 0) * sideSign
                    const restToward = ex.slice(1).reduce((s, f) => s + (f.contribution || 0), 0) * sideSign
                    if (topToward < 0.25 || restToward >= 0) return null
                    // Two flavors, same chip: rest ≈ 0 means "this one reading IS the whole
                    // case" (MIA@KC 2026-09-03: bullpen +0.29, rest −0.00 — mild); rest clearly
                    // negative means "one reading is overruling a model that leans the other
                    // way" (CWS@HOU 2026-09-01: divergence +0.86, rest −0.27 — the scary one).
                    const opposed = restToward < -0.05
                    return <span style={{ color: 'var(--amber)', fontWeight: 700 }} title={`ONE-SIGNAL BET: '${ex[0].feature}' alone pushes ${topToward.toFixed(2)} toward ${bet.side}, while the seven next-largest features COMBINED net ${restToward.toFixed(2)} — ${opposed ? 'the loudest parts of the model lean the other way and this single reading overrules them' : 'the rest of the model roughly cancels itself out, so this single reading is the entire case for the bet'}. If that one signal is off${ex[0].feature.includes('market') || ex[0].feature.includes('consensus') || ex[0].feature.includes('divergence') ? ' (thin book coverage, a stale opening line, one book out of sync)' : ''}, the whole edge collapses. Not filtered out — but treat as low-corroboration: a reason to pass or size down, like MOVED AGAINST.`}> · ⚠ one-signal</span>
                  })()}{cor.n ? ` · ${cor.k}/${cor.n} agree` : ''}{f5c === null ? '' : (() => {
                    // Red + bold specifically for FAVORITES without F5 backing — the weakest
                    // measured class that's still positive (+1.8% full-sample, +6.5% last-1,000):
                    // the first bets to size down or skip when the bankroll is spread thin.
                    // Dogs with F5 ✗ stay neutral gray — F5 has no measured effect on dog ROI.
                    const weakFav = !f5c && bet.type === 'favorite'
                    return <span style={{ color: f5c ? '#3fb950' : weakFav ? '#f85149' : '#8b949e', fontWeight: weakFav ? 700 : 400 }} title={f5c
                      ? 'F5 VALUE check: the F5 model rates this side’s first-5-innings PRICE as >=2 pts generous. This is about the price, NOT a prediction of who leads after 5 — the F5 model can favor the OTHER team to lead and still mark this side’s longer price as good value (seen live CWS@HOU 9/3: F5 had HOU 58% to lead, while CWS’s F5 price was 2 pts cheap). Corrected measurement (9/3, after fixing a bug that had silently disabled every earlier F5 test): bets with F5 agreement made +15.4% ROI (n=432, positive in both backtest windows) vs +6.3% without it — the gap is almost entirely in FAVORITES, which made just +1.8% full-sample (+6.5% on the last 1,000) when F5 disagreed. Dogs are strong either way.'
                      : weakFav
                        ? 'WEAKEST CLASS: a favorite the F5 model does NOT back — these made just +1.8% ROI full-sample (+6.5% on the last 1,000), the thinnest still-positive group on the board. First candidates to size down or skip when the bankroll is spread thin. Not excluded: they do stay positive, and hard-gating them was never supported by a clean test.'
                        : 'F5 VALUE check: the F5 model does NOT rate this side’s first-5-innings price as >=2 pts generous — no corroboration from the F5 market angle. About the price, not a prediction of who leads after 5. For DOGS this has no measured effect on ROI (+16-21% either way).'}>{f5c ? ' · F5 value ✓' : ' · F5 value ✗'}</span>
                  })()}{(() => {
                    // PEN+WHIP chip (user ask 9/4, in caps with the live ROI next to it): does
                    // the bet side have BOTH the better starter WHIP and the better bullpen
                    // (FIP) pre-game? Frozen on the bet by the backend; the ROI shown is the
                    // LIVE record of that split (by_signal.pen_whip_yes/no), which on the first
                    // 118 settled bets ran 70.9% hit / +21.0% flat (yes) vs 49.2% / −9.7% (no).
                    // Noise bands still overlap — information, never a gate.
                    const pw = bet.pen_whip
                    if (pw == null) return null
                    const agg = e && e.by_signal && e.by_signal[pw ? 'pen_whip_yes' : 'pen_whip_no']
                    const roiTxt = agg && agg.flat_roi_pct != null ? `${agg.flat_roi_pct > 0 ? '+' : ''}${Number(agg.flat_roi_pct).toFixed(1)}%` : ''
                    return <span style={{ color: pw ? '#3fb950' : '#f85149', fontWeight: 700 }}
                      title={pw
                        ? `PEN+WHIP ✓: our side has BOTH the better starter WHIP and the better bullpen (by FIP) as of this morning. Live record of both-edge bets: ${roiTxt || 'n/a'} flat ROI${agg ? ` on ${agg.n} settled bets, hit ${(100 * agg.hit_rate).toFixed(0)}%` : ''} — essentially all of Model E's live profit has come from this group, and the full-sample association points the same way (both-edge teams win 57.5% vs the market's expected 55.9%). Noise bands still overlap between the groups, so this is information, not a gate.`
                        : `PEN+WHIP ✗: our side does NOT have both pitching edges (starter WHIP + bullpen FIP). Live record of these bets: ${roiTxt || 'n/a'} flat ROI${agg ? ` on ${agg.n} settled bets, hit ${(100 * agg.hit_rate).toFixed(0)}%` : ''} — underwater so far, while both-edge bets carry the profit. Small samples, overlapping noise bands: a caution flag, not a filter.`}>
                      {' '}· PEN+WHIP {pw ? '✓' : '✗'}{roiTxt ? ` ${roiTxt}` : ''}{agg ? ` (${agg.n})` : ''}
                    </span>
                  })()}{(() => {
                    // Historical ROI of this bet's CLASS -- class averages from the measured
                    // record, never this game's expected profit. Sources: last-1,000 ruleset
                    // test (2026-09-03 rerun with the F5 gate actually working) for dog grades
                    // and favorites overall; full-sample F5-agreement study for the F5 splits.
                    let cr
                    if (bet.type === 'underdog') {
                      cr = bet.dog_grade === 'A'
                        ? { roi: 26.3, n: 83, win: 'last 1,000 games', extra: 'grade-A dog flips (model has the dog >= 55%) — +21-35% on the full sample too, the best class in every test ever run' }
                        : { roi: 19.1, n: 76, win: 'last 1,000 games', extra: 'grade-B dog flips (model 52-55% on the dog)' }
                    } else if (f5c === true) {
                      cr = { roi: 14.6, n: 202, win: 'full sample', extra: 'favorites WITH F5 value backing' }
                    } else if (f5c === false) {
                      cr = { roi: 1.8, n: 336, win: 'full sample', extra: 'favorites WITHOUT F5 backing — the weakest still-positive class (+6.5% on the last 1,000, n=89)' }
                    } else {
                      cr = { roi: 12.8, n: 142, win: 'last 1,000 games', extra: 'all favorites (no F5 read available for this game)' }
                    }
                    // LIVE-FIRST (user call 2026-09-04, "i want all data current"): the one chip
                    // shown is the class's REAL record whenever any live bets exist — yellow,
                    // with (n) and its noise band. Falls back to the TYPE-level live record
                    // (labeled) when the exact class has none; the backtest figure appears only
                    // in the tooltip as reference, or as the chip itself when nothing live exists.
                    const key = bet.type === 'underdog'
                      ? (bet.dog_grade === 'A' ? 'dog_a' : 'dog_b')
                      : (f5c === true ? 'fav_f5yes' : f5c === false ? 'fav_f5no' : 'fav_nof5')
                    const lv = e && e.by_class && e.by_class[key]
                    const tvv = e && e.by_type && e.by_type[bet.type === 'underdog' ? 'underdog' : 'favorite']
                    const useLv = lv && lv.n > 0 && lv.flat_roi_pct != null
                    const src = useLv ? lv : (tvv && tvv.n > 0 && tvv.flat_roi_pct != null ? tvv : null)
                    if (src) {
                      const noise = Math.round(200 / Math.sqrt(src.n))
                      const label = useLv ? '' : ` ${bet.type === 'underdog' ? 'dogs' : 'favs'}`
                      // Under 15 bets a class ROI is pure noise (±52pts at n=15, ±141 at n=2) —
                      // render it dimmed with an explicit noise tag so a lucky +61% on two bets
                      // can't outshout a demotion built on n=25-336 evidence.
                      const tiny = src.n < 15
                      const roiTxt = `${src.flat_roi_pct > 0 ? '+' : ''}${Number(src.flat_roi_pct).toFixed(1)}%`
                      return <span style={{ color: tiny ? '#8b949e' : '#ffb627', fontWeight: tiny ? 400 : 700 }}
                        title={`LIVE ${useLv ? 'record of this class' : `record of ALL ${bet.type === 'underdog' ? 'underdog' : 'favorite'} bets (this exact class has no settled live bets yet)`}: ${roiTxt} flat ROI on ${src.n} real graded bets${src.hit_rate != null ? `, hit ${(100 * src.hit_rate).toFixed(0)}%` : ''} — a ±${noise}-point noise band at this sample size${tiny ? ', which makes this number statistically MEANINGLESS — it is shown only so you can watch it grow up' : ', so treat the sign loosely and the digits not at all'}. Updates automatically as bets settle. Backtest reference for this class: ${cr.roi > 0 ? '+' : ''}${cr.roi}% on ${cr.n} bets (${cr.win}).`}> · live {roiTxt} ({src.n}{label}{tiny ? ' · noise' : ''})</span>
                    }
                    const col = cr.roi >= 15 ? '#3fb950' : cr.roi >= 8 ? 'var(--text-secondary)' : '#f85149'
                    return <span style={{ color: col, fontWeight: 700 }} title={`No live bets exist for this class or type yet — the backtest figure is shown as the only available number: ${cr.roi > 0 ? '+' : ''}${cr.roi}% on ${cr.n} bets (${cr.win}), flat stakes at fair de-vigged prices. The chip switches to the live record automatically as soon as real bets settle.`}> · class {cr.roi > 0 ? '+' : ''}{cr.roi}% (backtest)</span>
                  })()}{(() => {
                    const lm = g.line_move
                    if (!lm || lm.move_pts == null) return null
                    const m = lm.move_pts
                    const hard = m <= -4
                    if (Math.abs(m) < 1) {
                      // Red once the bet has been flagged 3+ hours and the market still hasn't
                      // budged — live record 9/4: the ENTIRE bleed sits in flat-line bets (49%
                      // hit / −22.4% ROI on 49) while moved-toward made +13.0% (n=38) and even
                      // moved-against made +4.9% (n=34). Every fresh bet starts flat, hence the
                      // age gate. Information, never a filter — samples are small.
                      const hrs = bet.first_seen_at ? (Date.now() - new Date(bet.first_seen_at).getTime()) / 3.6e6 : 0
                      const stale = hrs >= 3
                      return <span style={{ color: stale ? '#f85149' : 'var(--text-tertiary)', fontWeight: stale ? 700 : 400 }} title={stale
                        ? `LINE STILL FLAT ~${Math.round(hrs)}h after we flagged this bet. In the live record the entire bleed is concentrated in flat-line bets: 49% hit / −22.4% ROI (n=49), versus +13.0% when the market moved toward us (n=38) and +4.9% when it moved against (n=34). A market that saw our flag and didn't budge has so far meant the market simply disagreed — and was right. Small samples; information, not a filter.`
                        : 'line flat — but this bet was flagged recently, and every bet starts flat. No signal yet.'}> · line flat{stale ? ' ⚠' : ''}</span>
                    }
                    return (
                      <span
                        style={{ color: hard ? '#f85149' : m < 0 ? '#8b949e' : '#3fb950', fontWeight: hard ? 700 : 400 }}
                        title={hard
                          ? 'WARNING: the market has moved 4+ points AGAINST this side since we first saw it. Pooled, those bets returned -44% (n=103) and the other side won 71%. On disjoint windows the direction held but the size did not (-56% early on 75 bets, -12% late on 28, CI straddling zero) — so this warns, it does not remove the bet. Treat as a reason to pass or size down.'
                          : `market has moved ${m > 0 ? 'toward' : 'against'} this side by ${Math.abs(m).toFixed(1)} pts since we first saw it (opened ${(lm.opening_prob * 100).toFixed(1)}%, now ${(lm.current_prob * 100).toFixed(1)}%). Mild moves carry no reliable signal.`}>
                        {' '}· line {m > 0 ? '+' : ''}{m.toFixed(1)} pts{hard ? ' ⚠ MOVED AGAINST' : ''}
                      </span>
                    )
                  })()}</span>
                  <span style={{ fontWeight: 700 }}>{bet.stake_units}u{bank ? <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}> {usd(bet.stake_units)}</span> : null}</span>
                  <span style={{ color: bet.ev_pct > 0 ? '#3fb950' : 'var(--text-tertiary)' }}>{signed(bet.ev_pct, 1, '%')}</span>
                  <span style={{ color: live ? 'var(--amber)' : 'var(--text-tertiary)' }}>{live ? `${g.status} (frozen)` : (g.game_time_utc ? new Date(g.game_time_utc).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : 'pre-game')}</span>
                  <WhyRow game={g} bet={bet} />
                </div>
              )
            })}
          </div>
        )}

        {/* ---- REST OF THE SLATE: every game with NO qualifying bet, and why (user ask 9/4:
             "i want every game shown"). The reason strings mirror model_e.compute_bet's real
             bars (fav >= 3 pts, dog flip >= 2 pts + >= 6 pts edge); the market prob is de-vigged
             from the live consensus books, same as the menu uses. Display only — no game here
             is bettable, that's the point. ---- */}
        {(() => {
          const noBet = (games || []).filter(g => !(g.model_e_bet && g.model_e_bet.stake_units != null))
          if (!noBet.length) return null
          const devig = g => {
            const books = g.live_odds && g.live_odds.books
            if (!books) return null
            const ps = Object.values(books).map(b => {
              if (b.home == null || b.away == null) return null
              const ih = b.home > 0 ? 100 / (b.home + 100) : -b.home / (-b.home + 100)
              const ia = b.away > 0 ? 100 / (b.away + 100) : -b.away / (-b.away + 100)
              return ih / (ih + ia)
            }).filter(p => p != null)
            return ps.length ? ps.reduce((s, p) => s + p, 0) / ps.length : null
          }
          const rows = noBet.map(g => {
            const p = g.model_e_prob
            const mkt = devig(g)
            let reason, detail
            if (p == null) { reason = 'model unavailable'; detail = 'no Model E probability for this game (usually a missing starter or missing market features)' }
            else if (mkt == null) { reason = 'no market price'; detail = 'no consensus moneyline available yet — the menu cannot price an edge without one' }
            else {
              const favIsHome = mkt >= 0.5
              const favAbbr = favIsHome ? g.home_team_abbr : g.away_team_abbr
              const dogAbbr = favIsHome ? g.away_team_abbr : g.home_team_abbr
              const pFav = favIsHome ? p : 1 - p
              const mFav = favIsHome ? mkt : 1 - mkt
              if (pFav >= 0.5) {
                const edge = (pFav - mFav) * 100
                reason = `${favAbbr} edge ${edge >= 0 ? '+' : ''}${edge.toFixed(1)} pts — favorites need +3`
                detail = `model ${(pFav * 100).toFixed(1)}% vs market ${(mFav * 100).toFixed(1)}% on the favorite ${favAbbr}. Favorite bets require the model at least 3 points above the de-vigged consensus (validated threshold); this one ${edge >= 3 ? 'HAS the edge but the model probability itself is below the internal bar' : 'falls short'}.`
              } else {
                const flip = (1 - pFav - 0.5) * 100
                const edge = ((1 - pFav) - (1 - mFav)) * 100
                if (flip < 2) {
                  reason = `slight ${dogAbbr} lean (+${flip.toFixed(1)} pt flip) — needs +2`
                  detail = `model ${((1 - pFav) * 100).toFixed(1)}% on the dog ${dogAbbr} vs market ${((1 - mFav) * 100).toFixed(1)}%. A dog bet first requires the model to actually FLIP the game (>= 52% on the dog); a sub-2-point lean is treated as agreement with the market.`
                } else {
                  reason = `${dogAbbr} flip +${edge.toFixed(1)} pts — dogs need +6`
                  detail = `model ${((1 - pFav) * 100).toFixed(1)}% on the dog ${dogAbbr} vs market ${((1 - mFav) * 100).toFixed(1)}%. Dog flips are only bet at a 6+ point edge (raised from 3 on 9/3 — the 3-6 point band measured negative in both validation windows).`
                }
              }
            }
            return { g, reason, detail }
          })
          return (
            <div style={{ marginTop: 14 }}>
              <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', paddingBottom: 4, borderBottom: '1px solid var(--line)' }}
                title="Every remaining game on the slate, shown with the reason the bet menu passed. A game with no row in the slip is a deliberate pass, not a missing game: most edges are too small to beat the vig, and the menu's profit comes from only betting the few that clear the validated bars.">
                rest of the slate — no bet ({rows.length} game{rows.length === 1 ? '' : 's'})
              </div>
              {rows.map(({ g, reason, detail }) => {
                const live = g.status && !['Scheduled', 'Pre-Game', 'Warmup'].includes(g.status)
                return (
                  <div key={`nobet-${g.game_pk}`} className="mono" style={{ display: 'grid', gridTemplateColumns: '1fr 260px 110px', gap: 10, alignItems: 'center', fontSize: 11, padding: '6px 6px', borderBottom: '1px solid var(--line)', color: 'var(--text-tertiary)' }}>
                    <span>
                      <span style={{ color: 'var(--text-secondary)' }}>{g.away_team_abbr}@{g.home_team_abbr}</span>
                      {g.model_e_prob != null ? <span> · model {(g.model_e_prob * 100).toFixed(1)}% home</span> : null}
                    </span>
                    <span title={detail}>{reason}</span>
                    <span>{live ? `${g.status}` : (g.game_time_utc ? new Date(g.game_time_utc).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : 'pre-game')}</span>
                  </div>
                )
              })}
              <div className="mono" style={{ fontSize: 9, color: 'var(--text-tertiary)', marginTop: 4 }}>
                passes, not omissions — the menu only bets edges that clear the validated bars (favorites +3 pts, dog flips +6 pts vs the de-vigged consensus). Betting every small edge measured negative after vig.
              </div>
            </div>
          )
        })()}

        <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 12, lineHeight: 1.5 }}>
          <b style={{ color: 'var(--text-secondary)' }}>How to use it:</b> place each row at the listed book (or the best price you can find),
          risking the units shown as a % of your bankroll (1u = 1%). Rows are ordered by what actually held up across both
          backtest windows: <b style={{ color: '#3fb950' }}>◆ grade-A underdog flips first</b> (model has the dog ≥ 55% — the best
          group in every test, +37.9% on the last 1,000 games), then other underdogs, then favorites. <b>SKIP</b> = no other model
          corroborates the side — that looked like a reliable filter twice, but the full 2,111-bet replay put those bets at +6.9%
          (CI −5.4% to +19.1%), so it no longer excludes anything. <b>One demotion exists</b> (a user sizing call, 9/3): favorites
          without F5 backing — the weakest measured still-positive class — sit in the red section at the bottom of the slip and are
          left out of the headline risk total. They are shown, not censored: the menu without them measured ~+13.8% full-sample /
          +18.1% recent vs ~+10.7% / +15.5% with them, so skipping them trades a little total profit for better ROI and smaller
          drawdowns. Every other qualifying bet counts in the risk total. Three sub-rules were tried as gates and none earned one — though the record needs a correction (9/3): the
          test behind &quot;F5 confirmation failed to reproduce&quot; had a bug that silently disabled its F5 gate on every run. Measured
          properly, F5-backed bets made +15.4% vs +6.3% without, with the whole gap in favorites (+1.8% full-sample when F5 disagrees)
          — still not a gate, since even that weakest class stays positive, but the F5 value mark deserves more weight than this note
          previously gave it, especially on favorites. <b style={{ color: 'var(--text-secondary)' }}>class %</b> on each row is the
          measured historical ROI of that bet's class (grade-A dog, F5-backed favorite, …) — an average over 76-336-bet samples at
          fair prices, shown so the pecking order is visible at a glance; it is never this game's expected profit. Once a class
          accumulates 150+ real graded bets in the forward record, its chip switches to the LIVE number automatically (tagged LIVE) —
          real bets outrank backtests here the moment there are enough of them. The original list (edge tiers, F5 confirmation,
          corroboration), so all three are shown as information, never as gates. Only the base rule decides a bet. Nothing is a lock:
          even grade-A dogs lose ~44% of the time.
          <br />
          <b style={{ color: '#f85149' }}>⚠ MOVED AGAINST</b> marks a bet whose price has moved 4+ points away from our side since we
          first saw it — the strongest negative signal in the data (pooled −44% on 103 bets; the side the market moves toward wins
          77.6% when the move is that big). It is a warning, not a filter: on split windows the direction held but the magnitude did
          not (−56% early, −12% late on only 28 bets), and four other sub-rules have already failed that same test. Nothing here is a lock:
          a BEST bet still loses ~35–40% of the time; it is simply priced wrong by more. If limits or bankroll bind, drop LEAN first.
          {' '}<b style={{ color: 'var(--amber)' }}>⚠ one-signal</b> marks a bet where the top feature pushes toward the bet side while
          every OTHER feature combined nets against it — one reading (usually market microstructure like sharp/public divergence)
          overruling the rest of the model. A bet whose loudest feature simply outweighs teammates that AGREE with it does not get
          flagged — that's corroboration, not isolation. The class of big-edge, low-corroboration bets still backtests positive, so it
          is information, not a filter — but if the one signal is wrong (thin book coverage, stale open), the edge is imaginary.
          Hover it for the exact feature.
          {' '}<b style={{ color: '#58a6ff' }}>⏱ Timing:</b> favorites are best bet early — their lines drift toward our side by
          first pitch (~+3 pts ROI in the timing study); underdog timing is neutral. <b style={{ color: 'var(--text-secondary)' }}>Compounding:</b> stakes
          are a % of your CURRENT bankroll — update the $ figure above as the roll changes (monthly is fine). Keeping units fixed
          while the roll grows quietly forfeits the geometric part of the edge. <b style={{ color: '#a371f7' }}>Kalshi:</b> each row
          shows the contract price in ¢ and the EV <b>after</b> Kalshi's ~7%·p·(1−p) trading fee. Bet a row on Kalshi only while
          that purple EV is positive; if it's negative but the sportsbook EV is positive, the edge exists only at the book's price.
          No Kalshi market for F5 — those stay sportsbook-only.
        </div>
      </div>

      {/* ---- F5 slip (re-added 2026-08-23) ---- */}
      <div style={{
        marginTop: 12, padding: '14px 18px', borderRadius: 8, border: '1px solid #58a6ff',
        background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))',
      }}>
        <div className="mono" style={{ fontSize: 10, color: '#58a6ff', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>
          first-5-innings bets {f5slip.length ? `(${f5slip.length} · shadow ${f5Units.toFixed(2)}u)` : ''} <span style={{ color: '#f85149' }}>⛔ SUSPENDED 9/4</span>
          <span style={{ color: 'var(--text-tertiary)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}> — logged as a shadow record only; do NOT place these until re-validation clears the thesis (live −18.0% on 61 bets; the F5 market out-picks the model 52.4%–47.6% exactly where bets fire)</span>
        </div>
        {f5slip.length === 0 ? (
          <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 6 }}>no F5 bets right now.</div>
        ) : (
          <div style={{ marginTop: 8 }}>
            {f5slip.map(({ g, bet }) => {
              const live = g.status && !['Scheduled', 'Pre-Game', 'Warmup'].includes(g.status)
              return (
                <div key={`f5-${g.game_pk}`} className="mono" style={{ display: 'grid', gridTemplateColumns: '110px 1fr 150px 90px 70px 110px', gap: 10, alignItems: 'center', fontSize: 12, padding: '7px 6px', borderBottom: '1px solid var(--line)' }}>
                  <span style={{ color: 'var(--text-tertiary)' }}>F5 moneyline</span>
                  <span>
                    <span style={{ color: 'var(--text-secondary)' }}>{g.away_team_abbr}@{g.home_team_abbr} — </span>
                    <span style={{ color: '#58a6ff', fontWeight: 700 }}>{bet.side} F5 {bet.best_price != null ? `${bet.best_price > 0 ? '+' : ''}${bet.best_price}` : ''}</span>
                    {bet.best_book ? <span style={{ color: 'var(--text-tertiary)' }}> @ {bet.best_book}</span> : null}
                    <span style={{ color: 'var(--text-tertiary)' }}> · {bet.type}{bet.dog_grade ? ` ${bet.dog_grade}` : ''}{bet.strength === 'strong' ? ' ★' : ''}</span>
                  </span>
                  <span style={{ color: 'var(--text-tertiary)' }}>{pct(bet.model_prob)} vs {pct(bet.market_prob)} (+{((bet.edge || 0) * 100).toFixed(1)} pts)</span>
                  <span style={{ fontWeight: 700 }}>{bet.stake_units}u{bank ? <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}> {usd(bet.stake_units)}</span> : null}</span>
                  <span style={{ color: bet.ev_pct > 0 ? '#3fb950' : 'var(--text-tertiary)' }}>{signed(bet.ev_pct, 1, '%')}</span>
                  <span style={{ color: live ? 'var(--amber)' : 'var(--text-tertiary)' }}>{live ? `${g.status} (frozen)` : (g.game_time_utc ? new Date(g.game_time_utc).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : 'pre-game')}</span>
                </div>
              )
            })}
          </div>
        )}
        <div className="mono" style={{ fontSize: 9, color: 'var(--text-tertiary)', marginTop: 6, lineHeight: 1.5 }}>
          Settled on the score after 5 innings (~15% of games are tied after 5 and PUSH — check your book). Stacks with a full-game
          bet on the same team — same lean, different market, graded separately.
          <div style={{ color: '#f85149', marginTop: 4 }}>
            <b>⚠ THESIS UNDER REVIEW (9/4).</b> The validation claim behind this section (+9.4% at real prices) is contradicted by
            three independent measurements: on raw picks the F5 MARKET is more accurate than the model (55.4% vs 54.4%); on the
            513 games where they DISAGREE — which is exactly when a bet fires — the model is right only <b>47.6%</b> vs the market&apos;s
            52.4%; and the live record below is deeply negative. A bet can still profit at a 47.6% hit rate if the prices are long
            enough, so this is not proof the edge is gone — but treat these as speculative, not as the app&apos;s best edge, until the
            forward record or a re-validation settles it.
          </div>
          {f5 && f5.bets && f5.bets.n > 0 && (
            <> <b style={{ color: f5.bets.units_profit >= 0 ? '#3fb950' : '#f85149' }}>Live so far: {f5.bets.n} bets, {signed(f5.bets.units_profit, 2, 'u')} ({signed(f5.bets.roi_pct, 1, '%')})</b>
            {f5.bets.n < 100 ? ' — still a small sample on its own (±25 pts of noise at this size), but it now points the same way as the disagreement-accuracy finding above, which is the part that is not small.' : ''}</>
          )}
        </div>
      </div>

      {/* ---- Model A selectivity (informational) — same menu math applied to A's number ---- */}
      {(() => {
        const dv = (h, a) => {
          if (h == null || a == null) return null
          const d = p => (p > 0 ? 1 + p / 100 : 1 + 100 / Math.abs(p))
          const ih = 1 / d(h), ia = 1 / d(a)
          return ih / (ih + ia)
        }
        const rows = (games || []).map(g => {
          const p = g.prediction && g.prediction.home_win_prob
          const m = g.live_odds ? dv(g.live_odds.home, g.live_odds.away) : null
          if (p == null || m == null) return null
          const favHome = m >= 0.5
          const pFav = favHome ? p : 1 - p
          const mFav = favHome ? m : 1 - m
          let type = null, side = null, pSide = null, mSide = null
          if (pFav < 0.48 && (1 - pFav) - (1 - mFav) >= 0.06) {
            type = 'dog flip'; side = favHome ? g.away_team_abbr : g.home_team_abbr; pSide = 1 - pFav; mSide = 1 - mFav
          } else if (pFav - mFav >= 0.03) {
            type = 'favorite'; side = favHome ? g.home_team_abbr : g.away_team_abbr; pSide = pFav; mSide = mFav
          }
          return type ? { g, type, side, pSide, mSide, edge: pSide - mSide } : null
        }).filter(Boolean).sort((a, b2) => b2.edge - a.edge)
        return (
          <div style={{
            marginTop: 12, padding: '14px 18px', borderRadius: 8, border: '1px dashed #58a6ff',
            background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))',
          }}>
            <div className="mono" style={{ fontSize: 10, color: '#58a6ff', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}
              title="Model A (the baseball-only primary) pushed through the EXACT same bet menu as Model E (favorite >= 3 pts, dog flip >= 6 pts). Live record when graded this way: +18.0% ROI, +39u on 76 bets since July 10 — the best of every model on the page. The honesty: A's big-sample walk-forward backtest measured only +1.9%, and forced to bet EVERY game it loses (−2.1% on 363), so the +18% is its selective bets during a hot stretch, not a proven edge. Shown as information, never in the risk total; if it still leads at 300+ bets, the menu decision gets re-litigated with real ammunition.">
              Model A selectivity {rows.length ? `(${rows.length} game${rows.length === 1 ? '' : 's'} today)` : ''} <span style={{ color: 'var(--text-tertiary)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>— the +18% live streak (76 bets) · backtest says +1.9% · informational, not in the risk total — hover for the full story</span>
            </div>
            {rows.length === 0 ? (
              <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 6 }}>no games clear Model A&apos;s menu today.</div>
            ) : rows.map(r => {
              // PINK highlight (user call 9/4): A's BIG clean edges. Live log since 7/10,
              // clean side-picks only (favorite agreement or true dog flip — the no-flip dog
              // leans measured −10.4% and stay excluded): edge ≥ 6 pts → 58.5% win / +15.9%
              // ROI (n=94); edge ≥ 8 pts → 59.4% / +20.6% (n=64). Noise ±21-25 pts at these
              // sizes — the monotonic ordering (bigger edge → better ROI) is the sturdy part.
              const hot8 = r.edge >= 0.08
              const hot6 = r.edge >= 0.06
              const pink = '#f472b6'
              return (
              <div key={`asel-${r.g.game_pk}`} className="mono" title={hot6 ? `BIG MODEL A EDGE (${(r.edge * 100).toFixed(1)} pts). Live record of A's clean ${hot8 ? '8' : '6'}+ point edges since 7/10: ${hot8 ? '59.4% win / +20.6% ROI on 64 games' : '58.5% win / +15.9% ROI on 94 games'} — graded at the de-vigged close minus 3.5% vig. Bigger A edges have been monotonically better (every-game −4.6% → 6+ +15.9% → 8+ +20.6%), but the noise band is still ±21-25 pts at this sample. Informational: not in the risk total.` : ''} style={{
                display: 'grid', gridTemplateColumns: '110px 1fr 150px 110px', gap: 10, alignItems: 'center', fontSize: 12, padding: '6px 6px', borderBottom: '1px solid var(--line)',
                background: hot8 ? 'rgba(244,113,181,0.18)' : hot6 ? 'rgba(244,113,181,0.10)' : 'transparent',
                borderLeft: `3px solid ${hot6 ? pink : 'transparent'}`,
              }}>
                <span style={{ color: hot6 ? pink : 'var(--text-tertiary)', fontWeight: hot6 ? 700 : 400 }}>{r.type}{hot8 ? ' · 8+ PTS' : hot6 ? ' · 6+ PTS' : ''}</span>
                <span><span style={{ color: 'var(--text-secondary)' }}>{r.g.away_team_abbr}@{r.g.home_team_abbr} — </span><b style={{ color: hot6 ? pink : '#58a6ff' }}>{r.side}</b></span>
                <span style={{ color: hot6 ? pink : 'var(--text-tertiary)', fontWeight: hot6 ? 700 : 400 }}>A {(r.pSide * 100).toFixed(1)}% vs {(r.mSide * 100).toFixed(1)}% (+{(r.edge * 100).toFixed(1)} pts)
                  {/* Type-specific LIVE ROI on pink rows (user ask 9/4): A's big-edge profit is
                      almost entirely dog flips — live since 7/10 at close−vig: dog flips +33.3%
                      (n=40, 62.5% win), favorites with 6+ pts just +1.9% (n=39). */}
                  {hot6 ? <span title={r.type === 'dog flip'
                    ? 'LIVE record of Model A dog flips (menu-qualifying, since 7/10, at the de-vigged close minus 3.5% vig): 62.5% win, +33.3% ROI on 40 games — where nearly all of A’s big-edge profit lives. ±32-pt noise band at n=40: strong, not settled.'
                    : 'LIVE record of Model A favorites with 6+ pts of edge (since 7/10, close minus vig): 59.0% win but only +1.9% ROI on 39 games — A’s big edges pay on DOG FLIPS (+33.3%), while its big favorite edges have been roughly breakeven so far.'}>
                    {' '}· {r.type === 'dog flip' ? 'dog flips +33.3% (40)' : 'big favs +1.9% (39)'}
                  </span> : null}
                </span>
                <span style={{ color: ['Scheduled', 'Pre-Game', 'Warmup'].includes(r.g.status) ? 'var(--text-tertiary)' : 'var(--amber)' }}>{['Scheduled', 'Pre-Game', 'Warmup'].includes(r.g.status) ? (r.g.game_time_utc ? new Date(r.g.game_time_utc).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : 'pre-game') : `${r.g.status} (frozen)`}</span>
              </div>
              )
            })}
            {rows.some(r => r.edge >= 0.06) ? (
              <div className="mono" style={{ fontSize: 9, color: '#f472b6', marginTop: 4 }}>
                pink = big clean A edge · live since 7/10: 6+ pts +15.9% ROI (94) · 8+ pts +20.6% (64) · clean side-picks only, at close minus vig — hover a row
              </div>
            ) : null}
          </div>
        )
      })()}

      {/* ---- Jacob's OMEGA BOOK card, proxied live from the clone on :8080 ---- */}
      {book && book.available && book.games && book.games.some(g => g.omega) && (
        <div style={{
          marginTop: 12, padding: '14px 18px', borderRadius: 8, border: '1px solid #d2a8ff',
          background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))',
        }}>
          <div className="mono" style={{ fontSize: 10, color: '#d2a8ff', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>
            Ω OMEGA — THE BOOK <span style={{ color: 'var(--text-tertiary)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>— Jacob&apos;s live card, proxied straight from his page so both books sit side by side. His numbers, his sizing, his calls.</span>
          </div>
          <div className="mono" style={{ display: 'grid', gridTemplateColumns: '90px 1fr 60px 70px 110px 110px', gap: 10, fontSize: 9, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', padding: '8px 6px 4px', borderBottom: '1px solid var(--line)' }}>
            <span>game</span><span>his lean · Ω vs mkt</span><span>conf</span><span>EV fair</span><span>his stake</span><span>call</span>
          </div>
          {book.games.filter(g => g.omega).sort((a, b2) => ((b2.bet_board && b2.bet_board.ev_pct) || (b2.omega.ev_fair * 100) || 0) - ((a.bet_board && a.bet_board.ev_pct) || (a.omega.ev_fair * 100) || 0)).map(g => {
            const o = g.omega, b = g.bet_board || {}
            const lean = b.side || (o.lean === 'home' ? g.matchup.split('@')[1] : g.matchup.split('@')[0])
            const ev = b.ev_pct != null ? b.ev_pct : o.ev_fair != null ? o.ev_fair * 100 : null
            const call = b.vetoed ? 'VETO' : (b.stake_units > 0 ? `${(b.type || 'lean').toUpperCase()} ${b.stake_units}u` : 'PASS')
            const ccolor = b.vetoed ? '#f85149' : b.stake_units > 0 ? (b.type === 'bet' ? '#3fb950' : 'var(--amber)') : 'var(--text-tertiary)'
            return (
              <div key={`book-${g.matchup}-${g.game_time_utc}`} className="mono" style={{ display: 'grid', gridTemplateColumns: '90px 1fr 60px 70px 110px 110px', gap: 10, alignItems: 'center', fontSize: 12, padding: '6px 6px', borderBottom: '1px solid var(--line)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>{g.matchup}</span>
                <span><b style={{ color: '#d2a8ff' }}>{lean}</b> <span style={{ color: 'var(--text-tertiary)' }}>{o.p_side != null ? `${(o.p_side * 100).toFixed(1)}%` : ''} vs {o.implied_side != null ? `${(o.implied_side * 100).toFixed(1)}%` : ''}{o.edge != null ? ` (${o.edge > 0 ? '+' : ''}${(Math.abs(o.edge) * 100).toFixed(1)} pts)` : ''}</span></span>
                <span style={{ color: (b.conf_score || 100) >= 100 ? 'var(--text-secondary)' : '#8b949e' }}>{b.conf_score != null ? b.conf_score : '—'}</span>
                <span style={{ color: ev > 0 ? '#3fb950' : 'var(--text-tertiary)' }}>{ev != null ? `${ev > 0 ? '+' : ''}${ev.toFixed(1)}%` : '—'}</span>
                <span>{b.stake_units > 0 ? <>{b.stake_units}u{bank ? <span style={{ color: 'var(--text-tertiary)' }}> {usd(b.stake_units)}</span> : null}</> : '—'}</span>
                <span style={{ color: ccolor, fontWeight: 700 }}>{call}</span>
              </div>
            )
          })}
          <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 8, lineHeight: 1.5 }}>
            Rendered from his service&apos;s own live numbers (cached ~2 min) — the certification claims on his page are his, not
            re-validated here. The scoreboard that settles whose book is better stays the running P&amp;L above: his real ledger is
            −3.3% overall (favorites +1.6%, dog flips +14.4%, dog_value −28%), and the Omega shadow line grades his model through
            this app&apos;s pipeline going forward. His stakes here are shown in his units, converted at YOUR bankroll — do not add
            them to the risk total above.
          </div>
        </div>
      )}

      {/* ---- unproven: dog shades ---- */}
      <div style={{
        marginTop: 12, padding: '14px 18px', borderRadius: 8, border: '1px dashed #8b949e',
        background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))',
      }}>
        <div className="mono" style={{ fontSize: 10, color: '#8b949e', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>
          unproven — underdog shades {shades.length ? `(${shades.length}, ${shadeUnits.toFixed(2)}u${bank ? ` = ${usd(shadeUnits)}` : ''})` : ''}
          <span style={{ color: 'var(--text-tertiary)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}> — model likes the dog more than the price, but still has the favorite winning</span>
        </div>
        {shades.length === 0 ? (
          <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 6 }}>
            none right now.
          </div>
        ) : shades.map(g => {
          const b = g.model_e_shade
          const live = g.status && !['Scheduled', 'Pre-Game', 'Warmup'].includes(g.status)
          return (
            <div key={`shade-${g.game_pk}`} className="mono" style={{ display: 'grid', gridTemplateColumns: '1fr 190px 95px 80px 110px', gap: 10, alignItems: 'center', fontSize: 12, padding: '6px 6px', borderBottom: '1px solid var(--line)' }}>
              <span>
                <span style={{ color: 'var(--text-secondary)' }}>{g.away_team_abbr}@{g.home_team_abbr} — </span>
                <span style={{ color: '#8b949e', fontWeight: 700 }}>{b.side} {b.best_price > 0 ? '+' : ''}{b.best_price}</span>
                {b.best_book ? <span style={{ color: 'var(--text-tertiary)' }}> @ {b.best_book}</span> : null}
                {kalshiChip(g, b.side_is_home, b.model_prob)}
              </span>
              <span style={{ color: 'var(--text-tertiary)' }}>
                model {pct(b.model_prob)} vs {pct(b.market_prob)} (+{((b.edge || 0) * 100).toFixed(1)} pts)
                {(() => { const n = shadePriceNote(b.market_prob); return n ? <span style={{ color: n.color, marginLeft: 6 }} title={n.title}>· {n.label}</span> : null })()}
              </span>
              <span style={{ fontWeight: 700 }}>{b.stake_units}u{bank ? <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}> {usd(b.stake_units)}</span> : null}</span>
              <span style={{ color: b.ev_pct > 0 ? '#3fb950' : 'var(--text-tertiary)' }}>{signed(b.ev_pct, 1, '%')}</span>
              <span style={{ color: live ? 'var(--amber)' : 'var(--text-tertiary)' }}>{live ? `${g.status} (frozen)` : (g.game_time_utc ? new Date(g.game_time_utc).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : 'pre-game')}</span>
            </div>
          )
        })}
        <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 8, lineHeight: 1.5 }}>
          <b style={{ color: '#8b949e' }}>Why these are separate:</b> the two backtest windows disagree on this pattern —
          <span style={{ color: '#3fb950' }}> +2.5%</span> on the last 1,000 games (n=207) but
          <span style={{ color: '#f85149' }}> −3.2%</span> on the full 3,586-game sample (n=934), and the sub-buckets flip sign
          between windows. Most likely noise around break-even, not an edge. For contrast, real flips — where the model actually
          makes the dog the likelier winner — returned +24.5% and +13.6% on those same two windows. These are shown, staked at
          quarter-Kelly if you want them, tracked on their own below, and <b>excluded from the risk total above</b>. Let the live
          record decide.
          <br />
          <b style={{ color: 'var(--text-secondary)' }}>Price matters more than the shade here:</b> shade dogs at
          <span style={{ color: '#3fb950' }}> +100 to +135</span> were the only bucket positive in both windows (+12.1% / +2.0%),
          while <span style={{ color: '#f85149' }}>+180 and longer went −32.7%</span> on 152 early bets — those dogs won 21.1%
          against a 31.3% implied price, i.e. the model overrates long shots by 5–7 pts. Every shade is listed regardless; the
          tag on each row tells you which bucket it is. The EV% shown comes from the model's own probability, which in the long-price
          bucket is the number the data disputes — so treat big EVs there as a reason to size down, not up.
        </div>
      </div>

      {/* ---- best underdogs ---- */}
      {(() => {
        const dogs = slip.filter(x => x.bet.type === 'underdog' && betTier(x.bet, x.g) !== 'SKIP')
          .sort((a, b) => (b.bet.model_prob || 0) - (a.bet.model_prob || 0))
        const priceNote = b => {
          const m = b.market_prob
          if (m == null) return ''
          return m >= 0.45 ? 'short dog' : m >= 0.40 ? 'mid dog (best range)' : 'big dog'
        }
        return (
          <div style={{
            marginTop: 12, padding: '14px 18px', borderRadius: 8, border: '1px solid #3fb950',
            background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))',
          }}>
            <div className="mono" style={{ fontSize: 10, color: '#3fb950', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>
              best underdogs today {dogs.length ? `(${dogs.length})` : ''}
              <span style={{ color: 'var(--text-tertiary)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}> — dogs the model actually flips to, ranked by how strongly</span>
            </div>
            {dogs.length === 0 ? (
              <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 6 }}>
                no underdog flips right now — the model doesn&apos;t have any market underdog as the likelier winner by the required margin.
              </div>
            ) : dogs.map(({ g, bet }) => (
              <div key={`dog-${g.game_pk}`} className="mono" style={{ display: 'grid', gridTemplateColumns: '40px 1fr 180px 70px 150px', gap: 10, alignItems: 'center', fontSize: 12, padding: '6px 6px', borderBottom: '1px solid var(--line)', background: bet.dog_grade === 'A' ? 'rgba(63,185,80,0.08)' : 'transparent' }}>
                <span style={{ color: bet.dog_grade === 'A' ? '#3fb950' : 'var(--text-tertiary)', fontWeight: 700 }} title={bet.dog_grade === 'A' ? 'model has the dog >= 55%: backtest +21% (55-60%) / +35% (60%+), positive every fold' : 'model has the dog 52-55%: backtest +6%'}>{bet.dog_grade || '—'}</span>
                <span><span style={{ color: 'var(--text-secondary)' }}>{g.away_team_abbr}@{g.home_team_abbr} — </span><span style={{ color: '#3fb950', fontWeight: 700 }}>{bet.side} {bet.best_price > 0 ? '+' : ''}{bet.best_price}</span>{bet.best_book ? <span style={{ color: 'var(--text-tertiary)' }}> @ {bet.best_book}</span> : null}{kalshiChip(g, bet.side_is_home, bet.model_prob)}</span>
                <span style={{ color: 'var(--text-tertiary)' }}>model {pct(bet.model_prob)} vs {pct(bet.market_prob)} · {priceNote(bet)}</span>
                <span style={{ fontWeight: 700 }}>{bet.stake_units}u{bank ? <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}> {usd(bet.stake_units)}</span> : null}</span>
                <span style={{ color: 'var(--text-tertiary)' }}>{betTier(bet, g)}{(() => { const c = corroboration(g, bet); return c.n ? ` · ${c.k}/${c.n} agree` : '' })()}</span>
              </div>
            ))}
            <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 8, lineHeight: 1.5 }}>
              What made underdogs pay in the backtest (932 flips, fair odds): grade A (model has the dog ≥ 55%) +21–35% and positive
              every period; grade B (52–55%) +6%; dogs priced +122 to +150 were the best range (+24%); dogs in near-pick&apos;em games
              with under 6 pts of edge are no longer bet (2-4 pts lost −18%; 4-6 pts cut 9/4 — at realistic vig, dropping them beat keeping them at every threshold combination tested). A dog the model still has as the loser is never a bet here,
              however tempting the price — that pattern tested negative at every shade size that was stable.
            </div>
          </div>
        )
      })()}

      {/* ---- every underdog on the slate, qualified or not ---- */}
      {(() => {
        const imp = x => (x > 0 ? 100 / (x + 100) : -x / (-x + 100))
        const dogs = (games || []).map(g => {
          const lo = g.live_odds, E = g.model_e_prob
          if (!lo || lo.home == null || E == null) return null
          const ih = imp(lo.home), ia = imp(lo.away), mk = ih / (ih + ia)
          const dogHome = mk < 0.5
          const price = dogHome ? lo.home : lo.away
          const books = lo.books || {}
          let best = price, bestBook = lo.bookmaker
          for (const [bk, pr] of Object.entries(books)) {
            const q = dogHome ? pr.home : pr.away
            if (q != null && (q > best)) { best = q; bestBook = bk }
          }
          const mDog = dogHome ? mk : 1 - mk
          const eDog = dogHome ? E : 1 - E
          const dec = best > 0 ? 1 + best / 100 : 1 + 100 / Math.abs(best)
          return { g, side: dogHome ? g.home_team_abbr : g.away_team_abbr, price: best, book: bestBook,
                   mDog, eDog, edge: eDog - mDog, ev: (eDog * dec - 1) * 100,
                   qualified: !!(g.model_e_bet && g.model_e_bet.type === 'underdog') || !!g.model_e_shade }
        }).filter(Boolean).sort((a, b) => b.edge - a.edge)
        if (!dogs.length) return null
        return (
          <div style={{ marginTop: 12, padding: '14px 18px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--panel)' }}>
            <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              all underdogs — every game on the slate ({dogs.length}), ranked by model edge
            </div>
            <div className="mono" style={{ display: 'grid', gridTemplateColumns: '110px 130px 150px 90px 90px 1fr', gap: 8, fontSize: 9, color: 'var(--text-tertiary)', textTransform: 'uppercase', marginTop: 6, paddingBottom: 3, borderBottom: '1px solid var(--line)' }}>
              <span>game</span><span>dog / best price</span><span>model vs market</span><span>edge</span><span>EV</span><span>status</span>
            </div>
            {dogs.map(d => (
              <div key={`dog-${d.g.game_pk}`} className="mono" style={{ display: 'grid', gridTemplateColumns: '110px 130px 150px 90px 90px 1fr', gap: 8, alignItems: 'center', fontSize: 11, padding: '4px 0', borderBottom: '1px solid var(--line)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>{d.g.away_team_abbr}@{d.g.home_team_abbr}</span>
                <span style={{ color: d.edge >= 0.02 ? '#3fb950' : 'var(--text-secondary)' }}>{d.side} {d.price > 0 ? '+' : ''}{d.price}<span style={{ color: 'var(--text-tertiary)' }}> {d.book ? d.book.slice(0, 4) : ''}</span></span>
                <span style={{ color: 'var(--text-tertiary)' }}>{(d.eDog * 100).toFixed(1)}% vs {(d.mDog * 100).toFixed(1)}%</span>
                <span style={{ color: d.edge > 0 ? '#3fb950' : '#f85149' }}>{d.edge > 0 ? '+' : ''}{(d.edge * 100).toFixed(1)} pts</span>
                <span style={{ color: d.ev > 0 ? '#3fb950' : '#f85149' }}>{d.ev > 0 ? '+' : ''}{d.ev.toFixed(1)}%<span style={{ display: 'block' }}>{kalshiChip(d.g, d.side === d.g.home_team_abbr, d.eDog, true)}</span></span>
                <span style={{ color: 'var(--text-tertiary)' }}>{d.qualified ? 'on the board above' : (d.edge >= 0.02 ? 'qualifies — refresh' : 'below threshold — model rates this dog at or under its price')}</span>
              </div>
            ))}
            <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 8, lineHeight: 1.5 }}>
              Every game&apos;s underdog at the best price across the 10 shopped books (Kalshi ¢ shown separately — its fee makes contract cents and book odds non-comparable), whether or not it clears a rule — so nothing is
              hidden. <b>Edge</b> is the model&apos;s probability minus the de-vigged market price; <b>EV</b> is what that edge is worth
              at the listed price. A <span style={{ color: '#f85149' }}>negative edge</span> means the model rates the dog at or below
              its price — betting it is −EV by the model&apos;s own math, not a small edge. Rows in green clear the 2-pt bar and appear
              in the sections above.
            </div>
          </div>
        )
      })()}

      {/* ---- every remaining game, so nothing is invisible ---- */}
      {(() => {
        const shown = new Set([...slip.map(x => x.g.game_pk), ...shades.map(g => g.game_pk)])
        const rest = (games || []).filter(g => !shown.has(g.game_pk))
        if (rest.length === 0) return null
        const gapOf = g => {
          const E = g.model_e_prob
          const lo = g.live_odds
          if (E == null) return { txt: g.model_e_prob == null ? 'no model number yet' : '', gap: null }
          if (!lo || lo.home == null) return { txt: 'no moneyline posted', gap: null }
          const imp = x => (x > 0 ? 100 / (x + 100) : -x / (-x + 100))
          const ih = imp(lo.home), ia = imp(lo.away), mk = ih / (ih + ia)
          const favHome = mk >= 0.5
          const eF = favHome ? E : 1 - E, mF = favHome ? mk : 1 - mk
          const side = favHome ? g.home_team_abbr : g.away_team_abbr
          return { txt: `model ${side} ${(eF * 100).toFixed(0)}% vs market ${(mF * 100).toFixed(0)}%`, gap: (eF - mF) * 100 }
        }
        return (
          <div style={{ marginTop: 12, padding: '12px 18px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--panel)' }}>
            <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              no bet ({rest.length}) — every other game on the slate, and why
            </div>
            {rest.map(g => {
              const { txt, gap } = gapOf(g)
              return (
                <div key={`nb-${g.game_pk}`} className="mono" style={{ display: 'grid', gridTemplateColumns: '110px 1fr 150px', gap: 10, fontSize: 11, padding: '3px 0', color: 'var(--text-tertiary)' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>{g.away_team_abbr}@{g.home_team_abbr}</span>
                  <span>{txt}</span>
                  <span style={{ color: g.market_blind ? '#f85149' : undefined }}>
                    {gap == null ? '—' : `gap ${gap > 0 ? '+' : ''}${gap.toFixed(1)} pts — under threshold`}
                    {g.market_blind ? <span style={{ color: '#8b949e' }}> · thin market data</span> : null}
                  </span>
                </div>
              )
            })}
            <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 6 }}>
              These clear no rule: the model is within ~3 pts of the market, or leans the market&apos;s way, or the line/starter isn&apos;t posted yet.
              Listed so the whole slate is accounted for — a bet appears here the moment it qualifies.
              <br />
              <span style={{ color: '#8b949e' }}>thin market data</span> flags a game whose market feature block was incomplete.
              It does <b>not</b> suppress the bet: measured on 2026-08-23, Model E running market-blind still returns +7.5%
              (CI +3.5% to +11.4%), and on the biggest starter mismatches +12.8% — slightly better than with the market. Adding
              starter stats back as a fallback tested worse in every variant. A last-known-good merge now repairs most of the gaps
              upstream anyway.
            </div>
          </div>
        )
      })()}

      {/* ---- what the research says (last-1000-game replay of this exact ruleset) ---- */}
      <div style={{
        marginTop: 12, padding: '14px 18px', borderRadius: 8, border: '1px solid var(--line)',
        background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))',
      }}>
        <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          backtest — this exact ruleset replayed on every gradeable game (2,221 bets, 2025-03-18 → 2026-08-18)
        </div>
        <div className="mono" style={{ display: 'flex', gap: 26, flexWrap: 'wrap', marginTop: 8, fontSize: 12 }}>
          <span><span style={{ color: 'var(--text-tertiary)' }}>all bets: </span><b>2,221</b> · hit <b>59.6%</b> · ROI <b style={{ color: '#3fb950' }}>+6.9%</b> after ~3% vig · <b style={{ color: '#3fb950' }}>+$15,344</b> at $100/u</span>
          <span><span style={{ color: '#3fb950' }}>◆ grade-A dogs: </span>362 · 55.8% · <b style={{ color: '#3fb950' }}>+16.3%</b></span>
          <span><span style={{ color: 'var(--text-tertiary)' }}>all underdogs: </span>622 · 53.5% · +12.2%</span>
          <span><span style={{ color: 'var(--text-tertiary)' }}>grade-B dogs: </span>260 · 50.4% · +6.6%</span>
          <span><span style={{ color: 'var(--text-tertiary)' }}>favorites: </span>1,599 · 61.9% · +4.8%</span>
        </div>
        <div className="mono" style={{ display: 'flex', gap: 26, flexWrap: 'wrap', marginTop: 6, fontSize: 11, color: 'var(--text-tertiary)' }}>
          <span>2025 season +5.5% (n=1,304) · 2026 season +8.8% (n=917) · worst drawdown −$2,382 · longest losing streak 8 bets · quarter-Kelly +8.1%</span>
        </div>
        <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 8, lineHeight: 1.5 }}>
          Walk-forward: each game was priced by models trained only on earlier games and graded against the closing line and the
          real winner — no hindsight. Fair (de-vigged) odds, flat 1u stakes; real books take another ~2–3% on the moneyline, and
          live edges typically come in near half of backtest, so plan on <b>+3–5%</b>, not +6.9%. The last-1,000-game slice showed +15.6% — that was one of the better stretches, not the norm; this full-sample number is the honest one.
          <br />
          <b style={{ color: 'var(--text-secondary)' }}>What did not reproduce:</b> the edge tiers inverted this window
          (BEST +9.4%, GOOD +24.5%, LEAN +28.1%), F5 confirmation added nothing (F5 ✓ +14.2% vs no-F5-read +21.2%), and 0-of-4
          corroboration — excluded until now — came back <b>+6.9%</b> on the full sample. All three are displayed, none gate a bet.
          The only thing that held in every window: <b>grade-A underdog flips</b>, which is why they rank first.
        </div>
      </div>

      {/* ---- running P&L ---- */}
      <div style={{
        marginTop: 12, padding: '14px 18px', borderRadius: 8, border: '1px solid var(--line)',
        background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))',
      }}>
        <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          running P&amp;L — every bet the models have placed, graded after the game (real forward record)
        </div>
        <div className="mono" style={{ display: 'flex', gap: 28, flexWrap: 'wrap', marginTop: 8, fontSize: 12 }}>
          <span><span style={{ color: 'var(--text-tertiary)' }}>all bets: </span>{totalBets} · <span style={{ color: totalProfit > 0 ? '#3fb950' : totalProfit < 0 ? '#f85149' : undefined, fontWeight: 700 }}>{signed(totalProfit, 2, 'u')}</span> on {totalStaked.toFixed(2)}u risked{totalStaked ? ` (ROI ${signed(100 * totalProfit / totalStaked, 1, '%')})` : ''}</span>
          {eAll && <span><span style={{ color: 'var(--text-tertiary)' }}>Model E: </span>{eAll.n} bets · hit {pct(eAll.hit_rate)} vs {pct(eAll.market_implied)} implied · {signed(eAll.units_profit, 2, 'u')} · ROI {signed(eAll.roi_pct, 1, '%')}{eAll.avg_clv_pts != null ? ` · CLV ${signed(eAll.avg_clv_pts, 2, ' pts')}` : ''}</span>}
          {f5Bets && <span><span style={{ color: '#58a6ff' }}>F5: </span>{f5Bets.n} bets · hit {pct(f5Bets.hit_rate)} · {signed(f5Bets.units_profit, 2, 'u')} · ROI {signed(f5Bets.roi_pct, 1, '%')}</span>}
          {e && e.shade && <span><span style={{ color: '#8b949e' }}>shades (unproven): </span>{e.shade.n} · hit {pct(e.shade.hit_rate)} · {signed(e.shade.units_profit, 2, 'u')} · ROI {signed(e.shade.roi_pct, 1, '%')}</span>}
          {e && e.omega && <span title="Jacob's Omega model (market price + a shrunk pull toward the baseball-only leg) graded through the IDENTICAL pipeline as Model E — same slate, same logged best prices, same quarter-Kelly stakes, same CLV bookkeeping. Wired 9/4 so the E-vs-Omega argument is settled by one shared scoreboard instead of two incomparable site displays. Shadow only: its bets are never on the slip and never in the risk total."><span style={{ color: '#d2a8ff' }}>Omega (shadow): </span>{e.omega.n} · hit {pct(e.omega.hit_rate)} · {signed(e.omega.units_profit, 2, 'u')} · ROI {signed(e.omega.roi_pct, 1, '%')}{e.omega.avg_clv_pts != null ? ` · CLV ${signed(e.omega.avg_clv_pts, 2, ' pts')}` : ''}</span>}
          {e && e.jacob_book && <span title="Jacob's live BOOK picks (the card below), captured pre-game into this app's log and settled through the identical grading pipeline as Model E — his stakes, neutral settlement, real prices, CLV tracked. This is his card's certification claim facing neutral grading for the first time; wiring began 9/4, so the sample builds from there."><span style={{ color: '#a5d6ff' }}>Jacob&apos;s BOOK (graded here): </span>{e.jacob_book.n} · hit {pct(e.jacob_book.hit_rate)} · {signed(e.jacob_book.units_profit, 2, 'u')} · ROI {signed(e.jacob_book.roi_pct, 1, '%')}{e.jacob_book.avg_clv_pts != null ? ` · CLV ${signed(e.jacob_book.avg_clv_pts, 2, ' pts')}` : ''}</span>}
          <span title="Static snapshot pulled 9/4 straight from the clone's own prediction log (Jul 10 – Sep 5, flat stakes at the frozen moneyline). These are the TWO PROFITABLE patterns on Jacob's page — the same two patterns this app's validated menu is built from. Full honesty: his overall ledger is −3.3% ROI (205 bets), because he also still runs dog_value — dogs the model likes but doesn't flip — which went 30% hit / −28% ROI on 50 bets. That's the exact pattern this app retired after it backtested negative three separate times.">
            <span style={{ color: '#d2a8ff', fontWeight: 700 }}>Omega on Jacob&apos;s page (real ledger): </span>
            <span style={{ background: 'rgba(210,168,255,0.12)', border: '1px solid #d2a8ff', borderRadius: 4, padding: '1px 6px' }}>favorites 117 · hit 59.8% · <b>+1.6%</b></span>
            {' '}<span style={{ background: 'rgba(63,185,80,0.12)', border: '1px solid #3fb950', borderRadius: 4, padding: '1px 6px' }}>dog flips 38 · hit 55.3% · <b style={{ color: '#3fb950' }}>+14.4%</b></span>
            <span style={{ color: 'var(--text-tertiary)' }}> · overall −3.3% incl. dog_value −28% — hover</span>
          </span>
          {!eAll && <span style={{ color: 'var(--text-tertiary)' }}>no graded bets yet — the record starts with tonight&apos;s slate.</span>}
        </div>
        {retro && retro.all && (
          <div className="mono" style={{ marginTop: 8, padding: '6px 10px', fontSize: 11, color: 'var(--text-secondary)', borderLeft: '3px solid var(--text-tertiary)', background: 'var(--panel)' }}
            title={`${retro.note || ''} Rule: ${retro.rule || ''}. Monthly (ROI at ~3.5% vig): ${(retro.by_month || []).map(m => `${m.month} ${m.flat_roi_pct_at_vig > 0 ? '+' : ''}${m.flat_roi_pct_at_vig}% (n=${m.n})`).join(' · ')}`}>
            <span style={{ color: 'var(--text-tertiary)' }}>{retro.label}: </span>
            {retro.all.n} bets · hit {pct(retro.all.hit_rate)} · <span style={{ color: retro.all.units_profit > 0 ? '#3fb950' : '#f85149', fontWeight: 700 }}>{signed(retro.all.units_profit, 1, 'u')}</span>
            {' '}· ROI {signed(retro.all.flat_roi_pct, 1, '%')} at close / {signed(retro.all.flat_roi_pct_at_vig, 1, '%')} at ~3.5% vig
            <span style={{ color: 'var(--text-tertiary)' }}> · hover for monthly + caveats</span>
          </div>
        )}
        <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 8 }}>
          Read this, not the backtests, to judge whether it&apos;s working: positive CLV is the earliest sign (hours), hit rate vs
          implied needs ~100 bets, ROI needs ~200–300 bets to separate from luck. A sustained negative CLV is the signal to stop.
        </div>
      </div>

      {/* the full board underneath for the per-model breakdown */}
      <BetBoard games={games} date={date} models={['E']} />
    </div>
  )
}
