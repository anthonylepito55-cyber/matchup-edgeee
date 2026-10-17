"""SHOW MC6's VERDICT NEXT TO A GOLD FAVOURITE MARK (2026-10-16).

User: "show MC6's EV next to a gold mark so you can see the disagreement on the card and decide
yourself, without betting anything on an unproven swap."

WHY. The gold favourite mark reads MC2 and nothing else, and MC2 is the only head with no form
term. On Grant vs Ito, MC2 sat +7.9pt over the de-vigged market at +8.7% EV and fired the mark
while every newer head declined it -- MC3 +3.1pt, MC5 +3.9pt, and MC6 only +1.2pt at MINUS 3.2%
EV. The card presented MC2's confidence as the board's view with nothing to say three better
predictors disagreed.

WHAT THIS IS NOT. It is not a gate. An MC6 veto would fire on 12% of gold marks and the vetoed
half measures -18.84% on SIX bets against +13.08% on 46 for the rest -- the right direction and
nowhere near enough to act on. Nothing is suppressed, no mark changes, no lane changes. The card
simply states what MC6 thinks of the same bet at the same price, and the reader decides.

WHAT IS SHOWN. MC6's EV at the OFFERED price (not the de-vigged one), because that is what a bet
actually returns, and the de-vigged margin is what made MC2 look right here in the first place.
Green when MC6 agrees the bet is positive, orange when it does not, with the point margin beside
it so agreement and disagreement are both legible.

MC6 absent on a card -- an unrated pair -- simply shows nothing rather than implying consent.
"""
import io
import os

F = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "TennisSection.jsx"))
s = io.open(F, encoding="utf-8").read()
assert "mc6ev" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


# ---- 1. carry MC6's read on the SAME bet out of the mark builder ----
rep("""      return { cell: gHL === 'w' ? 'FAV 4pt+ W -100/200' : 'FAV 4pt+ M -100/150',
               // isFav drives the GOLD treatment below: these are the cells the Dog picks tab
               // marks gold (2026-10-15), and the board must not disagree with it on colour.
               isFav: true,""",
    """      // MC6'S VERDICT ON THE SAME BET (2026-10-16, user ask). Carried, not enforced: the
      // gold rule still reads MC2 alone. MC6 is the only head here with a form term, and on
      // Grant vs Ito it was the one that noticed a favourite on four straight losses.
      // EV is taken at the OFFERED price -- the de-vigged margin is exactly what made MC2
      // look right on that card -- so this is what the bet would actually return at MC6's
      // number. Null when MC6 has no read, which must not be mistaken for agreement.
      const _m6h = match.mc6
      const _m6fav = (_m6h && _m6h.p1_prob != null)
        ? (fav1 ? _m6h.p1_prob : 1 - _m6h.p1_prob) : null
      return { cell: gHL === 'w' ? 'FAV 4pt+ W -100/200' : 'FAV 4pt+ M -100/150',
               // isFav drives the GOLD treatment below: these are the cells the Dog picks tab
               // marks gold (2026-10-15), and the board must not disagree with it on colour.
               isFav: true,
               mc6ev: (_m6fav != null && _favDec) ? (_m6fav * _favDec - 1) : null,
               mc6over: _m6fav != null ? (_m6fav - mkfav) : null,""")

# ---- 2. render it on the chip ----
rep("""          <span style={{ fontWeight: 400, opacity: 0.85 }}>{` · ${mc2Mark.live} · watch only`}</span>
        </div>
      ) : null}
      {gMarkShow ? (""",
    """          <span style={{ fontWeight: 400, opacity: 0.85 }}>{` · ${mc2Mark.live} · watch only`}</span>
          {/* MC6'S VERDICT ON THE SAME BET (2026-10-16). Shown, never enforced -- the mark is
              still MC2's. MC6 is the only head with a form term, so where it disagrees the
              reader gets to see it instead of the board presenting MC2's confidence alone. */}
          {mc2Mark.isFav && mc2Mark.mc6ev != null ? (
            <span style={{
              marginLeft: 6, padding: '0 5px', borderRadius: 5, fontSize: 9.5, fontWeight: 800,
              color: mc2Mark.mc6ev >= 0 ? '#3fb950' : '#f0883e',
              border: `1px solid ${mc2Mark.mc6ev >= 0 ? 'rgba(63,185,80,0.55)' : 'rgba(240,136,62,0.65)'}`,
              background: mc2Mark.mc6ev >= 0 ? 'rgba(63,185,80,0.10)' : 'rgba(240,136,62,0.12)',
            }}
              title={`MC6 ON THIS SAME BET: ${mc2Mark.mc6ev >= 0 ? '+' : ''}${Math.round(1000 * mc2Mark.mc6ev) / 10}% EV at the OFFERED price, `
                + `${mc2Mark.mc6over >= 0 ? '+' : ''}${Math.round(1000 * mc2Mark.mc6over) / 10}pt over the de-vigged market `
                + `(MC2 has it ${mc2Mark.amt}pt over).\\n\\n`
                + `${mc2Mark.mc6ev >= 0
                    ? 'MC6 AGREES this is a positive-EV bet. Both the oldest head and the newest are on the same side.'
                    : 'MC6 DISAGREES: at its number this bet LOSES money at the price offered. The gold mark reads MC2 alone, and MC2 is the only head here with no form term -- it sees a favourite on a losing run only through slow-moving Elo.'}\\n\\n`
                + `THIS IS NOT A GATE. Nothing is suppressed and the mark has not changed. A veto would fire on 12% of gold marks, and the vetoed half measures -18.84% on SIX bets against +13.08% on 46 for the rest -- the right direction, far too few to act on. It is shown so you can see the disagreement and decide.\\n\\n`
                + `Measured context: MC6 is the most accurate head in the project (AUC .7071 against MC2's .6889 on 786 matched rows, market .7096) and on favourites the cards MC6 flags and MC2 rejects are the only positive favourite cell in that table (+0.26% on 12), while the cards both agree on are -16.73% on 13.`}>
              {`MC6 ${mc2Mark.mc6ev >= 0 ? '\\u2713' : '\\u2717'} ${mc2Mark.mc6ev >= 0 ? '+' : ''}${Math.round(1000 * mc2Mark.mc6ev) / 10}% EV`}
            </span>
          ) : null}
        </div>
      ) : null}
      {gMarkShow ? (""")

io.open(F, "w", encoding="utf-8", newline="").write(s)
print("patched TennisSection.jsx")
for k in ("mc6ev", "mc6over", "MC6 ON THIS SAME BET"):
    print("   %-22s %d" % (k, s.count(k)))
print("RESULT: OK")
