"""ONE BOARD COLOUR FOR EVERY LIVE-POSITIVE CARD (2026-10-10, user: "make all games the same
board color instead of diff colors if it's positive").

Until now a highlighted card took one of seven colours depending on WHICH cell fired -- black
for the women's c75 dog, green for bait, purple for C-ALONE+GOLD, blue for tier 1, teal for
Model P, pink for the watch cells, orange (already dead). The colour carried no extra
information: every one of them already means the same thing, because `hlOK(lane, gender)` only
returns true when that lane's BACKTEST is positive for the gender AND its LIVE ROI is above zero
on 3+ settles. So seven colours were seven ways of saying "a live-positive signal fires here".

This collapses them to ONE: green, the colour of a positive number. The per-signal BADGES inside
the card keep their own colours, so it is still obvious which signal fired -- only the card's
own background, border and glow are unified.

Nothing about WHICH cards highlight changes here, and the auto-unmark behaviour the user asked
for is already live: hlOK re-reads each lane's live ROI from the frozen-log study on every
render, so a lane that turns negative loses its colour by itself.
"""
import io

P = "frontend/src/TennisSection.jsx"


def rep(a, b):
    s = io.open(P, encoding="utf-8").read()
    assert s.count(a) == 1, (s.count(a), a[:100])
    io.open(P, "w", encoding="utf-8", newline="\n").write(s.replace(a, b))


# ---- 1. one boolean for "this card has a live-positive signal" -------------------------
rep("""  const hlOK = (lane, g) => hlWhy(lane, g) === null""",
    """  const hlOK = (lane, g) => hlWhy(lane, g) === null
  // ONE COLOUR (2026-10-10, user "make all games the same board color"): every hl* flag below
  // already means exactly the same thing -- a cell whose backtest is positive for this gender
  // AND whose live lane ROI is above zero. So the seven colours carried no information the
  // badges did not already carry. hlAny is the single switch; HL is the one treatment.""")

rep("""  const hlP = (!!(pModel && pModel.bet) && hlOK('p_dog', gHL)) || (!!(pModel && pModel.close) && hlOK(`p_close_t${pModel.close_tier || 1}`, gHL))""",
    """  const hlP = (!!(pModel && pModel.bet) && hlOK('p_dog', gHL)) || (!!(pModel && pModel.close) && hlOK(`p_close_t${pModel.close_tier || 1}`, gHL))
  // the single switch -- any live-positive cell lights the card, all of them the same way
  const hlAny = hlBlack || hlGreen || hlPurple || hlBlue || hlP || hlPink || hlOrange
  // one treatment: green, because it means "positive"
  const HL = {
    bg: 'rgba(63,185,80,0.13)',
    border: '1px solid rgba(63,185,80,0.85)',
    rail: '#3fb950',
    glow: '0 0 16px rgba(63,185,80,0.26)',
  }""")

# ---- 2. the card styling, collapsed ----------------------------------------------------
rep("""      background: hlBlack ? 'rgba(8,10,14,0.92)' : hlGreen ? (false ? 'rgba(248,81,73,0.09)' : 'rgba(63,185,80,0.13)') : hlPurple ? 'rgba(188,140,255,0.13)' : hlBlue ? 'rgba(88,166,255,0.11)' : hlP ? 'rgba(45,212,191,0.11)' : hlPink ? 'rgba(247,120,186,0.13)' : hlOrange ? 'rgba(240,136,62,0.10)' : 'var(--panel)',""",
    """      background: hlAny ? HL.bg : 'var(--panel)',""")

rep("""      border: hlBlack ? '2px solid #e8e8ea' : hlGreen ? (false ? '1px solid rgba(248,81,73,0.55)' : '1px solid rgba(63,185,80,0.85)') : hlPurple ? '1px solid rgba(188,140,255,0.85)' : hlBlue ? '1px solid rgba(88,166,255,0.80)' : hlP ? '1px solid rgba(45,212,191,0.80)' : hlPink ? '1px solid rgba(247,120,186,0.85)' : hlOrange ? '1px solid rgba(240,136,62,0.65)' : '1px solid var(--line)', borderRadius: 10,""",
    """      border: hlAny ? HL.border : '1px solid var(--line)', borderRadius: 10,""")

rep("""      padding: '18px 20px 16px', borderLeft: `3px solid ${hlBlack ? '#f0f0f2' : hlGreen ? (false ? '#f85149' : '#3fb950') : hlPurple ? '#bc8cff' : hlBlue ? '#58a6ff' : hlP ? '#2dd4bf' : hlPink ? '#f778ba' : hlOrange ? '#f0883e' : leagueColor}`,""",
    """      padding: '18px 20px 16px', borderLeft: `3px solid ${hlAny ? HL.rail : leagueColor}`,""")

rep("""      boxShadow: hlBlack ? '0 0 22px rgba(0,0,0,0.85), inset 0 0 40px rgba(255,255,255,0.04)' : hlGreen ? (false ? 'none' : '0 0 16px rgba(63,185,80,0.26)') : hlPurple ? '0 0 18px rgba(188,140,255,0.30)' : hlBlue ? '0 0 16px rgba(88,166,255,0.25)' : hlP ? '0 0 16px rgba(45,212,191,0.25)' : hlPink ? '0 0 16px rgba(247,120,186,0.28)' : hlOrange ? '0 0 14px rgba(240,136,62,0.18)' : undefined,""",
    """      boxShadow: hlAny ? HL.glow : undefined,""")
print("board colour collapsed to one: any live-positive cell -> green")
