"""HIDE THE CELLS THAT FAIL THEIR LIVE-ROI GATE (2026-10-11, user: "only highlight positive
live roi picks remove highlights of everything else", then "Both" on hide+floor and "Keep 3"
on the dog floor).

The gate already refused to COLOUR a cell whose live lane ROI was at or below zero -- that part
was working, e.g. tier1 women at -7.8% and p_dog men at -41.9% were already dark. What it still
did was DRAW the cell anyway, dimmed to 50% opacity with a "⚪ NO HIGHLIGHT (live -7.8% (7-10))"
note in front of it. That is the clutter being removed here: a ribbon cell that fails its gate
now renders nothing at all.

Scope decisions:
  * the dog floor stays at 3 (user: "Keep 3"); the favourite floor stays at the 25 shipped
    earlier today
  * EXPLICIT WATCH cells are untouched -- they are labelled NO BET rather than highlighted, and
    they are the record that justifies a demotion. CE5 is -31.4% on n=63 and FADE-GOLD -7.5%
    on n=38, i.e. actively earning their demotion, which is worth seeing.
  * the Ⓟ MODEL P line is untouched: it always renders TAKE-or-PASS with P's probability and
    EV, so it is a model readout rather than a ribbon mark. Only its noHL prefix is dropped,
    since the card colour already carries that information.
"""
import io

P = "frontend/src/TennisSection.jsx"


def rep(a, b):
    s = io.open(P, encoding="utf-8").read()
    assert s.count(a) == 1, (s.count(a), a[:100])
    io.open(P, "w", encoding="utf-8", newline="\n").write(s.replace(a, b))


# ---- the four ribbon blocks: render only when their own gate passes --------------------
# 2026-10-11: each of these used to draw dimmed with a NO HIGHLIGHT reason when its lane was
# live-negative. They now render nothing, so the card only ever shows qualifying cells.
rep("      {blackC75W ? (", "      {blackC75W && hlBlack ? (")
rep("      {!baitGreen && purpleCGF ? (", "      {!baitGreen && purpleCGF && hlPurple ? (")
rep("      {!baitGreen && tier1Blue && !purpleCGF && !purpleCE5 && !purpleFGW ? (",
    "      {!baitGreen && tier1Blue && hlBlue && !purpleCGF && !purpleCE5 && !purpleFGW ? (")
rep("      {baitGreen ? (", "      {baitGreen && hlGreen ? (")

# ---- pink: hide the failed TAKE cells, keep the explicit WATCH ones --------------------
rep("""      {pinkCells ? pinkCells.map((pc, j) => {""",
    """      {/* 2026-10-11: a pink TAKE cell that fails its live gate is dropped entirely; the
          explicit WATCH cells stay, because they are labelled NO BET and their record is the
          evidence for the demotion. */}
      {pinkCells ? pinkCells.filter(pc => pc.watch || hlOK(pc.lane, pc.g)).map((pc, j) => {""")

# ---- the NO HIGHLIGHT prefixes are now dead weight on the blocks that survive ----------
rep("""            {hlBlack ? null : noHL(hlWhy('c75_dog_100plus', 'w'))}\n""", "")
rep("""          {hlPurple ? null : noHL(hlWhy(purpleCGF.premium ? 'cgf_premium' : 'cgf_shallow_fav', gHL))}\n""", "")
rep("""          {hlBlue ? null : noHL(blueWhy)}\n""", "")
rep("""          {hlGreen ? null : noHL(baitGreen.c75Flip === false ? 'MC refuses — backtest negative' : hlWhy('bait_mcflip', gHL))}\n""", "")
rep("""            {pModel.bet && !hlP ? noHL(hlWhy('p_dog', gHL)) : null}\n""", "")

# the pink one keeps a prefix, but only ever for a WATCH cell now
rep("""            {(!pc.watch && hlOK(pc.lane, pc.g)) ? null : noHL(pc.watch ? 'watch only' : hlWhy(pc.lane, pc.g))}""",
    """            {pc.watch ? noHL('watch only') : null}""")

# and the surviving blocks are always qualifying, so stop dimming them
rep("""style={{ fontSize: 9, fontWeight: 800, color: '#f0f0f2', marginBottom: 6, letterSpacing: '0.05em', background: 'linear-gradient(90deg, rgba(255,255,255,0.10), transparent)', padding: '3px 6px', borderRadius: 4, border: '1px solid rgba(255,255,255,0.35)', opacity: hlBlack ? 1 : 0.5 }}>""",
    """style={{ fontSize: 9, fontWeight: 800, color: '#f0f0f2', marginBottom: 6, letterSpacing: '0.05em', background: 'linear-gradient(90deg, rgba(255,255,255,0.10), transparent)', padding: '3px 6px', borderRadius: 4, border: '1px solid rgba(255,255,255,0.35)' }}>""")
rep("""style={{ fontSize: 9, fontWeight: 800, color: '#bc8cff', marginBottom: 6, letterSpacing: '0.04em', textShadow: '0 0 8px rgba(188,140,255,0.5)', opacity: hlPurple ? 1 : 0.5 }}>""",
    """style={{ fontSize: 9, fontWeight: 800, color: '#bc8cff', marginBottom: 6, letterSpacing: '0.04em', textShadow: '0 0 8px rgba(188,140,255,0.5)' }}>""")
rep("""style={{ fontSize: 9, fontWeight: 800, color: '#58a6ff', marginBottom: 6, letterSpacing: '0.04em', textShadow: '0 0 8px rgba(88,166,255,0.5)', opacity: hlBlue ? 1 : 0.5 }}>""",
    """style={{ fontSize: 9, fontWeight: 800, color: '#58a6ff', marginBottom: 6, letterSpacing: '0.04em', textShadow: '0 0 8px rgba(88,166,255,0.5)' }}>""")
print("failed ribbon cells now hidden; watch cells and the P readout kept")
