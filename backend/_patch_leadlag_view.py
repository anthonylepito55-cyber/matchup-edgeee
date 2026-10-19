"""DOG TAB: read-only status view for the Phase 5 lead-lag paper experiment (2026-10-18).

Same pattern as the auto-bet view: its own pill, polls /api/tennis/leadlag every 2 minutes,
renders the frozen config hash, period status, outcome counts, fills/CLV when they exist, and
the venue adjust-latency the engine measures as a by-product. Pure display -- no action path.
"""
import io
import os

F = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "DogPicksPanel.jsx"))
t = io.open(F, encoding="utf-8").read()
assert "LeadLagView" not in t, "already added"


def rep(old, new):
    global t
    assert t.count(old) == 1, "found %d of %r" % (t.count(old), old[:80])
    t = t.replace(old, new)


VIEW = r'''// \U0001F6F0 PHASE 5 LEAD-LAG PAPER EXPERIMENT (2026-10-18): read-only status of the
// pre-registered Pinnacle lead-lag test. PAPER ONLY -- no order path exists anywhere.
function LeadLagView({ ll }) {
  if (!ll) return <div className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>loading lead-lag status...</div>
  const oc = ll.by_outcome || {}
  return (
    <div className="mono" style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 11 }}>
      <div style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--panel)', lineHeight: 1.55 }}>
        <b style={{ color: '#a7d8fa' }}>PAPER EXPERIMENT {'—'} PHASE5_LEADLAG_EXPERIMENT_PLAN.md.</b>{' '}
        Takes the stale Kalshi/Polymarket top-of-book within seconds of a qualifying Pinnacle move; success is
        pre-registered (200+ fills, CLV {'≥'} +1.5pp t{'≥'}3, net paper ROI {'>'} 0, then an equal Period B).
        Config <b>{ll.config_sha}</b> {'·'} burst {ll.burst_enabled ? 'ON' : 'off'} {'·'} {' '}
        {ll.period_A_start
          ? <b style={{ color: '#3fb950' }}>Period A running since {String(ll.period_A_start_iso || ll.period_A_start).slice(0, 16)}</b>
          : <b style={{ color: '#e3b341' }}>AWAITING READINESS {'—'} no signals are being recorded</b>}
      </div>
      <div style={{ padding: '7px 12px', borderRadius: 8, border: '1px solid var(--line)' }}>
        signals {ll.signals || 0}
        {Object.keys(oc).length ? ' · ' + Object.entries(oc).map(([k, v]) => k + ' ' + v).join(' · ') : ''}
        {ll.fills != null ? <> {'·'} fills <b>{ll.fills}</b> (size-unknown {ll.fills_size_unknown || 0}) {'·'} settled {ll.settled || 0} {'·'} pending {ll.pending || 0}</> : null}
        {ll.roi_pct != null ? <> {'·'} P/L <b style={{ color: (ll.pnl_usd || 0) >= 0 ? '#3fb950' : '#f85149' }}>${ll.pnl_usd} ({ll.roi_pct}%)</b></> : null}
        {ll.clv_mean_pp != null ? <> {'·'} CLV <b>{ll.clv_mean_pp}pp</b> (n{ll.clv_n}{ll.clv_t != null ? ', t ' + ll.clv_t : ''})</> : null}
        {ll.adjust_latency_s ? <> {'·'} venue adjust latency median {ll.adjust_latency_s.median}s p90 {ll.adjust_latency_s.p90}s (n{ll.adjust_latency_s.n})</> : null}
      </div>
      {(ll.recent || []).slice().reverse().map((r, i) => (
        <div key={i} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', padding: '5px 12px', borderRadius: 7, border: '1px solid var(--line)', color: 'var(--text-secondary)' }}>
          <span>{r.matchup}</span><span style={{ color: 'var(--text-tertiary)' }}>{r.league}</span>
          <span>{'+' + Math.round(10 * r.move_pp) / 10}pp move</span>
          <span style={{ marginLeft: 'auto', fontWeight: 700,
            color: r.outcome === 'filled' || r.outcome === 'partial' ? '#3fb950' : 'var(--text-tertiary)' }}>
            {r.outcome}{r.fill_price_am != null && (r.outcome === 'filled' || r.outcome === 'partial') ? ' @ ' + r.fill_price_am : ''}
          </span>
        </div>
      ))}
    </div>
  )
}

'''
rep("export default function DogPicksPanel({ query }) {", VIEW + "export default function DogPicksPanel({ query }) {")

rep("""  const [auto, setAuto] = useState(null)
  useEffect(() => {
    const go = () => fetch('/api/tennis/autobet').then(r => r.json()).then(setAuto).catch(() => {})
    go()
    const id = setInterval(go, 120000)
    return () => clearInterval(id)
  }, [])
""",
    """  const [auto, setAuto] = useState(null)
  useEffect(() => {
    const go = () => fetch('/api/tennis/autobet').then(r => r.json()).then(setAuto).catch(() => {})
    go()
    const id = setInterval(go, 120000)
    return () => clearInterval(id)
  }, [])
  // Phase 5 lead-lag paper experiment status (2026-10-18), read-only
  const [ll, setLl] = useState(null)
  useEffect(() => {
    const go = () => fetch('/api/tennis/leadlag').then(r => r.json()).then(setLl).catch(() => {})
    go()
    const id = setInterval(go, 120000)
    return () => clearInterval(id)
  }, [])
""")

rep("""        {pill(mode === 'auto', `\\u{1F916} auto-bet \\u00b7 paper${auto ? ` (${(auto.bets || []).length})` : ''}`, () => setMode('auto'))}""",
    """        {pill(mode === 'auto', `\\u{1F916} auto-bet \\u00b7 paper${auto ? ` (${(auto.bets || []).length})` : ''}`, () => setMode('auto'))}
        {pill(mode === 'leadlag', `\\u{1F6F0}\\uFE0F lead-lag${ll && ll.fills != null ? ` (${ll.fills})` : ''}`, () => setMode('leadlag'))}""")

rep("""      {mode === 'auto' ? (
        <AutoBetView auto={auto} />
      ) : mode === 'today' ? (""",
    """      {mode === 'leadlag' ? (
        <LeadLagView ll={ll} />
      ) : mode === 'auto' ? (
        <AutoBetView auto={auto} />
      ) : mode === 'today' ? (""")

io.open(F, "w", encoding="utf-8", newline="").write(t)
print("LeadLagView wired: pill + state + branch")
print("RESULT: OK")
