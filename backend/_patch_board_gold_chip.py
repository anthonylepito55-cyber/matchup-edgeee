"""THE MARK CHIP GOES GOLD TOO, NOT JUST THE CARD (2026-10-15, follow-up).

Painting only the card frame gold would leave the chip on it reading brown, so a gold card would
still announce itself in brown text with a brown rule. Same cells, same mark -- one colour.

The chip is shared by the dog and favourite cells, so the colours become conditional on
mc2Mark.isFav rather than replaced: dog marks keep brown exactly as they were.
"""
import io
import os

F = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "TennisSection.jsx"))
s = io.open(F, encoding="utf-8").read()
assert "GOLD chip for the favourite cells" not in s, "already patched"

OLD = """            padding: '3px 6px', borderRadius: 4, color: '#e3b98f',
            background: 'linear-gradient(90deg, rgba(140,86,45,0.30), transparent)',
            border: '1px solid rgba(176,110,60,0.70)',"""
assert s.count(OLD) == 1, "chip style block not found (%d)" % s.count(OLD)
NEW = """            // GOLD chip for the favourite cells (2026-10-15): the card frame goes gold for
            // mc2Mark.isFav, so the chip on it must not stay brown. Dog marks keep brown.
            padding: '3px 6px', borderRadius: 4,
            color: mc2Mark.isFav ? '#ffe9a3' : '#e3b98f',
            background: mc2Mark.isFav
              ? 'linear-gradient(90deg, rgba(255,215,0,0.26), transparent)'
              : 'linear-gradient(90deg, rgba(140,86,45,0.30), transparent)',
            border: `1px solid ${mc2Mark.isFav ? 'rgba(255,215,0,0.75)' : 'rgba(176,110,60,0.70)'}`,"""
s = s.replace(OLD, NEW)

OLD2 = """          <span style={{ fontSize: 11, fontWeight: 900, color: '#f0cba4' }}>"""
assert s.count(OLD2) == 1, "chip name span not found (%d)" % s.count(OLD2)
s = s.replace(OLD2, """          <span style={{ fontSize: 11, fontWeight: 900,
            color: mc2Mark.isFav ? '#ffd700' : '#f0cba4' }}>""")

# the chip's leading glyph: brown square for dogs, gold medal for the favourite cells
OLD3 = """          title={`🟤 MC2 ${mc2Mark.cell} — where MC v2 is saying something, NOT a recommendation."""
assert s.count(OLD3) == 1, "chip title not found"
s = s.replace(OLD3, """          title={`${mc2Mark.isFav ? '🥇' : '🟤'} MC2 ${mc2Mark.cell} — where MC v2 is saying something, NOT a recommendation.""")

io.open(F, "w", encoding="utf-8", newline="").write(s)
print("patched TennisSection.jsx")
print("   mc2Mark.isFav refs: %d" % s.count("mc2Mark.isFav"))
print("RESULT: OK")
