"""MC6's VERDICT ON THE DOG TAB's GOLD MARKS (2026-10-16).

User: "make sure to show it on the dogs tab".

Same chip as the board's, on the same rule, reading the mc6_ev now carried on every lane pick.
Green when MC6 agrees the bet is positive at the offered price, orange when it does not.

Shown ONLY on gold favourite rows, matching the board. Dog cells carry the number too -- it is on
every pick record -- but the question that prompted this is specifically about favourites: the
gold mark reads MC2 alone, MC2 is the only head with no form term, and on Grant vs Ito it fired a
mark that MC3, MC5 and MC6 all declined. Putting an EV badge on every dog row as well would bury
that signal in noise rather than sharpen it.

NOT A GATE, exactly as on the board. Nothing is hidden, no cell changes, no record changes. The
tab still ranks and gates on MC2's lanes.
"""
import io
import os

F = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "DogPicksPanel.jsx"))
s = io.open(F, encoding="utf-8").read()
assert "mc6_ev" not in s, "already patched"

# the gold favourite badge on a today-row is rendered from `fb`; append the MC6 chip after it
OLD = """                    {fb ? (
                      <span title={fb.note + '  ' + ((cells.find(c => c.key === 'mc2_fav4_w') || {}).note || '')}
                        style={{ fontSize: 10, fontWeight: 800, color: fb.col,
                          border: '1px solid ' + fb.col + '99', borderRadius: 6, padding: '0 5px' }}>
                        {'⭐ ' + fb.tag}
                      </span>
                    ) : null}"""
assert s.count(OLD) == 1, "gold badge not found (%d)" % s.count(OLD)

NEW = OLD + """
                    {/* MC6'S VERDICT ON THE SAME BET (2026-10-16, user "make sure to show it on
                        the dogs tab"). Same chip as the board's. The gold mark reads MC2 alone and
                        MC2 is the only head without a form term, so where the newest head
                        disagrees the reader sees it. Favourites only, matching the board: every
                        pick carries mc6_ev, but badging every dog row too would bury the signal.
                        NOT A GATE -- nothing is hidden and no cell or record changes. */}
                    {fb && s.p.mc6_ev != null ? (
                      <span style={{
                        fontSize: 9.5, fontWeight: 800, padding: '0 5px', borderRadius: 5,
                        color: s.p.mc6_ev >= 0 ? '#3fb950' : '#f0883e',
                        border: `1px solid ${s.p.mc6_ev >= 0 ? 'rgba(63,185,80,0.55)' : 'rgba(240,136,62,0.65)'}`,
                        background: s.p.mc6_ev >= 0 ? 'rgba(63,185,80,0.10)' : 'rgba(240,136,62,0.12)',
                      }}
                        title={`MC6 ON THIS SAME BET: ${s.p.mc6_ev >= 0 ? '+' : ''}${Math.round(1000 * s.p.mc6_ev) / 10}% EV at the OFFERED price.\\n\\n`
                          + `${s.p.mc6_ev >= 0
                              ? 'MC6 AGREES this is a positive-EV bet at the price offered.'
                              : 'MC6 DISAGREES: at its number this bet LOSES money at the price offered. The gold mark reads MC2 alone, and MC2 is the only head here with no form term -- it sees a favourite on a losing run only through slow-moving Elo.'}\\n\\n`
                          + `THIS IS NOT A GATE. Nothing is hidden and the mark has not changed. A veto would fire on 12% of gold marks and the vetoed half measures -18.84% on SIX bets against +13.08% on 46 for the rest -- the right direction, far too few to act on.\\n\\n`
                          + `Context: MC6 is the most accurate head in the project (AUC .7071 vs MC2's .6889 on 786 matched rows, market .7096), and on favourites the cards MC6 flags while MC2 rejects are the only positive favourite cell in that comparison (+0.26% on 12) against -16.73% on 13 where both agree.`}>
                        {`MC6 ${s.p.mc6_ev >= 0 ? '\\u2713' : '\\u2717'} ${s.p.mc6_ev >= 0 ? '+' : ''}${Math.round(1000 * s.p.mc6_ev) / 10}%`}
                      </span>
                    ) : null}"""
s = s.replace(OLD, NEW)
io.open(F, "w", encoding="utf-8", newline="").write(s)
print("patched DogPicksPanel.jsx")
print("   mc6_ev refs: %d" % s.count("mc6_ev"))
print("RESULT: OK")
