"""THE DOG TAB AND THE BOARD'S MARKS SWITCH FROM MC2 TO MC6 (2026-10-16).

User, after the fair comparison: "I feel like we should go with mc6 for the dog tab instead of
mc2."

WHAT SETTLED IT. The objection I had been holding was that MC6's lead lived in its backfill,
where it replayed matches with correct as-of ratings while MC2's value was whatever it really
produced on states up to four days stale. That was testable rather than arguable, so
_mc2_asof_for_mc6rows.py re-priced MC2 as-of on exactly those 633 rows and _mc6_vs_mc2_fair.py
scored both heads with identical input quality:

                      MC2 as-of (fair)      MC6 as-of
    dogs 4pt          +9.39%  / 253         +22.06% / 243   t 2.58
    dogs 6pt          +11.99% / 211         +26.57% / 203   t 2.80
    favs 4pt          -2.20%  / 66          +15.04% / 78    t 1.68
    TAB RULE          +8.61%  / 277         +23.37% / 281   t 3.35

The lead GREW once the confound was removed, and my hypothesis was backwards: correct ratings
made MC2 worse (+14.89% stale -> +8.61% fair), so staleness had been flattering MC2 rather than
MC6. The reprice moved 49% of MC2's values by more than 2pt, so it was a real test.

WHAT CHANGES: the four lane keys the tab's cells, pink rules, gold favourite marks and board
gates read. MC2 -> MC6. Thresholds, bands, gender splits, price caps and league gates are all
untouched -- the head changes, the rule does not.

WHAT DOES NOT CHANGE, and the user should see it on screen: the MC6 lanes REFUSE recon rows, as
every money lane here does, so their displayed records start at n=71/57/9/5 against MC2's
459/396/36/34. The picks become MC6-driven immediately; the ROI printed beside them is
small-sample for about two weeks. That is the honest cost of the switch and it is not papered
over -- MIN_CELL_N stays at 25, so thin cells read as thin.

MC2's lanes keep scoring underneath, so the comparison continues and this is reversible by
inverting these same four substitutions.
"""
import io
import os

DIR = os.path.dirname(os.path.abspath(__file__))
SUB = (("mc2_dog4_all", "mc6_dog4_all"), ("mc2_dog6_all", "mc6_dog6_all"),
       ("mc2_fav4_w", "mc6_fav4_w"), ("mc2_fav4_m", "mc6_fav4_m"))

# ------------------------------------------------------------------ the dog tab
F = os.path.normpath(os.path.join(DIR, "..", "frontend", "src", "DogPicksPanel.jsx"))
s = io.open(F, encoding="utf-8").read()
assert "mc6_dog4_all" not in s, "dog tab already switched"
before = {k: s.count(k) for k, _ in SUB}
for old, new in SUB:
    s = s.replace("'%s'" % old, "'%s'" % new)
# the user-facing labels should say which head they are now reading
s = s.replace("'\U0001F7E1 MC2 4pt+ FAV · WOMEN −100..−200'",
              "'\U0001F7E1 MC6 4pt+ FAV · WOMEN −100..−200'")
s = s.replace("'\U0001F7E1 MC2 4pt+ FAV · men (control)'",
              "'\U0001F7E1 MC6 4pt+ FAV · men (control)'")
s = s.replace("'\U0001F7E4 MC2 6pt+ DOG'", "'\U0001F7E4 MC6 6pt+ DOG'")
s = s.replace("'\U0001F7E4 MC2 4pt+ DOG'", "'\U0001F7E4 MC6 4pt+ DOG'")
s = s.replace("tag: 'MC2 4pt+ M'", "tag: 'MC6 4pt+ M'")
s = s.replace("tag: 'MC2 4pt+ W'", "tag: 'MC6 4pt+ W'")
s = s.replace("tag: 'MC2 6pt+ M'", "tag: 'MC6 6pt+ M'")

BANNER = """// ===========================================================================================
// THIS TAB READS MC6, NOT MC2 (2026-10-16, user call).
//
// The rule is unchanged -- same 4pt/6pt thresholds, same gender x band splits, same +300 cap and
// ITF-men exclusion. Only the HEAD changed, after both were scored with identical input quality
// on 633 identical rows (_mc6_vs_mc2_fair.py):
//
//                   MC2 as-of (fair)    MC6 as-of
//     dogs 6pt      +11.99% / 211       +26.57% / 203   t 2.80
//     TAB RULE      +8.61%  / 277       +23.37% / 281   t 3.35
//
// That comparison exists because MC6's raw advantage was confounded: on its backfilled rows it
// replayed with correct as-of ratings while MC2's value came from states up to four days stale.
// Re-pricing MC2 as-of removed the confound and the lead GREW -- correct ratings made MC2 worse,
// so staleness had been flattering MC2, not MC6.
//
// READ THE SAMPLES. MC6's lanes refuse recon rows, as every money lane here does, so they START
// NEAR EMPTY: n=71/57/9/5 against MC2's 459/396/36/34. The picks are MC6-driven from today; the
// ROI beside them needs about two weeks. MIN_CELL_N stays at 25, so thin cells read as thin
// rather than being promoted early.
//
// MC2's lanes keep scoring underneath. Reverting is these four substitutions inverted.
// ===========================================================================================
"""
s = BANNER + s
io.open(F, "w", encoding="utf-8", newline="").write(s)
print("patched DogPicksPanel.jsx")
for old, new in SUB:
    print("   %-14s -> %-14s  (%d refs)" % (old, new, before[old]))

# ------------------------------------------------------------------ the board's gold fav lane
T = os.path.normpath(os.path.join(DIR, "..", "frontend", "src", "TennisSection.jsx"))
t = io.open(T, encoding="utf-8").read()
OLD = "    const _favLane = gHL === 'w' ? 'mc2_fav4_w' : 'mc2_fav4_m'"
assert t.count(OLD) == 1, "board fav lane not found"
t = t.replace(OLD, "    // reads MC6 from 2026-10-16, matching the Dog tab -- same rule, different head\n"
                   "    const _favLane = gHL === 'w' ? 'mc6_fav4_w' : 'mc6_fav4_m'")
io.open(T, "w", encoding="utf-8", newline="").write(t)
print("patched TennisSection.jsx (board gold-fav lane)")
print("RESULT: OK")
