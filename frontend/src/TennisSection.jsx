import React, { useEffect, useState, useMemo } from 'react'
import { americanOddsToImpliedProb } from './odds.js'

const LEAGUE_COLOR = { atp: '#4A9EFF', wta: '#FF6FA5' }

const SURFACE_COLOR = {
  Hard: '#4A9EFF', Clay: '#D97748', Grass: '#3DDC84', Carpet: '#B98CE0',
}

// Tennis FORWARD RECORD panel (2026-09-06): tennis ran two months with predictions but no
// ledger — nothing frozen, nothing graded. The backend now logs every priced prediction
// before first serve and settles from real results; this panel shows that record growing
// from zero. Until it has real sample, the honest banner is "unproven — do not bet this".
function TennisTrackRecord() {
  const [r, setR] = useState(null)
  useEffect(() => {
    fetch('/api/tennis/track-record').then(x => x.json()).then(setR).catch(() => {})
  }, [])
  if (!r) return null
  const small = !r.n || r.n < 50
  return (
    <div style={{ margin: '14px 0', padding: '12px 18px', borderRadius: 8, border: '1px solid var(--line)', background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))' }}>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>
        Tennis forward record <span style={{ color: 'var(--text-tertiary)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>— started 2026-09-06 · every priced prediction frozen before first serve, graded from real results</span>
      </div>
      <div className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 6, lineHeight: 1.6 }}>
        {r.n ? (
          <>
            model {(100 * r.model_accuracy).toFixed(1)}% vs market {(100 * r.market_accuracy).toFixed(1)}% on {r.n} settled ·
            flat-pick ROI {r.flat_roi_pct > 0 ? '+' : ''}{r.flat_roi_pct}% ·
            disagreements: {r.n_disagree}{r.disagree_flat_roi_pct != null ? ` (model ${(100 * r.disagree_model_accuracy).toFixed(0)}% right, ROI ${r.disagree_flat_roi_pct > 0 ? '+' : ''}${r.disagree_flat_roi_pct}%)` : ''}
          </>
        ) : (
          <>{r.total_logged || 0} predictions logged · {r.settled || 0} settled — the ledger just started; numbers appear as matches finish.</>
        )}
        {small ? <span style={{ color: '#f85149', fontWeight: 700 }}> · UNPROVEN — this model has never been graded before; do not bet tennis until this record earns it (±{r.n ? Math.round(200 / Math.sqrt(r.n)) : '∞'}pt noise band)</span> : null}
      </div>
    </div>
  )
}

// Cross-book price-edge scanner (2026-09-09): the 2026 backtests showed every public stat
// is already in the price — the one path that needs no model is a bettable book lagging the
// sharp consensus (Pinnacle/Circa de-vigged). The backend scans ATP/WTA/Challenger/ITF and
// flags any bettable side priced ≥2pts better than sharp fair (longshots under 25% fair
// excluded — de-vig math is least trustworthy there). Every flag is frozen at first serve
// into a flat-1u forward record with CLV vs the closing sharp fair. Checkpoint: 75 settled.
const SCAN_LEAGUE_LABEL = { atp: 'ATP', wta: 'WTA', atp_challenger: 'CHALLENGER', itf_men: 'ITF M', itf_women: 'ITF W' }

function PriceEdgeScanner({ scan }) {
  const [rec, setRec] = useState(null)
  useEffect(() => {
    fetch('/api/tennis/scanner-record').then(x => x.json()).then(setRec).catch(() => {})
  }, [])
  const gold = '#e3b341'
  const edges = scan?.edges ?? []
  return (
    <div style={{ margin: '14px 0', padding: '12px 18px', borderRadius: 8, border: `1px solid ${gold}55`, background: `linear-gradient(180deg, ${gold}0d, var(--panel))` }}>
      <div className="mono" style={{ fontSize: 10, color: gold, textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>
        Cross-book price scanner <span style={{ color: 'var(--text-tertiary)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>— pre-registered experiment · a bettable book ≥2pts better than the sharp (Pinnacle/Circa) de-vigged consensus · ATP · WTA · Challenger · ITF</span>
      </div>
      {scan ? (
        <div className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 6 }}>
          scanned {scan.scanned} matches · {scan.priced} priced by a sharp book · {edges.length} flag{edges.length === 1 ? '' : 's'}
          {edges.length === 0 && <span style={{ color: 'var(--text-tertiary)' }}> — no book is lagging the sharp consensus right now (a typical price runs ~3–4pts worse than fair; that gap is the vig)</span>}
        </div>
      ) : (
        <div className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 6 }}>scan unavailable — appears with today's slate.</div>
      )}
      {edges.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 10 }}>
          {edges.map((e, i) => (
            <div key={`${e.fixture_id}_${e.side}`} className="mono" style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10, flexWrap: 'wrap',
              padding: '8px 12px', borderRadius: 6, border: `1px solid ${gold}44`, background: `${gold}0a`, fontSize: 11,
            }}>
              <span>
                <span style={{ color: gold, fontWeight: 700, fontSize: 9, letterSpacing: '0.05em' }}>{SCAN_LEAGUE_LABEL[e.league] || e.league}</span>
                <span style={{ color: 'var(--text-secondary)' }}> {e.player_1} vs {e.player_2}</span>
                <span style={{ color: 'var(--text-tertiary)', fontSize: 10 }}> · {e.tournament}</span>
              </span>
              <span style={{ whiteSpace: 'nowrap' }}>
                <span style={{ color: 'var(--text-primary)', fontWeight: 700 }}>{e.side_player}</span>
                <span style={{ color: 'var(--text-secondary)' }}> {fmtPrice(e.price)} @ {e.book}</span>
                <span style={{ color: 'var(--edge-pos)', fontWeight: 700 }}> +{(100 * e.edge).toFixed(1)}pt</span>
                <span style={{ color: 'var(--text-tertiary)', fontSize: 10 }}> vs fair {(100 * e.fair_prob).toFixed(0)}%</span>
                {e.fair_move != null && Math.abs(e.fair_move) >= 0.005 && (
                  <span style={{ color: e.fair_move > 0 ? 'var(--edge-pos)' : 'var(--edge-neg)', fontSize: 10 }}>
                    {' '}· fair {e.fair_move > 0 ? '↑' : '↓'}{Math.abs(100 * e.fair_move).toFixed(1)} since first seen
                  </span>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 8, lineHeight: 1.5 }}>
        {rec?.overall ? (
          <>
            record: {rec.overall.n} settled of {rec.total_flagged} flagged · win {(100 * rec.overall.win_rate).toFixed(0)}% (fair promised {(100 * rec.overall.avg_fair_promised).toFixed(0)}%) ·
            flat ROI {rec.overall.flat_roi_pct > 0 ? '+' : ''}{rec.overall.flat_roi_pct}% · CLV {rec.overall.avg_clv_pt > 0 ? '+' : ''}{rec.overall.avg_clv_pt}pt · beat close {rec.overall.beat_close_pct}%
          </>
        ) : (
          <>record: {rec?.total_flagged ?? 0} flagged · {rec?.settled ?? 0} settled — starts empty, grows as flags settle.</>
        )}
        {!rec?.proven && <span style={{ color: '#f85149', fontWeight: 700 }}> · SHADOW ONLY — flat 1u, judged at {rec?.checkpoint_n ?? 75} settled; prices move fast, CLV is the health metric. Do not bet this yet.</span>}
      </div>
    </div>
  )
}

export default function TennisSection() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => { fetchTennis() }, [])

  async function fetchTennis() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/tennis/today')
      if (!res.ok) throw new Error(`API returned ${res.status}`)
      setData(await res.json())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const matches = data?.matches ?? []
  const withPrediction = matches.filter(m => m.prediction)
  const withoutPrediction = matches.filter(m => !m.prediction)
  const sorted = useMemo(
    () => [...withPrediction].sort((a, b) =>
      Math.abs(b.prediction.player_1_win_prob - 0.5) - Math.abs(a.prediction.player_1_win_prob - 0.5)
    ),
    [withPrediction]
  )

  return (
    <div>
      <div style={{
        marginTop: 20, padding: '10px 16px', borderRadius: 6,
        background: 'rgba(140,140,150,0.06)', border: '1px solid var(--line)',
        fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.5,
      }}>
        Built from free historical match data (surface record, Elo, opponent quality, head-to-head,
        rest days). Backtested against the market and does not beat it — serve/return stats were also
        tested (two held-out seasons) and turned out fully priced in as well. Treat predictions as a
        second opinion; the price scanner below is the only tennis signal being forward-tested as a bet.
      </div>

      <TennisTrackRecord />

      <PriceEdgeScanner scan={data?.price_scan} />

      {error && (
        <div style={{
          background: 'rgba(255,92,92,0.08)', border: '1px solid var(--edge-neg)',
          borderRadius: 8, padding: '14px 18px', margin: '20px 0', color: 'var(--edge-neg)',
          fontSize: 14, fontFamily: 'var(--font-mono)',
        }}>
          Couldn't reach /api/tennis/today — is the backend running? ({error})
        </div>
      )}

      {loading && (
        <div style={{ color: 'var(--text-secondary)', padding: '60px 0', textAlign: 'center', fontFamily: 'var(--font-mono)' }}>
          loading today's matches…
        </div>
      )}

      {!loading && !error && matches.length === 0 && (
        <div style={{ color: 'var(--text-secondary)', padding: '60px 0', textAlign: 'center' }}>
          No ATP/WTA singles matches found for today.
        </div>
      )}

      {!loading && !error && matches.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 16 }}>
          {sorted.map((m, i) => (
            <MatchCard key={m.fixture_id} match={m} animDelay={Math.min(i * 0.04, 0.3)} />
          ))}
          {withoutPrediction.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>
                no prediction available ({withoutPrediction.length})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {withoutPrediction.map(m => <NoPredictionRow key={m.fixture_id} match={m} />)}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function NoPredictionRow({ match }) {
  return (
    <div style={{
      background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 8,
      padding: '10px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap',
    }}>
      <span className="mono" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
        {match.player_1} vs {match.player_2}
        <span style={{ color: 'var(--text-tertiary)' }}> — {match.tournament}</span>
      </span>
      <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>{match.note}</span>
    </div>
  )
}

function MatchCard({ match, animDelay }) {
  const [showFeatures, setShowFeatures] = useState(false)
  const pred = match.prediction
  const leagueColor = LEAGUE_COLOR[match.league] || 'var(--amber)'
  const surfaceColor = SURFACE_COLOR[match.surface] || 'var(--text-tertiary)'

  const p1Prob = pred.player_1_win_prob
  const favoredIsP1 = p1Prob >= 0.5
  const favoredName = favoredIsP1 ? match.player_1 : match.player_2
  const favoredProb = favoredIsP1 ? p1Prob : 1 - p1Prob

  const odds = match.live_odds
  const marketFavoredProb = useMemo(() => {
    if (!odds) return null
    const p1Implied = americanOddsToImpliedProb(String(odds.player_1))
    const p2Implied = americanOddsToImpliedProb(String(odds.player_2))
    if (p1Implied == null || p2Implied == null) return null
    // de-vig
    const total = p1Implied + p2Implied
    const p1Fair = p1Implied / total
    return favoredIsP1 ? p1Fair : 1 - p1Fair
  }, [odds, favoredIsP1])

  const edge = marketFavoredProb != null ? favoredProb - marketFavoredProb : null

  return (
    <div className="game-card card-enter" style={{
      background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 10,
      padding: '18px 20px 16px', borderLeft: `3px solid ${leagueColor}`,
      animationDelay: `${animDelay}s`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
        <span className="mono" style={{ fontSize: 10, color: leagueColor, fontWeight: 700, letterSpacing: '0.05em' }}>
          {match.league.toUpperCase()}
        </span>
        <span className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
          {match.tournament} · {match.round}
        </span>
        <span className="mono" style={{
          fontSize: 9, fontWeight: 700, letterSpacing: '0.05em', color: surfaceColor,
          border: `1px solid ${surfaceColor}`, borderRadius: 4, padding: '2px 6px',
        }} title={match.surface_estimated ? 'No exact tournament match in historical data — defaulted to the tour’s most common surface' : undefined}>
          {match.surface.toUpperCase()}{match.surface_estimated ? '?' : ''}
        </span>
      </div>

      <div className="mono" style={{ fontSize: 13, color: 'var(--text-primary)', marginTop: 8 }}>
        <span style={{ fontWeight: favoredIsP1 ? 700 : 400, color: favoredIsP1 ? leagueColor : 'var(--text-primary)' }}>{match.player_1}</span>
        <span style={{ color: 'var(--text-tertiary)' }}> vs </span>
        <span style={{ fontWeight: !favoredIsP1 ? 700 : 400, color: !favoredIsP1 ? leagueColor : 'var(--text-primary)' }}>{match.player_2}</span>
      </div>

      <div style={{
        marginTop: 14, padding: '14px 16px', borderRadius: 8,
        background: `linear-gradient(135deg, ${leagueColor}1c, ${leagueColor}0a)`, border: `1px solid ${leagueColor}55`,
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Favored:</span>
          <span style={{ fontSize: 18, fontWeight: 700, color: leagueColor, lineHeight: 1 }}>{favoredName}</span>
          <span className="mono" style={{
            fontSize: 30, fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1,
            fontFamily: 'var(--font-display)', letterSpacing: '-0.02em',
          }}>
            {(favoredProb * 100).toFixed(0)}<span style={{ fontSize: 16, opacity: 0.6 }}>%</span>
          </span>
          {edge != null && <EdgeBadge edge={edge} />}
        </div>
        {match.reason && (
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6, lineHeight: 1.4 }}>
            {match.reason}
          </div>
        )}
      </div>

      {odds && (
        <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 8 }}>
          market: {match.player_1} {fmtPrice(odds.player_1)} / {match.player_2} {fmtPrice(odds.player_2)} ({odds.bookmaker})
        </div>
      )}

      {match.features && (
        <div style={{ marginTop: 10 }}>
          <button onClick={() => setShowFeatures(s => !s)} style={{
            background: 'none', border: 'none', color: 'var(--text-tertiary)', fontSize: 10,
            fontFamily: 'var(--font-mono)', letterSpacing: '0.03em', padding: 0,
            display: 'inline-flex', alignItems: 'center', gap: 4, opacity: 0.75,
          }}>
            <span style={{ display: 'inline-block', transition: 'transform 0.15s', transform: showFeatures ? 'rotate(90deg)' : 'none' }}>▸</span>
            {showFeatures ? 'hide' : 'show'} model inputs
          </button>
          {showFeatures && <FeatureTable features={match.features} />}
        </div>
      )}
    </div>
  )
}

function fmtPrice(p) {
  if (p == null) return '—'
  return p > 0 ? `+${p}` : `${p}`
}

function EdgeBadge({ edge }) {
  const positive = edge > 0
  const pct = Math.abs(edge * 100).toFixed(1)
  return (
    <span className="mono" style={{
      fontSize: 11, fontWeight: 600, padding: '3px 8px', borderRadius: 5, marginLeft: 'auto',
      color: positive ? 'var(--edge-pos)' : 'var(--edge-neg)',
      background: positive ? 'rgba(61,220,132,0.1)' : 'rgba(255,92,92,0.1)',
      border: `1px solid ${positive ? 'var(--edge-pos)' : 'var(--edge-neg)'}`,
      whiteSpace: 'nowrap',
    }}>
      {positive ? '+' : '-'}{pct}% edge
    </span>
  )
}

const FEATURE_LABELS = {
  elo_diff: 'overall Elo',
  surface_elo_diff: 'surface Elo',
  surface_form_diff: 'surface form',
  overall_form_diff: 'overall form',
  opponent_quality_diff: 'opponent quality',
  h2h_diff: 'head-to-head',
  rest_days_diff: 'rest days',
  best_of_5: 'best of 5',
}

function FeatureTable({ features }) {
  return (
    <div style={{ marginTop: 8, borderTop: '1px solid var(--line)', paddingTop: 8 }}>
      {Object.entries(FEATURE_LABELS).map(([key, label]) => {
        const val = features[key]
        return (
          <div key={key} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
            <span className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{label}</span>
            <span className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
              {val == null ? '—' : typeof val === 'number' ? val.toFixed(2) : val}
            </span>
          </div>
        )
      })}
    </div>
  )
}
