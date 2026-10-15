"""THE SURFACE SPLIT FOLLOWS THE LEADER, LIKE THE HEADLINE DOES (2026-10-15 fix).

The H2H line printed its overall record LEADER-first ("Virtanen 2-0") but the surface split
P1-first, because that is how surface_p1_wins is stored. On any card where the leader is p2 the
two halves then read as contradicting each other:

    H2H: Virtanen 2-0 . hard 0-2        <- same fact, stated from two different sides
    H2H: Kubka 2-0 . hard 0-2

Same class of bug as the winner-first score orientation caught an hour earlier, and the same fix:
decide one subject for the line and state everything from it. The split now follows whoever the
headline names; when the record is level there is no leader, so it stays p1-first.
"""
import io
import os

F = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "TennisSection.jsx"))
s = io.open(F, encoding="utf-8").read()
assert "SAME ORIENTATION AS THE HEADLINE" not in s, "already patched"

OLD = ("            {h.surface_n ? <span style={{ opacity: 0.75 }}>{` \\u00b7 "
       "${String(h.surface || '').toLowerCase()} ${h.surface_p1_wins}-"
       "${h.surface_n - h.surface_p1_wins}`}</span> : null}")
assert s.count(OLD) == 1, "surface-split span not found (%d)" % s.count(OLD)

NEW = (
    "            {/* SAME ORIENTATION AS THE HEADLINE (2026-10-15 fix). The overall record prints\n"
    "                leader-first while surface_p1_wins is p1-first, so an unoriented split read as\n"
    "                a contradiction: \"Virtanen 2-0 \\u00b7 hard 0-2\". It now follows the leader;\n"
    "                a level record has no leader, so that case stays p1-first. */}\n"
    "            {h.surface_n ? (() => {\n"
    "              const sp1 = h.surface_p1_wins, sp2 = h.surface_n - h.surface_p1_wins\n"
    "              const o = (lead != null && lead !== n1) ? [sp2, sp1] : [sp1, sp2]\n"
    "              return <span style={{ opacity: 0.75 }}>"
    "{` \\u00b7 ${String(h.surface || '').toLowerCase()} ${o[0]}-${o[1]}`}</span>\n"
    "            })() : null}")

s = s.replace(OLD, NEW)
io.open(F, "w", encoding="utf-8", newline="").write(s)
print("patched TennisSection.jsx")
print("   orientation fix present: %s" % ("SAME ORIENTATION AS THE HEADLINE" in s))
print("RESULT: OK")
