import React, { useEffect, useState } from 'react'
import { RecentFormLine, SeasonStatsLine, TeamStatsLine, LineupBreakdown } from './App.jsx'

export default function HistorySection() {
  const [dates, setDates] = useState([])
  const [selectedDate, setSelectedDate] = useState(null)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => { fetchDates() }, [])
  useEffect(() => { if (selectedDate) fetchDay(selectedDate) }, [selectedDate])

  async function fetchDates() {
    try {
      const res = await fetch('/api/history/dates')
      if (!res.ok) throw new Error(`API returned ${res.status}`)
      const json = await res.json()
      const allDates = json.dates || []
      // Default to the most recent date that isn't today (today's games likely
      // aren't settled yet) — if that's all there is, fall back to the latest.
      const today = new Date().toISOString().slice(0, 10)
      const past = allDates.filter(d => d !== today)
      setDates(allDates)
      setSelectedDate(past[0] || allDates[0] || null)
    } catch (e) {
      setError(e.message)
      setLoading(false)
    }
  }

  async function fetchDay(date) {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/history/${date}`)
      if (!res.ok) throw new Error(`API returned ${res.status}`)
      setData(await res.json())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const games = data?.games ?? []
  const wpRecord = data?.win_prob_record
  const kRecord = data?.strikeout_record

  return (
    <div>
      <div style={{
        marginTop: 20, padding: '10px 16px', borderRadius: 6,
        background: 'rgba(140,140,150,0.06)', border: '1px solid var(--line)',
        fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.5,
      }}>
        Exactly what was predicted before each game started, read straight from the logged
        forward-test record — never recomputed with hindsight. Use this to see where the model
        actually got it right or wrong, and what might be worth digging into next.
      </div>

      {dates.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
          <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            date:
          </span>
          {dates.map(d => (
            <button key={d} onClick={() => setSelectedDate(d)} className={selectedDate === d ? '' : 'btn-ghost'} style={{
              background: selectedDate === d ? 'var(--panel-raised)' : 'transparent',
              border: `1px solid ${selectedDate === d ? 'var(--amber)' : 'var(--line)'}`,
              borderRadius: 5, color: selectedDate === d ? 'var(--amber)' : 'var(--text-secondary)',
              fontSize: 11, padding: '4px 10px', fontFamily: 'var(--font-mono)',
            }}>
              {d}
            </button>
          ))}
        </div>
      )}

      {(wpRecord || kRecord) && (
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 14 }}>
          {wpRecord && (
            <RecordChip
              label="win-prob"
              correct={wpRecord.correct}
              total={wpRecord.total}
            />
          )}
          {kRecord && (
            <RecordChip
              label="strikeout props"
              correct={kRecord.correct}
              total={kRecord.total}
            />
          )}
        </div>
      )}

      {error && (
        <div style={{
          background: 'rgba(255,92,92,0.08)', border: '1px solid var(--edge-neg)',
          borderRadius: 8, padding: '14px 18px', margin: '20px 0', color: 'var(--edge-neg)',
          fontSize: 14, fontFamily: 'var(--font-mono)',
        }}>
          Couldn't reach the history API ({error})
        </div>
      )}

      {!error && dates.length === 0 && !loading && (
        <div style={{ color: 'var(--text-secondary)', padding: '60px 0', textAlign: 'center' }}>
          No logged predictions yet — check back after a slate has run.
        </div>
      )}

      {loading && (
        <div style={{ color: 'var(--text-tertiary)', padding: '40px 0', textAlign: 'center', fontSize: 13 }}>
          loading…
        </div>
      )}

      {!loading && !error && games.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 14 }}>
          {games.map(g => <HistoryGameCard key={g.game_pk} game={g} />)}
        </div>
      )}
    </div>
  )
}

function RecordChip({ label, correct, total }) {
  const pct = total > 0 ? Math.round((correct / total) * 100) : null
  const color = pct == null ? 'var(--text-tertiary)' : pct >= 50 ? 'var(--edge-pos)' : 'var(--edge-neg)'
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
      <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}:
      </span>
      <span className="mono" style={{ fontSize: 14, fontWeight: 700, color }}>
        {correct}/{total} {pct != null && `(${pct}%)`}
      </span>
    </div>
  )
}

function HistoryGameCard({ game: g }) {
  const home = g.home_team_abbr
  const away = g.away_team_abbr
  const settled = g.settled
  const homeWon = g.home_won
  const correct = g.correct
  const homeProb = g.model_home_win_prob
  const favoredIsHome = homeProb != null ? homeProb >= 0.5 : null
  const favoredTeam = favoredIsHome == null ? null : (favoredIsHome ? home : away)
  const favoredProb = favoredIsHome == null ? null : (favoredIsHome ? homeProb : 1 - homeProb)

  const cardColor = !settled ? 'var(--line)' : correct ? 'var(--edge-pos)' : 'var(--edge-neg)'

  return (
    <div style={{
      background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 10,
      padding: '14px 18px', borderLeft: `3px solid ${cardColor}`,
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
          {away} @ {home}
          <span className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)', fontWeight: 400, marginLeft: 8 }}>
            {g.away_pitcher_name} vs {g.home_pitcher_name}
          </span>
        </div>
        {settled ? (
          <span className="mono" style={{ fontSize: 12, fontWeight: 700, color: cardColor }}>
            {correct ? 'CORRECT' : 'WRONG'} — final {away} {g.away_score} · {home} {g.home_score}
          </span>
        ) : (
          <span className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>not yet settled</span>
        )}
      </div>

      <div className="mono" style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>
        Favored: <span style={{ fontWeight: 700 }}>{favoredTeam}</span> {favoredProb != null && `${(favoredProb * 100).toFixed(0)}%`}
        {g.overridden && <span style={{ color: 'var(--amber)', marginLeft: 6 }}>(overridden)</span>}
        {g.market_home_prob != null && (
          <span style={{ color: 'var(--text-tertiary)', marginLeft: 8 }}>
            market: {home} {(g.market_home_prob * 100).toFixed(0)}%
          </span>
        )}
      </div>

      {g.reason && (
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4, lineHeight: 1.4 }}>
          {g.reason}
        </div>
      )}

      {g.recent_form && (
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 8 }}>
          <RecentFormLine stats={g.recent_form.away} />
          <RecentFormLine stats={g.recent_form.home} />
        </div>
      )}
      {g.season_stats && (
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 3 }}>
          <SeasonStatsLine stats={g.season_stats.away} />
          <SeasonStatsLine stats={g.season_stats.home} />
        </div>
      )}
      {g.team_stats && (
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 3 }}>
          <TeamStatsLine label={away} stats={g.team_stats.away} />
          <TeamStatsLine label={home} stats={g.team_stats.home} />
        </div>
      )}

      {g.lineup_breakdown && (g.lineup_breakdown.home?.batters?.length > 0 || g.lineup_breakdown.away?.batters?.length > 0) && (
        <div style={{ marginTop: 8 }}>
          <LineupToggle lineupBreakdown={g.lineup_breakdown} homeAbbr={home} awayAbbr={away} />
        </div>
      )}

      {g.strikeouts && g.strikeouts.length > 0 && (
        <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', marginTop: 8 }}>
          {g.strikeouts.map(k => (
            <span key={k.pitcher_name} className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
              {k.pitcher_name}: {k.call} {k.line} (pred {k.predicted_k})
              {k.settled && (
                <span style={{ color: k.correct ? 'var(--edge-pos)' : k.correct === false ? 'var(--edge-neg)' : 'var(--text-tertiary)', marginLeft: 4 }}>
                  → actual {k.actual_k} {k.correct === true ? '✓' : k.correct === false ? '✗' : '(push)'}
                </span>
              )}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}


function LineupToggle({ lineupBreakdown, homeAbbr, awayAbbr }) {
  const [open, setOpen] = useState(false)
  return (
    <div>
      <button onClick={() => setOpen(o => !o)} className="mono btn-ghost" style={{
        background: 'transparent', border: 'none', color: 'var(--text-tertiary)',
        fontSize: 10, padding: 0, textDecoration: 'underline', cursor: 'pointer',
      }}>
        {open ? 'hide' : 'show'} lineup
      </button>
      {open && (
        <div style={{ marginTop: 6 }}>
          <LineupBreakdown label={awayAbbr} batters={lineupBreakdown.away?.batters} predicted={lineupBreakdown.away?.predicted} />
          <LineupBreakdown label={homeAbbr} batters={lineupBreakdown.home?.batters} predicted={lineupBreakdown.home?.predicted} />
        </div>
      )}
    </div>
  )
}
