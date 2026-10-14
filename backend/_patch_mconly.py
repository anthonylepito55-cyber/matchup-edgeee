"""STRIP THE BOARD TO MC2/MC3/MC5 ONLY (2026-10-13).

User: "any signals under the picks u can remove them unless its mc2 mc3 and mc5 also any
highlights that arent mc2 mc3 and mc5 u can remove", with the example strip:

    GRAY 2pt DOG / MC TOSS-UP / ⚄ MC DOG / ➕ MC / ➕ C-MC

Note "MC" in those labels is the OLD Monte-Carlo-on-C family (refuted, watch-only), NOT MC2 --
so a naive "keep anything containing MC" test would keep exactly the chips being complained
about. Every label in the per-card chip strip was enumerated and NONE of them is MC2/MC3/MC5:
the new heads render as model lines and brown marks, never as chips. So the strip goes whole.

GATED, NOT DELETED. One flag, MC_ONLY, switches the display; every predicate, lane and
`bet()` call underneath keeps running exactly as before, so the live records continue to
accumulate and nothing has to be rebuilt to turn a family back on. Same approach as the blue
seasonal-band revert, where the lanes kept scoring silently after the colour was pulled.

WHAT IS REMOVED
  * the per-card chip strip (every ➕ / ★ / ⚄ / GRAY / MC / c75 / FADE / TIER chip)
  * the ⚖️ conflict-resolver badges
  * the player-name colours (gray-line pick, ★ C+GRAY DOG, and the three red flags) -- all
    Model C / gray-line families
  * the top-right category badge
  * the ✖ X DOG marker (Model X)
  * the Ⓖ G FAV-OVER / G DOG-FLIP badge and its black/yellow card colours
  * the green highlight family (hlAny: black c75, bait green, purple CGF, tier-1 blue,
    Model P, pink) and the dark-blue family (gray dog, s52)

WHAT STAYS
  * MC2 / MC3 / MC5 model lines and the per-card model dropdown
  * the market line
  * 🟤 BROWN marks (mc2Mark -- requires MC2, MC3 and MC5 to agree on the side) and the
    🟠 MC2 5-8pt watch mark (orangeMark)
  * the stats dropdown
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "frontend", "src", "TennisSection.jsx")
P = os.path.normpath(P)
s = io.open(P, encoding="utf-8").read()
assert "MC_ONLY" not in s, "already patched"
n0 = len(s)


def rep(old, new, count=1):
    global s
    assert s.count(old) == count, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


# ---------------------------------------------------------------- the flag
rep("const MC2_AUTO_UNMARK = false",
    """// MC2/MC3/MC5 ONLY (2026-10-13, user "any signals under the picks u can remove them
// unless its mc2 mc3 and mc5 also any highlights that arent mc2 mc3 and mc5"). Display-only
// gate: every predicate, lane and bet() underneath still runs, so the live records keep
// accumulating and flipping this back to false restores the old board untouched.
const MC_ONLY = true
const MC2_AUTO_UNMARK = false""")

# ------------------------------------------------- name colours (all Model C / gray line)
rep("""  const nameHighlight = isP1 => {
    if (starDogSideP1 !== null && starDogSideP1 === isP1) {""",
    """  const nameHighlight = isP1 => {
    if (MC_ONLY) return null          // every family here is Model C / gray line, not MC2
    if (starDogSideP1 !== null && starDogSideP1 === isP1) {""")

# ------------------------------------------------------- highlight families -> MC2 only
rep("""  const hlBlack = !!blackC75W && hlOK('c75_dog_100plus', 'w')""",
    """  // MC_ONLY: the green and dark-blue families are c75 / bait / CGF / tier-1 / Model P /
  // pink / gray-dog / s52 -- none of them MC2, MC3 or MC5 -- so they stop painting cards.
  // The underlying predicates are left intact above so their lanes keep scoring.
  const hlBlack = !MC_ONLY && !!blackC75W && hlOK('c75_dog_100plus', 'w')""")
for name, expr in (
    ("hlGreen", "!!baitGreen && baitGreen.c75Flip !== false && hlOK('bait_mcflip', gHL)"),
    ("hlPurple", "!!purpleCGF && hlOK(purpleCGF.premium ? 'cgf_premium' : 'cgf_shallow_fav', gHL)"),
    ("hlBlue", "!!tier1Blue && tier1Blue.cells.some(c => hlOK(c.lane, gHL))"),
    ("hlPink", "!!pinkCells && pinkCells.some(c => !c.watch && hlOK(c.lane, c.g))"),
):
    rep("  const %s = %s" % (name, expr), "  const %s = !MC_ONLY && (%s)" % (name, expr))
rep("  const hlGrayDog = grayDogs.some(h => livePos(h.lane, gHL))",
    "  const hlGrayDog = !MC_ONLY && grayDogs.some(h => livePos(h.lane, gHL))")
rep("  const hlS52 = !!blueS52 && livePos(blueS52.lane, gHL)",
    "  const hlS52 = !MC_ONLY && !!blueS52 && livePos(blueS52.lane, gHL)")
rep("  const hlP = (!!(pModel && pModel.bet) && hlOK('p_dog', gHL)) || (!!(pModel && pModel.close) && hlOK(`p_close_t${pModel.close_tier || 1}`, gHL))",
    "  const hlP = !MC_ONLY && ((!!(pModel && pModel.bet) && hlOK('p_dog', gHL)) || (!!(pModel && pModel.close) && hlOK(`p_close_t${pModel.close_tier || 1}`, gHL)))")

# ------------------------------------------------- Model G: ungated marks, not an MC head
rep("""  const HLs = hlAny ? HL
    : (hlGrayDog || hlS52) ? HL_DARKBLUE
      : (gMark && !gMark.recon) ? ((gMark.cell === 'FAV-OVER') ? HL_BLACK : HL_YELLOW)
        : (mc2Mark && !mc2Mark.recon && !mc2Mark.avoid) ? HL_BROWN : HL_ORANGE""",
    """  // MC_ONLY: G's black/yellow marks are a third model's visibility marks, so they go too;
  // brown (MC2+MC3+MC5 agreement) and the orange MC2 watch mark are all that can paint.
  const gMarkShow = !MC_ONLY && gMark
  const HLs = hlAny ? HL
    : (hlGrayDog || hlS52) ? HL_DARKBLUE
      : (gMarkShow && !gMark.recon) ? ((gMark.cell === 'FAV-OVER') ? HL_BLACK : HL_YELLOW)
        : (mc2Mark && !mc2Mark.recon && !mc2Mark.avoid) ? HL_BROWN : HL_ORANGE""")
rep("""  const hlOn = hlAny || hlGrayDog || hlS52 || !!(gMark && !gMark.recon)
    || !!(mc2Mark && !mc2Mark.recon && !mc2Mark.avoid) || !!orangeMark""",
    """  const hlOn = hlAny || hlGrayDog || hlS52 || !!(gMarkShow && !gMark.recon)
    || !!(mc2Mark && !mc2Mark.recon && !mc2Mark.avoid) || !!orangeMark""")
rep("      {gMark ? (", "      {gMarkShow ? (")

# ------------------------------------------- the chip strip and the conflict-resolver row
rep("""        if (!mc3 || mc3.p1_prob == null || mc3.market_aware_p1 == null || mc3.market_p1 == null) return null""",
    """        if (MC_ONLY) return null       // no chip in this strip is MC2, MC3 or MC5
        if (!mc3 || mc3.p1_prob == null || mc3.market_aware_p1 == null || mc3.market_p1 == null) return null""")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched TennisSection.jsx (%+d chars)" % (len(s) - n0))
assert s.count("MC_ONLY") >= 12
print("   MC_ONLY refs: %d" % s.count("MC_ONLY"))
print("RESULT: OK")
