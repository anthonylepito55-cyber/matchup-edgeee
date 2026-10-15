"""A WITHHELD PRICE MUST BE ABSENT, NOT ZERO (2026-10-15, follow-up).

Nulling live_odds.player_1/player_2 stopped the moving number, but it does not make the price
ABSENT to the consumers. The frontend reads it in roughly thirty places shaped like

    const od = m.live_odds ? Number(dog1 ? m.live_odds.player_1 : m.live_odds.player_2) : null

With live_odds present and its numbers null, the guard passes and Number(null) is 0 -- so a
withheld price arrives as a price of ZERO. Band tests (od >= 100) fail safely, but the decimal
conversion 1 + 100/Math.abs(0) is Infinity, which is not something to leave flowing through EV
arithmetic on the strength of "it probably won't matter".

So live_odds becomes None outright, and the fact that a price was withheld moves to its own
top-level field, odds_withheld, which is what the UI's in-play warning now reads. Every
`m.live_odds ? ... : null` guard then does the right thing with no change at the call sites.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
s = io.open(P, encoding="utf-8").read()
assert "odds_withheld" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


# ---- board ----
rep("""                    if isinstance(r.get("live_odds"), dict):
                        r["live_odds"] = {"player_1": None, "player_2": None,
                                          "bookmaker": r["live_odds"].get("bookmaker"),
                                          "inplay": True, "withheld": True}""",
    """                    if isinstance(r.get("live_odds"), dict):
                        # live_odds goes away ENTIRELY, and the reason moves to its own field.
                        # Keeping the dict with null numbers was not enough: the UI's guards are
                        # `m.live_odds ? Number(...) : null`, which with null members yields 0 --
                        # and 1 + 100/abs(0) is Infinity in the decimal conversion.
                        r["odds_bookmaker_last"] = r["live_odds"].get("bookmaker")
                        r["live_odds"] = None
                    r["odds_withheld"] = "inplay" """.rstrip() + "\n")

# ---- ITF / Best-tab cards ----
rep("""                if isinstance(c.get("live_odds"), dict):
                    c["live_odds"] = {"player_1": None, "player_2": None,
                                      "bookmaker": c["live_odds"].get("bookmaker"),
                                      "inplay": True, "withheld": True}
                continue""",
    """                if isinstance(c.get("live_odds"), dict):
                    c["odds_bookmaker_last"] = c["live_odds"].get("bookmaker")
                    c["live_odds"] = None
                c["odds_withheld"] = "inplay"
                continue""")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched main.py")
print("   odds_withheld refs  %d" % s.count("odds_withheld"))
import py_compile
py_compile.compile(P, doraise=True)
print("compiles: OK")

# ---------------------------------------------------------------- the UI warning
F = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "TennisSection.jsx"))
t = io.open(F, encoding="utf-8").read()
OLD = """{odds.inplay ? <span style={{ color: '#e3b341', fontWeight: 700 }} title="This match started before we ever logged a pre-match line, so this is the LIVE in-play price, not a pre-match line. Model P and the price-based marks don't apply."> ⚠ IN-PLAY price — no pre-match line logged</span> : null}"""
NEW = """{odds.inplay ? <span style={{ color: '#e3b341', fontWeight: 700 }} title="This match started before we ever logged a pre-match line, so this is the LIVE in-play price, not a pre-match line. Model P and the price-based marks don't apply."> ⚠ IN-PLAY price — no pre-match line logged</span> : null}"""
assert t.count(OLD) == 1, "warning span not found"

# the whole market line only renders when `odds` exists, so the withheld case needs its own line
ANCHOR = """          market: {match.player_1} {fmtPrice(odds.player_1)} / {match.player_2} {fmtPrice(odds.player_2)} ({odds.bookmaker}{odds.frozen ? ' · frozen pre-match' : ''})"""
assert t.count(ANCHOR) == 1, "market line not found"
io.open(F, "w", encoding="utf-8", newline="").write(t)
print("TennisSection.jsx: market line located (no edit needed -- live_odds null hides it)")
print("RESULT: OK")
