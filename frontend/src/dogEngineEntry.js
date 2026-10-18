// SERVER-SIDE ENTRY FOR THE DOG TAB'S PICK LOGIC (2026-10-17).
//
// Bundled for Node by `npm run build` into dist/dog_engine.cjs, which the deploy copies to
// backend/static/ next to the page bundle. backend/tennis_autobet.py pipes the same
// /api/tennis/track-record JSON the tab fetches into it and reads back the highlighted picks, so
// the bot bets exactly what the tab paints -- one code path (buildCells / buildStacked / markOf in
// DogPicksPanel.jsx), never a Python copy that can drift.
//
//   node dog_engine.cjs [nowMs] < track-record.json
//
// Output: { now, n_list, highlights: [...] } -- n_list is every card the tab lists, highlights
// the pink (dog) and gold (favourite) ones.
import { buildCells, buildStacked, markOf } from './DogPicksPanel.jsx'

const chunks = []
process.stdin.on('data', c => chunks.push(c))
process.stdin.on('end', () => {
  const d = JSON.parse(Buffer.concat(chunks).toString('utf8'))
  const st = ((d && (d.ab25 || d)) || {}).study || {}
  const now = Number(process.argv[2]) || Date.now()
  const cells = buildCells(st)
  const stacked = buildStacked(cells, now)
  const out = stacked.map((x) => {
    const m = markOf(x)
    return {
      // gold for a favourite, pink for a dog -- the same split the tab paints
      kind: m ? (x.p.odds < 0 ? 'gold' : 'pink') : null,
      tag: m ? m.tag : null,
      pick: x.p.pick, opp: x.p.opp, date: x.p.date, start: x.p.start,
      league: x.p.league, tournament: x.p.tournament || null, surface: x.p.surface || null,
      odds: x.p.odds, mc6_ev: x.p.mc6_ev == null ? null : x.p.mc6_ev,
      gender: x.g, cells: x.cells.map(c => c.key),
    }
  })
  process.stdout.write(JSON.stringify({ now, n_list: out.length, highlights: out.filter(h => h.kind) }))
})
