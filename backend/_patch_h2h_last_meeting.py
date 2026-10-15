"""THE H2H RECORD GAINS ITS MOST RECENT MEETING (2026-10-15).

User: "u know how the drop down models have a h2h with a record -- can u mark when the most recent
h2h game was and who won it", then "On every game with h2h".

A bare "H2H 2-0" is the one tennis stat where the DATE changes its meaning completely, and this
session produced the case that proves it: Stricker vs Virtanen showed 0-2 to Virtanen, which reads
as a live edge until you see both meetings were 2022 and 2023. MC6 discounts them to 7% of weight
for exactly that reason, but the card's own H2H line said nothing about it, so the number on
screen and the number in the model disagreed with no way to tell.

BACKEND: the H2H index already groups every meeting for a pair, so the latest one is free -- its
date, who won, the score and the surface are recorded alongside the record. Exposed through both
predict() and h2h_for() (the latter feeds the results-history cards), oriented to p1/p2 so the
frontend never has to know about slugs.

FRONTEND is a separate patch: the line must show on EVERY card with an H2H, not only when the
Model A drop-down is open, which is what the user asked for on the follow-up.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tennis_model_a.py")
s = io.open(P, encoding="utf-8").read()
assert '"last"' not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


# ---- 1. record the latest meeting while the index is being built ----
rep("""        for surf, sg2 in g.groupby("surface"):
            e["surf"][surf] = {"n": int(len(sg2)), a: int(sg2["won"].sum()),
                               b: int(len(sg2) - sg2["won"].sum())}""",
    """        for surf, sg2 in g.groupby("surface"):
            e["surf"][surf] = {"n": int(len(sg2)), a: int(sg2["won"].sum()),
                               b: int(len(sg2) - sg2["won"].sum())}
        # THE MOST RECENT MEETING (2026-10-15, user ask). Free here -- every meeting for the
        # pair is already in `g`. A bare "H2H 2-0" is the one record whose meaning depends
        # entirely on its date: Stricker vs Virtanen reads 0-2 and both meetings are from 2022
        # and 2023, which is why MC6 discounts them to 7% of weight. The card should be able to
        # say so instead of showing a number that looks current.
        try:
            _lastrow = g.sort_values("date").iloc[-1]
            e["last"] = {
                "date": str(_lastrow["date"])[:10],
                # `g` is this pair seen from `a`'s side, so won==1 means a won
                "winner": a if bool(_lastrow["won"]) else b,
                "score": (str(_lastrow["score"]) if "score" in g.columns
                          and _lastrow["score"] is not None else None),
                "surface": (str(_lastrow["surface"]) if "surface" in g.columns else None),
                "tournament": (str(_lastrow["tournament"]) if "tournament" in g.columns else None),
            }
        except Exception:  # noqa: BLE001
            e["last"] = None""")


# ---- 2. expose it, oriented to p1/p2 ----
LASTBLK = '''
def _h2h_last(h, s1, s2):
    """The pair's most recent meeting, oriented to p1/p2 so the UI never sees a slug.
    `winner` is "p1" or "p2"; None when the index has no date for this pair."""
    lw = (h or {}).get("last")
    if not lw or not lw.get("date"):
        return None
    w = lw.get("winner")
    return {"date": lw["date"],
            "winner": "p1" if w == s1 else ("p2" if w == s2 else None),
            "score": lw.get("score"), "surface": lw.get("surface"),
            "tournament": lw.get("tournament")}

'''
rep("def h2h_for(name1, name2, surface=None):", LASTBLK.lstrip("\n") + "\ndef h2h_for(name1, name2, surface=None):")

rep("""        out["h2h"] = {"n": h["n"], "p1_wins": h["wins"].get(s1, 0), "p2_wins": h["wins"].get(s2, 0),
                      "surface_n": hs.get("n", 0), "surface_p1_wins": hs.get(s1, 0),
                      "surface": surface}""",
    """        out["h2h"] = {"n": h["n"], "p1_wins": h["wins"].get(s1, 0), "p2_wins": h["wins"].get(s2, 0),
                      "surface_n": hs.get("n", 0), "surface_p1_wins": hs.get(s1, 0),
                      "surface": surface, "last": _h2h_last(h, s1, s2)}""")

rep("""    return {"n": h["n"], "p1_wins": h["wins"].get(s1, 0), "p2_wins": h["wins"].get(s2, 0),
            "surface_n": hs.get("n", 0), "surface_p1_wins": hs.get(s1, 0), "surface": surface}""",
    """    return {"n": h["n"], "p1_wins": h["wins"].get(s1, 0), "p2_wins": h["wins"].get(s2, 0),
            "surface_n": hs.get("n", 0), "surface_p1_wins": hs.get(s1, 0), "surface": surface,
            "last": _h2h_last(h, s1, s2)}""")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched tennis_model_a.py")
for k in ('e["last"]', "_h2h_last", '"last": _h2h_last'):
    print("   %-20s %d" % (k, s.count(k)))
import py_compile
py_compile.compile(P, doraise=True)
print("compiles: OK")
print("RESULT: OK")
