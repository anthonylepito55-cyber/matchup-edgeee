/**
 * Converts American odds (e.g. "-130", "+110") to implied win probability.
 * Note: this is the RAW implied probability including the sportsbook's
 * vig/juice — it will sum to slightly over 100% across both sides of a
 * game. For a cleaner edge comparison you'd normalize by the overround,
 * but showing raw implied probability is more conservative (it slightly
 * understates your edge rather than overstating it).
 */
export function americanOddsToImpliedProb(oddsStr) {
  const odds = parseFloat(oddsStr)
  if (isNaN(odds) || odds === 0) return null

  if (odds > 0) {
    return 100 / (odds + 100)
  } else {
    return -odds / (-odds + 100)
  }
}
