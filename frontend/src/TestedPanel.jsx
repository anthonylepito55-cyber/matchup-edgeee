// 🧪 TESTED & REFUTED (2026-10-12, user: "ship these view only").
//
// Every idea that was measured and did NOT earn a mark, with the number that killed it. This
// exists so the same ground is not re-tested in three months, and so a glance explains why an
// obvious-looking stat is absent from the board.
//
// VIEW ONLY. Nothing here fires a mark, feeds a lane, or changes a pick. These are closed
// questions, recorded with their evidence.
//
// Each row carries the measurement, the sample, and a one-line reason. Where a result is thin
// or provisional it says so rather than reading as settled -- a refutation on 25 bets is not
// the same claim as one on 96,663.
import React, { useState } from 'react'

const ROWS = [
  {
    g: 'Stat line',
    n: 'Pressure points (serve + return)',
    r: '−8.9%',
    sub: 'dog better on BOTH dials, n=6,984 archive',
    why: 'Worse than backing a random dog (−7.6%). Favourite side −7.1% on 14,613. Every gender, year, price band and level negative; 2026 worst at −13.0%. Live agrees in sign but has only 178 rows (3 days), so the archive is the evidence.',
    hard: true,
  },
  {
    g: 'Stat line',
    n: 'L3 window (last 3 matches)',
    r: 'saturated',
    sub: '+1.5% vs L5 +6.6%, men n=117',
    why: 'Reproduces L5’s shape but never improves on it — the effect saturates by five matches. Where L3 and L5 disagree, L3-only returns −20.6% and L5-only −29.1%, so L3’s extra games are not the good ones. Kept as a display line only.',
  },
  {
    g: 'Stat line',
    n: 'Men’s unforced errors',
    r: '−12.8%',
    sub: 'INVERTED — dog making fewer errors, n=1,252',
    why: 'The messier dog does better (−6.6%). Tightening makes it worse monotonically: ≥1 fewer UE/set −10.2%, ≥2 −13.0%, ≥3 −19.4%. Women are the opposite (+8.5% in the +100..+250 band) — UE is a women-only stat.',
    hard: true,
  },
  {
    g: 'Stat line',
    n: 'Double faults (men’s low-error dog)',
    r: '−9.0%',
    sub: 'vs its own control at −8.9%, n=28,005',
    why: 'Signal and control are indistinguishable — DF carries zero pricing information for men. Tested because DF is the one error stat at scale (97% of rows). Every split negative, all six years negative.',
    hard: true,
  },
  {
    g: 'Models',
    n: 'sUTR as a standalone pick',
    r: 'anti-signal on dogs',
    sub: 'sUTR on the dog: 35.1% vs 41.9% implied, −23.9%, n=57',
    why: 'Best single stat we have for men (62.0% vs the best context stat’s 57.6%) but 4.6pt behind the price and agreeing with it 83% of the time. Its DISAGREEMENTS are its worst games. Also: when sUTR calls a match close (<0.25 gap) it wins 45.2% — worse than a coin flip.',
  },
  {
    g: 'Models',
    n: 'Every stat, singly and combined',
    r: 'nothing beats the price',
    sub: '163,654 matches, 19 stats, both genders',
    why: 'Best single stat picks 59.6% against a market calling 66% of the same games. Seven-of-seven agreement reaches 73–75% — and the market calls 74.8/75.5% of those, so EDGE is +0.2 to +1.1pt and ROI still −5 to −6%. Agreement measures how lopsided a match is, which the price already encodes.',
    hard: true,
  },
  {
    g: 'Models',
    n: 'Reweighting the stat line for profit',
    r: '−6.8%',
    sub: 'profit-optimised, dogs only, n=8,765 walk-forward',
    why: 'Indistinguishable from backing every +100..+200 dog (≈−7%). The tell: raising the EV threshold does nothing — +0% −6.8%, +5% −6.8%, +10% −7.0%. A model with real information concentrates it when you demand more edge. The weighting was never the problem; the inputs are.',
    hard: true,
  },
  {
    g: 'Models',
    n: 'Model G as a bet',
    r: 'no edge on any cell',
    sub: '53,136 bets: dogs −11.3%/−11.8%, favs −7.6%/−5.4%',
    why: 'The 52w stat line, opponent-rank-adjusted and sample-size-shrunk. AUC .660 vs the market’s .728, behind Model C, and the market-aware version is indistinguishable from the raw price (logloss .6083 vs .6087). No positive gender×side×year cell, no gradient in the edge buckets, every price band negative. Kept as a card line and watch-only lanes — the ONE thing in it that measured real was the opponent adjustment itself (+1.2/+2.0/+2.8 AUC pts), which is a stat correction, not a bet.',
    hard: true,
  },
  {
    g: 'Models',
    n: 'Shrinking stats by sample size',
    r: 'a wash',
    sub: '+0.1 / 0.0 / −0.1 AUC pts, se 0.35pt',
    why: 'Empirical-Bayes shrinkage of every 52w rate by its own denominator — service games for hold%, return games for break%, pressure points for the dials — with k estimated from the variance components rather than chosen. It changes the numbers a lot and the predictions not at all, because the n features were already in the model: told how many games a figure rests on, it had already learned how much to discount it. Worth knowing before building it a third time.',
    hard: true,
  },
  {
    g: 'Marks',
    n: '10pt gray-dog threshold',
    r: '2026 gradient is flat',
    sub: '+8.7 / +8.4 / +15.0 by gap bucket in 2026',
    why: 'Across three years the gradient looked strong (−3.0 / +6.4 / +25.5), but that is mostly 2024–25. In 2026 it nearly vanishes, and live is inverted (4–10pt +24.6% on 15 vs 10pt+ +6.3% on 43). Recommendation to raise the threshold was withdrawn.',
  },
  {
    g: 'Markets',
    n: 'Kalshi sum-to-100 arbitrage',
    r: 'all false positives',
    sub: '75 of 913 event sets under 100c — none real',
    why: 'Kalshi "events" are mostly NOT exhaustive and mutually exclusive: candidate lists with no none-of-the-above, multi-select fields where many resolve YES, and cumulative "at or above X" ladders. Median ask-sum is 363c. Depth killed the rest anyway — thinnest legs were 0.11–1.0 contracts.',
    hard: true,
  },
  {
    g: 'Markets',
    n: 'Steam-chasing the exchanges',
    r: 'they follow in 3–6s',
    sub: 'Novig 3.5s, Kalshi 5.1s, Polymarket 6.4s',
    why: 'A 20s poll cannot resolve that window, let alone act inside it, and the measured delay is an upper bound. Betfair is slowest at 28s. The one interesting detail: Kalshi re-prices in 5s while absorbing 0% of the move — so any Kalshi edge is persistent level mispricing, not latency.',
    hard: true,
  },
  {
    g: 'Markets',
    n: 'Deep-in-the-money yield on Kalshi',
    r: 'empty',
    sub: '0 of 1,000 open markets quoted 90–99c',
    why: 'The band simply does not exist — bots have it. There is no bond-like "buy the near-certainty" trade available.',
    hard: true,
  },
  {
    g: 'Windows',
    n: 'Season vs 52 weeks',
    r: '52w wins',
    sub: '6 of 9 stats where the windows disagree',
    why: 'Including both pressure dials (svPress 52.7% vs 47.3%, rtPress 51.0% vs 49.0%). Season only wins Oct–Dec once its window has filled, and is worst Apr–Jun — a sample-size effect, not recency. The card shows both so the divergence is visible.',
  },
  {
    g: 'Feeds',
    n: 'The Odds API for tennis stats',
    r: 'no stats at all',
    sub: '/participants is names only; /scores is sets won',
    why: 'Every stat field absent — ace, double_fault, first_serve, break_point, unforced. /stats and /players are 404, and there is no challenger or ITF key at any tier. Its real value is historical ODDS (5-min grid back to mid-2024, Pinnacle included), which is what OpticOdds denies us.',
    hard: true,
  },
  {
    g: 'Feeds',
    n: 'Goalserve unforced errors',
    r: 'wrong gender',
    sub: 'ATP 57% of matches, WTA 0%',
    why: 'Supplies UE for the only gender where UE is an anti-signal (men −12.8%), and none for the gender where it pays. Useless to us twice over, though the rest of the feed earns its place.',
    hard: true,
  },
  {
    g: 'Our own picks',
    n: 'CLV on tour, vs Pinnacle’s close',
    r: 'zero',
    sub: '187 matches, |t| ≤ 1.4',
    why: 'Market dog −0.02pp, Model C’s pick −0.13pp, C on the dog −0.25pp (beats the close only 39% of the time). A TIGHT null, not an inconclusive one: at this sample a real +1pt edge would show t ≈ +8.9. Our frozen prices ARE closing prices though — 59% within 1pt of Pinnacle, unbiased.',
    hard: true,
  },
]

const GROUPS = ['Stat line', 'Models', 'Marks', 'Markets', 'Windows', 'Feeds', 'Our own picks']

export default function TestedPanel() {
  const [open, setOpen] = useState(null)
  return (
    <div style={{ padding: '10px 2px 40px' }}>
      <div className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4, fontWeight: 700 }}>
        🧪 TESTED &amp; REFUTED — {ROWS.length} closed questions
      </div>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginBottom: 14, lineHeight: 1.6, maxWidth: 940 }}>
        Everything measured that did <b>not</b> earn a mark, with the number that killed it. This is here so the
        same ground is not re-tested later, and so it is obvious why an obvious-looking stat is missing from the
        board. <b>View only</b> — nothing on this tab fires a mark, feeds a lane, or changes a pick.
        Rows flagged <span style={{ color: '#f85149' }}>■</span> rest on large samples and should be treated as
        settled; the rest are provisional and could move.
      </div>
      {GROUPS.map(g => {
        const rows = ROWS.filter(r => r.g === g)
        if (!rows.length) return null
        return (
          <div key={g} style={{ marginBottom: 16 }}>
            <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, marginBottom: 6 }}>{g}</div>
            {rows.map((r, i) => {
              const id = g + i
              const isOpen = open === id
              return (
                <div key={id}
                  onClick={() => setOpen(isOpen ? null : id)}
                  style={{
                    cursor: 'pointer', borderRadius: 7, marginBottom: 5, padding: '8px 11px',
                    background: 'var(--panel)', border: '1px solid var(--line)',
                    borderLeft: `3px solid ${r.hard ? '#f85149' : '#8b949e'}`,
                  }}>
                  <div className="mono" style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-primary)', minWidth: 230 }}>{r.n}</span>
                    <span style={{ fontSize: 12, fontWeight: 900, color: '#f85149' }}>{r.r}</span>
                    <span style={{ fontSize: 9.5, color: 'var(--text-tertiary)' }}>{r.sub}</span>
                    <span style={{ fontSize: 9, color: 'var(--text-tertiary)', marginLeft: 'auto' }}>{isOpen ? '▾' : '▸'}</span>
                  </div>
                  {isOpen ? (
                    <div className="mono" style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 7, lineHeight: 1.65, paddingLeft: 2 }}>
                      {r.why}
                    </div>
                  ) : null}
                </div>
              )
            })}
          </div>
        )
      })}
      <div className="mono" style={{ fontSize: 9.5, color: 'var(--text-tertiary)', marginTop: 18, lineHeight: 1.7, maxWidth: 940 }}>
        What survived all of this, for contrast: the <b>model heads</b> (c75 / C on dogs), the
        <b> seasonal +100..+200 band</b> cell, the <b>women’s UE lane</b> on hard court — and
        execution, which is not a prediction problem at all. The single clearest lesson across every row
        above is that the public pre-match stat line is exhausted: it has now been tested singly, combined,
        across four time windows, and reweighted three ways.
      </div>
    </div>
  )
}
