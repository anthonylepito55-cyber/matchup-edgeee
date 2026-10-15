"""THE LAST-MEETING SCORE MUST BE ORIENTED TO THE WINNER (2026-10-15, follow-up).

Caught in the smoke test before it reached a card. The H2H index stores each meeting from the
LEXICOGRAPHICALLY-FIRST player's side, which has nothing to do with who won or with which player
the card calls p1:

    Zverev vs De Minaur -> winner p1 (Zverev), score "4-6 6-7(5) 4-6"

That score is De Minaur's games first, so printed next to "Zverev won" it reads as though Zverev
lost every set. A card that says "X won 4-6 6-7 4-6" is simply wrong, and wrong in a way a reader
would believe.

So the stored row now records WHOSE side the score is written from, and the score is flipped to be
winner-first when those differ. Flipping a set is "x-y" -> "y-x"; the tiebreak parenthetical is
left alone, because by convention it already holds the LOSER's points in that tiebreak, so
"6-7(5)" correctly becomes "7-6(5)".
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tennis_model_a.py")
s = io.open(P, encoding="utf-8").read()
assert "_flip_score" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


# record whose side the stored score is written from
rep("""                "surface": (str(_lastrow["surface"]) if "surface" in g.columns else None),
                "tournament": (str(_lastrow["tournament"]) if "tournament" in g.columns else None),""",
    """                "surface": (str(_lastrow["surface"]) if "surface" in g.columns else None),
                "tournament": (str(_lastrow["tournament"]) if "tournament" in g.columns else None),
                # the score is written from THIS player's side, which is neither necessarily the
                # winner nor the card's p1 -- recorded so it can be oriented, not guessed at
                "score_for": a,""")

# the flipper + winner-first orientation
rep('''def _h2h_last(h, s1, s2):
    """The pair's most recent meeting, oriented to p1/p2 so the UI never sees a slug.
    `winner` is "p1" or "p2"; None when the index has no date for this pair."""
    lw = (h or {}).get("last")
    if not lw or not lw.get("date"):
        return None
    w = lw.get("winner")
    return {"date": lw["date"],
            "winner": "p1" if w == s1 else ("p2" if w == s2 else None),
            "score": lw.get("score"), "surface": lw.get("surface"),
            "tournament": lw.get("tournament")}''',
    '''def _flip_score(sc):
    """"4-6 6-7(5) 4-6" -> "6-4 7-6(5) 6-4". The tiebreak parenthetical is left in place: by
    convention it holds the LOSER's points in that tiebreak, so it stays attached to the set."""
    if not sc:
        return sc
    out = []
    for tok in str(sc).split():
        m = re.match(r"^(\\d+)-(\\d+)(\\(.*\\))?$", tok)
        out.append("%s-%s%s" % (m.group(2), m.group(1), m.group(3) or "") if m else tok)
    return " ".join(out)


def _h2h_last(h, s1, s2):
    """The pair's most recent meeting, oriented to p1/p2 so the UI never sees a slug.

    `winner` is "p1" or "p2". `score` is rewritten WINNER-FIRST: the index stores it from the
    lexicographically-first player's side, which is neither necessarily the winner nor the card's
    p1, and printing it unoriented next to a winner's name states the opposite of what happened.
    """
    lw = (h or {}).get("last")
    if not lw or not lw.get("date"):
        return None
    w = lw.get("winner")
    sc = lw.get("score")
    if sc and lw.get("score_for") and lw["score_for"] != w:
        sc = _flip_score(sc)
    return {"date": lw["date"],
            "winner": "p1" if w == s1 else ("p2" if w == s2 else None),
            "score": sc, "surface": lw.get("surface"),
            "tournament": lw.get("tournament")}''')

if "\nimport re" not in s and "\nimport re\n" not in s:
    s = s.replace("import numpy as np", "import re\n\nimport numpy as np", 1)

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched tennis_model_a.py")
print("   _flip_score refs: %d   score_for refs: %d" % (s.count("_flip_score"), s.count("score_for")))
import py_compile
py_compile.compile(P, doraise=True)
print("compiles: OK")
print("RESULT: OK")
