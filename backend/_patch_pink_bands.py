"""BAND-SPECIFIC PINK MARKS ON THE DOG TAB (2026-10-14).

User: "for +100 to +150 dogs mc2 highlight them all pink on dog tab", then "for +150-200 only
mc2/6pt and fade form marked pink". Then "Ship all" / "No I want that marked to" for the third band
(+200..+250, c75 family) after the concern below was raised -- so all three ship.

The rule is band-dependent because the cells genuinely behave differently by band, which the
cell x band matrix showed (_dog_cell_by_band.py):

  +100..+150  ANY MC2-family cell. Every bucket on the whole board clearing |t| >= 2 lives here
              and is MC2:
                  MC2 DOG (pink)       n=119  72-47  +29.97%  +$891.50  t 3.11  <- highest t found
                  MC2 DOG BAND         n=62   38-24  +29.61%  +$459.00  t 2.26
                  MC2 TAKE DOG (unst.) n=79   46-33  +26.34%  +$520.25  t 2.19

  +150..+200  ONLY MC2 6pt / TAKE and FADE FORM. The rest of the MC2 family inverts here and the
              c75 family is flat:
                  MC2 6pt+ / TAKE      n=54   24-30  +21.30%  t 1.15
                  FADE FORM dogs       n=11          +22.70%           <- eleven bets
                  MC2 DOG (pink)       n=22    7-15  -12.41%   excluded
                  MC2 DOG BAND         n=9           -12.20%   excluded
                  c75 DOG FLIP         n=39   14-25   -2.79%   excluded
                  c50+c75 DOG          n=34   12-22   -5.09%   excluded
                  TIER-AVOID dogs      n=41   15-26   -1.98%   excluded

STRENGTH OF EACH, honestly, and written onto the tab in these terms:
  * +100..+150 is the only part with real support, and even there 3 of 40 buckets clear t=2
    against ~2.0 expected by chance. What lifts it above that is that the hits CLUSTER in one
    band and one family where chance would scatter, and the band is positive for 19 of 20 cells
    and is the only band clearing t=2 overall (+16.07% on 254, t 2.35). The three cells overlap
    heavily, so it is nearer one finding than three.
  * +150..+200 rests on t 1.15 for the MC2 side and ELEVEN bets for fade form. A lean.

THE +200..+250 BAND, shipped on the user's explicit call with the concern on record. It looked
like four c75 cells agreeing (+50.4%/13, +33.8%/12, +29.5%/10, +20.6%/8). Deduped it is THIRTEEN
BETS, 6-7, t 1.12 -- c75_dog_100plus alone IS all thirteen, so the four cells are the same bets
counted four times rather than four confirmations, and all thirteen fall inside one ten-day
window. The badge reads "c75 n13" so the sample travels with the mark.

Display only: a pink row treatment and a badge naming which rule fired. No lane changes, no board
marks, nothing filtered out -- non-pink picks are listed exactly as before.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "frontend", "src", "DogPicksPanel.jsx")
P = os.path.normpath(P)
s = io.open(P, encoding="utf-8").read()
assert "PINK_RULES" not in s, "already patched"

TIPS = {
    "__TIP_LO__": (
        "MC2 dog at +100..+150 - the one cell x band concentration on this board. MC2 pink "
        "+29.97% on 119 (t 3.11, the highest t anywhere), MC2 band +29.61% on 62 (t 2.26), "
        "MC2 take +26.34% on 79 (t 2.19). Caveat: 3 of 40 buckets clear t=2 against ~2 expected "
        "by chance, but they cluster in one band and one family where chance scatters, and this "
        "band is positive for 19 of 20 cells. The three cells overlap, so this is one finding, "
        "not three."),
    "__TIP_HI__": (
        "MC2 6pt / TAKE or FADE FORM at +150..+200 - the only cells that survive this band. "
        "MC2 6pt/take +21.30% on 54 (t 1.15); fade form +22.70% on just 11. Everything else "
        "inverts here: MC2 pink -12.41% on 22, MC2 band -12.20%, c75 flip -2.79% on 39, "
        "c50+c75 -5.09% on 34, tier-avoid -1.98% on 41. A LEAN, not a result."),
    "__TIP_C75__": (
        "c75 family at +200..+250 - the band where c75 and MC2 swap places (c75 +50.4%, MC2 "
        "-2.89% on 37). THIRTEEN BETS, 6-7, t 1.12, all inside one ten-day window. The four c75 "
        "cells are NOT four confirmations: c75_dog_100plus alone is all 13, so they are the same "
        "bets counted four times. Marked on your call with the sample stated - one bad week "
        "flips it negative."),
}

BLOCK = """// BAND-SPECIFIC PINK (2026-10-14, user asks). The cells behave differently by band, so the rule
// does too. Every number behind this is in _patch_pink_bands.py.
//
//   +100..+150  ANY MC2-family cell. Every bucket on the board clearing |t| >= 2 is here and is
//               MC2: pink +29.97%/119 (t 3.11), band +29.61%/62 (t 2.26), take +26.34%/79 (t 2.19).
//   +150..+200  ONLY MC2 6pt / TAKE (+21.30%/54, t 1.15) and FADE FORM (+22.70% on just 11),
//               because the rest invert here: MC2 pink -12.41%/22, MC2 band -12.20%,
//               c75 flip -2.79%/39, c50+c75 -5.09%/34, tier-avoid -1.98%/41.
//
// Only the first band has real support, and even there 3 of 40 buckets clear t=2 against ~2
// expected by chance -- what lifts it is that the hits cluster in one band and one family where
// chance scatters. The second band is a lean (t 1.15, and eleven bets for fade form).
//
//   +200..+250  the C75 FAMILY, which swaps places with MC2 (c75 +50.4% against MC2 -2.89%/37).
//               SHIPPED ON THE USER'S EXPLICIT CALL after the sample was shown and the concern
//               raised: deduped it is THIRTEEN BETS, 6-7, t 1.12, all inside one ten-day window,
//               and c75_dog_100plus alone IS all 13 -- the four cells are the same bets counted
//               four times, not four confirmations. The badge carries "n13" so the sample is
//               never out of sight, and one bad week flips it negative.
//
// Display only: no lane, no board mark, nothing filtered out.
const PINK = '#f778ba'
const PINK_TAG = '\\u{1F9E1} '
const PINK_RULES = [
  { lo: 100, hi: 150, tag: 'MC2', tip: '__TIP_LO__',
    cells: new Set(['pink_mc2_dog', 'mc2_dog_band', 'mc2_take_dog_all', 'mc2_dog6_all',
                    'mc2_dog_flip']) },
  { lo: 150, hi: 200, tag: '6pt/FADE', tip: '__TIP_HI__',
    cells: new Set(['mc2_dog6_all', 'mc2_take_dog_all', 'pf_c75_dis_dog']) },
  { lo: 200, hi: 250, tag: 'c75 n13', tip: '__TIP_C75__',
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

const DROP_LEAGUES = new Set(['itf_men'])"""


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


rep("const DROP_LEAGUES = new Set(['itf_men'])", BLOCK)

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
                        border: '1px solid ' + PINK + '88', borderRadius: 6, padding: '0 5px' }}>
                        {PINK_TAG}{pr.tag}
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
    "<b style={{ color: PINK }}>{PINK_TAG}Pink</b> = <b>MC2</b> at <b>+100..+150</b> (every bucket clearing t=2 is here "
    "and is MC2: pink +29.97%/119 t 3.11, band +29.61%/62 t 2.26, take +26.34%/79 t 2.19), or "
    "<b>MC2 6pt/take or fade form</b> at <b>+150..+200</b> (+21.30%/54 t 1.15 and +22.70% on 11 — a lean; "
    "the other cells invert there), or the <b>c75 family</b> at <b>+200..+250</b> (c75 and MC2 swap places there, "
    "but this is <b>13 bets, 6-7, t 1.12</b> — the four c75 cells are the same 13 bets counted four times). "
    "<b>ITF men is excluded</b>")

for k, v in TIPS.items():
    assert k in s, k
    s = s.replace(k, v)
assert "__TIP_" not in s

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched DogPicksPanel.jsx")
for k in ("PINK_RULES", "pinkRule(", "PINK_TAG"):
    print("   %-14s refs %d" % (k, s.count(k)))
print("RESULT: OK")
