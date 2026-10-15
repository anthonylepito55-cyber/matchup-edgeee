"""HIGHEST-ROI FIRST, AND EVERY NUMBER IS GENDER x BAND (2026-10-14).

User: "focus on the highest roi picks to take" and then "Make sure it's gender specific".

THE PROBLEM WITH THE TAB AS IT STOOD. The today list was ordered by start time, and each cell
chip reported genderRec(cel.c, g) -- that gender's record across ALL prices. Both of those hide
the thing the board actually runs on. The men's MC2 4pt lane is -3.04% across all prices and
+30.6% at +100..+150; the women's c75 flip lane blends to +7.84% while its +100..+150 half is
-23.53% on 47. A gender-wide number is not gender-specific enough when every gate on this tab is
gender x BAND.

THREE CHANGES, all on one basis: the cell's OWN picks, filtered to this gender, this price band,
and the tab's population (no ITF men, nothing above +300) -- identical to splitByBand and dedupe.

1. bandGenderRec(cel, g, odds) is the single source for every record shown on a card. The chips
   now read "M +31%/52 · $+7.64" instead of the all-price gender blend.

2. THE ORDER. Default is now by $/bet of the card's best gender x band cell, descending, with
   readable cells (>= MIN_CELL_N settles) placed ahead of thin ones -- ROI rank is not confidence
   rank, and the two headline cells on this tab are also its two smallest. A pill flips back to
   start time. The headline figure sits on the card so the screen order is explained by what is
   printed on it.

3. A GATE THIS CLOSES. MARK_CELLS cells were exempt from genderOK so that a lane whose blend is
   negative could still mark its good band -- necessary, but it also let the OPPOSITE case
   through: the women's c75 flip at +100..+150, -23.53% on 47 settles, was listed (unpainted)
   because the lane blend is positive. A cell is now dropped for a card when its gender x band
   record is readable and not positive, mark cell or not, and a card left with no cell drops off.
   That is the same forward-negative rule the rest of the tab already applies, measured on the
   axis the marks are actually defined on.

Nothing about the colours changes -- pink and gold keep their existing rules.
"""
import io
import os

P = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "DogPicksPanel.jsx"))
s = io.open(P, encoding="utf-8").read()
assert "bandGenderRec" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


# ---------------------------------------------------------------- 1. the record helper
rep("""const bandOf = od => (od == null ? null : (BANDS.find(([, lo, hi]) => od >= lo && od <= hi) || [null])[0])""",
    """const bandOf = od => (od == null ? null : (BANDS.find(([, lo, hi]) => od >= lo && od <= hi) || [null])[0])

// EVERY NUMBER ON A CARD IS GENDER x BAND (2026-10-14, user: "make sure it's gender specific").
// A gender-wide record is not specific enough on this tab, because every gate here is defined on
// gender x price band and the two disagree hard: the men's MC2 4pt lane is -3.04% over all prices
// and +30.6% at +100..+150, and the women's c75 flip lane blends to +7.84% while its +100..+150
// half is -23.53% on 47. Summed from the cell's OWN picks on the tab's population (no ITF men,
// nothing above +300) so it cannot drift from the lane that scores it, or from splitByBand.
function bandGenderRec(cel, g, odds) {
  const b = bandOf(odds)
  if (!b) return { n: 0, band: null }
  const lo = (BANDS.find(x => x[0] === b) || [])[1]
  const hi = (BANDS.find(x => x[0] === b) || [])[2]
  const ps = (cel.picks || []).filter(p => p.odds != null && p.odds >= lo && p.odds <= hi
    && priceOK(p) && leagueOK(p) && genderOf(p) === g)
  const done = ps.filter(p => p.won != null)
  const profit = done.reduce((a, p) => a + (p.pnl || 0), 0)
  return { band: b, n: done.length, wins: done.filter(p => p.won).length,
           pending: ps.length - done.length, profit_usd: profit,
           per_bet: done.length ? profit / done.length : 0,
           roi_pct: done.length ? Math.round(1000 * profit / (25 * done.length)) / 10 : 0 }
}

// the card's headline: its best gender x band cell, readable cells ahead of thin ones. ROI rank is
// NOT confidence rank -- the top two cells on this tab are also its two smallest samples -- so the
// sort puts anything with >= MIN_CELL_N settles ahead of everything thinner regardless of ROI.
function bestRec(s) {
  let best = null
  for (const cel of s.cells) {
    const d = bandGenderRec(cel, s.g, s.p.odds)
    if (!d.n) continue
    const thick = d.n >= MIN_CELL_N
    if (!best || (thick !== best.thick ? thick
      : d.per_bet > best.d.per_bet)) best = { cel, d, thick }
  }
  return best
}""")

# ---------------------------------------------------------------- 2. the gender x band cell gate
rep("""      const g = genderOf(p)
      // a cell the board marks from is judged by its RULE's band, not by its blended record
      if (!MARK_CELLS.has(cel.key)) {
        if (!genderOK(cel.c, g)) continue     // this gender's half of the cell loses money
        if (!cellThick(cel.c, g)) continue    // ...and this gender's half is too small to read
      }""",
    """      const g = genderOf(p)
      // a cell the board marks from is judged by its RULE's band, not by its blended record
      if (!MARK_CELLS.has(cel.key)) {
        if (!genderOK(cel.c, g)) continue     // this gender's half of the cell loses money
        if (!cellThick(cel.c, g)) continue    // ...and this gender's half is too small to read
      }
      // ...but NO cell survives a readable, non-positive record on its own gender x band. The
      // MARK_CELLS exemption above exists so a lane with a negative BLEND can still mark its good
      // band; it was also letting the reverse through -- the women's c75 flip at +100..+150, -23.53%
      // on 47, listed unpainted because the lane blend is positive (2026-10-14, user "make sure
      // it's gender specific"). Fewer than MIN_CELL_N settles is unknown, not negative.
      {
        const bg = bandGenderRec(cel, g, p.odds)
        if (bg.n >= MIN_CELL_N && (bg.roi_pct || 0) <= 0) continue
      }""")

# ---------------------------------------------------------------- 3. the order
rep("""  stacked.sort((a, b) => (whenMs(a.p) - whenMs(b.p)) || (b.cells.length - a.cells.length))""",
    """  // HIGHEST ROI FIRST BY DEFAULT (2026-10-14, user: "focus on the highest roi picks to take").
  // Ranked on $/bet of the best gender x band cell, readable samples ahead of thin ones, so the
  // order on screen matches the number printed on the card. The pill flips back to start time.
  const byTime = (a, b) => (whenMs(a.p) - whenMs(b.p)) || (b.cells.length - a.cells.length)
  if (order === 'edge') {
    stacked.sort((a, b) => {
      const x = bestRec(a), y = bestRec(b)
      if (!x || !y) return (!x && !y) ? byTime(a, b) : (x ? -1 : 1)
      if (x.thick !== y.thick) return x.thick ? -1 : 1
      return (y.d.per_bet - x.d.per_bet) || byTime(a, b)
    })
  } else {
    stacked.sort(byTime)
  }""")

rep("""  const [mode, setMode] = useState('today')""",
    """  const [mode, setMode] = useState('today')
  const [order, setOrder] = useState('edge')   // 'edge' = best gender x band $/bet first""")

rep("""        {pill(mode === 'today', `live + upcoming (${stacked.length})`, () => setMode('today'))}""",
    """        {pill(mode === 'today', `live + upcoming (${stacked.length})`, () => setMode('today'))}""")

# ---------------------------------------------------------------- 4. the toggle + headline on card
rep("""        stacked.length ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>""",
    """        stacked.length ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div className="mono" style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 10,
              color: 'var(--text-tertiary)', marginBottom: 2 }}>
              <span>order</span>
              {pill(order === 'edge', 'best ROI first', () => setOrder('edge'))}
              {pill(order === 'time', 'start time', () => setOrder('time'))}
              <span style={{ marginLeft: 6 }}>
                every record below is this pick’s <b>gender × price band</b>, not the lane blend ·
                readable cells (≥{MIN_CELL_N} settles) rank above thin ones
              </span>
            </div>""")

rep("""              const yel = !!fb
              return (""",
    """              const yel = !!fb
              const br = bestRec(s)      // the card's own gender x band headline
              return (""")

rep("""                    <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>over {s.p.opp}</span>""",
    """                    <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>over {s.p.opp}</span>
                    {br ? (
                      <span title={`BEST CELL ON THIS CARD, measured on ${s.g === 'w' ? "WOMEN'S" : "MEN'S"} `
                        + `${br.d.band} only -- ${br.cel.label}: ${br.d.wins}-${br.d.n - br.d.wins}, `
                        + `${br.d.roi_pct > 0 ? '+' : ''}${br.d.roi_pct}% ROI, $${br.d.per_bet.toFixed(2)} per `
                        + `$25 bet.${br.thick ? '' : ` ONLY ${br.d.n} SETTLES -- below the ${MIN_CELL_N}`
                        + ` floor, so this ROI cannot be read as a forecast and the card ranks below`
                        + ` every readable one.`} This is what the list is sorted on.`}
                        style={{ fontSize: 10, fontWeight: 800, padding: '0 5px', borderRadius: 6,
                          color: br.d.per_bet >= 0 ? '#3fb950' : '#f85149',
                          border: `1px solid ${br.d.per_bet >= 0 ? 'rgba(63,185,80,0.5)' : 'rgba(248,81,73,0.5)'}`,
                          opacity: br.thick ? 1 : 0.62 }}>
                        {`${br.d.per_bet >= 0 ? '+' : '−'}$${Math.abs(br.d.per_bet).toFixed(2)}/bet`}
                        <span style={{ color: 'var(--text-tertiary)', fontWeight: 600 }}>
                          {` ${s.g.toUpperCase()} ${br.d.band} · ${br.d.roi_pct > 0 ? '+' : ''}${br.d.roi_pct}%/${br.d.n}${br.thick ? '' : ' thin'}`}
                        </span>
                      </span>
                    ) : null}""")

# ---------------------------------------------------------------- 5. chips on the same basis
rep("""                    {s.cells.map((cel, j) => (
                      <span key={j} title={`${cel.note}  [record shown is the ${s.g === 'w' ? "WOMEN'S" : "MEN'S"} half of this cell, which is what applies to this match]`} style={{
                        fontSize: 9, padding: '1px 6px', borderRadius: 7,
                        border: '1px solid rgba(63,185,80,0.35)', color: '#3fb950',
                      }}>
                        {cel.label} <span style={{ color: 'var(--text-tertiary)' }}>
                          {(() => {
                            const d = genderRec(cel.c, s.g)
                            return d.n ? `${s.g.toUpperCase()} ${d.roi_pct > 0 ? '+' : ''}${Math.round(d.roi_pct)}%/${d.n}` : `${s.g.toUpperCase()} new`
                          })()}
                        </span>
                      </span>
                    ))}""",
    """                    {s.cells.map((cel, j) => {
                      // GENDER x BAND, not the gender-wide blend (2026-10-14). The blend is the
                      // wrong number here: the men's MC2 4pt lane reads -3.04% across all prices
                      // and +30.6% in the band these picks are actually in.
                      const d = bandGenderRec(cel, s.g, s.p.odds)
                      const thin = d.n > 0 && d.n < MIN_CELL_N
                      return (
                        <span key={j} title={`${cel.note}\\n\\n[the record shown is `
                          + `${s.g === 'w' ? "WOMEN'S" : "MEN'S"} ${d.band || 'this band'} ONLY, which is `
                          + `the basis every gate on this tab uses -- not this cell's gender-wide blend`
                          + `${d.n ? `. ${d.wins}-${d.n - d.wins}, $${d.per_bet.toFixed(2)} per $25 bet` : ''}`
                          + `${thin ? `, and at ${d.n} settles it is below the ${MIN_CELL_N} floor` : ''}]`} style={{
                          fontSize: 9, padding: '1px 6px', borderRadius: 7,
                          border: '1px solid rgba(63,185,80,0.35)', color: '#3fb950',
                          opacity: thin ? 0.6 : 1,
                        }}>
                          {cel.label} <span style={{ color: 'var(--text-tertiary)' }}>
                            {d.n ? `${s.g.toUpperCase()} ${d.roi_pct > 0 ? '+' : ''}${Math.round(d.roi_pct)}%/${d.n}${thin ? ' thin' : ''}`
                              : `${s.g.toUpperCase()} new`}
                          </span>
                        </span>
                      )
                    })}""")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched DogPicksPanel.jsx")
for k in ("bandGenderRec", "bestRec", "order === 'edge'", "setOrder"):
    print("   %-22s %d" % (k, s.count(k)))
print("RESULT: OK")
