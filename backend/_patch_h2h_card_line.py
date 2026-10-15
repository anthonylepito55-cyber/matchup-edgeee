"""AN H2H LINE ON EVERY CARD THAT HAS ONE (2026-10-15).

User: "can u mark when the most recent h2h game was and who won it", then "On every game with
h2h" -- so this is its own always-visible line, not something inside the Model A drop-down.

It sits directly under the MARKET line, above the model lines, because it is a FACT about the
match rather than an opinion about it, and because the models below it (MC6 in particular) are
weighting this exact record -- the reader should see what they are weighting first.

WHAT IT SHOWS AND WHY EACH PART IS THERE:
  record        who leads and by how much, named rather than "2-0" with no subject
  how long ago  the whole point of the request. A bare "0-2" reads as a live edge; "0-2, last
                played 2.6 years ago" reads as what it is. Coloured once it is over 2 years old.
  who won it    with the score WINNER-FIRST (the backend orients it; the index stores scores from
                the lexicographically-first player's side, which would otherwise print as though
                the winner lost)
  surface       flagged when the last meeting was on a DIFFERENT surface to today's match, since
                that is when an old H2H is least transferable

The tooltip carries the surface split and explains how MC6 actually weights this record, so the
line and the model cannot silently disagree -- Stricker vs Virtanen is the case that prompted
this: 0-2 on screen, and 7% of weight inside MC6, with nothing on the card to reconcile them.
"""
import io
import os

F = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "frontend", "src", "TennisSection.jsx"))
s = io.open(F, encoding="utf-8").read()
assert "H2H_LINE" not in s, "already patched"

ANCHOR = """      {match.mc2 ? (
        <div className="mono" style={{ marginTop: 6, fontSize: 10, color: '#c9a7fa', opacity: match.mc2.recon ? 0.75 : 1 }}"""
assert s.count(ANCHOR) == 1, "MC2 line anchor not found (%d)" % s.count(ANCHOR)

NEW = """      {/* H2H_LINE (2026-10-15, user "mark when the most recent h2h game was and who won it" /
          "On every game with h2h"). Under MARKET and above the models on purpose: it is a fact
          about the match, and the models below -- MC6 especially -- are weighting this exact
          record, so the reader should see what is being weighted before seeing the weighting. */}
      {(() => {
        const h = match.model_a && match.model_a.h2h
        if (!h || !(h.p1_wins || h.p2_wins)) return null
        const n1 = match.player_1.split(' ').slice(-1)[0]
        const n2 = match.player_2.split(' ').slice(-1)[0]
        const lead = h.p1_wins === h.p2_wins ? null : (h.p1_wins > h.p2_wins ? n1 : n2)
        const hi = Math.max(h.p1_wins, h.p2_wins), lo2 = Math.min(h.p1_wins, h.p2_wins)
        const L = h.last
        // how long ago, which is the entire point of the request
        let ago = null, yrs = null
        if (L && L.date) {
          const d = Date.parse(L.date + 'T00:00:00Z')
          if (isFinite(d)) {
            yrs = (Date.now() - d) / (365.25 * 24 * 3600 * 1000)
            ago = yrs < 1 / 12 ? `${Math.max(1, Math.round(yrs * 365))}d ago`
              : yrs < 1 ? `${Math.round(yrs * 12)}mo ago` : `${yrs.toFixed(1)}y ago`
          }
        }
        const stale = yrs != null && yrs >= 2
        const winner = L && L.winner ? (L.winner === 'p1' ? n1 : n2) : null
        const diffSurf = L && L.surface && match.surface
          && String(L.surface).toLowerCase() !== String(match.surface).toLowerCase()
        return (
          <div className="mono" style={{ marginTop: 3, fontSize: 10, color: '#e3b341', opacity: 0.95 }}
            title={`HEAD-TO-HEAD, from the full match database.\\n\\n${lead ? `${lead} leads ${hi}-${lo2}` : `level ${hi}-${lo2}`}`
              + `${h.surface_n ? `, and on ${String(h.surface || '').toLowerCase()} it is ${h.surface_p1_wins}-${h.surface_n - h.surface_p1_wins} to ${n1} over ${h.surface_n} meeting${h.surface_n === 1 ? '' : 's'}` : ''}.`
              + `${L && L.date ? `\\n\\nMOST RECENT MEETING: ${L.date}${ago ? ` (${ago})` : ''} -- ${winner} won${L.score ? ` ${L.score}` : ''}${L.surface ? `, on ${String(L.surface).toLowerCase()}` : ''}${L.tournament ? `, ${L.tournament}` : ''}. The score is written winner-first.` : ''}`
              + `${stale ? `\\n\\nREAD THE DATE. This record is over two years old, and an H2H that old is close to inert: MC6 weights head-to-head on a 365-day half-life, so a meeting this far back survives at roughly ${Math.max(1, Math.round(100 * Math.pow(0.5, yrs)))}% of full weight and is then damped again by how little evidence that leaves. A bare "${hi}-${lo2}" looks like a live edge; this one mostly is not.` : ''}`
              + `${diffSurf ? `\\n\\nDIFFERENT SURFACE: that meeting was on ${String(L.surface).toLowerCase()} and this match is on ${String(match.surface).toLowerCase()}, which is where an old head-to-head transfers least.` : ''}`
              + `\\n\\nMeasured, for context: head-to-head is almost entirely priced in. The H2H leader beats the de-vigged close by only +0.75pt, and on the dog side -- the only side this board bets -- by exactly nothing.`}>
            {'\\u{1F91D} H2H: '}
            <b>{lead ? `${lead} ${hi}-${lo2}` : `level ${hi}-${lo2}`}</b>
            {h.surface_n ? <span style={{ opacity: 0.75 }}>{` \\u00b7 ${String(h.surface || '').toLowerCase()} ${h.surface_p1_wins}-${h.surface_n - h.surface_p1_wins}`}</span> : null}
            {L && L.date ? (
              <span style={{ opacity: 0.85 }}>
                {` \\u00b7 last ${L.date}`}
                {ago ? <span style={{ color: stale ? '#f0883e' : 'inherit', fontWeight: stale ? 700 : 400 }}>{` (${ago})`}</span> : null}
                {winner ? ` \\u2014 ${winner} won${L.score ? ` ${L.score}` : ''}` : ''}
                {L.surface ? <span style={{ opacity: 0.8 }}>{` \\u00b7 ${String(L.surface).toLowerCase()}`}{diffSurf ? ' \\u26a0' : ''}</span> : null}
              </span>
            ) : <span style={{ opacity: 0.7 }}>{' \\u00b7 no date on record'}</span>}
          </div>
        )
      })()}

""" + ANCHOR
s = s.replace(ANCHOR, NEW)
io.open(F, "w", encoding="utf-8", newline="").write(s)
print("patched TennisSection.jsx")
print("   H2H_LINE refs: %d" % s.count("H2H_LINE"))
print("RESULT: OK")
