"""REMOVE THE NAMED TABS (2026-10-14).

User: "Remove, best tab, prices, p/l, sets, star picks, dog and star splits, low error dogs, and
model x tab, leave dog picks tab, board, $25 tab, and results history".

REMOVED (8):  best · prices · tabpl (Tab P/L) · sets · picks (Star picks) · splits (Dog/Star
              splits) · uedog (Low-error dogs) · modelx

KEPT and named by the user (4):  board · dogpicks · ab25 ($25 tab) · history

NOT NAMED EITHER WAY (2): itf and tested. The remove list does not contain them and the keep list
does not either, so they are LEFT IN PLACE rather than guessed at -- removing a tab nobody asked
about is the worse error. Flagged to the user instead.

Done with a HIDDEN_TABS set rather than by deleting the panels: the components, their data and
their routes are untouched, so any of these comes back by removing one string. The dispatch is
guarded too, so a stale ?view= or a remembered state cannot land on a hidden panel -- it falls
through to the board.
"""
import io
import os

P = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "TennisSection.jsx"))
s = io.open(P, encoding="utf-8").read()
assert "HIDDEN_TABS" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:80])
    s = s.replace(old, new)


# ---- the set, at module scope ----
rep("const ITF_MEN_ON_BOARD = false",
    """const ITF_MEN_ON_BOARD = false

// TABS HIDDEN (2026-10-14, user: "Remove, best tab, prices, p/l, sets, star picks, dog and star
// splits, low error dogs, and model x tab, leave dog picks tab, board, $25 tab, and results
// history"). Hidden, not deleted -- the panels, their data and their routes are untouched, so any
// of these returns by removing one string from this set.
//
// 'itf' and 'tested' are in NEITHER the remove list nor the keep list, so they stay. Note ITF is
// now merged into the board for MC2-marked dogs, which makes its own tab largely redundant.
const HIDDEN_TABS = new Set(['best', 'prices', 'tabpl', 'sets', 'picks', 'splits', 'uedog', 'modelx'])""")

# ---- the tab row ----
rep("""].map(([k, label]) => (""",
    """].filter(([k]) => !HIDDEN_TABS.has(k)).map(([k, label]) => (""")

# ---- normalise the view itself, so a stale/remembered hidden tab lands on the BOARD ----
# Guarding the dispatch instead would render an empty page: the board is the final else branch
# of that chain, so returning null for a hidden view shows nothing at all.
rep("""  const [view, setView] = useState('board')""",
    """  const [viewRaw, setView] = useState('board')
  // a hidden tab (or a stale remembered one) falls back to the board rather than an empty page
  const view = HIDDEN_TABS.has(viewRaw) ? 'board' : viewRaw""")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched TennisSection.jsx")
print("   HIDDEN_TABS refs: %d" % s.count("HIDDEN_TABS"))
print("RESULT: OK")
