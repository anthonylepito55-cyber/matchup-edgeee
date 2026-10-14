"""SPLIT THE FAVOURITE MARK: YELLOW -100..-150, GOLD -150..-200 (2026-10-14).

User: "mark -150 to -200 favorites gold as well on the dog tab".

Both bands are the same cell -- a women's favourite that MC2 rates 4pt+ above the de-vigged
market -- and both are in the one lane (mc2_fav4_w, which covers -100..-200). This only separates
them on screen, because they are separately measured and the deeper band is the stronger half:

    -100..-150   n=28  19-9   67.9% hit vs 55.5% needed   +22.31%   t 1.40   -> YELLOW
    -150..-200   n=23  18-5   78.3% hit vs 63.2% needed   +23.50%   t 1.73   -> GOLD

So gold is the better half on both ROI and t, which is the right way round for the brighter
colour. The badge carries the band and the n so the two can never be read as one number.

Colours are chosen to be distinguishable on the dark board rather than two shades of amber:
yellow stays the existing #e3b341, gold is #ffd700 with a stronger glow.

Both remain inside FAV_CELLS, so neither enters any dog aggregate.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "frontend", "src", "DogPicksPanel.jsx")
P = os.path.normpath(P)
s = io.open(P, encoding="utf-8").read()
assert "GOLD" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


rep("""const YELLOW = '#e3b341'
const FAV_CELLS = new Set(['mc2_fav4_w', 'mc2_fav4_m'])
const isFavPick = p => p.odds != null && p.odds < 0""",
    """const YELLOW = '#e3b341'
const GOLD = '#ffd700'
const FAV_CELLS = new Set(['mc2_fav4_w', 'mc2_fav4_m'])
const isFavPick = p => p.odds != null && p.odds < 0

// TWO BANDS, TWO COLOURS (2026-10-14, user "mark -150 to -200 favorites gold as well"). Same
// cell and same lane -- a women's favourite MC2 rates 4pt+ over the market -- but the bands are
// separately measured and the deeper one is the stronger half, so gold is the brighter colour:
//     -100..-150  n=28  19-9   67.9% hit vs 55.5% needed  +22.31%  t 1.40  -> yellow
//     -150..-200  n=23  18-5   78.3% hit vs 63.2% needed  +23.50%  t 1.73  -> gold
// The badge carries the band and the n so the two are never read as one number.
const FAV_BANDS = [
  { lo: -150, hi: -100, tag: 'FAV \\u2212100/150', col: YELLOW, rgba: '227,179,65',
    note: '-100..-150: +22.31% on 28 (19-9), 67.9% hit against 55.5% needed, t 1.40.' },
  { lo: -200, hi: -150, tag: 'FAV \\u2212150/200', col: GOLD, rgba: '255,215,0',
    note: '-150..-200: +23.50% on 23 (18-5), 78.3% hit against 63.2% needed, t 1.73 -- the stronger half.' },
]
const favBandOf = p => (p.odds == null || p.odds >= 0) ? null
  : (FAV_BANDS.find(b => p.odds >= b.lo && p.odds <= b.hi) || null)""")

# the live/upcoming row: colour by band
rep("""              const yel = isFavPick(s.p) && s.cells.some(c => FAV_CELLS.has(c.key))""",
    """              const fb = (isFavPick(s.p) && s.cells.some(c => FAV_CELLS.has(c.key)))
                ? favBandOf(s.p) : null
              const yel = !!fb""")

rep("""                  background: yel ? 'rgba(227,179,65,0.10)' : pr ? 'rgba(247,120,186,0.10)' : 'var(--panel)',
                  border: `1px solid ${yel ? 'rgba(227,179,65,0.85)' : pr ? 'rgba(247,120,186,0.85)'
                    : n >= 3 ? 'rgba(63,185,80,0.55)' : 'var(--line)'}`,
                  boxShadow: yel ? '0 0 14px rgba(227,179,65,0.22)'
                    : pr ? '0 0 14px rgba(247,120,186,0.22)' : undefined,""",
    """                  background: fb ? `rgba(${fb.rgba},0.10)` : pr ? 'rgba(247,120,186,0.10)' : 'var(--panel)',
                  border: `1px solid ${fb ? `rgba(${fb.rgba},0.85)` : pr ? 'rgba(247,120,186,0.85)'
                    : n >= 3 ? 'rgba(63,185,80,0.55)' : 'var(--line)'}`,
                  boxShadow: fb ? `0 0 16px rgba(${fb.rgba},0.30)`
                    : pr ? '0 0 14px rgba(247,120,186,0.22)' : undefined,""")

rep("""                    {yel ? (
                      <span title={(cells.find(c => c.key === 'mc2_fav4_w') || {}).note}
                        style={{ fontSize: 10, fontWeight: 800, color: YELLOW,
                          border: '1px solid ' + YELLOW + '88', borderRadius: 6, padding: '0 5px' }}>
                        {'\\u2b50 FAV'}
                      </span>
                    ) : null}""",
    """                    {fb ? (
                      <span title={fb.note + '  ' + ((cells.find(c => c.key === 'mc2_fav4_w') || {}).note || '')}
                        style={{ fontSize: 10, fontWeight: 800, color: fb.col,
                          border: '1px solid ' + fb.col + '99', borderRadius: 6, padding: '0 5px' }}>
                        {'\\u2b50 ' + fb.tag}
                      </span>
                    ) : null}""")

rep("""                    <span style={{ fontSize: 13, fontWeight: 700, color: yel ? YELLOW : pr ? PINK : 'var(--text-primary)' }}>{s.p.pick}</span>""",
    """                    <span style={{ fontSize: 13, fontWeight: 700, color: fb ? fb.col : pr ? PINK : 'var(--text-primary)' }}>{s.p.pick}</span>""")

# the history rows get the band colour too
rep("""                        background: pinkRule(p, histCells(p).map(c => c.key)) ? 'rgba(247,120,186,0.09)' : 'var(--panel)',
                        border: `1px solid ${pinkRule(p, histCells(p).map(c => c.key)) ? 'rgba(247,120,186,0.6)'
                          : p.won ? 'rgba(63,185,80,0.3)' : 'var(--line)'}`,""",
    """                        background: favBandOf(p) ? `rgba(${favBandOf(p).rgba},0.09)`
                          : pinkRule(p, histCells(p).map(c => c.key)) ? 'rgba(247,120,186,0.09)' : 'var(--panel)',
                        border: `1px solid ${favBandOf(p) ? `rgba(${favBandOf(p).rgba},0.65)`
                          : pinkRule(p, histCells(p).map(c => c.key)) ? 'rgba(247,120,186,0.6)'
                          : p.won ? 'rgba(63,185,80,0.3)' : 'var(--line)'}`,""")

# the favourite summary line: split the women's box by band
rep("""                  <div style={{ fontSize: 10, color: YELLOW, fontWeight: 700, marginBottom: 5 }}>
                    🟡 FAVOURITES — separate from every dog number above. MC2 4pt+ over the market at −100..−200.
                  </div>""",
    """                  <div style={{ fontSize: 10, fontWeight: 700, marginBottom: 5 }}>
                    <span style={{ color: YELLOW }}>🟡 −100..−150</span>
                    <span style={{ color: 'var(--text-tertiary)' }}>{' / '}</span>
                    <span style={{ color: GOLD }}>🥇 −150..−200 (the stronger half)</span>
                    <span style={{ color: 'var(--text-tertiary)' }}>
                      {' — FAVOURITES, separate from every dog number above. MC2 4pt+ over the market. '}
                      {'Yellow +22.31%/28 t 1.40 · gold +23.50%/23 t 1.73 · combined +22.85%/51 t 2.16.'}
                    </span>
                  </div>""")

rep("\\u2b50 Yellow = a FAVOURITE</b>, kept visually and numerically separate from the dogs: ",
    "\\u2b50 Yellow (\\u2212100..\\u2212150) and \\ud83e\\udd47 gold (\\u2212150..\\u2212200) = a FAVOURITE</b>, kept visually and numerically separate from the dogs: ")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched DogPicksPanel.jsx")
for k in ("GOLD", "FAV_BANDS", "favBandOf"):
    print("   %-12s refs %d" % (k, s.count(k)))
assert "const yel = !!fb" in s
print("RESULT: OK")
