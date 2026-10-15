"""MC6 ON THE BOARD CARDS (2026-10-15).

User: "add mc6 to the board cards so i can see".

A line beside MC2 / MC3 / MC5, in the same shape as theirs, showing MC6's probability, its move
against MC2, and the two inputs that caused the move -- because the whole point of MC6 is that it
is MC2 plus exactly two terms, so a card should say which one moved it and by how much.

Shown per card: the H2H term with how many meetings and how much WEIGHTED evidence stands behind
it (w, after the 365-day half-life -- two meetings last month and two from 2019 are not the same
thing and the number has to show that), and the surface-form residual with each player's value.

The line is always on, like MC2/MC3/MC5 -- it is not behind the "other models" expander.
"""
import io
import os

F = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "TennisSection.jsx"))
s = io.open(F, encoding="utf-8").read()
assert "MC6:" not in s, "already patched"

ANCHOR = """             · surface L5+season+clutch · watch only</span>
        </div>
      ) : null}
"""
assert s.count(ANCHOR) == 1, "MC5 block end not found (%d)" % s.count(ANCHOR)

TIP = (
    "`MC v6 (2026-10-15, your ask: \"exactly like mc2 but has recent h2h surface form as well\"). "
    "EXACTLY MC2 PLUS TWO TERMS -- it calls MC2 and re-blends MC2's own legs, so the Elo leg, the "
    "Markov engine, the day-form quadrature and the thin-sample tilt are literally MC2's and "
    "cannot drift. At weight zero MC6 IS MC2 to the last decimal, which makes the difference on "
    "this card exactly the two terms below and nothing else.\\n\\n"
    "(1) RECENT H2H -- recency-weighted head-to-head, 365-day half-life, damped by w/(w+1) so a "
    "single old meeting barely counts while four recent ones count properly. Carries the weighted "
    "win share plus a games-margin component, which is where \"beat them easily\" enters. "
    "Weight 0.25.\\n"
    "(2) SURFACE FORM -- as a RESIDUAL, not a win rate: the exponentially-weighted mean of "
    "(result minus what Elo expected) over that player's matches ON THIS SURFACE, 5-match "
    "half-life, differenced between the two. A plain surface win rate would mostly re-state Elo; "
    "the residual is the part Elo has NOT absorbed. Weight 0.50.\\n\\n"
    "WEIGHTS WERE MEASURED BEFORE THE MODULE WAS WRITTEN (170,714 archive rows, walk-forward, "
    "held-out years) -- the process lesson from MC5, whose weights had to be set afterwards:\\n"
    "    MC2 baseline        AUC .6820 (2025) / .6853 (2026)\\n"
    "    surface form only   +.0034 / +.0024   <- the term that works\\n"
    "    h2h only            +.0011 / +.0007   <- small, positive both years\\n"
    "    shipped .25/.50     +.0043 / +.0045   Brier -.0013 / -.0012\\n"
    "    h2h at weight 1.0   -.0016 / -.0023   <- H2H turned up HURTS\\n\\n"
    "THE WIN IS SURFACE FORM, NOT H2H. H2H had already failed twice the same day before MC6 "
    "existed: the market prices it (+0.75pt over the de-vigged close at z 2.41, and EXACTLY ZERO "
    "on the bettable dog cells), and bolting it onto MC2's full pipeline moved AUC by +0.0001 with "
    "a 95% interval through zero. It ships at 0.25 because at that weight it is positive in both "
    "held-out years and costs nothing -- not because H2H was vindicated. What changed the number "
    "is the surface-form term, which had never been tested before.\\n\\n"
    "Also honest: the weights were chosen on the same held-out years they are reported on, so "
    "+0.0043 is the optimistic end. 0.50 was taken rather than the argmax (1.0 on 2026) to leave "
    "some of that selection on the table; 2024 shows the same shape, so the DIRECTION has three "
    "years of agreement even if the exact value does not.\\n\\n"
    "WATCH ONLY -- no mark, and no lane bets it yet. A better predictor is not a better bet: MC3 "
    "and MC5 both beat MC2 on AUC and neither is bettable, and every MC head measured -8.7% to "
    "-9.7% at every edge gate. The mc6_vs_mc2 lane opened at n=0 on 2026-10-15 22:00Z and is what "
    "will decide it.${match.mc6.h2h_n ? ` THIS CARD: ${match.mc6.h2h_n} prior meeting"
    "${match.mc6.h2h_n === 1 ? '' : 's'}, weighted evidence w=${match.mc6.h2h_w} after the "
    "365-day decay, h2h term ${match.mc6.h2h > 0 ? '+' : ''}${match.mc6.h2h}.` : ' THIS CARD: no "
    "prior meeting, so the H2H term is exactly zero and only surface form moves it.'}"
    "${match.mc6.sf1 != null ? ` Surface-form residuals ${match.mc6.sf1 > 0 ? '+' : ''}"
    "${match.mc6.sf1} vs ${match.mc6.sf2 > 0 ? '+' : ''}${match.mc6.sf2} (positive = winning more "
    "than Elo expects on this surface lately).` : ''} State built ${match.mc6.asof}.`")

NEW = ANCHOR + """
      {/* MC6 (2026-10-15, user "add mc6 to the board cards so i can see"). Always on, beside
          MC2/MC3/MC5 -- not behind the other-models expander. Shows the move against MC2 and
          WHICH of the two terms caused it, since that is the only thing MC6 adds. */}
      {match.mc6 ? (
        <div className="mono" style={{ marginTop: 3, fontSize: 10, color: '#fab7a7', opacity: match.mc6.recon ? 0.75 : 1 }}
          title={""" + TIP + """}>
          {match.mc6.recon ? '~' : ''}{'\\u{1F9EE}\\u2076'} MC6: {match.player_1.split(' ').slice(-1)[0]} <b>{Math.round(100 * match.mc6.p1_prob)}%</b> — <b>{Math.round(100 * (1 - match.mc6.p1_prob))}%</b> {match.player_2.split(' ').slice(-1)[0]}
          <span style={{ opacity: 0.75 }}>
            {match.mc6.d_mc2 != null ? ` · ${(() => { const dd = Math.round(1000 * match.mc6.d_mc2) / 10; return (dd > 0 ? '+' : '') + dd + 'pt vs MC2' })()}` : ''}
            {match.mc6.h2h_n ? ` · h2h ${match.mc6.h2h > 0 ? '+' : ''}${Math.round(1000 * match.mc6.h2h) / 1000} (${match.mc6.h2h_n}m, w${match.mc6.h2h_w})` : ' · no h2h'}
            {match.mc6.sform ? ` · sform ${match.mc6.sform > 0 ? '+' : ''}${Math.round(1000 * match.mc6.sform) / 1000}` : ' · sform 0'}
            {' · watch only'}
          </span>
        </div>
      ) : null}
"""
s = s.replace(ANCHOR, NEW)
io.open(F, "w", encoding="utf-8", newline="").write(s)
print("patched TennisSection.jsx")
print("   MC6 line refs: %d" % s.count("match.mc6"))
print("RESULT: OK")
