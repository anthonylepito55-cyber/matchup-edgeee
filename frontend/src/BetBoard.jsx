import React from 'react'

// Today's bet board -- the bets the F5 model and Model E actually like, pulled from the same
// /api/today payload the cards below render from (model_f5_bet / model_e_bet, see
// backend/model_e.compute_bet). A game with no row here is a game where neither model found a
// validated, positive-EV disagreement with the market -- "no bet" is the default, by design.
// Prices/stakes are the frozen pre-game values once a game starts (prediction_frozen).

const fmtPrice = p => (p == null ? '—' : `${p > 0 ? '+' : ''}${p}`)
const pct = x => (x == null ? '—' : `${(x * 100).toFixed(0)}%`)
const gameTime = iso => {
  if (!iso) return ''
  try { return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) } catch { return '' }
}

// Tiering is on the one thing the backtests showed predicts ROI: the size of the disagreement
// (ROI@fair rose ~+11% -> +15% -> +20% -> +26-34% as the gap went 2 -> 4 -> 6 -> 8 pts, in both
// Model E and F5), with underdog bets ~2x favorite bets at the same gap. Score = edge in pts,
// +1.5 for an underdog. BEST >= 6, GOOD >= 4, LEAN otherwise.
export const betScore = bet => (bet.edge || 0) * 100 + (bet.type === 'underdog' ? 1.5 : 0)

// Corroboration: how many of the OTHER models (B = market_model_prob, C = model_c_prob, A = the
// primary prediction's raw prob, E-baseball = model_e_baseball_prob) also lean our side by >= 2 pts
// vs the market. Backtest on 2,245 held-out Model E bets: 0 of 4 = -6.8% ROI (negative in 3 of 4
// folds) -> SKIP; 2-3 of 4 = +20-23% (positive every fold); 4 of 4 = +7.9%. Only the 0-of-4 SKIP
// is acted on -- the rest is shown as information; the edge tiers stay the ranking.
export const corroboration = (game, bet) => {
  if (!game || !bet || bet.market_prob == null) return { k: 0, n: 0 }
  const raw = game.prediction && (game.prediction.model_home_win_prob != null ? game.prediction.model_home_win_prob : game.prediction.home_win_prob)
  const probs = [game.market_model_prob, game.model_c_prob, raw, game.model_e_baseball_prob]
  let k = 0, n = 0
  for (const p of probs) {
    if (p == null) continue
    n += 1
    const side = bet.side_is_home ? p : 1 - p
    if (side - bet.market_prob >= 0.02) k += 1
  }
  return { k, n }
}
// F5 confirmation: does the F5 model ALSO beat the F5 market on our side by >= 2 pts? Backtest on
// 1,864 held-out Model E bets: yes -> 63.2% hit, +18.4% ROI, positive in all 4 folds; favorites
// WITHOUT it -> 55.8%, -1.2% (a wash, not worth the vig); underdogs are fine either way.
// Returns true / false / null (no F5 read for this game).
export const f5Confirms = (game, bet) => {
  if (!game || !bet || game.model_f5_prob == null || !game.f5_odds || game.f5_odds.home_prob == null) return null
  const f5side = bet.side_is_home ? game.model_f5_prob : 1 - game.model_f5_prob
  const f5mkt = bet.side_is_home ? game.f5_odds.home_prob : 1 - game.f5_odds.home_prob
  return f5side - f5mkt >= 0.02
}
export const betTier = (bet, game) => {
  const c = game ? corroboration(game, bet) : { k: 1, n: 0 }
  // NOTHING is excluded any more. 0-of-4 corroboration looked like a reliable filter on two
  // samples (-6.8% on 2,245 bets; -11.3% on the last-1,000-game replay) but the FULL 2,111-bet
  // walk-forward replay (Mar 2025 - Aug 2026, `_max_ruleset_test.py`) put those same bets at
  // +6.9% ROI, CI [-5.4%, +19.1%] -- unproven in both directions, not a demonstrated loser.
  // Demoted 2026-08-21 to a display tag, like the tiers and the F5 tag. Third sub-rule in a row
  // to fail on a bigger sample; only the base rule (compute_bet) gates a bet now.
  if (c.n >= 3 && c.k === 0) return 'LOW'
  // (F5 ✗ on a favorite used to force WEAK here. Removed 2026-08-21: the +18% F5-confirmation
  // advantage did NOT reproduce on the last 1,000 games -- F5 ✓ +14.2%, F5 ✗ dogs +11.2%, and
  // bets with NO F5 read at all did best at +21.2%. The tag is still shown as information.)
  return betScore(bet) >= 6 ? 'BEST' : betScore(bet) >= 4 ? 'GOOD' : 'LEAN'
}

// Ranking priority. Deliberately NOT the edge tiers: the edge->ROI gradient inverted on the
// last-1,000-game replay (BEST +9.4%, GOOD +24.5%, LEAN +28.1%) versus the full 2,245-bet sample
// (BEST ~+23%, LEAN ~+11%), so tier is no longer trusted as a profit ranking. What held in BOTH
// windows: underdog flips beat favorites (+24.5%/+16.9% vs +11.7%/+9.9%), and grade-A dog flips
// (model has the dog >= 55%) were the best group anywhere -- +37.9% on 82 recent bets, +21-35%
// on the full sample. So: grade-A dogs, then other dogs, then favorites, edge as the tiebreak.
export const betPriority = (bet, game) => {
  if (bet.type === 'underdog') return (bet.dog_grade === 'A' ? 300 : 200) + betScore(bet)
  return 100 + betScore(bet)
}
const TIER_STYLE = {
  BEST: { color: '#ffb627', label: 'BEST', title: 'edge >= 6 pts (backtest ROI ~+19-34% at fair odds)' },
  GOOD: { color: '#3fb950', label: 'GOOD', title: 'edge 4-6 pts (backtest ROI ~+15%)' },
  LEAN: { color: 'var(--text-tertiary)', label: 'LEAN', title: 'edge 3-4 pts -- smallest edge that still fires since the 9/4 threshold raise (2-pt edges were mostly paying vig and no longer bet)' },
  LOW: { color: '#8b949e', label: 'LOW', title: 'no other model corroborates this side (0 of 4). Looked bad on two samples (-6.8%, -11.3%) but the full 2,111-bet replay put these at +6.9% (CI -5.4% to +19.1%) -- unproven, not excluded. Informational only.' },
}

function TierTag({ bet, game }) {
  const t = TIER_STYLE[betTier(bet, game)]
  return (
    <span className="mono" title={t.title} style={{
      fontSize: 9, fontWeight: 700, letterSpacing: '0.06em', color: t.color,
      border: `1px solid ${t.color}`, borderRadius: 4, padding: '1px 5px', marginRight: 6,
    }}>{t.label}</span>
  )
}

function BetRow({ game, bet, market, label, highlight }) {
  const color = bet.type === 'underdog' ? '#3fb950' : '#58a6ff'
  const live = game.status && !['Scheduled', 'Pre-Game', 'Warmup'].includes(game.status)
  return (
    <div className="mono" style={{
      display: 'grid', gridTemplateColumns: '100px 1fr 130px 70px 120px 90px', gap: 10, alignItems: 'center',
      fontSize: 11, padding: '6px 8px', borderBottom: '1px solid var(--line)',
      background: highlight ? 'rgba(255,182,39,0.08)' : 'transparent', borderLeft: highlight ? '3px solid #ffb627' : '3px solid transparent',
    }}>
      <span style={{ color: 'var(--text-secondary)' }}>{label ? <span style={{ color: 'var(--text-tertiary)' }}>{label} </span> : null}{game.away_team_abbr}@{game.home_team_abbr}</span>
      <span style={{ color, fontWeight: 700 }}>
        <TierTag bet={bet} game={game} />{bet.side} {fmtPrice(bet.best_price)}{bet.best_book ? <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}> @ {bet.best_book}</span> : null}
        {bet.strength === 'strong' ? <span title="edge ≥ 6 pts — the range where backtest ROI roughly doubled"> ★</span> : null}
      </span>
      <span style={{ color: 'var(--text-tertiary)' }} title="how many of the other 4 models (B, C, A, baseball-only) also lean this side by >=2 pts">
        model {pct(bet.model_prob)} · mkt {pct(bet.market_prob)}{(() => { const c = corroboration(game, bet); return c.n ? ` · ${c.k}/${c.n} agree` : '' })()}{(() => { const f = f5Confirms(game, bet); return f === null ? '' : f ? ' · F5 ✓' : ' · F5 ✗' })()}
      </span>
      <span>{bet.stake_units != null ? `${bet.stake_units}u` : '—'}</span>
      <span style={{ color: 'var(--text-tertiary)' }}>
        EV {bet.ev_pct != null ? `${bet.ev_pct > 0 ? '+' : ''}${bet.ev_pct}%` : '—'} · {bet.type}
      </span>
      <span style={{ color: live ? 'var(--amber)' : 'var(--text-tertiary)' }}>
        {live ? game.status : gameTime(game.game_time_utc)}
      </span>
    </div>
  )
}

function Section({ title, subtitle, rows, empty }) {
  return (
    <div style={{ marginTop: 10 }}>
      <div className="mono" style={{ fontSize: 9, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {title} <span style={{ textTransform: 'none', letterSpacing: 0 }}>— {subtitle}</span>
      </div>
      {rows.length === 0 ? (
        <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', padding: '6px 0' }}>{empty}</div>
      ) : rows}
    </div>
  )
}

export default function BetBoard({ games, date, models = ['F5', 'E'] }) {
  if (!games || games.length === 0) return null
  const showF5 = models.includes('F5'), showE = models.includes('E')
  const f5 = (showF5 ? games : []).filter(g => g.model_f5_bet && g.model_f5_bet.stake_units != null)
    .sort((a, b) => betScore(b.model_f5_bet) - betScore(a.model_f5_bet))
  const e = (showE ? games : []).filter(g => g.model_e_bet && g.model_e_bet.stake_units != null)
    .sort((a, b) => betScore(b.model_e_bet) - betScore(a.model_e_bet))
  const pending = games.filter(g => ['Scheduled', 'Pre-Game', 'Warmup'].includes(g.status)).length
  const f5units = f5.reduce((s, g) => s + (g.model_f5_bet.stake_units || 0), 0)
  const eunits = e.reduce((s, g) => s + (g.model_e_bet.stake_units || 0), 0)

  return (
    <div style={{
      marginTop: 16, padding: '14px 18px', borderRadius: 8,
      background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))',
      border: '1px solid var(--amber)', boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, flexWrap: 'wrap' }}>
        <span className="mono" style={{ fontSize: 11, color: 'var(--amber)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>
          today&apos;s bets{date ? ` · ${date}` : ''}
        </span>
        <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
          {showF5 ? `${f5.length} F5 · ` : ''}{e.length} Model E · {pending} game{pending === 1 ? '' : 's'} still pre-game (bets can appear/update until first pitch)
        </span>
      </div>

      {(() => {
        const all = [...f5.map(g => ({ g, bet: g.model_f5_bet, label: 'F5' })), ...e.map(g => ({ g, bet: g.model_e_bet, label: 'E' }))]
          .sort((a, b) => betScore(b.bet) - betScore(a.bet))
        const best = all.filter(x => betTier(x.bet, x.g) === 'BEST')
        const strongest = all[0]
        return (
          <div style={{ marginTop: 10, padding: '8px 10px', borderRadius: 6, border: '1px solid rgba(255,182,39,0.45)', background: 'rgba(255,182,39,0.05)' }}>
            <div className="mono" style={{ fontSize: 10, color: '#ffb627', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>
              best bets {best.length ? `(${best.length})` : ''}
              <span style={{ color: 'var(--text-tertiary)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}> — edge ≥ 6 pts, the range where backtest ROI roughly doubled; underdogs rank above favorites at the same gap</span>
            </div>
            {best.length === 0 ? (
              <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', padding: '6px 0' }}>
                no BEST-tier bets right now{strongest ? ` — strongest is ${strongest.label} ${strongest.g.away_team_abbr}@${strongest.g.home_team_abbr} ${strongest.bet.side} at ${((strongest.bet.edge || 0) * 100).toFixed(1)} pts (${betTier(strongest.bet, strongest.g)})` : ''}.
              </div>
            ) : best.map(x => <BetRow key={`best-${x.label}-${x.g.game_pk}`} game={x.g} bet={x.bet} label={x.label} highlight />)}
          </div>
        )
      })()}

      {showF5 && <Section
        title="F5 — first 5 innings"
        subtitle={`${f5.length} bet${f5.length === 1 ? '' : 's'}, ${f5units.toFixed(2)}u total · 1st Half Moneyline, best of 5 books, quarter-Kelly`}
        rows={f5.map(g => <BetRow key={`f5-${g.game_pk}`} game={g} bet={g.model_f5_bet} highlight={betTier(g.model_f5_bet, g) === 'BEST'} />)}
        empty="no F5 bets right now — the F5 model doesn't disagree with the F5 market by a validated margin on any game."
      />}
      <Section
        title="Model E — full game"
        subtitle={`${e.length} bet${e.length === 1 ? '' : 's'}, ${eunits.toFixed(2)}u total · moneyline, best of 5 books, quarter-Kelly`}
        rows={e.map(g => <BetRow key={`e-${g.game_pk}`} game={g} bet={g.model_e_bet} highlight={betTier(g.model_e_bet, g) === 'BEST'} />)}
        empty="no Model E bets right now."
      />

      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 10 }}>
        Only the two validated patterns fire: the model flips to the market&apos;s underdog (≥6 pts of edge since 9/4), or it&apos;s ≥3 pts more bullish on the
        favorite than the price. A 62%-vs-65% shade toward the dog is not a bet. Stakes are units of a 100u bankroll at
        quarter-Kelly, capped at 5u; ★ = edge ≥ 6 pts. Ties after 5 innings push on F5.
      </div>
    </div>
  )
}
