"""LIVE BADGE + A DOG HISTORY VIEW (2026-10-14).

User: "And show me which dog games are live" and "And get rid of the finished ones with a dog
history tab".

A pick is LIVE when its match has started and still has no result, UPCOMING when it has not
started, FINISHED once it settles. The betting list now holds only live and upcoming; finished
picks move to their own view, grouped by day with that day's record, ROI and P/L.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "frontend", "src", "DogPicksPanel.jsx")
P = os.path.normpath(P)
s = io.open(P, encoding="utf-8").read()
assert "isLive" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:85])
    s = s.replace(old, new)


rep("const whenMs = p => {", """// A pick is LIVE when its match has started and has no result yet, UPCOMING when it has not
// started, and FINISHED once it settles (2026-10-14, user "show me which dog games are live" /
// "get rid of the finished ones with a dog history tab"). The betting list keeps only live and
// upcoming, so it stays a list of things you can still act on.
const isFinished = p => p.won != null
const isLive = p => !isFinished(p) && whenMs(p) <= Date.now()
const whenMs = p => {""")

rep("  let stacked = Object.values(byMatch)",
    """  // live + upcoming only -- finished picks are skipped by the `p.won != null` test above
  let stacked = Object.values(byMatch)""")

rep("""  // when the list spans more than one local day, each row gets its date so the order reads
  const multiDay = new Set(stacked.map(x => dayLabel(whenMs(x.p)))).size > 1""",
    """  // when the list spans more than one local day, each row gets its date so the order reads
  const multiDay = new Set(stacked.map(x => dayLabel(whenMs(x.p)))).size > 1

  // FINISHED picks for the history view: deduped to one row per dog, newest day first, and
  // grouped by day so each day carries its own record and P/L.
  const finished = dedupe(cells, isFinished).sort((a, b) => whenMs(b) - whenMs(a))
  const histCells = (p) => cells.filter(cel => genderOK(cel.c, genderOf(p))
    && cel.picks.some(x => x.date === p.date && x.pick === p.pick && x.opp === p.opp))
  const histDays = []
  for (const p of finished) {
    const d = dayLabel(whenMs(p))
    if (!histDays.length || histDays[histDays.length - 1].d !== d) histDays.push({ d, ps: [] })
    histDays[histDays.length - 1].ps.push(p)
  }""")

rep("""        {pill(mode === 'today', `today (${stacked.length})`, () => setMode('today'))}
        {pill(mode === 'cells', `by cell (${cells.length})`, () => setMode('cells'))}""",
    """        {pill(mode === 'today', `live + upcoming (${stacked.length})`, () => setMode('today'))}
        {pill(mode === 'hist', `history (${finished.length})`, () => setMode('hist'))}
        {pill(mode === 'cells', `by cell (${cells.length})`, () => setMode('cells'))}""")

rep("""                    <span style={{ color: 'var(--text-tertiary)', fontSize: 10, fontWeight: 700, minWidth: 92 }}>
                      {multiDay ? `${dayLabel(whenMs(s.p))} ` : ''}{fmtPT(s.p.start) || s.p.date}
                    </span>""",
    """                    <span style={{ color: 'var(--text-tertiary)', fontSize: 10, fontWeight: 700, minWidth: 92 }}>
                      {multiDay ? `${dayLabel(whenMs(s.p))} ` : ''}{fmtPT(s.p.start) || s.p.date}
                    </span>
                    {isLive(s.p) ? (
                      <span title="Started and not settled yet -- this match is in progress."
                        style={{ fontSize: 9, fontWeight: 800, color: '#f85149', border: '1px solid #f8514988', borderRadius: 6, padding: '0 5px' }}>
                        {'\\u25cf LIVE'}
                      </span>
                    ) : null}""")

HIST = """      ) : mode === 'hist' ? (
        histDays.length ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {histDays.map((grp, gi) => {
              const a = agg(grp.ps)
              return (
                <div key={gi}>
                  <div className="mono" style={{ display: 'flex', alignItems: 'baseline', gap: 9, marginBottom: 4 }}>
                    <span style={{ fontSize: 11, fontWeight: 800, color: 'var(--text-primary)' }}>{grp.d}</span>
                    <span style={{ fontSize: 12, fontWeight: 800, color: a.profit >= 0 ? '#3fb950' : '#f85149' }}>{usd(a.profit)}</span>
                    <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                      {a.w}-{a.l}{a.roi != null ? ` \\u00b7 ${a.roi > 0 ? '+' : ''}${a.roi.toFixed(1)}%` : ''}
                    </span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                    {grp.ps.slice().sort((x, y) => whenMs(x) - whenMs(y)).map((p, i) => (
                      <div key={i} className="mono" style={{
                        display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap',
                        padding: '5px 11px', borderRadius: 7, background: 'var(--panel)',
                        border: `1px solid ${p.won ? 'rgba(63,185,80,0.3)' : 'var(--line)'}`,
                      }}>
                        <span style={{ fontSize: 10, color: 'var(--text-tertiary)', minWidth: 52 }}>{fmtPT(p.start)}</span>
                        <span style={{ fontSize: 11, fontWeight: 800, minWidth: 14, color: p.won ? '#3fb950' : '#f85149' }}>
                          {p.won ? 'W' : 'L'}
                        </span>
                        <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>{p.pick}</span>
                        <span style={{ fontSize: 10, color: '#3fb950', fontWeight: 700 }}>
                          {p.odds != null ? (p.odds > 0 ? `+${p.odds}` : p.odds) : ''}
                        </span>
                        <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>over {p.opp}</span>
                        {p.score ? <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>{p.score}</span> : null}
                        <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
                          {histCells(p).length} cells
                        </span>
                        <span style={{ fontSize: 11, fontWeight: 700, marginLeft: 'auto', color: (p.pnl || 0) >= 0 ? '#3fb950' : '#f85149' }}>
                          {p.pnl == null ? '' : usd(p.pnl)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="mono" style={{ fontSize: 12, color: 'var(--text-tertiary)', padding: 12 }}>no settled dog picks yet.</div>
        )
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          {cells.sort((a, b) => (b.t || -9) - (a.t || -9)).map((cel) => {"""

rep("""      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          {cells.sort((a, b) => (b.t || -9) - (a.t || -9)).map((cel) => {""", HIST)

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched DogPicksPanel.jsx")
for k in ("isLive", "histDays", "mode === 'hist'"):
    print("   %-18s refs %d" % (k, s.count(k)))
print("RESULT: OK")
