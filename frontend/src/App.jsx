import React, { useEffect, useState, useMemo } from 'react'
import ProbabilityBar from './ProbabilityBar.jsx'
import ModelStatus from './ModelStatus.jsx'
import TrackRecord from './TrackRecord.jsx'
import StrikeoutTrackRecord from './StrikeoutTrackRecord.jsx'
import PitcherDetail from './PitcherDetail.jsx'
import TeamDetail from './TeamDetail.jsx'
import TennisSection from './TennisSection.jsx'
import HistorySection from './HistorySection.jsx'
import { americanOddsToImpliedProb } from './odds.js'
import { getTeamColor } from './teamColors.js'

const API_BASE = ''  // proxied to localhost:8000 via vite.config.js

const HIGH_CONVICTION_THRESHOLD = 0.20 // |home_win_prob - 0.5| at or above this gets a "top pick" badge
const SURE_CONVICTION_THRESHOLD = 0.08 // |home_win_prob - 0.5| at or above this, with no active caveats, counts as "sure"

export default function App() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [oddsByGame, setOddsByGame] = useState({}) // gamePk -> { home: "-130", away: "+110" }
  const [sortMode, setSortMode] = useState('confidence') // 'confidence' | 'time'
  const [betFilter, setBetFilter] = useState('all') // 'all' | 'sure' | 'unsure'
  const [selectedPitcher, setSelectedPitcher] = useState(null) // { id, name } | null
  const [selectedTeam, setSelectedTeam] = useState(null) // { abbr, color } | null
  const [sport, setSport] = useState('mlb') // 'mlb' | 'tennis'
  const [view, setView] = useState('today') // 'today' | 'history' (MLB only)

  useEffect(() => {
    fetchToday()
  }, [])

  async function fetchToday() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/api/today`)
      if (!res.ok) throw new Error(`API returned ${res.status}`)
      const json = await res.json()
      setData(json)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function updateOdds(gamePk, side, value) {
    setOddsByGame(prev => ({
      ...prev,
      [gamePk]: { ...prev[gamePk], [side]: value },
    }))
  }

  const games = data?.games ?? []

  // An opener-affected game's prediction is built around a pitcher who'll likely hand off
  // after 1-2 innings to a bulk/relief arm the model can't see at all — never trustworthy
  // enough to surface as a "top pick" or sort to the top of confidence mode, no matter how
  // decisive the raw number looks.
  const convictionOf = g => (g.prediction && !g.opener_affected) ? Math.abs(g.prediction.home_win_prob - 0.5) : -1

  // "Unsure" = any reason not to trust this pick at face value: no prediction yet, an opener
  // in play, an active pitcher_warnings caveat (thin sample, long layoff, IL return, prior-season
  // blend, rain risk...), incomplete underlying data, or just too close to a coin flip to act on
  // even with clean data. Everything else is "sure" — a real, uncaveated stat edge.
  const isUnsure = g => (
    !g.prediction ||
    g.opener_affected ||
    (g.pitcher_warnings && g.pitcher_warnings.length > 0) ||
    (g.data_quality && !g.data_quality.complete) ||
    convictionOf(g) < SURE_CONVICTION_THRESHOLD
  )

  const sortedGames = useMemo(() => {
    if (sortMode !== 'confidence') return games
    return [...games].sort((a, b) => convictionOf(b) - convictionOf(a))
  }, [games, sortMode])

  const filteredGames = useMemo(() => {
    if (betFilter === 'sure') return sortedGames.filter(g => g.prediction && !isUnsure(g))
    if (betFilter === 'unsure') return sortedGames.filter(g => g.prediction && isUnsure(g))
    return sortedGames
  }, [sortedGames, betFilter])

  return (
    <div className="scoreboard-bg" style={{ minHeight: '100vh', paddingBottom: 80 }}>
      <TopBar date={data?.date} onRefresh={fetchToday} loading={loading} sport={sport} onSportChange={setSport} />

      <main style={{ maxWidth: 920, margin: '0 auto', padding: '0 24px' }}>
        {sport === 'mlb' ? (
          <>
            <ModelStatus />
            <TrackRecord />
            <StrikeoutTrackRecord />
            <ViewToggle view={view} onChange={setView} />

            {view === 'history' ? (
              <HistorySection />
            ) : (
              <>
            {error && (
              <div style={{
                background: 'rgba(255,92,92,0.08)', border: '1px solid var(--edge-neg)',
                borderRadius: 8, padding: '14px 18px', margin: '20px 0', color: 'var(--edge-neg)',
                fontSize: 14, fontFamily: 'var(--font-mono)',
              }}>
                Couldn't reach the API at /api/today — is the backend running? ({error})
              </div>
            )}

            {loading && !data && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 20 }}>
                {[0, 1, 2].map(i => <GameCardSkeleton key={i} />)}
              </div>
            )}

            {!loading && !error && games.length === 0 && (
              <div style={{ color: 'var(--text-secondary)', padding: '60px 0', textAlign: 'center' }}>
                No games found for today.
              </div>
            )}

            {!loading && !error && games.length > 0 && (
              <>
                <SortToggle mode={sortMode} onChange={setSortMode} />
                <BetFilterToggle mode={betFilter} onChange={setBetFilter} counts={{
                  all: sortedGames.filter(g => g.prediction).length,
                  sure: sortedGames.filter(g => g.prediction && !isUnsure(g)).length,
                  unsure: sortedGames.filter(g => g.prediction && isUnsure(g)).length,
                }} />
              </>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 12 }}>
              {filteredGames.map((g, i) => (
                <GameCard
                  key={g.game_pk}
                  game={g}
                  odds={oddsByGame[g.game_pk] || {}}
                  onOddsChange={(side, val) => updateOdds(g.game_pk, side, val)}
                  highConviction={convictionOf(g) >= HIGH_CONVICTION_THRESHOLD}
                  onSelectPitcher={setSelectedPitcher}
                  onSelectTeam={setSelectedTeam}
                  animDelay={Math.min(i * 0.04, 0.3)}
                />
              ))}
            </div>
              </>
            )}
          </>
        ) : (
          <TennisSection />
        )}
      </main>

      {selectedPitcher && (
        <PitcherDetail
          pitcherId={selectedPitcher.id}
          pitcherName={selectedPitcher.name}
          onClose={() => setSelectedPitcher(null)}
        />
      )}
      {selectedTeam && (
        <TeamDetail
          teamAbbr={selectedTeam.abbr}
          teamColor={selectedTeam.color}
          onClose={() => setSelectedTeam(null)}
        />
      )}
    </div>
  )
}

function TopBar({ date, onRefresh, loading, sport, onSportChange }) {
  return (
    <header style={{
      borderBottom: '1px solid var(--line)', padding: '22px 24px',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      position: 'sticky', top: 0, zIndex: 10,
      background: 'rgba(11,15,20,0.85)', backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)',
    }}>
      <div style={{ maxWidth: 920, margin: '0 auto', width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <span style={{
            fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 20,
            letterSpacing: '-0.02em', color: 'var(--text-primary)',
          }}>
            MATCHUP <span style={{ color: 'var(--amber)', textShadow: '0 0 18px rgba(255,182,39,0.35)' }}>EDGE</span>
          </span>
          {sport === 'mlb' && (
            <span className="mono" style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
              {date || '—'}
            </span>
          )}
        </div>

        <SportTabs sport={sport} onChange={onSportChange} />

        {sport === 'mlb' && (
          <button onClick={onRefresh} disabled={loading} className="btn-ghost mono" style={{
            background: 'transparent', border: '1px solid var(--line)', borderRadius: 6,
            color: 'var(--text-secondary)', fontSize: 12, padding: '8px 14px',
            letterSpacing: '0.03em', display: 'inline-flex', alignItems: 'center', gap: 7,
          }}>
            <span style={{
              display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
              background: 'var(--amber)', animation: loading ? 'pulse-glow 1s ease-in-out infinite' : 'none',
              opacity: loading ? 1 : 0.4,
            }} />
            {loading ? 'REFRESHING…' : 'REFRESH'}
          </button>
        )}
      </div>
    </header>
  )
}

function SportTabs({ sport, onChange }) {
  const options = [
    { key: 'mlb', label: 'MLB' },
    { key: 'tennis', label: 'TENNIS' },
  ]
  return (
    <div style={{ display: 'flex', gap: 6 }}>
      {options.map(o => (
        <button key={o.key} onClick={() => onChange(o.key)} className={sport === o.key ? '' : 'btn-ghost'} style={{
          background: sport === o.key ? 'var(--panel-raised)' : 'transparent',
          border: `1px solid ${sport === o.key ? 'var(--amber)' : 'var(--line)'}`,
          borderRadius: 5, color: sport === o.key ? 'var(--amber)' : 'var(--text-secondary)',
          fontSize: 11, padding: '5px 12px', fontFamily: 'var(--font-mono)', letterSpacing: '0.03em',
        }}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

function ViewToggle({ view, onChange }) {
  const options = [
    { key: 'today', label: 'today' },
    { key: 'history', label: 'previous day' },
  ]
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 16 }}>
      {options.map(o => (
        <button key={o.key} onClick={() => onChange(o.key)} className={view === o.key ? '' : 'btn-ghost'} style={{
          background: view === o.key ? 'var(--panel-raised)' : 'transparent',
          border: `1px solid ${view === o.key ? 'var(--amber)' : 'var(--line)'}`,
          borderRadius: 5, color: view === o.key ? 'var(--amber)' : 'var(--text-secondary)',
          fontSize: 11, padding: '5px 12px', fontFamily: 'var(--font-mono)', letterSpacing: '0.03em',
        }}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

function GameCardSkeleton() {
  return (
    <div style={{
      background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 10,
      padding: '18px 20px 16px',
    }}>
      <div className="skeleton" style={{ width: 160, height: 16 }} />
      <div className="skeleton" style={{ width: 200, height: 12, marginTop: 10 }} />
      <div className="skeleton" style={{ width: '100%', height: 54, marginTop: 14, borderRadius: 8 }} />
      <div className="skeleton" style={{ width: '100%', height: 28, marginTop: 14, borderRadius: 6 }} />
    </div>
  )
}

function SortToggle({ mode, onChange }) {
  const options = [
    { key: 'confidence', label: 'confidence' },
    { key: 'time', label: 'game order' },
  ]
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 16 }}>
      <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        sort:
      </span>
      {options.map(o => (
        <button key={o.key} onClick={() => onChange(o.key)} className={mode === o.key ? '' : 'btn-ghost'} style={{
          background: mode === o.key ? 'var(--panel-raised)' : 'transparent',
          border: `1px solid ${mode === o.key ? 'var(--amber)' : 'var(--line)'}`,
          borderRadius: 5, color: mode === o.key ? 'var(--amber)' : 'var(--text-secondary)',
          fontSize: 11, padding: '4px 10px', fontFamily: 'var(--font-mono)',
        }}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

function BetFilterToggle({ mode, onChange, counts }) {
  const options = [
    { key: 'all', label: 'all', count: counts.all },
    { key: 'sure', label: 'bet', count: counts.sure, color: 'var(--edge-pos)' },
    { key: 'unsure', label: 'not bet', count: counts.unsure, color: 'var(--text-tertiary)' },
  ]
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
      <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        show:
      </span>
      {options.map(o => (
        <button key={o.key} onClick={() => onChange(o.key)} className={mode === o.key ? '' : 'btn-ghost'} style={{
          background: mode === o.key ? 'var(--panel-raised)' : 'transparent',
          border: `1px solid ${mode === o.key ? (o.color || 'var(--amber)') : 'var(--line)'}`,
          borderRadius: 5, color: mode === o.key ? (o.color || 'var(--amber)') : 'var(--text-secondary)',
          fontSize: 11, padding: '4px 10px', fontFamily: 'var(--font-mono)',
        }}>
          {o.label} ({o.count})
        </button>
      ))}
    </div>
  )
}

function TeamChip({ abbr, color, onSelect }) {
  return (
    <span
      onClick={onSelect ? () => onSelect({ abbr, color }) : undefined}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        cursor: onSelect ? 'pointer' : 'default',
        textDecoration: onSelect ? 'underline' : 'none', textDecorationStyle: 'dotted', textUnderlineOffset: 3,
      }}
      title={onSelect ? `View ${abbr}'s team snapshot` : undefined}
    >
      <span style={{ width: 8, height: 8, borderRadius: 2, background: color, flexShrink: 0 }} />
      {abbr}
    </span>
  )
}

function PitcherLink({ id, name, onSelect }) {
  if (!name) return <span>TBD</span>
  if (!id || !onSelect) return <span>{name}</span>
  return (
    <span
      onClick={() => onSelect({ id, name })}
      style={{ cursor: 'pointer', textDecoration: 'underline', textDecorationStyle: 'dotted', textUnderlineOffset: 3 }}
      title={`View ${name}'s season trend`}
    >
      {name}
    </span>
  )
}

function GameCard({ game, odds, onOddsChange, highConviction, onSelectPitcher, onSelectTeam, animDelay = 0 }) {
  const [showMarket, setShowMarket] = useState(false)
  const [showStats, setShowStats] = useState(false)
  const [showLineup, setShowLineup] = useState(false)
  const [showRating, setShowRating] = useState(false)
  const [showInjuries, setShowInjuries] = useState(false)
  const pred = game.prediction
  const liveOdds = game.live_odds

  const awayColor = getTeamColor(game.away_team_abbr)
  const homeColor = getTeamColor(game.home_team_abbr)

  const modelHomeProb = pred?.home_win_prob ?? null
  const source = pred ? 'pitching model' : null

  // Manual entry overrides live odds when present; otherwise fall back to the live line.
  const effectiveHomeOdds = odds.home || (liveOdds ? String(liveOdds.home) : '')
  const effectiveAwayOdds = odds.away || (liveOdds ? String(liveOdds.away) : '')
  const usingLiveOdds = !odds.home && !odds.away && !!liveOdds

  const marketHomeProb = useMemo(() => {
    if (!effectiveHomeOdds) return null
    return americanOddsToImpliedProb(effectiveHomeOdds)
  }, [effectiveHomeOdds])

  const edge = (modelHomeProb != null && marketHomeProb != null)
    ? modelHomeProb - marketHomeProb
    : null

  // The favorite call-out is derived ONLY from modelHomeProb (season/recent
  // FIP, K-BB%, bullpen, opponent lineup, park factor, rest days). It never
  // looks at odds; a team can be the market favorite and still be the
  // pitching-matchup underdog here, and that's the point of the app.
  const favoredIsHome = modelHomeProb != null ? modelHomeProb >= 0.5 : null
  const favoredTeam = favoredIsHome == null ? null : (favoredIsHome ? game.home_team_abbr : game.away_team_abbr)
  const favoredProb = favoredIsHome == null ? null : (favoredIsHome ? modelHomeProb : 1 - modelHomeProb)
  const favoredColor = favoredIsHome == null ? 'var(--amber)' : (favoredIsHome ? homeColor : awayColor)

  const hasStats = !!(game.recent_form || game.season_stats || game.h2h)

  return (
    <div className="game-card card-enter" style={{
      background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 10,
      padding: '18px 20px 16px',
      borderLeft: `3px solid ${favoredColor}`,
      animationDelay: `${animDelay}s`,
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 6 }}>
          <TeamChip abbr={game.away_team_abbr} color={awayColor} onSelect={onSelectTeam} />
          <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>@</span>
          <TeamChip abbr={game.home_team_abbr} color={homeColor} onSelect={onSelectTeam} />
        </div>
        {highConviction && (
          <span className="mono top-pick-badge" style={{
            fontSize: 9, fontWeight: 700, letterSpacing: '0.06em', color: 'var(--amber)',
            border: '1px solid var(--amber)', borderRadius: 4, padding: '2px 6px',
          }}>
            TOP PICK
          </span>
        )}
      </div>
      <div className="mono" style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
        <PitcherLink id={game.away_pitcher_id} name={game.away_pitcher_name} onSelect={onSelectPitcher} />
        <span style={{ color: 'var(--text-tertiary)' }}> vs </span>
        <PitcherLink id={game.home_pitcher_id} name={game.home_pitcher_name} onSelect={onSelectPitcher} />
      </div>

      {game.pitcher_warnings && <PitcherWarnings warnings={game.pitcher_warnings} />}
      {game.data_quality && !game.data_quality.complete && (
        <DataQualityWarning dataQuality={game.data_quality} />
      )}

      {pred ? (
        <>
          {favoredTeam && (
            <FavoredCallout
              team={favoredTeam} prob={favoredProb} source={source} reason={game.reason}
              overridden={pred?.overridden} modelProb={pred?.model_home_win_prob}
              favoredIsHome={favoredIsHome} color={favoredColor}
            />
          )}

          <div style={{ marginTop: 14 }}>
            <ProbabilityBar
              awayLabel={game.away_team_abbr}
              homeLabel={game.home_team_abbr}
              homeProb={modelHomeProb}
              marketHomeProb={showMarket ? marketHomeProb : null}
              awayColor={awayColor}
              homeColor={homeColor}
            />
          </div>

          {game.market_model_prob != null && (
            <div
              className="mono"
              style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 4 }}
              title="A second model, trained on the same baseball features PLUS line movement and other market-derived signals — shown for comparison only, never the number driving the prediction above. A big gap here means the market may know something the baseball features alone don't (or vice versa)."
            >
              market-aware model: {game.market_model_prob >= 0.5 ? game.home_team_abbr : game.away_team_abbr}{' '}
              {((game.market_model_prob >= 0.5 ? game.market_model_prob : 1 - game.market_model_prob) * 100).toFixed(0)}%
            </div>
          )}

          {hasStats && (
            <div style={{ marginTop: 12 }}>
              <ToggleLink onClick={() => setShowStats(s => !s)} open={showStats} label="pitcher stats" />
              {showStats && (
                <div style={{ marginTop: 8 }}>
                  {game.recent_form && (
                    <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                      <RecentFormLine stats={game.recent_form.away} />
                      <RecentFormLine stats={game.recent_form.home} />
                    </div>
                  )}
                  {game.season_stats && (
                    <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 3 }}>
                      <SeasonStatsLine stats={game.season_stats.away} />
                      <SeasonStatsLine stats={game.season_stats.home} />
                    </div>
                  )}
                  {game.h2h && (
                    <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 3 }}>
                      <H2HLine stats={game.h2h.away} oppAbbr={game.home_team_abbr} />
                      <H2HLine stats={game.h2h.home} oppAbbr={game.away_team_abbr} />
                    </div>
                  )}
                  {game.team_stats && (
                    <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 3 }}>
                      <TeamStatsLine label={game.away_team_abbr} stats={game.team_stats.away} />
                      <TeamStatsLine label={game.home_team_abbr} stats={game.team_stats.home} />
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {game.lineup_breakdown && (game.lineup_breakdown.home?.batters?.length > 0 || game.lineup_breakdown.away?.batters?.length > 0) && (
            <div style={{ marginTop: 8 }}>
              <ToggleLink onClick={() => setShowLineup(s => !s)} open={showLineup} label="lineup" />
              {showLineup && (
                <div style={{ marginTop: 8 }}>
                  <LineupBreakdown label={game.away_team_abbr} batters={game.lineup_breakdown.away?.batters} predicted={game.lineup_breakdown.away?.predicted} />
                  <LineupBreakdown label={game.home_team_abbr} batters={game.lineup_breakdown.home?.batters} predicted={game.lineup_breakdown.home?.predicted} />
                </div>
              )}
            </div>
          )}

          {game.rating_breakdown && (
            <div style={{ marginTop: 8 }}>
              <ToggleLink onClick={() => setShowRating(s => !s)} open={showRating} label="rating breakdown" />
              {showRating && (
                <RatingBreakdown
                  rating={game.rating_breakdown}
                  homeAbbr={game.home_team_abbr}
                  awayAbbr={game.away_team_abbr}
                />
              )}
            </div>
          )}

          {game.injuries && ((game.injuries.home?.length > 0) || (game.injuries.away?.length > 0)) && (
            <div style={{ marginTop: 8 }}>
              <ToggleLink onClick={() => setShowInjuries(s => !s)} open={showInjuries} label="injury report" />
              {showInjuries && (
                <div style={{ marginTop: 8 }}>
                  <InjuryReport label={game.away_team_abbr} injuries={game.injuries.away} />
                  <InjuryReport label={game.home_team_abbr} injuries={game.injuries.home} />
                </div>
              )}
            </div>
          )}

          {game.strikeout_predictions && (
            <StrikeoutPropsTable
              awayName={game.away_pitcher_name} homeName={game.home_pitcher_name}
              away={game.strikeout_predictions.away} home={game.strikeout_predictions.home}
            />
          )}

          <div style={{ marginTop: 10 }}>
            <ToggleLink onClick={() => setShowMarket(s => !s)} open={showMarket} label="market odds" />
          </div>

          {showMarket && (
            <div style={{ marginTop: 8, borderTop: '1px solid var(--line)', paddingTop: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                <span className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                  {usingLiveOdds && (
                    <span>
                      live odds: {liveOdds.away > 0 ? `+${liveOdds.away}` : liveOdds.away} / {liveOdds.home > 0 ? `+${liveOdds.home}` : liveOdds.home} ({liveOdds.bookmaker})
                    </span>
                  )}
                </span>
                {edge != null && <EdgeBadge edge={edge} />}
              </div>
              <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
                <OddsInput
                  label={`${game.away_team_abbr} ML`}
                  value={odds.away || ''}
                  placeholder={liveOdds ? String(liveOdds.away) : '-130'}
                  onChange={v => onOddsChange('away', v)}
                />
                <OddsInput
                  label={`${game.home_team_abbr} ML`}
                  value={odds.home || ''}
                  placeholder={liveOdds ? String(liveOdds.home) : '-130'}
                  onChange={v => onOddsChange('home', v)}
                />
              </div>
              {game.book_odds && Object.keys(game.book_odds).length > 0 && (
                <BookByBookOdds bookOdds={game.book_odds} awayAbbr={game.away_team_abbr} homeAbbr={game.home_team_abbr} />
              )}
            </div>
          )}
        </>
      ) : (
        <div className="mono" style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 14 }}>
          {game.note || 'Prediction unavailable — probable pitchers not yet confirmed.'}
        </div>
      )}
    </div>
  )
}

function ToggleLink({ onClick, open, label }) {
  return (
    <button onClick={onClick} style={{
      background: 'none', border: 'none', color: 'var(--text-tertiary)', fontSize: 10,
      fontFamily: 'var(--font-mono)', letterSpacing: '0.03em', padding: 0,
      display: 'inline-flex', alignItems: 'center', gap: 4, opacity: 0.75,
    }}>
      <span style={{ display: 'inline-block', transition: 'transform 0.15s', transform: open ? 'rotate(90deg)' : 'none' }}>▸</span>
      {open ? 'hide' : 'show'} {label}
    </button>
  )
}

function StrikeoutPropsTable({ awayName, homeName, away, home }) {
  if (!away && !home) return null
  return (
    <div style={{ marginTop: 14, borderTop: '1px solid var(--line)', paddingTop: 12 }}>
      <div className="mono" style={{
        fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase',
        letterSpacing: '0.05em', marginBottom: 8,
      }}>
        strikeout props
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(90px,1.4fr) 0.9fr 0.9fr 0.8fr 0.8fr 1.1fr', gap: '4px 10px', alignItems: 'center' }}>
        <StrikeoutPropRow name={awayName} prop={away} />
        <StrikeoutPropRow name={homeName} prop={home} />
      </div>
    </div>
  )
}

function StrikeoutPropRow({ name, prop }) {
  if (!prop) return null
  const overPct = Math.round(prop.over_prob * 100)
  const underPct = Math.round(prop.under_prob * 100)
  const leanOver = prop.over_prob >= 0.5
  const fmtPrice = p => (p == null ? '—' : p > 0 ? `+${p}` : `${p}`)

  const pp = prop.prizepicks
  const ppLineDiffers = pp && pp.line !== prop.line

  return (
    <>
      <span className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{name || 'TBD'}</span>
      <span className="mono" style={{ fontSize: 11, color: 'var(--text-primary)' }}>{prop.predicted} K</span>
      <span className="mono" style={{ fontSize: 11, color: 'var(--text-primary)' }}>
        O/U {prop.line}
        {prop.line_source === 'model' && (
          <span style={{ color: 'var(--text-tertiary)' }} title="No sportsbook line posted yet — model-generated line">*</span>
        )}
      </span>
      <span className="mono" style={{ fontSize: 11, color: leanOver ? 'var(--edge-pos)' : 'var(--text-tertiary)' }}>
        o {overPct}%
      </span>
      <span className="mono" style={{ fontSize: 11, color: !leanOver ? 'var(--edge-pos)' : 'var(--text-tertiary)' }}>
        u {underPct}%
      </span>
      <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
        {prop.bookmaker ? `${prop.bookmaker} ${fmtPrice(prop.over_price)}/${fmtPrice(prop.under_price)}` : '—'}
      </span>
      {pp && <PrizePicksLine pp={pp} differs={ppLineDiffers} />}
      {prop.market_model_predicted_k != null && (
        <div
          className="mono"
          style={{ gridColumn: '1 / -1', fontSize: 10, color: 'var(--text-tertiary)', marginTop: -2, marginBottom: 2, paddingLeft: 2 }}
          title="A second model, trained on the same baseball features PLUS this pitcher's own posted player-prop lines (outs/earned runs/hits allowed) — shown for comparison only, never the number driving the prediction above."
        >
          market-aware model: {prop.market_model_predicted_k} K
        </div>
      )}
    </>
  )
}

function PrizePicksLine({ pp, differs }) {
  const ppOverPct = Math.round(pp.over_prob * 100)
  const ppLeanOver = pp.over_prob >= 0.5
  return (
    <div style={{
      gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: 8,
      marginTop: -2, marginBottom: 2, paddingLeft: 2,
    }}>
      <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
        PrizePicks O/U{' '}
        <span style={{ color: differs ? 'var(--amber)' : 'var(--text-tertiary)', fontWeight: differs ? 700 : 400 }}>
          {pp.line}
        </span>
        {differs && <span style={{ color: 'var(--amber)' }} title="Differs from the sportsbook line above"> ⚠</span>}
        {' '}
        <span style={{ color: ppLeanOver ? 'var(--edge-pos)' : 'var(--text-tertiary)' }}>o {ppOverPct}%</span>
        {' / '}
        <span style={{ color: !ppLeanOver ? 'var(--edge-pos)' : 'var(--text-tertiary)' }}>u {100 - ppOverPct}%</span>
      </span>
      {pp.deep_link && (
        <a href={pp.deep_link} target="_blank" rel="noopener noreferrer" className="mono"
           style={{ fontSize: 10, color: 'var(--amber)', textDecoration: 'underline' }}>
          open in PrizePicks ↗
        </a>
      )}
    </div>
  )
}

function PitcherWarnings({ warnings }) {
  return (
    <div style={{
      marginTop: 8, padding: '8px 12px', borderRadius: 6,
      background: 'rgba(255,182,39,0.06)', border: '1px solid rgba(255,182,39,0.25)',
    }}>
      {warnings.map((w, i) => (
        <div key={i} style={{ fontSize: 11, color: 'var(--amber)', lineHeight: 1.4, display: 'flex', gap: 6 }}>
          <span>⚠</span>
          <span style={{ color: 'var(--text-secondary)' }}>{w}</span>
        </div>
      ))}
    </div>
  )
}

function DataQualityWarning({ dataQuality }) {
  return (
    <div
      title={`${dataQuality.completeness_pct}% of model features available for this matchup`}
      style={{
        marginTop: 8, padding: '8px 12px', borderRadius: 6,
        background: 'rgba(140,140,150,0.08)', border: '1px solid var(--line)',
      }}
    >
      <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.4, display: 'flex', gap: 6 }}>
        <span style={{ color: 'var(--text-tertiary)' }}>◐</span>
        <span>
          Incomplete data this refresh — missing {dataQuality.missing_labels.join(', ')}.
          Prediction below is based on the remaining {dataQuality.completeness_pct}% of signals.
        </span>
      </div>
    </div>
  )
}

export function RecentFormLine({ stats }) {
  if (!stats || !stats.sample_size || stats.era == null || Number.isNaN(stats.era)) {
    return <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>last 5: n/a</span>
  }
  const fip = stats.fip != null ? stats.fip.toFixed(2) : '—'
  const unit = stats.sample_type === 'appearances' ? 'outings (incl. relief)' : 'starts'
  return (
    <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }} title="FIP drives the prediction, not ERA — ERA over a handful of outings is easily skewed by defense/luck">
      last {stats.sample_size} {unit}: {fip} FIP ({stats.era.toFixed(2)} ERA) · {stats.k9.toFixed(1)} K/9 · {stats.bb9.toFixed(1)} BB/9
    </span>
  )
}

export function SeasonStatsLine({ stats }) {
  if (!stats || stats.era == null) {
    return <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>season: n/a</span>
  }
  const fip = stats.fip != null ? stats.fip.toFixed(2) : '—'
  const kbb = stats.k_bb_pct != null ? stats.k_bb_pct.toFixed(1) : '—'
  return (
    <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
      season: {stats.era.toFixed(2)} ERA · {fip} FIP · {kbb}% K-BB
    </span>
  )
}

export function TeamStatsLine({ label, stats }) {
  if (!stats) {
    return <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>{label} team: n/a</span>
  }
  const avg = stats.season_avg != null ? stats.season_avg.toFixed(3) : '—'
  const woba = stats.season_woba != null ? stats.season_woba.toFixed(3) : '—'
  const kPct = stats.season_k_pct != null ? `${stats.season_k_pct.toFixed(1)}%` : '—'
  const bullpenFip = stats.bullpen_fip != null ? stats.bullpen_fip.toFixed(2) : '—'
  const bullpenEra = stats.bullpen_era != null ? stats.bullpen_era.toFixed(2) : '—'
  const hlBullpenFip = stats.high_leverage_bullpen_fip != null ? stats.high_leverage_bullpen_fip.toFixed(2) : '—'
  const recentAvg = stats.recent_batting_avg != null ? stats.recent_batting_avg.toFixed(3) : '—'
  return (
    <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
      {label} team: {avg} AVG · {woba} wOBA · {kPct} K · {recentAvg} AVG last 7 · pen {bullpenFip} FIP / {bullpenEra} ERA ({hlBullpenFip} high-lev)
    </span>
  )
}

export function LineupBreakdown({ label, batters, predicted }) {
  if (!batters || batters.length === 0) {
    return (
      <div style={{ marginBottom: 8 }}>
        <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 700 }}>{label}</div>
        <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>lineup not posted yet</div>
      </div>
    )
  }
  return (
    <div style={{ marginBottom: 8 }}>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 700, marginBottom: 2 }}>
        {label}
        {predicted && (
          <span style={{ color: 'var(--amber)', fontWeight: 400, marginLeft: 6 }} title="Not officially posted yet — best guess from this team's last 5 games' actual batting orders">
            (predicted)
          </span>
        )}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {batters.map((b, i) => {
          const seasonAvg = b.season_avg != null ? b.season_avg.toFixed(3) : '—'
          const vsHandAvg = b.vs_hand_avg != null ? b.vs_hand_avg.toFixed(3) : '—'
          const thinSample = b.vs_hand_pa != null && b.vs_hand_pa < 20
          return (
            <div key={b.batter_id || i} className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', display: 'flex', gap: 6 }}>
              <span style={{ width: 14, color: 'var(--text-tertiary)', opacity: 0.6 }}>{i + 1}.</span>
              <span style={{ flex: 1, color: 'var(--text-secondary)' }}>{b.name || `#${b.batter_id}`} ({b.hand})</span>
              <span>{seasonAvg} AVG</span>
              <span title={thinSample ? `only ${b.vs_hand_pa} PA against this hand — small sample` : `${b.vs_hand_pa} PA against this hand`}>
                {vsHandAvg} vs-hand{thinSample && b.vs_hand_pa > 0 ? '*' : ''}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function H2HLine({ stats, oppAbbr }) {
  if (!stats || !stats.starts) {
    return <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>vs {oppAbbr}: no starts on record (2025-2026)</span>
  }
  const fip = stats.fip != null ? stats.fip.toFixed(2) : '—'
  const era = stats.era != null ? stats.era.toFixed(2) : '—'
  return (
    <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }} title="Info only — not used in the prediction. Backtested and found to hurt accuracy, likely because MLB rosters/matchups change too much year to year for a small head-to-head sample to beat season/recent form.">
      vs {oppAbbr}: {stats.starts} start{stats.starts !== 1 ? 's' : ''}, {fip} FIP ({era} ERA)
    </span>
  )
}

// Display-only book-by-book comparison (see odds_fetcher.get_consensus_odds's book_probs) — each
// CONSENSUS_BOOKS member's own current devigged home win probability, for line-shopping
// transparency. The model's consensus_prob_diff/book_disagreement features are derived from
// this same data, but this table itself isn't a model input.
function BookByBookOdds({ bookOdds, awayAbbr, homeAbbr }) {
  const entries = Object.entries(bookOdds).sort((a, b) => b[1] - a[1])
  return (
    <div style={{ marginTop: 12, borderTop: '1px solid var(--line)', paddingTop: 10 }}>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 700, marginBottom: 4 }}>
        book-by-book ({homeAbbr} win prob)
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {entries.map(([book, prob]) => (
          <div key={book} className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', display: 'flex', gap: 6 }}>
            <span style={{ flex: 1, color: 'var(--text-secondary)' }}>{book}</span>
            <span>{awayAbbr} {((1 - prob) * 100).toFixed(0)}%</span>
            <span style={{ width: 8 }} />
            <span>{homeAbbr} {(prob * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// Display-only, live-only real-time injury report (see odds_fetcher.get_active_injuries) — not
// fed into any prediction, since OpticOdds' /injuries endpoint has no historical query support
// and so can't be reconstructed walk-forward-safely for training. Pure roster-context transparency.
export function InjuryReport({ label, injuries }) {
  if (!injuries || injuries.length === 0) {
    return (
      <div style={{ marginBottom: 8 }}>
        <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 700 }}>{label}</div>
        <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>no injuries listed</div>
      </div>
    )
  }
  return (
    <div style={{ marginBottom: 8 }}>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 700, marginBottom: 2 }}>{label}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {injuries.map((inj, i) => (
          <div key={i} className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', display: 'flex', gap: 6 }}>
            <span style={{ flex: 1, color: 'var(--text-secondary)' }}>
              {inj.player}{inj.position ? ` (${inj.position})` : ''}
            </span>
            <span style={{ color: 'var(--edge-neg)' }}>{inj.status}</span>
            <span>{inj.type}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

const RATING_CATEGORY_LABELS = {
  starting_pitcher_quality: 'Starting pitcher quality',
  bullpen_availability: 'Bullpen availability',
  batter_pitch_type_matchup: 'Batter vs pitch-type matchup',
  weather_and_park: 'Weather & park factors',
  official_lineups: 'Official lineups',
  team_offense_30d: 'Team offense (30d)',
  defensive_metrics: 'Defensive metrics',
  market_movement: 'Betting market movement',
  travel_fatigue: 'Travel & fatigue',
}

// Display-only: a separate, hand-weighted rating system using the categories/priority order the
// user specified directly, not the trained model's own learned weights. Backtested SEPARATELY
// and found less accurate than the trained model above (see rating_system.py) — this exists for
// transparent reasoning ("why"), not as a second prediction to trust over the main one.
export function RatingBreakdown({ rating, homeAbbr, awayAbbr }) {
  if (!rating || !rating.category_contributions) return null
  const entries = Object.entries(rating.category_contributions).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
  const favoredIsHome = rating.home_win_prob >= 0.5
  const favored = favoredIsHome ? homeAbbr : awayAbbr
  const favoredProb = favoredIsHome ? rating.home_win_prob : rating.away_win_prob
  return (
    <div
      style={{ marginTop: 8 }}
      title="A separate rating system, hand-weighted by your own stated priority order (pitcher quality first, then bullpen, matchups, etc.) — for transparent reasoning, not the number driving the prediction above. Backtested less accurate than the trained model, kept for the category-by-category 'why'."
    >
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 700, marginBottom: 3 }}>
        rating system says: {favored} {(favoredProb * 100).toFixed(0)}%
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {entries.map(([cat, val]) => {
          const label = RATING_CATEGORY_LABELS[cat] || cat
          const leansHome = val > 0
          const magnitude = Math.min(Math.abs(val) / 0.5, 1)
          return (
            <div key={cat} className="mono" style={{ fontSize: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 170, color: 'var(--text-tertiary)' }}>{label}</span>
              <div style={{ flex: 1, height: 4, background: 'var(--line)', borderRadius: 2, position: 'relative' }}>
                <div style={{
                  position: 'absolute', top: 0, bottom: 0,
                  [leansHome ? 'left' : 'right']: '50%',
                  width: `${magnitude * 50}%`,
                  background: leansHome ? 'var(--edge-pos)' : 'var(--edge-neg)',
                  borderRadius: 2,
                }} />
              </div>
              <span style={{
                width: 50, textAlign: 'right',
                color: val > 0 ? 'var(--edge-pos)' : val < 0 ? 'var(--edge-neg)' : 'var(--text-tertiary)',
              }}>
                {val > 0 ? '+' : ''}{val.toFixed(2)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function FavoredCallout({ team, prob, source, reason, overridden, modelProb, favoredIsHome, color }) {
  const rawFavoredProb = overridden && modelProb != null
    ? (favoredIsHome ? modelProb : 1 - modelProb)
    : null
  return (
    <div style={{
      marginTop: 14, padding: '14px 16px', borderRadius: 8,
      background: `linear-gradient(135deg, ${color}1c, ${color}0a)`, border: `1px solid ${color}55`,
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Favored:</span>
        <span style={{ fontSize: 22, fontWeight: 700, color, lineHeight: 1 }}>{team}</span>
        <span className="mono" style={{
          fontSize: 30, fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1,
          fontFamily: 'var(--font-display)', letterSpacing: '-0.02em',
        }}>
          {(prob * 100).toFixed(0)}<span style={{ fontSize: 16, opacity: 0.6 }}>%</span>
        </span>
        <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginLeft: 'auto' }}>
          {source} — pitching matchup, not odds
        </span>
      </div>
      {reason && (
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6, lineHeight: 1.4 }}>
          {reason}
        </div>
      )}
      {overridden && rawFavoredProb != null && (
        <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 6 }} title="Every underlying stat agreed strongly in the same direction, so this was nudged further that way — a transparent adjustment on top of the model, not part of its training.">
          adjusted from model's raw {(rawFavoredProb * 100).toFixed(0)}% — every stat agrees, strongly
        </div>
      )}
    </div>
  )
}

function OddsInput({ label, value, placeholder = '-130', onChange }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11, color: 'var(--text-secondary)' }}>
      {label}
      <input
        className="mono"
        placeholder={placeholder}
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          background: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 5,
          color: 'var(--text-primary)', padding: '7px 10px', width: 90, fontSize: 13,
        }}
      />
    </label>
  )
}

function EdgeBadge({ edge }) {
  const positive = edge > 0
  const pct = Math.abs(edge * 100).toFixed(1)
  return (
    <div className="mono" style={{
      fontSize: 12, fontWeight: 600, padding: '5px 10px', borderRadius: 5,
      color: positive ? 'var(--edge-pos)' : 'var(--edge-neg)',
      background: positive ? 'rgba(61,220,132,0.1)' : 'rgba(255,92,92,0.1)',
      border: `1px solid ${positive ? 'var(--edge-pos)' : 'var(--edge-neg)'}`,
      whiteSpace: 'nowrap',
    }}>
      {positive ? '+' : '-'}{pct}% edge (home)
    </div>
  )
}
