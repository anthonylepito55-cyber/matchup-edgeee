"""REMOVE MODEL P AND ITS HIGHLIGHTS FROM THE UI (2026-10-14).

User: "Remove model P and it's highlights".

ONE FLAG, the same shape as MC_ONLY, rather than deleting several hundred lines across six call
sites. Setting SHOW_MODEL_P = false switches off, in one place:

    * the `Ⓟ Model P` tab button and its panel
    * the Ⓟ MODEL P chip on every card (TAKE / PASS line)
    * the 👑 Ⓟ DOG FLIP crown, which is drawn inside that chip
    * the Ⓟ CLOSE chip
    * the Ⓟ MODEL P TODAY strip
    * hlP -- so Model P can no longer colour a card at all
    * the second model_p block further down the card

It is done by forcing `pModel` to null, which is what every one of those reads from, plus three
small guards for the surfaces that do not go through pModel.

WHAT IS DELIBERATELY NOT DONE: the backend model, its columns and its lanes (p_dog, p_dog_flip,
p_close*) are untouched and keep scoring silently. Deleting them would throw away the forward
record of a model this project has already changed its mind about twice -- including the 👑 crown,
whose backtest said women +32.6% while the frozen log says -37.65% on 17. If the lanes are wanted
gone too, that is a separate and destructive step; say so and it is one more change.
"""
import io
import os

P = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "TennisSection.jsx"))
s = io.open(P, encoding="utf-8").read()
assert "SHOW_MODEL_P" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:80])
    s = s.replace(old, new)


# ---- the flag, beside MC_ONLY ----
rep("const MC_ONLY = true",
    """const MC_ONLY = true
// MODEL P REMOVED (2026-10-14, user "Remove model P and it's highlights"). One flag, the same
// shape as MC_ONLY: it nulls `pModel`, which every Model P surface reads from -- the card chip,
// the 👑 DOG FLIP crown drawn inside it, the Ⓟ CLOSE chip and the hlP highlight gate -- plus the
// tab, the panel and the TODAY strip, which are guarded separately below.
//
// The BACKEND is untouched: tennis_model_p.py and the p_dog / p_dog_flip / p_close* lanes keep
// scoring silently, so the forward record survives. Worth keeping given the 👑 crown's backtest
// claimed women +32.6% while the frozen log reads -37.65% on 17 -- the lanes are the only thing
// that catches that. Flip this to true to bring the whole display back.
const SHOW_MODEL_P = false""")

# ---- kill pModel, which starves the chip, the crown, the CLOSE chip and hlP ----
rep("""  const pModel = (() => {
    const mp = match.model_p""",
    """  const pModel = (() => {
    if (!SHOW_MODEL_P) return null        // removes the chip, the crown, Ⓟ CLOSE and hlP at once
    const mp = match.model_p""")

# ---- the tab button ----
rep("""['modelx', 'Model X'], ['modelp', 'Ⓟ Model P'], ['uedog', '🧤 Low-error dogs']""",
    """['modelx', 'Model X'], ...(SHOW_MODEL_P ? [['modelp', 'Ⓟ Model P']] : []), ['uedog', '🧤 Low-error dogs']""")

# ---- the panel dispatch ----
rep("""view === 'modelp' ? <ModelPPanel matches={matches} /> :""",
    """view === 'modelp' && SHOW_MODEL_P ? <ModelPPanel matches={matches} /> :""")

# ---- the TODAY strip ----
rep("""function ModelPStrip({ matches }) {""",
    """function ModelPStrip({ matches }) {
  if (!SHOW_MODEL_P) return null""")

# ---- the second model_p block further down the card ----
rep("""      {(() => {
        const mp = match.model_p
        const lo = match.live_odds || {}
        const mk = match.model_c && match.model_c.market_p1 != null ? match.model_c.market_p1 : null""",
    """      {(() => {
        if (!SHOW_MODEL_P) return null
        const mp = match.model_p
        const lo = match.live_odds || {}
        const mk = match.model_c && match.model_c.market_p1 != null ? match.model_c.market_p1 : null""")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched TennisSection.jsx")
print("   SHOW_MODEL_P guards: %d" % s.count("SHOW_MODEL_P"))
print("RESULT: OK")
