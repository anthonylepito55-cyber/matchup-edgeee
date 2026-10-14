"""YELLOW FAVOURITES ON THE DOG TAB (2026-10-14).

User: "add the women lane on the dog tab" and, earlier, "highlight them Yellow so I know the diff
between the favorites and dogs".

ONE favourite cell is added -- the women's MC2 4pt+ favourite at -100..-200 -- plus its men's
control so the split keeps being tested on screen rather than assumed.

Favourite picks are kept OUT of every dog aggregate. The daily boxes, the price bands and the
pink rules all describe dog bets at plus prices; folding a -150 favourite into them would corrupt
numbers the user reads to decide dog bets. Favourites get their own summary box and their own
colour, which is the whole point of the yellow.

THE EVIDENCE, on the card: forward +26.72% on 24 (18-6), and on forward + corrected recon
+22.85% on 51 (37-14, 72.5% hit against 59.0% needed, t 2.16) -- positive in both windows and
both price bands, while the men's half of the same cut is -9.21% on 74 and every women's
favourite in that range is -3.64%. 51 bets, and both the gender split and the 4pt threshold were
found by scanning this data.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "frontend", "src", "DogPicksPanel.jsx")
P = os.path.normpath(P)
s = io.open(P, encoding="utf-8").read()
assert "YELLOW" not in s, "already patched"

TIP_W = ("MC2 rates this WOMENS favourite 4+ points above the de-vigged market, priced -100..-200. "
         "Forward +26.72% on 24 (18-6). On forward + corrected recon: +22.85% on 51 (37-14, 72.5% hit "
         "against 59.0% needed, t 2.16) -- positive in BOTH windows (fwd +26.72%/24, recon +19.40%/27) "
         "and BOTH bands (-100..-150 +22.31%/28, -150..-200 +23.50%/23). The MENS half of the same cut "
         "is -9.21% on 74, and every womens favourite in that range is -3.64%, so this is not a generic "
         "favourite effect. The only favourite cell in this project to clear t=2. STILL THIN: 51 bets, "
         "and the gender split and 4pt threshold were both found by scanning this data.")
TIP_M = ("The MENS half of the same cut, kept visible as the control that justifies the womens cell: "
         "+1.63% on 25 forward, -9.21% on 74 pooled. NOT a take -- it is here so the split keeps being "
         "tested on screen instead of assumed.")


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


# ---- the two favourite cells, flagged so they stay out of the dog maths ----
rep("""const CELLS = [
  ['🟤 MC2 6pt+ DOG · all prices', 'mc2_dog6_all',""",
    """// 🟡 FAVOURITE CELLS (2026-10-14). Flagged fav:true so they are excluded from every dog
// aggregate -- the daily boxes, the price bands and the pink rules all describe dog bets at plus
// prices, and folding a -150 favourite into them would corrupt the numbers used to decide dog
// bets. They get their own box and their own colour.
const YELLOW = '#e3b341'
const FAV_CELLS = new Set(['mc2_fav4_w', 'mc2_fav4_m'])
const isFavPick = p => p.odds != null && p.odds < 0

const CELLS = [
  ['🟡 MC2 4pt+ FAV · WOMEN −100..−200', 'mc2_fav4_w', '__TIP_W__'],
  ['🟡 MC2 4pt+ FAV · men (control)', 'mc2_fav4_m', '__TIP_M__'],
  ['🟤 MC2 6pt+ DOG · all prices', 'mc2_dog6_all',""")

# ---- keep favourites out of the dog aggregates ----
rep("""function dedupe(cells, filterFn) {
  const out = new Map()
  for (const cel of cells) {""",
    """function dedupe(cells, filterFn) {
  const out = new Map()
  for (const cel of cells) {
    if (FAV_CELLS.has(cel.key)) continue      // favourites never enter the dog maths""")

# ---- a favourite summary box next to the dog ones ----
rep("""            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 700, marginBottom: 5 }}>
              BY PRICE BAND — all days, deduped
            </div>""",
    """            {(() => {
              // the favourite cells get their own line, never mixed into the dog totals
              const fp = []
              const seenF = new Set()
              for (const cel of cells) {
                if (!FAV_CELLS.has(cel.key)) continue
                for (const p of cel.picks) {
                  if (!leagueOK(p)) continue
                  const k = `${cel.key}|${p.date}|${p.pick}`
                  if (seenF.has(k)) continue
                  seenF.add(k)
                  fp.push([cel, p])
                }
              }
              const wCell = cells.find(c => c.key === 'mc2_fav4_w')
              const mCell = cells.find(c => c.key === 'mc2_fav4_m')
              if (!wCell && !mCell) return null
              const bx = (cel, lab) => {
                if (!cel) return null
                const c = cel.c
                return (
                  <div key={lab} title={cel.note} style={{
                    padding: '7px 12px', borderRadius: 8, background: 'var(--panel)', minWidth: 150,
                    border: `1px solid ${lab.indexOf('women') >= 0 ? 'rgba(227,179,65,0.7)' : 'var(--line)'}`,
                  }}>
                    <div style={{ fontSize: 9, color: YELLOW, fontWeight: 700, letterSpacing: '0.04em' }}>{lab}</div>
                    {c.n ? (
                      <>
                        <div style={{ fontSize: 14, fontWeight: 800, color: (c.profit_usd || 0) >= 0 ? '#3fb950' : '#f85149' }}>{usd(c.profit_usd)}</div>
                        <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                          {c.wins}-{c.n - c.wins} · {c.roi_pct > 0 ? '+' : ''}{c.roi_pct}%{c.pending ? ` · ${c.pending} pend` : ''}
                        </div>
                      </>
                    ) : <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 3 }}>0 settled</div>}
                  </div>
                )
              }
              return (
                <>
                  <div style={{ fontSize: 10, color: YELLOW, fontWeight: 700, marginBottom: 5 }}>
                    🟡 FAVOURITES — separate from every dog number above. MC2 4pt+ over the market at −100..−200.
                  </div>
                  <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginBottom: 14 }}>
                    {bx(wCell, 'women (the take)')}
                    {bx(mCell, 'men (control)')}
                  </div>
                </>
              )
            })()}
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 700, marginBottom: 5 }}>
              BY PRICE BAND — all days, deduped
            </div>""")

# ---- yellow rows + badge in the live/upcoming list ----
rep("""                  background: pr ? 'rgba(247,120,186,0.10)' : 'var(--panel)',
                  border: `1px solid ${pr ? 'rgba(247,120,186,0.85)'
                    : n >= 3 ? 'rgba(63,185,80,0.55)' : 'var(--line)'}`,
                  boxShadow: pr ? '0 0 14px rgba(247,120,186,0.22)' : undefined,""",
    """                  background: yel ? 'rgba(227,179,65,0.10)' : pr ? 'rgba(247,120,186,0.10)' : 'var(--panel)',
                  border: `1px solid ${yel ? 'rgba(227,179,65,0.85)' : pr ? 'rgba(247,120,186,0.85)'
                    : n >= 3 ? 'rgba(63,185,80,0.55)' : 'var(--line)'}`,
                  boxShadow: yel ? '0 0 14px rgba(227,179,65,0.22)'
                    : pr ? '0 0 14px rgba(247,120,186,0.22)' : undefined,""")

rep("""              const pr = pinkRule(s.p, s.cells.map(c => c.key))""",
    """              const pr = pinkRule(s.p, s.cells.map(c => c.key))
              // a FAVOURITE pick -- yellow, and never pink, so the two can never be confused
              const yel = isFavPick(s.p) && s.cells.some(c => FAV_CELLS.has(c.key))""")

rep("""                    {pr ? (
                      <span title={pr.tip} style={{ fontSize: 10, fontWeight: 800, color: PINK,""",
    """                    {yel ? (
                      <span title={(cells.find(c => c.key === 'mc2_fav4_w') || {}).note}
                        style={{ fontSize: 10, fontWeight: 800, color: YELLOW,
                          border: '1px solid ' + YELLOW + '88', borderRadius: 6, padding: '0 5px' }}>
                        {'\\u2b50 FAV'}
                      </span>
                    ) : null}
                    {pr && !yel ? (
                      <span title={pr.tip} style={{ fontSize: 10, fontWeight: 800, color: PINK,""")
rep("""                    <span style={{ fontSize: 13, fontWeight: 700, color: pr ? PINK : 'var(--text-primary)' }}>{s.p.pick}</span>""",
    """                    <span style={{ fontSize: 13, fontWeight: 700, color: yel ? YELLOW : pr ? PINK : 'var(--text-primary)' }}>{s.p.pick}</span>""")

rep("<b>ITF men is excluded</b>",
    "<b style={{ color: YELLOW }}>\\u2b50 Yellow = a FAVOURITE</b>, kept visually and numerically separate from the dogs: "
    "MC2 4pt+ over the market on a <b>women\\u2019s</b> favourite at \\u2212100..\\u2212200 \\u2014 +22.85% on 51 (t 2.16), positive in "
    "both windows and both bands, against \\u22129.21% for the men\\u2019s half. <b>ITF men is excluded</b>")

for k, v in (("__TIP_W__", TIP_W), ("__TIP_M__", TIP_M)):
    assert k in s, k
    s = s.replace(k, v)

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched DogPicksPanel.jsx")
for k in ("FAV_CELLS", "isFavPick", "YELLOW"):
    print("   %-12s refs %d" % (k, s.count(k)))
print("RESULT: OK")
