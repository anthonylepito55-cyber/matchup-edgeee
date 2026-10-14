import React, { useEffect, useState } from 'react'

// 🐕 DOG PICKS (2026-10-14, user: "make a new tab called dog picks and add all of the picks
// with these cells into that tab as well as 6-4 split dogs, mc2 dog flips, c75 dog flips and
// fade form dogs").
//
// Every pick comes from tennis_log's own lane records (study[lane].picks), which bet() writes
// for each lane named in _PICK_LANES. No predicate is re-implemented here, so the tab cannot
// drift out of lockstep with the lanes that score it -- the one thing that has gone wrong
// repeatedly when board logic and lane logic were written twice.
//
// The ROI and dollar figures are the lane's FORWARD record from the frozen log. They are shown
// without rounding up the uncertainty: `t` is ROI over its own standard error, and at these
// prices a 20-bet cell needs roughly 40 points of ROI to reach t=2. 104 dog cells were measured
// and 4 clear t=2, which is about what 104 lanes on ~1,000 shared games would throw up by
// chance -- so these are candidates, not proven edges, and the tab says so rather than
// implying a green number is a verdict.

// label, lane key, and a one-line note. Ordered by how much evidence each has, not by ROI.
const CELLS = [
  ['🧊 FADE FORM · dogs', 'pf_c75_dis_dog',
   'c75 pick where the pure-results form overlay points at the OPPONENT, and the pick is the dog. Best t on the board (2.40).'],
  ['🔀 6-4 SPLIT · dogs', 'split64_fade_dog',
   'The 10 heads split exactly 6-4; back the 4-minority when it is the dog. Even across genders (M +27.6 / W +27.7).'],
  ['⚄ c75 DOG FLIP', 'mc_c75_dog',
   'c75 puts the market underdog past 50% and picks it outright. The largest honest sample of any flip (no recon rows).'],
  ['🟤 MC2 DOG FLIP', 'mc2_dog_flip',
   'MC2 puts the market dog past 50%. The LANE is only days old (MC2_LIVE_FROM 2026-10-13), so n here is tiny; across the whole forward log MC2 flips are +14.3% on 84.'],
  ['🐕 c75 DOG +100 up', 'c75_dog_100plus',
   'Every c75 dog priced +100 or longer. Biggest dollar earner on the board and the deepest sample.'],
  ['🎾 RETURNER DOG (W)', 'returner_dog_w',
   'Women, dog wins the return-pressure gap. Highest ROI of any dog cell, on only 25 settles.'],
  ['🎯 ALL-ROUND DOG (W)', 'allround_dog_w',
   'Women, dog better on serve AND return pressure. 22 settles.'],
  ['⚄ c50+c75 DOG · no D', 'cc75_nod_dog',
   'Both C-MC variants back the dog and Model D does NOT. 77 settles.'],
  ['⭐ STAR DOG (resolver 1)', 'cr1_stardog',
   'The conflict-resolver tier-1 star dog. 52 settles.'],
  ['⚄ c50+c75 DOG', 'cc75_dog', 'Both C-MC variants back the dog, D ignored.'],
  ['🩷 FADE-B DOG (M)', 'pink_fadeb_dog_m', 'Men, pink fade-B dog watch cell.'],
  ['🩷 MC2 DOG (pink)', 'pink_mc2_dog', 'The pink MC2 dog watch cell.'],
  ['⛔ TIER-AVOID · dogs', 'tier_avoid_dog',
   'The dog side of cards the board labels AVOID. Counter-intuitive and worth watching: the avoid applies to the favourite, and the dog has paid.'],
  ['Ⓓ D-MA DOG', 'dma_dog', 'Model D market-aware picks the dog.'],
  ['🟤 MC2 DOG BAND', 'mc2_dog_band', 'MC2 dog inside the +100..+250 price band.'],
  ['⚪ C+GRAY DOG late', 'cgray_dog_late', 'C and the gray line on the dog, later rounds.'],
  ['🔁 OVERLAY DOG', 'ovl_dog', 'The overlay dog cell.'],
  ['⚔ FIGHT MC4 DOG', 'fight_mc4_dog', 'MC4 disagrees with the market on the dog.'],
]

function tstat(c) {
  const n = c && c.n, w = c && c.wins, roi = c && c.roi_pct
  if (!n || w == null || roi == null || n < 2) return null
  const r = roi / 100
  if (w <= 0) return null
  const gain = (r * n + (n - w)) / w          // implied average winning payout
  const varr = (w * gain * gain + (n - w)) / n - r * r
  if (!(varr > 0)) return null
  return r / (Math.sqrt(varr) / Math.sqrt(n))
}

const usd = v => `${v < 0 ? '-' : '+'}$${Math.abs(v || 0).toFixed(2)}`

export default function DogPicksPanel({ query }) {
  const [rec, setRec] = useState(null)
  const [open, setOpen] = useState(null)
  const [mode, setMode] = useState('today')
  useEffect(() => {
    const go = () => fetch('/api/tennis/track-record').then(r => r.json())
      .then(d => setRec(d.ab25 || null)).catch(() => {})
    go()
    const id = setInterval(go, 120000)
    return () => clearInterval(id)
  }, [])
  const st = (rec && rec.study) || {}
  const q = (query || '').trim().toLowerCase()

  const cells = CELLS.map(([label, key, note]) => {
    const c = st[key] || {}
    return { label, key, note, c, picks: c.picks || [], t: tstat(c) }
  }).filter(x => x.c && (x.c.n || x.picks.length))

  // TODAY: every unsettled pick, grouped by match, so a dog several cells agree on is visible
  const byMatch = {}
  for (const cel of cells) {
    for (const p of cel.picks) {
      if (p.won != null || p.settled) continue
      const k = `${p.pick}|||${p.opp}`
      if (!byMatch[k]) byMatch[k] = { p, cells: [] }
      byMatch[k].cells.push(cel)
    }
  }
  let stacked = Object.values(byMatch)
  if (q) {
    stacked = stacked.filter(s => (`${s.p.pick} ${s.p.opp} ${s.p.tournament || ''}`).toLowerCase().includes(q))
  }
  stacked.sort((a, b) => b.cells.length - a.cells.length
    || (a.p.pick || '').localeCompare(b.p.pick || ''))

  const pill = (on, label, onClick) => (
    <button onClick={onClick} className="mono" style={{
      padding: '4px 12px', borderRadius: 12, fontSize: 11, cursor: 'pointer',
      border: `1px solid ${on ? '#3fb950' : 'var(--line)'}`,
      background: on ? 'rgba(63,185,80,0.13)' : 'transparent',
      color: on ? '#3fb950' : 'var(--text-secondary)', fontWeight: on ? 700 : 400,
    }}>{label}</button>
  )

  if (!rec) {
    return <div className="mono" style={{ padding: 18, color: 'var(--text-tertiary)', fontSize: 12 }}>loading dog cells…</div>
  }

  return (
    <div style={{ padding: '4px 0 20px' }}>
      <div className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 10 }}>
        <b style={{ color: '#3fb950' }}>🐕 DOG PICKS</b> — every dog cell with a positive forward record, and the
        picks each one is on. Records come straight from the lanes that score them, so nothing here can disagree
        with the $25 tab. <b>Read the t column, not the ROI</b>: at dog prices a 20-bet cell needs about 40 points
        of ROI to reach t=2, so a big number on a small sample is variance. Of 104 dog cells measured, 4 clear
        t=2 — roughly what 104 lanes on ~1,000 shared games produce by chance — so treat these as candidates
        rather than settled edges. Cells overlap heavily; the dollar figures are <i>not</i> additive.
      </div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
        {pill(mode === 'today', `today (${stacked.length})`, () => setMode('today'))}
        {pill(mode === 'cells', `by cell (${cells.length})`, () => setMode('cells'))}
      </div>

      {mode === 'today' ? (
        stacked.length ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {stacked.map((s, i) => {
              const n = s.cells.length
              const col = n >= 3 ? '#3fb950' : n === 2 ? '#e3b341' : 'var(--text-secondary)'
              return (
                <div key={i} className="mono" style={{
                  padding: '9px 13px', borderRadius: 8, background: 'var(--panel)',
                  border: `1px solid ${n >= 3 ? 'rgba(63,185,80,0.55)' : 'var(--line)'}`,
                }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
                    <span style={{ color: col, fontWeight: 800, fontSize: 10, minWidth: 54 }}>
                      {n} cell{n === 1 ? '' : 's'}
                    </span>
                    <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{s.p.pick}</span>
                    <span style={{ fontSize: 11, color: '#3fb950', fontWeight: 700 }}>
                      {s.p.odds != null ? (s.p.odds > 0 ? `+${s.p.odds}` : s.p.odds) : ''}
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>over {s.p.opp}</span>
                    <span style={{ fontSize: 10, color: 'var(--text-tertiary)', marginLeft: 'auto' }}>
                      {s.p.tournament} · {s.p.surface} · {String(s.p.league || '').toUpperCase()}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginTop: 6 }}>
                    {s.cells.map((cel, j) => (
                      <span key={j} title={cel.note} style={{
                        fontSize: 9, padding: '1px 6px', borderRadius: 7,
                        border: '1px solid rgba(63,185,80,0.35)', color: '#3fb950',
                      }}>
                        {cel.label} <span style={{ color: 'var(--text-tertiary)' }}>
                          {cel.c.n ? `${cel.c.roi_pct > 0 ? '+' : ''}${Math.round(cel.c.roi_pct)}%/${cel.c.n}` : 'new'}
                          {cel.t != null ? ` t${cel.t.toFixed(1)}` : ''}
                        </span>
                      </span>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="mono" style={{ fontSize: 12, color: 'var(--text-tertiary)', padding: 12 }}>
            no unsettled dog-cell picks right now{q ? ' matching that search' : ''}.
          </div>
        )
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          {cells.sort((a, b) => (b.t || -9) - (a.t || -9)).map((cel) => {
            const c = cel.c
            const isOpen = open === cel.key
            const pos = (c.roi_pct || 0) > 0
            return (
              <div key={cel.key} className="mono" title={cel.note}
                onClick={() => setOpen(isOpen ? null : cel.key)}
                style={{
                  padding: '10px 14px', borderRadius: 8, background: 'var(--panel)',
                  border: `1px solid ${pos ? 'rgba(63,185,80,0.4)' : 'var(--line)'}`,
                  cursor: cel.picks.length ? 'pointer' : 'default',
                }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: pos ? '#3fb950' : 'var(--text-secondary)', minWidth: 190 }}>
                    {cel.label}
                  </span>
                  <span style={{ fontSize: 14, fontWeight: 700, color: (c.profit_usd || 0) >= 0 ? '#3fb950' : '#f85149' }}>
                    {usd(c.profit_usd)}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                    {c.n ? `${c.wins}-${c.n - c.wins} · ${c.roi_pct > 0 ? '+' : ''}${c.roi_pct}%` : '0 settled'}
                    {c.pending ? ` · ${c.pending} pending` : ''}
                  </span>
                  <span style={{
                    fontSize: 10, fontWeight: 700,
                    color: cel.t == null ? 'var(--text-tertiary)' : cel.t >= 2 ? '#3fb950' : cel.t >= 1.5 ? '#e3b341' : 'var(--text-tertiary)',
                  }}>
                    {cel.t == null ? '' : `t ${cel.t.toFixed(2)}`}{cel.t != null && cel.t >= 2 ? ' ✓2se' : ''}
                  </span>
                  <span style={{ fontSize: 10, color: 'var(--text-tertiary)', marginLeft: 'auto' }}>
                    {cel.picks.length ? `${cel.picks.length} picks${isOpen ? ' ▾' : ' ▸'}` : ''}
                  </span>
                </div>
                {isOpen && cel.picks.length ? (
                  <div style={{ marginTop: 8, borderTop: '1px solid var(--line)', paddingTop: 6, maxHeight: 320, overflowY: 'auto' }}>
                    {cel.picks.slice().reverse().map((p, i) => (
                      <div key={i} style={{ fontSize: 10, display: 'flex', gap: 7, padding: '2px 0', color: 'var(--text-secondary)' }}>
                        <span style={{ color: 'var(--text-tertiary)', minWidth: 58 }}>{p.date}</span>
                        <span style={{ minWidth: 14, fontWeight: 700, color: p.won == null ? '#e3b341' : p.won ? '#3fb950' : '#f85149' }}>
                          {p.won == null ? '…' : p.won ? 'W' : 'L'}
                        </span>
                        <span style={{ flex: 1 }}>{p.pick} <span style={{ color: 'var(--text-tertiary)' }}>vs {p.opp}</span></span>
                        <span style={{ color: 'var(--text-tertiary)', minWidth: 42 }}>
                          {p.odds != null ? (p.odds > 0 ? `+${p.odds}` : p.odds) : ''}
                        </span>
                        <span style={{ minWidth: 56, textAlign: 'right', color: p.pnl == null ? 'var(--text-tertiary)' : p.pnl >= 0 ? '#3fb950' : '#f85149' }}>
                          {p.pnl == null ? '' : usd(p.pnl)}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
