"""🩷 PINK ON THE DOG TAB -- BAND-SPECIFIC (2026-10-14).

User: "for +100 to +150 dogs mc2 highlight them all pink on dog tab", then "for +150-200 only
mc2/6pt and fade form marked pink".

The rule is band-dependent because the cells behave differently by band, which is what the
cell x band matrix showed (_dog_cell_by_band.py):

  +100..+150 -- ANY MC2-family cell. Every bucket on the board clearing |t| >= 2 is here and is
  MC2:
        MC2 DOG (pink)        n=119  72-47  +29.97%  +$891.50  t 3.11   <- highest t on the board
        MC2 DOG BAND          n=62   38-24  +29.61%  +$459.00  t 2.26
        MC2 TAKE DOG (unst.)  n=79   46-33  +26.34%  +$520.25  t 2.19

  +150..+200 -- ONLY MC2 6pt / TAKE and FADE FORM, because the rest of the MC2 family inverts
  here and the c75 family is flat:
        MC2 6pt+ / TAKE DOG   n=54   24-30  +21.30%  +$287.50  t 1.15
        FADE FORM dogs        n=11          +22.70%                     <- only 11 bets
        MC2 DOG (pink)        n=22    7-15  -12.41%                     excluded
        MC2 DOG BAND          n=9           -12.20%                     excluded
        c75 DOG FLIP          n=39   14-25   -2.79%                     excluded
        c50+c75 DOG           n=34   12-22   -5.09%                     excluded
        TIER-AVOID dogs       n=41   15-26   -1.98%                     excluded

HONEST ABOUT THE EVIDENCE, as the tab itself says:
  * 3 of 40 buckets clear |t| >= 2 against ~2.0 expected by chance, so the raw count is barely
    above noise. What makes it more than that is that the hits CLUSTER -- one band, one family --
    where chance scatters across a 40-bucket matrix, and +100..+150 is positive for 19 of 20
    cells and is the only band clearing t=2 overall (+16.07% on 254, t 2.35).
  * the three +100..+150 cells overlap heavily, so this is closer to ONE finding than three.
  * the +150..+200 half rests on t 1.15 for the MC2 side and ELEVEN bets for fade form. That is
    a lean, not a result, and it is labelled as such on the badge.

Display only: a pink row treatment and a 🩷 badge. No lane changes, no board marks, nothing
filtered out -- non-pink picks are still listed exactly as before.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "frontend", "src", "DogPicksPanel.jsx")
P = os.path.normpath(P)
s = io.open(P, encoding="utf-8").read()
assert "PINK_RULES" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


TIP_LO = ("MC2 dog at +100..+150 \\u2014 the one cell\\u00d7band concentration on this board. "
          "MC2 pink +29.97% on 119 (t 3.11, the highest t anywhere), MC2 band +29.61% on 62 "
          "(t 2.26), MC2 take +26.34% on 79 (t 2.19). Caveat: 3 of 40 buckets clear t=2 against "
          "~2 expected by chance, but they cluster in one band and one family, and +100..+150 is "
          "positive for 19 of 20 cells. The three cells overlap, so this is one finding, not three.")
TIP_HI = ("MC2 6pt / TAKE or FADE FORM at +150..+200 \\u2014 the only cells that survive this band. "
          "MC2 6pt/take +21.30% on 54 (t 1.15); fade form +22.70% on just 11. Everything else "
          "inverts here: MC2 pink -12.41% on 22, MC2 band -12.20%, c75 flip -2.79% on 39, "
          "c50+c75 -5.09% on 34, tier-avoid -1.98% on 41. A LEAN, not a result \\u2014 t 1.15 and "
          "eleven bets respectively.")

TIP_C75 = ("c75 family at +200..+250 \u2014 the band where c75 and MC2 swap places. c75 +100up "
           "+50.40% on 13, c75 flip +33.80% on 12, c50+c75 +29.50% on 10, c50+c75-no-D +20.60% on 8, "
           "while MC2 6pt/take is -2.89% on 37 here. VERY THIN: every one of those cells is 8-13 bets "
           "and none clears t=2, and they overlap heavily so the distinct sample is smaller still. "
           "The direction is consistent across all four, which is the only reason it is marked.")

_BLOCK = """// 🩷 PINK, BAND-SPECIFIC (2026-10-14, user asks). The cells behave differently by band, so the
// rule does too -- see _patch_pinkmc2.py for every number behind this.
//
//   +100..+150  ANY MC2-family cell. Every bucket on the board clearing |t| >= 2 is here and is
//               MC2: pink +29.97%/119 (t 3.11), band +29.61%/62 (t 2.26), take +26.34%/79 (t 2.19).
//   +150..+200  ONLY MC2 6pt / TAKE (+21.30%/54, t 1.15) and FADE FORM (+22.70% on just 11),
//               because the rest invert here: MC2 pink -12.41%/22, MC2 band -12.20%,
//               c75 flip -2.79%/39, c50+c75 -5.09%/34, tier-avoid -1.98%/41.
//   +200..+250  the C75 FAMILY, which swaps places with MC2 in this band: c75 +100up +50.40%/13,
//               c75 flip +33.80%/12, c50+c75 +29.50%/10, no-D +20.60%/8, against MC2 6pt/take
//               -2.89%/37. Very thin -- 8 to 13 bets each, none clearing t=2, heavily
//               overlapping. Marked only because all four point the same way.
//
// 3 of 40 buckets clear t=2 against ~2 expected by chance, so the count alone is barely above
// noise; what makes it more is that the hits cluster in one band and one family where chance
// scatters, and +100..+150 is positive for 19 of 20 cells. The +150..+200 half is a LEAN -- t 1.15
// and eleven bets. Display only: no lane, no board mark, nothing filtered out.
const PINK = '#f778ba'
const PINK_RULES = [
  { lo: 100, hi: 150, tip: '__TIP_LO__',
    cells: new Set(['pink_mc2_dog', 'mc2_dog_band', 'mc2_take_dog_all', 'mc2_dog6_all', 'mc2_dog_flip']) },
  { lo: 150, hi: 200, tip: '__TIP_HI__',
    cells: new Set(['mc2_dog6_all', 'mc2_take_dog_all', 'pf_c75_dis_dog']) },
  { lo: 200, hi: 250, tip: '__TIP_C75__',
    cells: new Set(['mc_c75_dog', 'c75_dog_100plus', 'cc75_dog', 'cc75_nod_dog']) },
]
const pinkRule = (p, cellKeys) => {
  if (p.odds == null) return null
  const keys = [...(cellKeys || [])]
  for (const r of PINK_RULES) {
    if (p.odds >= r.lo && p.odds <= r.hi && keys.some(k => r.cells.has(k))) return r
  }
  return null
}

const DROP_LEAGUES = new Set(['itf_men'])""" )
_js = s_js_placeholder

rep("""              const n = s.cells.length
              const col = n >= 3 ? '#3fb950' : n === 2 ? '#e3b341' : 'var(--text-secondary)'
              return (
                <div key={i} className="mono" style={{
                  padding: '9px 13px', borderRadius: 8, background: 'var(--panel)',
                  border: `1px solid ${n >= 3 ? 'rgba(63,185,80,0.55)' : 'var(--line)'}`,
                }}>""",
    """              const n = s.cells.length
              const col = n >= 3 ? '#3fb950' : n === 2 ? '#e3b341' : 'var(--text-secondary)'
              const pr = pinkRule(s.p, s.cells.map(c => c.key))
              return (
                <div key={i} className="mono" style={{
                  padding: '9px 13px', borderRadius: 8,
                  background: pr ? 'rgba(247,120,186,0.10)' : 'var(--panel)',
                  border: `1px solid ${pr ? 'rgba(247,120,186,0.85)'
                    : n >= 3 ? 'rgba(63,185,80,0.55)' : 'var(--line)'}`,
                  boxShadow: pr ? '0 0 14px rgba(247,120,186,0.22)' : undefined,
                }}>""")

rep("""                    <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{s.p.pick}</span>""",
    """                    {pr ? (
                      <span title={pr.tip} style={{ fontSize: 10, fontWeight: 800, color: PINK,
                        border: `1px solid ${PINK}88`, borderRadius: 6, padding: '0 5px' }}>
                        {pr.lo === 100 ? '\\ud83e\\udde1 MC2' : '\\ud83e\\udde1 6pt/FADE'}
                      </span>
                    ) : null}
                    <span style={{ fontSize: 13, fontWeight: 700, color: pr ? PINK : 'var(--text-primary)' }}>{s.p.pick}</span>""")

rep("""                      <div key={i} className="mono" style={{
                        display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap',
                        padding: '5px 11px', borderRadius: 7, background: 'var(--panel)',
                        border: `1px solid ${p.won ? 'rgba(63,185,80,0.3)' : 'var(--line)'}`,
                      }}>""",
    """                      <div key={i} className="mono" style={{
                        display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap',
                        padding: '5px 11px', borderRadius: 7,
                        background: pinkRule(p, histCells(p).map(c => c.key)) ? 'rgba(247,120,186,0.09)' : 'var(--panel)',
                        border: `1px solid ${pinkRule(p, histCells(p).map(c => c.key)) ? 'rgba(247,120,186,0.6)'
                          : p.won ? 'rgba(63,185,80,0.3)' : 'var(--line)'}`,
                      }}>""")

rep("<b>ITF men is excluded</b>",
    "<b style={{ color: PINK }}>\\ud83e\\udde1 Pink</b> = an <b>MC2</b> dog at <b>+100..+150</b> (every bucket clearing t=2 is here and is MC2: "
    "pink +29.97%/119 t 3.11, band +29.61%/62 t 2.26, take +26.34%/79 t 2.19), or <b>MC2 6pt\\u2009/\\u2009take or fade form</b> at "
    "<b>+150..+200</b> (+21.30%/54 t 1.15 and +22.70% on 11 \\u2014 a lean, not a result; the other cells invert in that band). "
    "or the <b>c75 family</b> at <b>+200..+250</b> (c75 swaps places with MC2 there: +50.4%/13, +33.8%/12, +29.5%/10 "
    "against MC2 -2.9%/37 \u2014 very thin, 8-13 bets each, marked because all four agree). "
    "<b>ITF men is excluded</b>")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched DogPicksPanel.jsx")
for k in ("PINK_RULES", "pinkRule", "PINK "):
    print("   %-16s refs %d" % (k.strip(), s.count(k)))
print("RESULT: OK")
