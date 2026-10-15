"""MC6 ON THE PREVIOUS-DAY TABS (2026-10-15).

User: "can u make mc6 show up on previous day tabs".

Three places, the same three MC2/MC3/MC5 already occupy:
  1. the history row builder in tennis_log.py -- a "mc6" object with side / pct / hit / recon
  2. the per-game chip strip on each past match
  3. the per-day model tally, so MC6 earns a day record beside the others

Shape is copied from mc5 deliberately, including the recon contract: a leading "~" marks a
walk-forward backfill rather than a frozen pre-match read, and those rows stay out of the forward
lanes. MC6 has no backfill yet, so every chip it shows today is a genuine frozen read -- which is
worth knowing when reading its record against MC3's and MC5's, whose history is largely
reconstructed.

HONEST LIMIT, stated here rather than discovered later: mc6_p1 only started being written on
2026-10-15, so past days will show MC2/MC3/MC5 chips and NO MC6 chip. That is correct rather than
broken -- MC6 did not exist then and nothing should imply it did. Filling the earlier days needs
an as-of backfill (rebuild the H2H and surface-form state with a date cutoff per day, as the MC3
as-of fill did on 2026-10-13), which is a separate job and must stamp mc6_recon=True.
"""
import io
import os

DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- 1. the row builder
P = os.path.join(DIR, "tennis_log.py")
s = io.open(P, encoding="utf-8").read()
assert '"mc6": (lambda' not in s, "tennis_log already patched"
OLD = ('            "mc5": (lambda p: ({**p, "recon": bool(r.get("mc5_recon"))\n'
       '                                 if pd.notna(r.get("mc5_recon")) else False} if p else None))'
       '(pickpct(r, "mc5_p1")),')
assert s.count(OLD) == 1, "mc5 history builder not found (%d)" % s.count(OLD)
NEW = OLD + (
    '\n            # MC v6 (2026-10-15, user "can u make mc6 show up on previous day tabs").\n'
    '            # Same shape and same recon contract as the others. Note it only starts on\n'
    '            # 2026-10-15 -- earlier days have no mc6_p1 and correctly show no chip, since\n'
    '            # MC6 did not exist then. Backfilling needs an as-of state rebuild per day.\n'
    '            "mc6": (lambda p: ({**p, "recon": bool(r.get("mc6_recon"))\n'
    '                                 if pd.notna(r.get("mc6_recon")) else False} if p else None))'
    '(pickpct(r, "mc6_p1")),')
s = s.replace(OLD, NEW)
io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched tennis_log.py")

# ---------------------------------------------------------------- 2 + 3. the UI
F = os.path.normpath(os.path.join(DIR, "..", "frontend", "src", "TennisSection.jsx"))
t = io.open(F, encoding="utf-8").read()
assert "m.mc6" not in t, "TennisSection already patched"

CHIP_OLD = ("                    {m.mc5.recon ? '~' : ''}\U0001F9EE⁵"
            "{m.mc5.side === 1 ? '◀' : '▶'}{m.mc5.hit ? '✓' : '✗'}</span> : null}")
assert t.count(CHIP_OLD) == 1, "mc5 history chip not found (%d)" % t.count(CHIP_OLD)
CHIP_NEW = CHIP_OLD + (
    "\n                  {/* MC6 (2026-10-15). Orange against MC5's lilac. MC6 = MC5 + a\n"
    "                      recency-weighted H2H and a surface-form residual, so it sits next to\n"
    "                      MC5 and the pair reads as base-then-terms. Only present from\n"
    "                      2026-10-15 on -- earlier games show no chip because MC6 did not\n"
    "                      exist, not because anything failed. */}\n"
    "                  {m.mc6 ? <span className=\"mono\" title={`\U0001F9EE⁶ MC v6"
    "${m.mc6.recon ? ' — ~ walk-forward BACKFILL, display-only' : ' (genuine frozen pre-match read)'}"
    ": ${m.mc6.p1_pct}% p1 — ${m.mc6.hit ? 'correct' : 'wrong'}. MC5 plus a recency-weighted "
    "head-to-head (365-day half-life) and a surface-form residual. Measured held-out: +0.0043/+0.0045 "
    "AUC over MC2, and the gain is the surface-form half — H2H alone is worth +0.0007 to +0.0011 "
    "and is NEGATIVE if turned up. Watch only.`}\n"
    "                    style={{ fontSize: 9, padding: '0 5px', borderRadius: 7, marginLeft: 3, "
    "border: `1px solid ${m.mc6.hit ? '#fab7a755' : '#f8514955'}`, color: m.mc6.hit ? '#fab7a7' : '#f85149', "
    "background: m.mc6.hit ? 'rgba(250,183,167,0.06)' : '#f851490d', opacity: m.mc6.recon ? 0.6 : 1 }}>\n"
    "                    {m.mc6.recon ? '~' : ''}\U0001F9EE⁶"
    "{m.mc6.side === 1 ? '◀' : '▶'}{m.mc6.hit ? '✓' : '✗'}</span> : null}")
t = t.replace(CHIP_OLD, CHIP_NEW)

TALLY_OLD = "bump('MC2', m.mc2); bump('MC3', m.mc3); bump('MC5', m.mc5)"
assert t.count(TALLY_OLD) == 1, "tally line not found"
t = t.replace(TALLY_OLD, TALLY_OLD + "; bump('MC6', m.mc6)")

io.open(F, "w", encoding="utf-8", newline="").write(t)
print("patched TennisSection.jsx")
print("   m.mc6 refs: %d   tally: %s" % (t.count("m.mc6"), "bump('MC6'" in t))
import py_compile
py_compile.compile(P, doraise=True)
print("compiles: OK")
print("RESULT: OK")
