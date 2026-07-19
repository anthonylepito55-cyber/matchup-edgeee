// Primary brand color per MLB team, keyed by the abbreviation the backend
// already sends. Used to give each matchup a real, recognizable identity
// (probability bar fill, team chips) instead of one generic app-wide accent
// standing in for every team.
const TEAM_COLORS = {
  ARI: '#A71930', AZ: '#A71930', ATL: '#CE1141', BAL: '#DF4601', BOS: '#BD3039', CHC: '#0E3386',
  CWS: '#27251F', CIN: '#C6011F', CLE: '#00385D', COL: '#33006F', DET: '#0C2340',
  HOU: '#EB6E1F', KC: '#004687', LAA: '#BA0021', LAD: '#005A9C', MIA: '#00A3E0',
  MIL: '#12284B', MIN: '#002B5C', NYM: '#FF5910', NYY: '#0C2340', OAK: '#003831',
  ATH: '#003831', PHI: '#E81828', PIT: '#FDB827', SD: '#2F241D', SF: '#FD5A1E',
  SEA: '#005C5C', STL: '#C41E3A', TB: '#092C5C', TEX: '#003278', TOR: '#134A8E',
  WSN: '#AB0003', WSH: '#AB0003',
}

const FALLBACK = '#8A97A6' // var(--text-secondary) — used for an unrecognized abbreviation

export function getTeamColor(abbr) {
  return TEAM_COLORS[abbr] || FALLBACK
}
