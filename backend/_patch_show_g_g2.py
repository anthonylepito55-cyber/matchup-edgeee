"""G AND G2 ARE ALWAYS VISIBLE ON A CARD (2026-10-15).

User: "unhide model g and g2 so i can see only them mc2 mc3 and mc 5 on every board pick".

The always-on set on a card becomes exactly MC2 / MC3 / MC5 / G / G2. A, B, C (with its C-MC
block), D, I and X stay behind the "other models" expander, which is what the 2026-10-13 ask set
up -- this moves two lines out of that drawer, it does not reopen the drawer.

What this deliberately does NOT do: G's black ("G FAV-OVER") and yellow ("G DOG-FLIP") board MARKS
stay hidden. Those are board colours, and colours move on a live lane record plus explicit
sign-off, not as a side effect of unhiding a number. Both also backtest -7.2% and G's favourite
side is worse than backing every favourite blindly, so they are watch-only reads. Say the word and
they come back separately.
"""
import io
import os

F = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "TennisSection.jsx"))
s = io.open(F, encoding="utf-8").read()
assert "ALWAYS SHOWN (2026-10-15" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:70])
    s = s.replace(old, new)


# ---- the two model lines become unconditional ----
rep("      {showMods && match.model_g ? (",
    "      {/* G AND G2 ARE ALWAYS SHOWN (2026-10-15, user \"unhide model g and g2 so i can see\n"
    "          only them mc2 mc3 and mc 5 on every board pick\"). The always-on set on a card is now\n"
    "          exactly MC2 / MC3 / MC5 / G / G2; A, B, C, D, I and X stay behind the expander.\n"
    "          This unhides the model LINES only -- G's black/yellow board MARKS stay off, because\n"
    "          board colours move on a live lane record plus sign-off, not as a side effect. */}\n"
    "      {match.model_g ? (")
rep("      {showMods && match.model_g2 ? (",
    "      {match.model_g2 ? (")

# ---- the header toggle's tooltip ----
rep("title={showModels ? 'Showing every model line on each card: A, B, C (with the C-MC block), "
    "D, G, G2, I and X, below MC2/MC3/MC5. Click to collapse them.' : 'Cards show only MC2, MC3 "
    "and MC5. Click to reveal the other eight model lines: A, B, C (with the C-MC block), D, G, "
    "G2, I and X.'}",
    "title={showModels ? 'Showing every model line on each card: A, B, C (with the C-MC block), "
    "D, I and X, below the always-on MC2/MC3/MC5/G/G2. Click to collapse them.' : 'Cards show "
    "MC2, MC3, MC5, G and G2. Click to reveal the other six model lines: A, B, C (with the C-MC "
    "block), D, I and X.'}")

# ---- the per-card expander's tooltip (contains ’ escapes -- matched via a marker) ----
i = s.find("title={cardModels ? 'Hide this card")
assert i > 0, "per-card expander tooltip not found"
j = s.find("}", s.find("always are shown", i) if False else s.find("'}", i)) + 1
old_tip = s[i:j]
assert "other eight model lines" in old_tip, "unexpected tooltip shape: %r" % old_tip[:200]
new_tip = (old_tip
           .replace("(A, B, C, D, G, G2, I, X)", "(A, B, C, D, I, X)")
           .replace("other eight model lines: A, B, C with the C-MC block, D, G, G2, I and X. "
                    "MC2, MC3 and MC5 are always shown.",
                    "other six model lines: A, B, C with the C-MC block, D, I and X. "
                    "MC2, MC3, MC5, G and G2 are always shown."))
assert new_tip != old_tip, "tooltip rewrite was a no-op"
s = s.replace(old_tip, new_tip, 1)

# ---- the comment that documents the split ----
rep("""  // eleven model lines; MC2/MC3/MC5 stay and the other eight -- A, B, C with its C-MC block,
  // D, G, G2, I and X -- render only when this is on.""",
    """  // eleven model lines. MC2/MC3/MC5 stay, and G/G2 joined them on 2026-10-15 at the user's ask
  // ("unhide model g and g2"), so the other six -- A, B, C with its C-MC block, D, I and X --
  // render only when this is on.""")

io.open(F, "w", encoding="utf-8", newline="").write(s)
print("patched TennisSection.jsx")
print("   showMods gates left : %d" % s.count("showMods &&"))
print("   always-on G / G2    : %d / %d"
      % (s.count("{match.model_g ?"), s.count("{match.model_g2 ?")))
print("   tooltip updated     : %s" % ("other six model lines" in s))
print("RESULT: OK")
