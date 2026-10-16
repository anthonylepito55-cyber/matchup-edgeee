"""THE H2H LINE SAYS WHEN THE LAST MEETING DIDN'T FINISH (2026-10-16).

User: "yes wire it", after the model-side cleaning measured as a flat zero.

To be clear about what this is and is not. Excluding unfinished matches from MC6's terms was
MEASURED and REFUTED -- margin-clean moved held-out AUC by -0.00000 / -0.00002 and no variant
beat the shipped version on both years. The arithmetic says why: unfinished rows are 3.9% of the
feature table, the margin component is 35% of the H2H term, and that term carries weight 0.25, so
the fix reaches about 0.34% of the blend. Nothing changes in any model here.

What DOES change is what the card tells the reader. The H2H line prints the last meeting's score:

    Virtanen won 6-7(3) 6-3 6-0

and on roughly 4% of lines that score belongs to a match somebody retired from. "won 6-4 3-0"
reads as a straight-sets beating when the opponent actually walked off in the second. The whole
reason that line exists is that a bare record misleads about what happened -- a silent retirement
is the same failure one level down.

So the last meeting now carries a `status` from tennis_score.classify, and the card appends
"(ret.)" or "(w/o)". Display only; no model, lane or mark reads it.
"""
import io
import os

DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- backend
P = os.path.join(DIR, "tennis_model_a.py")
s = io.open(P, encoding="utf-8").read()
assert '"status"' not in s, "tennis_model_a already patched"


def rep(src, old, new, c=1):
    assert src.count(old) == c, "found %d of %r" % (src.count(old), old[:90])
    return src.replace(old, new)


s = rep(s, "import re\n", "import re\n\nimport tennis_score as _tscore\n", 1)

s = rep(s, """                # the score is written from THIS player's side, which is neither necessarily the
                # winner nor the card's p1 -- recorded so it can be oriented, not guessed at
                "score_for": a,""",
        """                # the score is written from THIS player's side, which is neither necessarily the
                # winner nor the card's p1 -- recorded so it can be oriented, not guessed at
                "score_for": a,
                # DID IT FINISH? (2026-10-16). TennisRatio strips retirement markers and keeps
                # the row, so this is read off the score SHAPE -- see tennis_score. Display only:
                # excluding these from MC6's terms was measured and moved AUC by zero.
                "status": _tscore.classify(_lastrow.get("score")),""")

s = rep(s, """    return {"date": lw["date"],
            "winner": "p1" if w == s1 else ("p2" if w == s2 else None),
            "score": sc, "surface": lw.get("surface"),
            "tournament": lw.get("tournament")}""",
        """    st = lw.get("status")
    return {"date": lw["date"],
            "winner": "p1" if w == s1 else ("p2" if w == s2 else None),
            "score": sc, "surface": lw.get("surface"),
            "tournament": lw.get("tournament"),
            "status": st,
            # a short tag the card can print as-is, so the UI does not re-implement the rule
            "tag": ("w/o" if st == _tscore.WALKOVER
                    else ("ret." if st in (_tscore.RETIRED_MIDSET, _tscore.RETIRED_AFTER_SET)
                          else None))}""")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched tennis_model_a.py")

# ---------------------------------------------------------------- frontend
F = os.path.normpath(os.path.join(DIR, "..", "frontend", "src", "TennisSection.jsx"))
t = io.open(F, encoding="utf-8").read()
assert "L.tag" not in t, "TennisSection already patched"

OLD = "                {winner ? ` \\u2014 ${winner} won${L.score ? ` ${L.score}` : ''}` : ''}"
assert t.count(OLD) == 1, "winner span not found (%d)" % t.count(OLD)
NEW = ("                {winner ? ` \\u2014 ${winner} won${L.score ? ` ${L.score}` : ''}` : ''}\n"
       "                {/* DID IT FINISH (2026-10-16). About 4% of these scores belong to a\n"
       "                    match someone retired from; \"won 6-4 3-0\" otherwise reads as a\n"
       "                    straight-sets beating. Display only -- excluding these rows from\n"
       "                    MC6's terms was measured and moved held-out AUC by zero. */}\n"
       "                {L.tag ? <span style={{ color: '#f0883e', fontWeight: 700 }}>{` (${L.tag})`}</span> : null}")
t = t.replace(OLD, NEW)

# and say so in the tooltip, where the record is explained
TIP_OLD = "The score is written winner-first.` : ''}`"
assert t.count(TIP_OLD) == 1, "tooltip anchor not found"
TIP_NEW = ("The score is written winner-first."
           "${L.tag === 'ret.' ? ' THAT MATCH DID NOT FINISH -- somebody retired, so the score is where it stopped rather than how it ended. The source strips retirement markers and keeps the row, so this is detected from the score shape: a final set that cannot be a completed set, or a lone set in a best-of-three.'"
           " : L.tag === 'w/o' ? ' THAT WAS A WALKOVER -- no tennis was played at all.' : ''}` : ''}`")
t = t.replace(TIP_OLD, TIP_NEW)

io.open(F, "w", encoding="utf-8", newline="").write(t)
print("patched TennisSection.jsx")
print("   L.tag refs: %d" % t.count("L.tag"))
import py_compile
py_compile.compile(P, doraise=True)
py_compile.compile(os.path.join(DIR, "tennis_score.py"), doraise=True)
print("compiles: OK")
print("RESULT: OK")
