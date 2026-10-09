import React, { useEffect, useState, useMemo } from 'react'
import { americanOddsToImpliedProb } from './odds.js'

const LEAGUE_COLOR = { atp: '#4A9EFF', wta: '#FF6FA5', atp_challenger: '#7FB3FF', itf_men: '#5AC8C8', itf_women: '#E08CC0' }

const SURFACE_COLOR = {
  Hard: '#4A9EFF', Clay: '#D97748', Grass: '#3DDC84', Carpet: '#B98CE0',
}

// BEST-PICK score (2026-10-02, user ask): rank matches by their strongest live-positive
// signal. Mirrors the green hierarchy: APEX > star+priced > star > fade-A dog > C-alone >
// fade-gold. Women's dog cells (live-cold) rank below men's. Used by board + ITF sort.
function pickScore(m) {
  const mc = m.model_c
  if (!mc || mc.market_p1 == null || mc.market_aware_p1 == null || mc.p1_prob == null) return 0
  const c1 = mc.p1_prob >= 0.5, g1 = mc.market_aware_p1 >= 0.5, dog1 = mc.market_p1 < 0.5
  const star = c1 === g1 && g1 === dog1
  const aP = m.model_a && m.model_a.p1_prob != null ? m.model_a.p1_prob >= 0.5 : null
  const bP = m.model_b && m.model_b.p1_prob != null ? m.model_b.p1_prob >= 0.5 : null
  const alone = aP !== null && bP !== null && aP !== c1 && bP !== c1
  const dAm = m.live_odds ? Number(dog1 ? m.live_odds.player_1 : m.live_odds.player_2) : null
  const dDec = dAm != null && !isNaN(dAm) ? (dAm > 0 ? 1 + dAm / 100 : 1 + 100 / Math.abs(dAm)) : null
  const priced = dDec != null && dDec >= 2.0
  let sc = 0
  if (star && alone && priced) sc = 100
  else if (star && priced) sc = 80
  else if (star && alone) sc = 70
  else if (star) sc = 60
  else if (aP !== null && bP !== null && aP !== bP && bP === c1 && bP === dog1) sc = 50
  else if (alone) sc = 40
  else {
    const mdog = dog1 ? mc.market_p1 : 1 - mc.market_p1
    const gdog = dog1 ? mc.market_aware_p1 : 1 - mc.market_aware_p1
    if (mdog - gdog >= 0.02) sc = 20
  }
  if (m.league === 'wta' && sc >= 40) sc -= 15
  return sc
}

// PST/PT start time (2026-10-02, user ask): show every game's start in Pacific and order by it.
const fmtPT = (utc) => {
  if (!utc) return null
  try {
    const d = new Date(utc)
    if (isNaN(d)) return null
    return d.toLocaleTimeString('en-US', { timeZone: 'America/Los_Angeles', hour: 'numeric', minute: '2-digit' }).replace(' ', '') + ' PT'
  } catch { return null }
}

// Tennis FORWARD RECORD panel (2026-09-06): tennis ran two months with predictions but no
// ledger — nothing frozen, nothing graded. The backend now logs every priced prediction
// before first serve and settles from real results; this panel shows that record growing
// from zero. Until it has real sample, the honest banner is "unproven — do not bet this".
function TennisTrackRecord() {
  const [r, setR] = useState(null)
  useEffect(() => {
    fetch('/api/tennis/track-record').then(x => x.json()).then(setR).catch(() => {})
  }, [])
  if (!r) return null
  const small = !r.n || r.n < 50
  return (
    <div style={{ margin: '14px 0', padding: '12px 18px', borderRadius: 8, border: '1px solid var(--line)', background: 'linear-gradient(180deg, var(--panel-raised), var(--panel))' }}>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>
        Tennis forward record <span style={{ color: 'var(--text-tertiary)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>— started 2026-09-06 · every priced prediction frozen before first serve, graded from real results</span>
      </div>
      <div className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 6, lineHeight: 1.6 }}>
        {r.n ? (
          <>
            model {(100 * r.model_accuracy).toFixed(1)}% vs market {(100 * r.market_accuracy).toFixed(1)}% on {r.n} settled ·
            flat-pick ROI {r.flat_roi_pct > 0 ? '+' : ''}{r.flat_roi_pct}% ·
            disagreements: {r.n_disagree}{r.disagree_flat_roi_pct != null ? ` (model ${(100 * r.disagree_model_accuracy).toFixed(0)}% right, ROI ${r.disagree_flat_roi_pct > 0 ? '+' : ''}${r.disagree_flat_roi_pct}%)` : ''}
          </>
        ) : (
          <>{r.total_logged || 0} predictions logged · {r.settled || 0} settled — the ledger just started; numbers appear as matches finish.</>
        )}
        {small ? <span style={{ color: '#f85149', fontWeight: 700 }}> · UNPROVEN — this model has never been graded before; do not bet tennis until this record earns it (±{r.n ? Math.round(200 / Math.sqrt(r.n)) : '∞'}pt noise band)</span> : null}
        {r.sr_dog ? (
          <span style={{ color: '#e879f9' }} title="SR-DOG pre-registered tracker — flat 1u on flagged underdogs whose surface serve+return beats the favorite. LIVE frozen-ledger numbers: 'reg' = scored over the ledger's settled matches before registration (frozen first-serve odds, as-of features; only 7 qualified pre-pool-expansion), then the post-reg chip accumulates forward. Judged at 50 post-reg settled. Backtest context: 2025 +15.1%/2026 +8.6% on the 190-player core.">
            {' '}· ★ SR-DOG live: reg {r.sr_dog.at_registration ? `${r.sr_dog.at_registration.flat_roi_pct > 0 ? '+' : ''}${r.sr_dog.at_registration.flat_roi_pct}% (${r.sr_dog.at_registration.n})` : '—'} · post-reg {r.sr_dog.n ? `${r.sr_dog.flat_roi_pct > 0 ? '+' : ''}${r.sr_dog.flat_roi_pct}% (${r.sr_dog.n}/${r.sr_dog.checkpoint})` : `0/${r.sr_dog.checkpoint}`}
          </span>
        ) : null}
        {r.sos ? (
          <span style={{ color: '#22d3ee' }} title="SOS win-rate tracker — player with equal-or-better surface stats but clearly tougher recent schedule. Question tracked: how often do they beat the other guy? (Backtest: 63-65% wins, but priced — ROI negative.)">
            {' '}· ◆ SOS: reg {r.sos.at_registration ? `${r.sos.at_registration.win_pct}% wins (${r.sos.at_registration.n})` : '—'} · live {r.sos.n ? `${r.sos.win_pct}% wins, ROI ${r.sos.flat_roi_pct > 0 ? '+' : ''}${r.sos.flat_roi_pct}% (${r.sos.n})` : '0 settled'}
          </span>
        ) : null}
      </div>
    </div>
  )
}

// Cross-book price-edge scanner (2026-09-09): the 2026 backtests showed every public stat
// is already in the price — the one path that needs no model is a bettable book lagging the
// sharp consensus (Pinnacle/Circa de-vigged). The backend scans ATP/WTA/Challenger/ITF and
// flags any bettable side priced ≥2pts better than sharp fair (longshots under 25% fair
// excluded — de-vig math is least trustworthy there). Every flag is frozen at first serve
// into a flat-1u forward record with CLV vs the closing sharp fair. Checkpoint: 75 settled.
const SCAN_LEAGUE_LABEL = { atp: 'ATP', wta: 'WTA', atp_challenger: 'CHALLENGER', itf_men: 'ITF M', itf_women: 'ITF W' }

function PriceEdgeScanner({ scan }) {
  const [rec, setRec] = useState(null)
  useEffect(() => {
    fetch('/api/tennis/scanner-record').then(x => x.json()).then(setRec).catch(() => {})
  }, [])
  const gold = '#e3b341'
  // Soft ponds first (user call 9/21): Challenger/ITF flags have carried the record
  // (challenger +28.8% at checkpoint pass), so they sort to the top, tour flags after,
  // best edge first within each tier. Each league tag carries its own LIVE record chip.
  const SOFT = { atp_challenger: 0, itf_men: 0, itf_women: 0, utr_men: 0, utr_women: 0 }
  const edges = [...(scan?.edges ?? [])].sort((a, b) =>
    ((a.league in SOFT ? 0 : 1) - (b.league in SOFT ? 0 : 1)) || (b.edge - a.edge))
  const leagueRec = lg => {
    const r = rec && rec.by_league && rec.by_league[lg]
    return r ? ` ${r.flat_roi_pct > 0 ? '+' : ''}${r.flat_roi_pct.toFixed(1)}% (${r.n})` : ''
  }
  return (
    <div style={{ margin: '14px 0', padding: '12px 18px', borderRadius: 8, border: `1px solid ${gold}55`, background: `linear-gradient(180deg, ${gold}0d, var(--panel))` }}>
      <div className="mono" style={{ fontSize: 10, color: gold, textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>
        Cross-book price scanner <span style={{ color: 'var(--text-tertiary)', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>— pre-registered experiment · a bettable venue ≥2pts better than the sharp (Pinnacle/Circa) de-vigged consensus · ATP · WTA · Challenger · ITF · includes Kalshi + Polymarket (★ = bettable where you live; Kalshi edges shown net of its ~0.07·p·(1−p) trading fee)</span>
      </div>
      {scan ? (
        <div className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 6 }}>
          scanned {scan.scanned} matches · {scan.priced} priced by a sharp book · {edges.length} flag{edges.length === 1 ? '' : 's'}
          {edges.length === 0 && <span style={{ color: 'var(--text-tertiary)' }}> — no book is lagging the sharp consensus right now (a typical price runs ~3–4pts worse than fair; that gap is the vig)</span>}
        </div>
      ) : (
        <div className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 6 }}>scan unavailable — appears with today's slate.</div>
      )}
      {edges.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 10 }}>
          {edges.map((e, i) => (
            <div key={`${e.fixture_id}_${e.side}`} className="mono" style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10, flexWrap: 'wrap',
              padding: '8px 12px', borderRadius: 6, border: `1px solid ${gold}44`, background: `${gold}0a`, fontSize: 11,
            }}>
              <span>
                <span style={{ color: gold, fontWeight: 700, fontSize: 9, letterSpacing: '0.05em' }}
                  title={`This league's live scanner record (flat 1u at flag prices, updates as flags settle):${leagueRec(e.league) || ' accruing'}`}>
                  {SCAN_LEAGUE_LABEL[e.league] || e.league}<span style={{ fontWeight: 400, color: 'var(--text-tertiary)' }}>{leagueRec(e.league)}</span>
                </span>
                <span style={{ color: 'var(--text-secondary)' }}> {e.player_1} vs {e.player_2}</span>
                <span style={{ color: 'var(--text-tertiary)', fontSize: 10 }}> · {e.tournament}</span>
              </span>
              <span style={{ whiteSpace: 'nowrap' }}>
                <span style={{ color: 'var(--text-primary)', fontWeight: 700 }}>{e.side_player}</span>
                <span style={{ color: 'var(--text-secondary)' }}> {fmtPrice(e.price)} @ {e.user_bettable ? '★ ' : ''}{e.book}</span>
                <span style={{ color: 'var(--edge-pos)', fontWeight: 700 }}> +{(100 * e.edge).toFixed(1)}pt</span>
                <span style={{ color: 'var(--text-tertiary)', fontSize: 10 }}> vs fair {(100 * e.fair_prob).toFixed(0)}%</span>
                {e.fair_move != null && Math.abs(e.fair_move) >= 0.005 && (
                  <span style={{ color: e.fair_move > 0 ? 'var(--edge-pos)' : 'var(--edge-neg)', fontSize: 10 }}>
                    {' '}· fair {e.fair_move > 0 ? '↑' : '↓'}{Math.abs(100 * e.fair_move).toFixed(1)} since first seen
                  </span>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 8, lineHeight: 1.5 }}>
        {rec?.overall ? (
          <>
            record: {rec.overall.n} settled of {rec.total_flagged} flagged · win {(100 * rec.overall.win_rate).toFixed(0)}% (fair promised {(100 * rec.overall.avg_fair_promised).toFixed(0)}%) ·
            flat ROI {rec.overall.flat_roi_pct > 0 ? '+' : ''}{rec.overall.flat_roi_pct}% · CLV {rec.overall.avg_clv_pt > 0 ? '+' : ''}{rec.overall.avg_clv_pt}pt · beat close {rec.overall.beat_close_pct}%
          </>
        ) : (
          <>record: {rec?.total_flagged ?? 0} flagged · {rec?.settled ?? 0} settled — starts empty, grows as flags settle.</>
        )}
        {!rec?.proven && <span style={{ color: '#f85149', fontWeight: 700 }}> · SHADOW ONLY — flat 1u, judged at {rec?.checkpoint_n ?? 75} settled; prices move fast, CLV is the health metric. Do not bet this yet.</span>}
        {rec?.proven && <span style={{ color: 'var(--edge-pos)', fontWeight: 700 }}> · ✓ PASSED its pre-registered checkpoint ({rec.checkpoint_n} settled) on the named health metric — CLV {rec.overall.avg_clv_pt > 0 ? '+' : ''}{rec.overall.avg_clv_pt}pt, beat the close {rec.overall.beat_close_pct}% of the time. Small flat stakes (0.5–1u) are now defensible on ★ venue flags only; sportsbook flags stay shadow. Record keeps running.</span>}
      </div>
    </div>
  )
}

// A/B $25 lanes panel (2026-09-28, user ask): live $ record of Model A alone (B disagrees),
// Model B alone (A disagrees), and both-agree, $25/pick at frozen first-serve odds.
function Ab25Panel() {
  const [rec, setRec] = useState(null)
  useEffect(() => {
    const go = () => fetch('/api/tennis/track-record').then(r => r.json()).then(d => setRec(d.ab25 || null)).catch(() => {})
    go()
    const id = setInterval(go, 120000)
    return () => clearInterval(id)
  }, [])
  const usd = v => `${v < 0 ? '-' : '+'}$${Math.abs(v).toFixed(2)}`
  const [openLane, setOpenLane] = useState(null)
  const st = (rec && rec.study) || {}
  const get = k => {
    if (!rec) return null
    if (k.startsWith('st:')) return st[k.slice(3)]
    if (k.startsWith('ln:')) return (rec.lanes || {})[k.slice(3)]
    return rec[k]
  }
  // [key, label, tooltip] — grouped into sections (2026-09-29, user ask: the red-name
  // config gets its own category, separate from the C mkt-aware lanes and the rest)
  const STARS = [
    ['agree_dog', '★ C+GRAY DOG', 'Blue C AND the gray line both on the market UNDERDOG: 54.8% at plus prices, +24.4/+21.6/+13.7% by year on 8,320 backtest bets.'],
    ['st:c_alone_gray_dog', '★ C ALONE + GRAY DOG', 'C defies A and B, gray confirms, side is a DOG: +25.2% on 3,097 backtest bets, +16.8% in 2026 — the strongest current-season cell in the build.'],
    ['st:apex_dog', '🔥 APEX DOG', 'The maximal validated stack: C-alone+gray DOG AND priced (decimal ≥2.0). Live +47.6% (and +70.8% on the men’s half, 8 bets). Each component is backtest-validated (C-alone+gray = best cell; priced-dog ROI rises with price). The board’s single best-pick flag — gender-aware, so the women’s side shows its own (currently cold) live record.'],
    ['st:gray_dog4', '★ GRAY DOG 4pt+', 'Gray line 4+ points above the market on a dog it picks: +9.1% in 2026 on 5,814 backtest bets.'],
    ['st:gold_names', '★ ALL GOLD NAMES', 'Every neon-yellow name on the board, $25 each — the union of C+GRAY DOG picks and gray-hated-dog fades. This is literally "bet what glows": the board’s take-color earning (or losing) its keep as one number.'],
    ['st:fade_a', '★ FADE MODEL A', 'A against BOTH B and C → $25 on the B&C side (the opposite of A). Backtest +8.0% on 5,080 (positive all 3 years); the dog half +14.8%, dog+gray-confirmed +20.5% (2026 +19.7%). A-alone’s own side backtests −20.6% and is 13-39 (−34%) live — its dissent is the most reliable wrongness measured. Registered 2026-09-30.'],
    ['st:fade_a_dog', '★ FADE A — DOG', 'Fade-A where the B&C side is the market DOG: +14.8% all-years / +11.5% in 2026 on 2,305 backtest bets. The half of fade-A that actually pays.'],
    ['st:fade_a_dog_gray', '★ FADE A — DOG+GRAY', 'Fade-A dog with the gray line also on the B&C side: +20.5% all-years / +19.7% in 2026 on 1,080 — TIER-1-class, next to C-alone+gray-dog among the best cells in the build.'],
    ['st:stardog_prime', '🎯 PRICED STAR DOG (≥2.0)', 'Star-dog ROI RISES with price (backtest, 2026-10-02): +20.5% at 2.0-2.5 (n=3,733), +34.6% at 2.5-3.0, +59% at 3.0-4.0; only short dogs (<1.8) are dead (−2%). So this lane = C+GRAY DOG at decimal ≥2.0 (plus-money). Longer price = higher ROI but higher variance. (The earlier "2.0-3.0 sweet spot" was an 18-bet live artifact the backtest corrected.)'],
    ['st:mc_tossup', 'MC TOSS-UP (watch)', 'The Monte Carlo’s closest calls — confidence 50-60% (near coin-flips). Live +15.3% on 13, the ONE MC bucket positive live (every confident/market-disagreeing MC bucket loses, and MC adds nothing as a filter). Mechanism unclear — likely the MC deferring to the market on toss-ups. Thin; tracked, not yet a confident take.'],
    ['st:cgray_dog_late', 'LATE ROUND DOG (watch)', 'C+gray dog in later rounds (QF/SF/F etc., not R1/qualifying): live +18.0% on 19. New round dimension, thin — and possibly confounded (later rounds = fewer, higher-quality matches). Tracked as a watch until ~40 settles.'],
  ]
  // TIER lanes (registered 2026-09-30, user ask): the board ribbon itself on trial —
  // $25 per pick from today forward, one lane per tier. TIER 1/2 bet the star dog,
  // TIER 3 the fade-gold favorite; AVOID bets C's side and NO BET gray's side so the
  // pass verdicts have to earn their keep in public too.
  const TIERS = [
    ['st:tier1', 'TIER 1 — MULTI-★ DOG', 'Star dog with a second signal stacked (C-alone or gray 4pt+). $25 each from 2026-09-30 forward.'],
    ['st:tier2', 'TIER 2 — SINGLE ★ DOG', 'C + gray on the dog, no extra stack. $25 each from 2026-09-30 forward.'],
    ['st:tier3', 'TIER 3 — FADE-GOLD FAV', 'Favorite over a gray-hated dog. $25 each from 2026-09-30 forward.'],
    ['st:tier_avoid', 'AVOID (tracked)', 'The ribbon’s no-play configs (pass-favorite / C-vs-gray fight), $25 on C’s side — this lane is supposed to LOSE; it proves the avoid verdict.'],
    ['st:tier_nobet', 'NO BET (tracked)', 'Everything with no lane fired, $25 on the gray side — the priced-in control the tiers above must beat.'],
  ]
  const REDS = [
    ['st:grayhate_dog', 'RED — GRAY-HATED DOG', 'Documented loser: dogs the gray line prices 2+ pts UNDER market won 27% and lost 25-31%/bet every backtest year. Tracked live so the avoid-list carries a current number.'],
    ['st:c_alone_gray_fav', 'RED — C+GRAY FAVORITE', 'C alone against A and B, gray confirms, on the market FAVORITE. Demoted from a take back to avoid 2026-10-02 (user call): live −6.7% on 31 settles. The DOG half of C-alone+gray is the +40% play; the favorite half loses. No bet either side.'],
  ]
  const MODELS = [
    ['ln:agree', 'A + B AGREE', 'Both models pick the same winner — $25 on that side.'],
    ['ln:a_alone', 'MODEL A ALONE', 'Disagreement matches, $25 on Model A’s side (full history + H2H model).'],
    ['ln:b_alone', 'MODEL B ALONE', 'Mirror of A-alone: $25 on Model B’s pick (last-10-on-court model). Backtest: −5.9% all-years / −3.1% in 2026 on 12,494 — mildly negative, far better than A’s side, but not a bet; fading A only pays when C is ALSO on B’s side (the ★ FADE A cell).'],
    ['c_all', 'C ALL PICKS', 'Every match Model C covers: $25 on its favored side, edge or no edge.'],
    ['c_edge', 'C-EDGE 5pt+', 'Raw C disagrees with the de-vigged frozen market by 5+ pts — the audit’s judge. Backtest +4..+11% vs soft averages; live is the test at real prices.'],
    ['c_alone', 'C ALONE', 'C against both A and B, $25 on C’s side (unfiltered). Backtest +14.8% all-years / +8.3% in 2026 on 9,410 — and never fade it (the A&B side lost −22.6%). The gray-dog slice (+16.8% bt26) is the star lane above.'],
    ['st:c_alone_gray', 'C ALONE + GRAY OK (all)', 'C alone with gray confirmation, favorite AND dog halves together: +15.1% on 6,778 backtest.'],
    ['c_with', 'C AGREES', 'C with at least one of A/B on the same side.'],
    ['cma_all', 'C MKT-AWARE ALL', 'The gray line’s favored side every match — doubles as the market-favorite control the other lanes must beat.'],
    ['cma_edge', 'C MKT-AWARE EDGE 2pt+', 'Gray line 2+ pts off the de-vigged market — the only head that beat the raw market in validation.'],
    ['st:grayhate_fav', 'FADE GRAY-HATED DOG', '$25 on the favorite over a gray-hated dog — the only favorite angle that tested positive (+2..4% in 2026, thin).'],
    ['st:cvg_c', 'C-SIDE OF FIGHT', 'C vs gray split: C’s side. Backtest decayed +15.9% (2024) to −1.5% (2026).'],
    ['st:cvg_gray', 'GRAY-SIDE OF FIGHT', 'The mirror control: gray’s side of the same fights (backtest −11.9%).'],
    ['st:abc_agree', 'A+B+C AGREE', 'Triple consensus: 69% hit, −1.9% backtest — control lane.'],
    ['st:abc_dog', 'A+B+C DOG', 'Triple consensus on a dog: decayed to +0.3% in 2026.'],
    ['st:green_names', 'ALL GREEN NAMES', 'Every plain dark-green name — the gray line’s pick where no gold or red overrides. The reference color’s own record: if this lane ever earns money at real prices, dark green would deserve promotion (per the two-key rule).'],
    ['st:fade_a_fav', 'FADE A — FAVORITE', 'Fade-A where the B&C side is the market favorite: thin (+2.4% all-years / +1.6% in 2026) — tracked as a control, not a manual take.'],
    ['st:d_all', 'MODEL D ALL PICKS', 'Every match Model D covers: $25 on its favored side. v3 (2026-10-01, rank-blind on user call — own ranks never compared, only schedule quality): picks 61-62% vs the market’s 66% walk-forward. This lane is its public live test.'],
    ['st:dma_all', 'D MKT-AWARE ALL', 'Model D’s gray head (form refit WITH the price): beat the raw market in 2024-25 validation, lost to it slightly in 2026. $25 on its side every match.'],
    ['st:d_gray_dog', 'D + GRAY DOG', 'Model D’s best backtest cell — D and its own gray head both on the market dog: v3 +9.7% (2024) → +11.2% (2025) → +2.9% (2026). The decay says recent form is mostly priced out; this lane is the live judge.'],
    ['st:d_alone', 'D ALONE', 'D against A, B AND C. Backtest: its dissent carries ZERO information (consensus performs identically with or without D) — tracked live to confirm in public.'],
    ['st:mc_all', 'MONTE CARLO ALL', '$25 on whichever side the 100,000-sim Monte Carlo favors, every covered match (registered 2026-10-01). The sim runs on recency-weighted serve/return stats with exact scoring math — this lane is its public win-rate and ROI test.'],
    ['st:mc_dog', 'MONTE CARLO DOG', 'The slice where the 100k-sim MC favors the market UNDERDOG — the only version of any signal that has ever paid in this build. Small volume; watch it.'],
    ['st:mc_biggray', '★ MC DOG+GRAY', 'The ONLY profitable MC-dog slice in backtest: MC favors the market dog ≥60% AND the gray line ALSO likes that dog — +19.3% over 3,173 (vs −6.0% for the raw MC big dog, which includes gray-hated traps like Jacquet). The gray line is doing the work; MC just tags along. Live tracked.'],
    ['st:mc_dog_big', 'MC BIG DOG — raw (watch)', 'Every MC big dog (≥60% sim on a market dog), gray-liked or not. Backtest −6.0% — the gray-HATED half (e.g. Jacquet) sinks it. Use MC DOG+GRAY above instead; this is the control.'],
    ['st:mc_4of4', 'MC + 4/4 SLIP (watch)', 'The Monte Carlo agrees with a 4/4 slip (A, B, C AND D all on the same side). Backtest: −2.2% over 29k (the MC does NOT filter consensus — 4/4 where MC disagrees was actually +0.4%). Tracked live, not a take.'],
    ['st:mc_gold', 'MC + GOLD NAME (watch)', 'The MC agrees with a gold name (star dog or fade-gold favorite). Backtest/live: inherits gold’s thin-favorite nature — MC’s co-sign adds no edge to an already-priced name. Tracked, not a take.'],
    ['st:mc_green', 'MC + GREEN NAME (watch)', 'The MC agrees with a green name (gray’s pick, no gold/red override — nearly all priced favorites). Tracked control; no edge expected.'],
    ['st:mc_c_all', 'C-MC · c50 (VISIBLE)', 'The C-MC anchoring shown on the cards: serve sim pulled HALFWAY toward Model C, no court-UTR. $25 on its side every match (registered 2026-10-02). First picks: Shapovalov & Ann Li. Compared head-to-head below against two invisible variants (c75, cUTR) — whichever earns the best live record over time can become the displayed one.'],
    ['st:mc_c75_all', 'C-MC · c75 (hidden test)', 'Invisible variant: serve sim anchored 75% toward Model C (vs 50% for the visible one). Fixes cases where padded serve stats drag the sim off a correct C read (the Storm Hunter 6-2 6-0 case: c50 had it 57%, too close). Tracked only; not shown on cards.'],
    ['st:mc_cutr_all', 'C-MC · cUTR (hidden test)', 'Invisible variant: serve sim with a STRONGER court-UTR de-padding applied first (0.75 shrink), THEN the halfway Model-C anchor. Attacks the padded-serve problem at the source (Storm Hunter’s doubles-inflated serve stats) rather than just leaning harder on C. Tracked only; not shown on cards.'],
    ['st:mc_c_and_d', 'MC-C + MC-D AGREE', 'The matches where the Model-C-anchored MC and the Model-D serve MC (MONTE CARLO ALL) land on the SAME side. Tests whether the two independent simulations confirming each other means anything — tracked from 2026-10-02, not a take.'],
    ['st:mcc_c75_agree', '⚄ C-MC + c75 TAKE', 'Your take (2026-10-03): $25 on every game where c-MC (c50) and the c75 variant agree. Live +21.9% on 25 (19-6) — hot but recent; the larger reconstructed sample is flat (+0.1%), and the two agree on ~88% of games so this is a broad net. Forward-tracked from today.'],
    ['st:cc75_d_dog', '🐕 c50+c75+D DOG', 'Your hypothesis (2026-10-04): a market DOG that c50 AND c75 AND Model D all back. Walk-forward backfill said this was WORSE than the no-D version (46% vs 58% hit), likely the padded-form trap — but the forward sample is tiny. This lane is the live judge; compare it to the no-D version below.'],
    ['st:cc75_nod_dog', '🐕 c50+c75 DOG · D on fav', 'The other half: a market dog c50 and c75 both like while Model D is on the FAVORITE. Backfill had this as the STRONGER group (73% / +90%). Tracked head-to-head against the D-agrees version to settle whether Model D agreeing on a dog helps or hurts.'],
    ['st:dma_edge2', '📈 D-MA 2pt EDGE', 'Model D’s market-aware head on its favored side, where its probability is ≥2 points OVER the market’s implied number. Of the four market-aware heads, this is the ONLY one that is +ROI when it dissents from the price: +7.5% on 53 (backfill). Forward-tracked take from 2026-10-04.'],
    ['st:all10_agree', '✅ ALL-10 AGREE', 'Every model + Monte Carlo on the SAME side: A, B, C, gray, D, D-ma, serve-MC, c50, c75, cUTR. The highest-hit-rate marker (80% / +4.4% backfill) — but near-always a clear favorite at short odds (only 2 of 35 were dogs, 1-1), so the ROI is small. Forward-tracked from 2026-10-04.'],
    ['st:cc75_dog', '🐕 c50+c75 DOG', 'A market DOG that both C-MC variants (c50 and c75) back, regardless of Model D. Analysis 2026-10-04: wins 47% vs the market-implied 38% (+9pt edge), flat +19% ROI. One of the validated priced-dog cells — take it.'],
    ['st:against_a', '↺ AGAINST A (watch)', 'Fade Model A: $25 on the OPPOSITE of A’s pick, every match. A is the weakest model, so fading it is a natural watch — but straight-fading also catches A’s correct calls, so live it’s only 49% / -4%. Watch, not a take. The validated fade is ★ FADE A (A dissenting from both B and C).'],
  ]
  const card = ([k, label, tip], border, labelColor) => {
    const l = get(k)
    const pkey = k.replace('st:', '').replace('ln:', '')
    const plist = (rec && rec.picks && rec.picks[pkey]) || []
    const open = openLane === pkey
    return (
      <div key={k} className="mono" title={tip} onClick={() => setOpenLane(open ? null : pkey)}
        style={{ padding: '12px 16px', borderRadius: 8, border: `1px solid ${border}`, background: 'var(--panel)', minWidth: 200, cursor: plist.length ? 'pointer' : 'default' }}>
        <div style={{ fontSize: 10, color: labelColor, fontWeight: 700, letterSpacing: '0.04em' }}>{label}</div>
        {l && l.n ? (
          <>
            <div style={{ fontSize: 16, fontWeight: 700, color: l.profit_usd >= 0 ? '#3fb950' : '#f85149', marginTop: 4 }}>{usd(l.profit_usd)}</div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{l.wins}-{l.n - l.wins} · ${l.staked_usd} staked · {l.roi_pct > 0 ? '+' : ''}{l.roi_pct}%{l.pending ? ` · ${l.pending} pending` : ''}</div>
          </>
        ) : (
          <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>{l && l.pending ? `${l.pending} pending` : '0 settled'} — accrues nightly</div>
        )}
        {open && plist.length ? (
          <div style={{ marginTop: 8, borderTop: '1px solid var(--line)', paddingTop: 6, maxHeight: 260, overflowY: 'auto' }}>
            {plist.map((pk, i) => (
              <div key={i} style={{ fontSize: 10, display: 'flex', gap: 6, padding: '2px 0', color: 'var(--text-secondary)' }}>
                <span style={{ color: 'var(--text-tertiary)', minWidth: 34 }}>{pk.d}</span>
                <span style={{ color: pk.w === null ? 'var(--amber)' : pk.w ? '#3fb950' : '#f85149', minWidth: 14, fontWeight: 700 }}>
                  {pk.w === null ? '…' : pk.w ? 'W' : 'L'}
                </span>
                <span style={{ flex: 1 }}>{pk.s} <span style={{ color: 'var(--text-tertiary)' }}>vs {pk.o}</span></span>
                <span style={{ color: 'var(--text-tertiary)' }}>{pk.pr != null ? (pk.pr > 0 ? `+${pk.pr}` : pk.pr) : ''}</span>
                <span style={{ color: pk.lg === 'W' ? '#d2a8ff' : 'var(--text-tertiary)', minWidth: 10 }}>{pk.lg}</span>
              </div>
            ))}
            <div style={{ fontSize: 9, color: 'var(--text-tertiary)', marginTop: 3 }}>last {plist.length} picks · newest first · … = pending · click card to close</div>
          </div>
        ) : null}
        {l && ((l.m && l.m.n) || (l.w && l.w.n)) ? (
          <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 2 }}
            title="Men (ATP/challenger/ITF men) vs women (WTA incl. 125Ks), live. Backtest: the women's side of the star cells hits 63-64% vs the men's 53-54% — this line tests that split in public.">
            {l.m && l.m.n ? `M ${l.m.wins}-${l.m.n - l.m.wins} ${l.m.roi_pct > 0 ? '+' : ''}${l.m.roi_pct}%` : 'M —'}
            {' · '}
            {l.w && l.w.n ? `W ${l.w.wins}-${l.w.n - l.w.wins} ${l.w.roi_pct > 0 ? '+' : ''}${l.w.roi_pct}%` : 'W —'}
          </div>
        ) : null}
        {l && ((l.dog && l.dog.n) || (l.fav && l.fav.n)) ? (
          <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 2 }}
            title="This signal's record split by whether the PICK was a market UNDERDOG vs FAVORITE. For almost every signal the real edge is in the dogs; favorite picks tend to be flat-to-negative (efficiently priced chalk).">
            {l.dog && l.dog.n ? <span style={{ color: l.dog.roi_pct > 3 ? '#3fb950' : l.dog.roi_pct < -3 ? '#f85149' : 'var(--text-tertiary)' }}>🐕 {l.dog.wins}-{l.dog.n - l.dog.wins} {l.dog.roi_pct > 0 ? '+' : ''}{l.dog.roi_pct}%</span> : '🐕 —'}
            {' · '}
            {l.fav && l.fav.n ? <span style={{ color: l.fav.roi_pct > 3 ? '#3fb950' : l.fav.roi_pct < -3 ? '#f85149' : 'var(--text-tertiary)' }}>⭐ {l.fav.wins}-{l.fav.n - l.fav.wins} {l.fav.roi_pct > 0 ? '+' : ''}{l.fav.roi_pct}%</span> : '⭐ —'}
          </div>
        ) : null}
        {l && ((l.m_dog && l.m_dog.n) || (l.m_fav && l.m_fav.n) || (l.w_dog && l.w_dog.n) || (l.w_fav && l.w_fav.n)) ? (
          <div style={{ fontSize: 9, color: 'var(--text-tertiary)', marginTop: 2 }}
            title="Gender × side crossed: men-dog / men-fav / women-dog / women-fav. Shows which exact slice carries the signal (e.g. the 6-4 fade is a men-dog play).">
            {(() => {
              const cc = c => (!c || !c.n) ? null : <span style={{ color: c.roi_pct > 3 ? '#3fb950' : c.roi_pct < -3 ? '#f85149' : 'var(--text-secondary)' }}>{c.roi_pct > 0 ? '+' : ''}{c.roi_pct}%/{c.n}</span>
              const md = cc(l.m_dog), mf = cc(l.m_fav), wd = cc(l.w_dog), wf = cc(l.w_fav)
              return <>
                {(md || mf) ? <>M {md ? <>🐕{md} </> : ''}{mf ? <>⭐{mf}</> : ''}</> : null}
                {((md || mf) && (wd || wf)) ? ' · ' : ''}
                {(wd || wf) ? <>W {wd ? <>🐕{wd} </> : ''}{wf ? <>⭐{wf}</> : ''}</> : null}
              </>
            })()}
          </div>
        ) : null}
      </div>
    )
  }
  const section = (title, note) => (
    <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700, margin: '14px 0 6px' }}>
      {title} <span style={{ fontWeight: 400, textTransform: 'none' }}>{note}</span>
    </div>
  )
  return (
    <div style={{ marginTop: 16 }}>
      <div className="mono" style={{ padding: '10px 16px', borderRadius: 6, border: '1px solid var(--line)', fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.5 }}>
        $25 a game, registered {rec ? rec.registered : '2026-09-28'}. Picks freeze at first serve with the odds; settled from the ledger.
        {rec && rec.pending ? ` ${rec.pending} pending.` : ''}
      </div>
      {section('🧊 Fade the form (live take · forward-only)', '— on an mc_c75 pick where quality-adjusted last-10-on-surface form (opponent quality + how competitive, NO serve stats) points at the OPPONENT, $25 on the MODEL side. The market overvalues recent form, so you fade it. Forward-only (reconstructed games excluded). The edge is ALL in the DOGS (🐕 line below); favorite form-fades are flat/negative. The FORM-AGREES card is the no-edge contrast.')}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        {card(['st:pf_c75_dis', '🧊 FADE FORM (take)', 'The 🧊 FORM-FADE board/Best signal as a $25 lane: every mc_c75 pick where the pure-results recent-form overlay (last-10-on-surface, opponent quality + how competitively they won/lost, NO serve stats) points at the OPPONENT — you fade that form narrative and stake $25 on the model’s pick. Live edge: men +18.9% (n117), women +4.9% (n70). Favorites are the steady half (~74% hit, +10%), dogs the high-variance half (+36%). One month of forward sample — real but unproven; m/w split below. Click to see the picks.'], '#56d4dd', '#56d4dd')}
        {card(['st:pf_c75_agr', '🔥 FORM AGREES (contrast)', 'The control half: mc_c75 picks where recent form AGREES with the model. This is the no-edge comparison — live men −2% / women −15% — shown so the separation that makes the FADE-FORM side worth taking is visible. NOT a take.'], '#8b949e', '#8b949e')}
      </div>
      {section('🔒 High-hit favorite stacks (candidates · UNVALIDATED)', '— a heavy favorite that recent FORM confirms, in a −300..−730 price band. These scanned ~85–91% hit + small +ROI IN-SAMPLE, but on tiny n and found by scanning many combos (multiple-comparison risk). Forward-tracked from today — do NOT bet real money until the live sample proves them. The M/W split is below each card.')}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        {card(['st:pf_ghfav', '🔒 GRAYHATE FAV + FORM', 'Take the market FAVORITE when (a) the gray line hates the dog (prices it 2+ pts under market = bait) AND (b) recent form also backs the favorite. Any price. In-sample 76% hit / +2.8% (n122) — the biggest-sample, most believable candidate. Forward-tracked.'], '#3fb950', '#3fb950')}
        {card(['st:pf_ghfav_pr', '🔒 GRAYHATE FAV + FORM · −300/730', 'Same as GRAYHATE FAV + FORM but only in the −300..−730 price window. In-sample 87% hit / +2.1% (n38). The best shot at a high-hit + positive-ROI cell — still unvalidated. Forward-tracked.'], '#3fb950', '#3fb950')}
        {card(['st:pf_c75fav_pr', '🔒 c75 FAV + FORM · −350/730', 'The C-MC c75 pick IS the favorite, recent form confirms it, priced −350..−730. In-sample 88% hit / +2.1% (n25). Unvalidated (small n). Forward-tracked.'], '#58a6ff', '#58a6ff')}
        {card(['st:pf_a10fav_pr', '🔒 ALL-10 FAV + FORM · −350/730', 'All 10 model heads agree on the favorite AND recent form confirms, priced −350..−730. In-sample 88% hit men / 91% hit all-gender, +1–5% (n16–22). The highest-hit candidate but the thinnest sample — two upsets from break-even. Forward-tracked.'], '#58a6ff', '#58a6ff')}
      </div>
      {section('🔀 Fade the 6-4 split (new · watch)', '— when the 10 model heads split exactly 6-4, $25 on the 4-MINORITY side (fade the slim majority). Backtest +80.7% men / +58% all, but n=17 — NOISE, unvalidated. Forward-tracked from today; the weekly checkpoint judges it.')}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        {card(['st:split64_fade', '🔀 FADE 6-4 SPLIT', 'When the 10 heads (A, B, C, gray, D, D-MA, serve-MC, c50, c75, cUTR) split exactly 6-4, $25 on the side only 4 agree on — fading the slim majority. In backtest the 6-majority was wrong ~76% of the time (men 24% hit), so the 4-minority (usually the live dog) won +80.7% on men (13-4) / +58% all. BUT n=17 — noise-level, UNVALIDATED. Forward-tracked from 2026-10-05; do not stake real money until the live sample grows. Men/women split shown below.'], '#d2a8ff', '#d2a8ff')}
      </div>
      {(() => {
        // C-MC VARIANT HEAD-TO-HEAD (2026-10-03, user "track which variant does best over
        // time"): all three anchorings bet the SAME matches, so rank them by live ROI and
        // crown the leader once the sample is meaningful. Winner can replace the displayed c50.
        const MINS = 20
        const rows = [
          ['c50', 'anchor 50% to C · no UTR · VISIBLE', st.mc_c_all],
          ['c75', 'anchor 75% to C', st.mc_c75_all],
          ['cUTR', 'anchor 50% to C + strong UTR de-pad', st.mc_cutr_all],
        ].map(([n, d, l]) => ({ n, d, l: l || {} }))
        const settled = rows.filter(r => r.l.n)
        const ranked = [...settled].sort((a, b) => (b.l.roi_pct || 0) - (a.l.roi_pct || 0))
        const leader = ranked[0]
        const callable = leader && leader.l.n >= MINS
        const need = settled.length ? Math.max(0, MINS - Math.max(...settled.map(r => r.l.n))) : MINS
        return (
          <>
            {section('C-MC variant head-to-head', '— three anchorings, same matches; which Monte-Carlo-on-C is best. Winner can replace the visible line.')}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
              {rows.map(({ n, d, l }) => {
                const isLeader = callable && leader.n === n
                return (
                  <div key={n} className="mono" title={d}
                    style={{ padding: '12px 16px', borderRadius: 8, minWidth: 190,
                      border: `1px solid ${isLeader ? '#58a6ff' : 'var(--line)'}`,
                      background: isLeader ? 'rgba(88,166,255,0.10)' : 'var(--panel)' }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#58a6ff', letterSpacing: '0.03em' }}>
                      {isLeader ? '👑 ' : ''}C-MC · {n}{n === 'c50' ? ' (visible)' : ''}
                    </div>
                    {l.n ? (
                      <>
                        <div style={{ fontSize: 16, fontWeight: 700, marginTop: 4, color: (l.roi_pct || 0) >= 0 ? '#3fb950' : '#f85149' }}>
                          {l.roi_pct > 0 ? '+' : ''}{l.roi_pct}%
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                          {l.wins}-{l.n - l.wins} · {usd(l.profit_usd)}{l.pending ? ` · ${l.pending} pend` : ''}
                        </div>
                        {(l.dog && l.dog.n) || (l.fav && l.fav.n) ? (
                          <div style={{ fontSize: 9, color: 'var(--text-tertiary)', marginTop: 2 }}
                            title="This variant's record split by whether its pick was a market DOG vs FAVORITE.">
                            {l.dog && l.dog.n ? <span style={{ color: l.dog.roi_pct > 3 ? '#3fb950' : l.dog.roi_pct < -3 ? '#f85149' : 'var(--text-tertiary)' }}>🐕 {l.dog.wins}-{l.dog.n - l.dog.wins} {l.dog.roi_pct > 0 ? '+' : ''}{l.dog.roi_pct}%</span> : '🐕 —'}
                            {' · '}
                            {l.fav && l.fav.n ? <span style={{ color: l.fav.roi_pct > 3 ? '#3fb950' : l.fav.roi_pct < -3 ? '#f85149' : 'var(--text-tertiary)' }}>⭐ {l.fav.wins}-{l.fav.n - l.fav.wins} {l.fav.roi_pct > 0 ? '+' : ''}{l.fav.roi_pct}%</span> : '⭐ —'}
                          </div>
                        ) : null}
                      </>
                    ) : (
                      <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>{l.pending ? `${l.pending} pending` : '0 settled'}</div>
                    )}
                    <div style={{ fontSize: 9, color: 'var(--text-tertiary)', marginTop: 3 }}>{d}</div>
                  </div>
                )
              })}
            </div>
            <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 6 }}>
              {callable
                ? `Leader so far: C-MC · ${leader.n} at ${leader.l.roi_pct > 0 ? '+' : ''}${leader.l.roi_pct}% over ${leader.l.n}. Lead holds → it can become the displayed line.`
                : `Too early to call — need ${need} more settled (min ${MINS}). All three track the same games from 2026-10-02; seeded with Shapovalov + Ann Li.`}
            </div>
          </>
        )
      })()}
      {section('★ bet lanes', '— the validated dog cells; the only manual takes the research supports')}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>{STARS.map(x => card(x, '#3fb95066', '#3fb950'))}</div>
      {section('tier ribbons on trial', '— $25 per board tier from 2026-09-30 forward; the ribbon’s own live record')}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>{TIERS.map(x => card(x, '#f5f13b44', '#f5f13b'))}</div>
      {section('red-flagged', '— tracked in public, never taken (matches the red names on the board)')}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>{REDS.map(x => card(x, '#f8514966', '#f85149'))}</div>
      {section('model lanes', '— experiments and controls (incl. C mkt-aware)')}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>{MODELS.map(x => card(x, 'var(--line)', '#58a6ff'))}</div>
    </div>
  )
}

export default function TennisSection() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [view, setView] = useState('board')
  const [query, setQuery] = useState('')
  const [laneRec, setLaneRec] = useState(null)
  // green-only mode (2026-10-02, user ask): hide red/avoid + live-negative signals.
  // Remembered across reloads; default on until live ROIs mature.
  const [greenOnly, setGreenOnly] = useState(() => {
    try { return localStorage.getItem('te_green_only') !== '0' } catch { return true }
  })
  const toggleGreen = () => setGreenOnly(v => {
    const nv = !v
    try { localStorage.setItem('te_green_only', nv ? '1' : '0') } catch { /* ignore */ }
    return nv
  })
  // C-MC variants reveal (2026-10-03, user "button that shows the invisible monte carlos
  // for C"): off by default; when on, each card's Model C block also shows the two hidden
  // anchor variants (c75, cUTR) beside the visible c50 line.
  const [showCMC, setShowCMC] = useState(() => {
    try { return localStorage.getItem('te_show_cmc') === '1' } catch { return false }
  })
  const toggleCMC = () => setShowCMC(v => {
    const nv = !v
    try { localStorage.setItem('te_show_cmc', nv ? '1' : '0') } catch { /* ignore */ }
    return nv
  })
  useEffect(() => {
    fetch('/api/tennis/track-record').then(r => r.json()).then(d => setLaneRec(d.ab25 || null)).catch(() => {})
  }, [])

  useEffect(() => {
    fetchTennis()
    // Manual refresh only (2026-09-28, user ask): the 60s auto-poll remounted the list into
    // its loading state and threw the scroll position back to the top mid-read. The slate
    // now loads once and only reloads from the button below.
  }, [])

  async function fetchTennis() {
    setLoading(true)
    setError(null)
    // SILENT RETRY (2026-10-07): the board loads once by design (no auto-poll), so a page
    // opened during a server restart/deploy used to stick on an empty board until a manual
    // reload. Retry the one-shot fetch a few times with backoff before giving up.
    let lastErr = null
    for (let attempt = 0; attempt < 4; attempt++) {
      try {
        if (attempt > 0) await new Promise(r => setTimeout(r, 4000 * attempt))
        const res = await fetch('/api/tennis/today')
        if (!res.ok) throw new Error(`API returned ${res.status}`)
        setData(await res.json())
        setLoading(false)
        return
      } catch (e) {
        lastErr = e
      }
    }
    setError(lastErr ? lastErr.message : 'load failed')
    setLoading(false)
  }

  const all = data?.matches ?? []
  // finished/cancelled matches drop off the board (2026-09-28, user ask); their record
  // lives in the trackers and the A/B $25 panel instead.
  const q = query.trim().toLowerCase()
  // feed-cancelled matches stay VISIBLE until 3h past their listed start (2026-09-29 user
  // ask, Kudermetova case: feeds sometimes mark matches cancelled then reinstate near start;
  // hide only once the scheduled time is long gone). Completed always hides.
  const staleCancel = m => m.status === 'cancelled'
    && (!m.start_time_utc || Date.parse(m.start_time_utc) < Date.now() - 3 * 3600 * 1000)
  const matches = all.filter(m => m.status !== 'completed' && !staleCancel(m))
    .filter(m => !q || [m.player_1, m.player_2, m.tournament, m.league]
      .some(s => s && String(s).toLowerCase().includes(q)))
  // A match earns a full card if ANY model covers it (2026-09-28, user "why don't you have
  // every single bet"): the old tour model only knows ATP/WTA mains, but Model A/B cover the
  // whole 1,760-player pool. Headline prob falls back main model -> A -> B; only matches
  // where a player has NO TennisRatio page at all stay in the bottom bucket.
  const headlineProb = m => m.prediction?.player_1_win_prob ?? m.model_a?.p1_prob ?? m.model_b?.p1_prob ?? null
  // A+B agreement floats to the top (2026-09-28, user ask) -- the agree lane's matches first,
  // strongest agreement (combined confidence) leading; disagreements and single-model cards below.
  const abAgree = m => !!(m.model_a && m.model_b && ((m.model_a.p1_prob >= 0.5) === (m.model_b.p1_prob >= 0.5)))
  const withPrediction = matches.filter(m => headlineProb(m) != null)
  const withoutPrediction = matches.filter(m => headlineProb(m) == null)
  const isLive = m => m.status === 'live'
  // Pure start-time order (2026-10-03, user "just put the games that start first in order"):
  // soonest first, latest last. Live/earlier games float up on their own (they started
  // before any upcoming game); matches with no known time sort to the bottom.
  const sorted = useMemo(
    () => [...withPrediction].sort((a, b) => {
      const ta = a.start_time_utc || '', tb = b.start_time_utc || ''
      if (!ta && !tb) return 0
      if (!ta) return 1
      if (!tb) return -1
      return ta.localeCompare(tb)
    }),
    [withPrediction]
  )

  return (
    <div>
      <div style={{
        marginTop: 20, padding: '10px 16px', borderRadius: 6,
        background: 'rgba(140,140,150,0.06)', border: '1px solid var(--line)',
        fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.5,
      }}>
        <style>{`@keyframes livePulse { 0%,100% { opacity: 1 } 50% { opacity: 0.35 } }`}</style>
        Cards are headlined by TENNIS MODEL A (full history + surface stats + opponent quality + H2H,
        1,760-player pool), with MODEL B (last-10-on-court, rank-adjusted wins) beside it — the original
        tour model was retired 2026-09-28 (it never beat the market). Both A and B validated as
        display-only too: the market's number beat theirs on 110k matches, so treat every model % as a
        second opinion. The price scanner below remains the only tennis signal forward-tested as a bet;
        the A vs B $25 tab tracks what the models are worth in dollars.
      </div>

      {/* Scanner first (user call 9/21, after it passed its 75-flag checkpoint): the flags —
          soft ponds foremost — are the tab's one validated signal; the model panels follow. */}
      <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'center' }}>
        <button onClick={fetchTennis} disabled={loading} className="mono" style={{
          padding: '5px 14px', borderRadius: 14, fontSize: 11, cursor: 'pointer',
          border: '1px solid var(--line)', background: 'transparent', color: 'var(--text-secondary)',
        }} title="Reload the slate (auto-refresh is off so the page never jumps while you read)">
          {loading ? 'reloading…' : '↻ reload'}
        </button>
        <input value={query} onChange={e => setQuery(e.target.value)} placeholder="search player / tournament…"
          className="mono" style={{ padding: '5px 12px', borderRadius: 14, fontSize: 11, width: 210,
            border: '1px solid var(--line)', background: 'transparent', color: 'var(--text-primary)', outline: 'none' }} />
        {query ? <button onClick={() => setQuery('')} className="mono" style={{ padding: '5px 10px', borderRadius: 14, fontSize: 11, cursor: 'pointer', border: '1px solid var(--line)', background: 'transparent', color: 'var(--text-tertiary)' }}>✕</button> : null}
        {[['board', 'board'], ['best', '🏆 Best'], ['prices', '💰 Prices'], ['tabpl', '📊 Tab P/L'], ['sets', '🎲 Sets'], ['picks', '⭐ Picks'], ['itf', 'ITF (M+W)'], ['ab25', 'A vs B — $25'], ['splits', '🐕/⭐ Splits'], ['history', 'results history'], ['modelx', 'Model X']].map(([k, label]) => (
          <button key={k} onClick={() => setView(k)} className="mono" style={{
            padding: '5px 14px', borderRadius: 14, fontSize: 11, cursor: 'pointer',
            border: `1px solid ${view === k ? '#e3b341' : 'var(--line)'}`,
            background: view === k ? 'rgba(227,179,65,0.12)' : 'transparent',
            color: view === k ? '#e3b341' : 'var(--text-secondary)', fontWeight: view === k ? 700 : 400,
          }}>{label}</button>
        ))}
        <button onClick={toggleGreen} className="mono"
          title={greenOnly ? 'GREEN-ONLY: red/avoid signals and live-negative lanes are hidden. Click to show the full board.' : 'FULL BOARD: all signals including red/avoid. Click to hide red and show green-only.'}
          style={{
            padding: '5px 14px', borderRadius: 14, fontSize: 11, cursor: 'pointer', marginLeft: 'auto',
            border: `1px solid ${greenOnly ? '#3fb950' : 'var(--line)'}`,
            background: greenOnly ? 'rgba(63,185,80,0.14)' : 'transparent',
            color: greenOnly ? '#3fb950' : 'var(--text-secondary)', fontWeight: 700,
          }}>{greenOnly ? '● GREEN-ONLY' : '○ full board'}</button>
        <button onClick={toggleCMC} className="mono"
          title={showCMC ? 'Hiding the two experimental C-MC anchor variants (c75, cUTR). Click to show them on each card.' : 'Show the two invisible C-MC variants (c75 = harder Model-C pull, cUTR = stronger court-UTR de-padding) beside the visible c50 line on each card. Tracking-only experiment.'}
          style={{
            padding: '5px 14px', borderRadius: 14, fontSize: 11, cursor: 'pointer',
            border: `1px solid ${showCMC ? '#58a6ff' : 'var(--line)'}`,
            background: showCMC ? 'rgba(88,166,255,0.14)' : 'transparent',
            color: showCMC ? '#58a6ff' : 'var(--text-secondary)', fontWeight: 700,
          }}>{showCMC ? '● C-MC variants' : '○ C-MC variants'}</button>
      </div>

      {view === 'best' ? <BestPanel query={query} laneRec={laneRec} /> : view === 'prices' ? <BestPanel query={query} laneRec={laneRec} priceOnly /> : view === 'tabpl' ? <TabProfitPanel /> : view === 'sets' ? <SetScanPanel /> : view === 'picks' ? <PicksPanel query={query} /> : view === 'itf' ? <ItfPanel query={query} laneRec={laneRec} greenOnly={greenOnly} showCMC={showCMC} /> : view === 'splits' ? <SplitsPanel /> : view === 'history' ? <HistoryPanel query={query} greenOnly={greenOnly} /> : view === 'ab25' ? <Ab25Panel /> : view === 'modelx' ? <ModelXPanel /> : (<>
      <PriceEdgeScanner scan={data?.price_scan} />

      {error && (
        <div style={{
          background: 'rgba(255,92,92,0.08)', border: '1px solid var(--edge-neg)',
          borderRadius: 8, padding: '14px 18px', margin: '20px 0', color: 'var(--edge-neg)',
          fontSize: 14, fontFamily: 'var(--font-mono)',
        }}>
          Couldn't reach /api/tennis/today — is the backend running? ({error})
        </div>
      )}

      {loading && !data && (
        <div style={{ color: 'var(--text-secondary)', padding: '60px 0', textAlign: 'center', fontFamily: 'var(--font-mono)' }}>
          loading today's matches…
        </div>
      )}

      {!loading && !error && matches.length === 0 && (
        <div style={{ color: 'var(--text-secondary)', padding: '60px 0', textAlign: 'center' }}>
          No ATP/WTA singles matches found for today.
        </div>
      )}

      {!error && matches.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 16 }}>
          {sorted.map((m, i) => (
            <MatchCard key={m.fixture_id} match={m} animDelay={Math.min(i * 0.04, 0.3)} laneRec={laneRec} greenOnly={greenOnly} showCMC={showCMC} />
          ))}
          {withoutPrediction.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>
                no prediction available ({withoutPrediction.length})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {withoutPrediction.map(m => <NoPredictionRow key={m.fixture_id} match={m} />)}
              </div>
            </div>
          )}
        </div>
      )}
      </>)}
    </div>
  )
}

function ItfPanel({ query, laneRec, greenOnly, showCMC }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    const go = () => fetch('/api/tennis/itf').then(r => r.json()).then(setData).catch(e => setErr(String(e)))
    go()
    const id = setInterval(go, 60000)  // poll every 60s so live games surface fast
    return () => clearInterval(id)
  }, [])
  if (err) return <div className="mono" style={{ color: 'var(--edge-neg)', padding: 20 }}>Couldn't load ITF ({err})</div>
  if (!data) return <div className="mono" style={{ color: 'var(--text-secondary)', padding: 40, textAlign: 'center' }}>loading ITF matches… (first open can take ~30s — models run on every card)</div>
  const q = query.trim().toLowerCase()
  const hasModel = m => m.model_c || m.model_i
  const filt = (data.matches || []).filter(m => hasModel(m) && (!q || (m.player_1 + ' ' + m.player_2 + ' ' + (m.tournament || '')).toLowerCase().includes(q)))
  // LIVE games get their own section at the very top (2026-10-02, user ask); the M/W
  // sections below show only not-yet-live matches, best picks first then sooner→later.
  const isLiveM = m => m.status === 'live'
  const byPick = (a, b) => (pickScore(b) - pickScore(a)) || (a.start_time_utc || '').localeCompare(b.start_time_utc || '')
  const liveAll = filt.filter(isLiveM).sort(byPick)
  const men = filt.filter(m => m.league === 'itf_men' && !isLiveM(m)).sort(byPick)
  const women = filt.filter(m => m.league === 'itf_women' && !isLiveM(m)).sort(byPick)
  // priced games with no model (players not in pool) — shown as compact rows so every
  // game appears, not just the modeled ones (2026-10-02, user "missing a bunch").
  const unmodeled = (data.matches || []).filter(m => !hasModel(m) && m.live_odds
    && (!q || (m.player_1 + ' ' + m.player_2 + ' ' + (m.tournament || '')).toLowerCase().includes(q)))
    .sort((a, b) => (a.start_time_utc || '').localeCompare(b.start_time_utc || ''))
  const section = (title, arr, color) => {
    const nLive = arr.filter(isLiveM).length
    return (
    <div style={{ marginTop: 18 }}>
      <div className="mono" style={{ fontSize: 12, fontWeight: 700, color, borderBottom: `1px solid ${color}44`, paddingBottom: 4, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span>{title} <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>· {arr.length}</span></span>
        {nLive ? (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10, color: '#f85149', fontWeight: 700 }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#f85149', boxShadow: '0 0 6px #f85149', animation: 'livePulse 1.4s ease-in-out infinite' }} />
            {nLive} LIVE
          </span>
        ) : null}
      </div>
      {arr.length ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 14 }}>
          {arr.map((m, i) => <MatchCard key={m.fixture_id} match={m} animDelay={Math.min(i * 0.03, 0.3)} laneRec={laneRec} greenOnly={greenOnly} showCMC={showCMC} />)}
        </div>
      ) : <div className="mono" style={{ color: 'var(--text-tertiary)', padding: 14, fontSize: 11 }}>none{q ? ' match that search' : ''}.</div>}
    </div>
    )
  }
  return (
    <div style={{ marginTop: 16 }}>
      <div className="mono" style={{ padding: '10px 16px', borderRadius: 6, border: '1px solid var(--line)', fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.5 }}>
        ITF circuit (the tier below Challengers), men and women — the SAME A/B/C/D + court-UTR + Monte Carlo models as the main board. Fixtures/odds via OpticOdds + Polymarket (the venues you can bet); live games surface within ~1 min. Games where a player isn't in the stat pool show as priced rows at the bottom (no model).
      </div>
      {liveAll.length ? section("🔴 LIVE NOW (M+W)", liveAll, '#f85149') : null}
      {section("ITF MEN", men, '#5AC8C8')}
      {section("ITF WOMEN", women, '#E08CC0')}
      {unmodeled.length ? (
        <div style={{ marginTop: 18 }}>
          <div className="mono" style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-tertiary)', borderBottom: '1px solid var(--line)', paddingBottom: 4 }}>
            PRICED · NO MODEL <span style={{ fontWeight: 400 }}>· {unmodeled.length} (players not in our stat pool)</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 10 }}>
            {unmodeled.map((m, i) => {
              const od = m.live_odds || {}
              const o = v => v == null ? '' : (Number(v) > 0 ? `+${v}` : `${v}`)
              return (
                <div key={m.fixture_id || i} className="mono" style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', borderRadius: 6, border: '1px solid var(--line)', fontSize: 11, flexWrap: 'wrap' }}>
                  <span style={{ minWidth: 60, color: m.league === 'itf_women' ? '#E08CC0' : '#5AC8C8', fontWeight: 700, fontSize: 9 }}>{(m.league || '').replace('itf_', 'ITF ').toUpperCase()}</span>
                  {fmtPT(m.start_time_utc) ? <span style={{ color: 'var(--text-secondary)', fontWeight: 700, fontSize: 10 }}>🕐 {fmtPT(m.start_time_utc)}</span> : null}
                  <span style={{ flex: 1, minWidth: 220 }}>{m.player_1} <span style={{ color: 'var(--text-tertiary)' }}>{o(od.player_1)}</span> <span style={{ color: 'var(--text-tertiary)' }}>vs</span> {m.player_2} <span style={{ color: 'var(--text-tertiary)' }}>{o(od.player_2)}</span></span>
                  <span style={{ color: 'var(--text-tertiary)', fontSize: 9 }}>{m.tournament || ''}{od.bookmaker ? ` · ${od.bookmaker}` : ''}</span>
                </div>
              )
            })}
          </div>
        </div>
      ) : null}
    </div>
  )
}

function PicksPanel({ query }) {
  // Daily pick sheet (2026-10-05, user ask): every match where the C-MC (c50) and c75
  // AGREE and their side is OVER the market price, split dogs vs favorites, biggest edge
  // first -- so the full day's actionable set is one glance, no re-asking.
  const [data, setData] = useState({ today: null, itf: null })
  const [err, setErr] = useState(null)
  const [mode, setMode] = useState('time')   // 'time' = by date/start-time, 'edge' = biggest edge first
  useEffect(() => {
    const go = () => {
      Promise.all([
        fetch('/api/tennis/today').then(r => r.json()).catch(() => ({ matches: [] })),
        fetch('/api/tennis/itf').then(r => r.json()).catch(() => ({ matches: [] })),
      ]).then(([t, i]) => setData({ today: t, itf: i })).catch(e => setErr(String(e)))
    }
    go(); const id = setInterval(go, 120000); return () => clearInterval(id)
  }, [])
  if (err) return <div className="mono" style={{ color: 'var(--edge-neg)', padding: 20 }}>Couldn't load picks ({err})</div>
  if (!data.today) return <div className="mono" style={{ color: 'var(--text-secondary)', padding: 40, textAlign: 'center' }}>loading picks…</div>
  const q = query.trim().toLowerCase()
  const ms = [...(data.today.matches || []), ...((data.itf || {}).matches || [])]
  const seen = new Set(); const dogs = []; const favs = []; const nomkt = []
  for (const m of ms) {
    if (!['unplayed', 'live'].includes(m.status)) continue
    const c = m.model_c || {}; const mc = c.mc || {}
    const c50 = mc.p1_pct, c75 = c.mc_c75_p1, mk = c.market_p1
    if (c50 == null || c75 == null) continue   // need a model pick (c50 + c75)
    const s50 = c50 >= 50, s75 = c75 >= 0.5
    if (s50 !== s75) continue                 // c-MC + c75 must agree
    const key = m.fixture_id || (m.player_1 + m.player_2)
    if (seen.has(key)) continue; seen.add(key)
    const pick = s50 ? m.player_1 : m.player_2
    const opp = s50 ? m.player_2 : m.player_1
    if (q && !(pick + ' ' + opp + ' ' + (m.tournament || '')).toLowerCase().includes(q)) continue
    const dmx = m.model_d || {}
    const thin = !!((dmx.sutr_p1 && dmx.sutr_p1.n != null && dmx.sutr_p1.n < 12)
      || (dmx.sutr_p2 && dmx.sutr_p2.n != null && dmx.sutr_p2.n < 12))
    const base = { pick, opp, c50: Math.round((s50 ? c50 : 100 - c50)), c75: Math.round((s50 ? c75 : 1 - c75) * 100), lg: m.league, t: m.start_time_utc, live: m.status === 'live', thin }
    if (mk == null) {                          // model has a pick but we can't trust a market
      nomkt.push({ ...base, od: null, mk: null, edge: null, dog: null, nomarket: true })
      continue
    }
    const c50s = s50 ? c50 / 100 : 1 - c50 / 100
    const c75s = s50 ? c75 : 1 - c75
    const mks = s50 ? mk : 1 - mk
    if (c50s <= mks) continue                 // must be OVER the market
    const od = m.live_odds ? (s50 ? m.live_odds.player_1 : m.live_odds.player_2) : null
    // LONG DOGS DROPPED here too (2026-10-08, user — same rule as the Best tab): a dog
    // pick priced over +250 doesn't make the sheet (+250..+400 went 1-6 in replay; the
    // Picks-sheet half of that band went 0-3). Lanes keep tracking them in the background.
    if (mks < 0.5 && od != null && od > 250) continue
    const row = { ...base, od, mk: Math.round(mks * 100), edge: Math.round(100 * (c50s - mks)), dog: mks < 0.5 }
    ;(mks < 0.5 ? dogs : favs).push(row)
  }
  dogs.sort((a, b) => b.edge - a.edge); favs.sort((a, b) => b.edge - a.edge)
  const all = [...dogs, ...favs, ...nomkt]
  const odfmt = v => v == null ? '' : (v > 0 ? `+${v}` : `${v}`)
  const hdr = () => (
    <div className="mono" style={{ display: 'flex', fontSize: 9, color: 'var(--text-tertiary)', padding: '0 8px 3px', borderBottom: '1px solid var(--line)' }}>
      <span style={{ flex: 1 }}>PICK (vs opp)</span><span style={{ width: 54 }}>odds</span><span style={{ width: 42 }}>c50</span><span style={{ width: 42 }}>c75</span><span style={{ width: 42 }}>mkt</span><span style={{ width: 46 }}>edge</span><span style={{ width: 44 }}>time</span>
    </div>
  )
  const rowEl = (r, i) => {
    // no-market rows: red; half-yellow/half-red when a player's rating is thin (stats may
    // be inflated). Keyed to match the board badge so the Picks tab reads the same.
    const bg = r.nomarket
      ? (r.thin ? 'linear-gradient(90deg, rgba(227,179,65,0.26) 0 50%, rgba(248,81,73,0.26) 50% 100%)' : 'rgba(248,81,73,0.10)')
      : undefined
    return (
    <div key={i} className="mono" title={r.nomarket ? ('Models like this pick, but no reliable market price (book line corrupt/missing) — edge UNVERIFIED, check the real price yourself.' + (r.thin ? ' ALSO: a player’s court-UTR is built on <12 matches, so the read may be inflated (thin/weak-schedule sample).' : '')) : undefined}
      style={{ display: 'flex', fontSize: 11, padding: '4px 8px', borderBottom: '1px solid rgba(255,255,255,0.03)', alignItems: 'center', background: bg }}>
      <span style={{ flex: 1 }}>
        {r.live ? <span style={{ color: '#f85149', fontSize: 8, marginRight: 4 }}>● LIVE</span> : null}
        <span style={{ marginRight: 4 }}>{r.nomarket ? (r.thin ? '⚠🟡' : '⚠') : r.dog ? '🐕' : '⭐'}</span>
        <span style={{ color: r.nomarket && !r.thin ? '#f85149' : 'var(--text-primary)', fontWeight: 700 }}>{r.pick}</span>
        <span style={{ color: 'var(--text-tertiary)' }}> vs {r.opp.split(' ').slice(-1)[0]}</span>
        <span style={{ color: 'var(--text-tertiary)', fontSize: 9 }}> · {String(r.lg || '').toUpperCase()}</span>
      </span>
      <span style={{ width: 54, color: r.od > 0 ? '#3fb950' : 'var(--text-secondary)' }}>{odfmt(r.od)}</span>
      <span style={{ width: 42 }}>{r.c50}%</span>
      <span style={{ width: 42 }}>{r.c75}%</span>
      <span style={{ width: 42, color: 'var(--text-tertiary)' }}>{r.nomarket ? '—' : `${r.mk}%`}</span>
      <span style={{ width: 46, color: r.nomarket ? '#f85149' : '#3fb950', fontWeight: 700 }}>{r.nomarket ? (r.thin ? 'no mkt+thin' : 'no mkt') : `+${r.edge}`}</span>
      <span style={{ width: 44, color: 'var(--text-tertiary)', fontSize: 9 }}>{fmtPT(r.t) || ''}</span>
    </div>
    )
  }
  const tbl = (rows, title, color, note) => (
    <div style={{ marginTop: 14 }}>
      <div className="mono" style={{ fontSize: 11, fontWeight: 700, color, letterSpacing: '0.04em' }}>{title} <span style={{ fontWeight: 400, color: 'var(--text-tertiary)' }}>— {rows.length} · {note}</span></div>
      {rows.length === 0 ? <div className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)', padding: '8px 0' }}>none</div>
        : <div style={{ marginTop: 6 }}>{hdr()}{rows.map(rowEl)}</div>}
    </div>
  )
  // group by local date for the time view
  const dayKey = t => {
    if (!t) return 'TBD'
    const d = new Date(t); if (isNaN(d)) return 'TBD'
    return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })
  }
  const byDay = {}
  for (const r of [...all].sort((a, b) => (a.t || '').localeCompare(b.t || ''))) {
    (byDay[dayKey(r.t)] = byDay[dayKey(r.t)] || []).push(r)
  }
  const dayOrder = Object.keys(byDay).sort((a, b) => {
    const ta = (byDay[a][0] || {}).t || '', tb = (byDay[b][0] || {}).t || ''
    return (a === 'TBD') - (b === 'TBD') || ta.localeCompare(tb)
  })
  const btn = (k, label) => (
    <button onClick={() => setMode(k)} className="mono" style={{ padding: '3px 12px', borderRadius: 12, fontSize: 10, cursor: 'pointer', marginLeft: 6, border: `1px solid ${mode === k ? '#3fb950' : 'var(--line)'}`, background: mode === k ? 'rgba(63,185,80,0.14)' : 'transparent', color: mode === k ? '#3fb950' : 'var(--text-secondary)', fontWeight: 700 }}>{label}</button>
  )
  return (
    <div style={{ marginTop: 16 }}>
      <div className="mono" style={{ padding: '10px 16px', borderRadius: 6, border: '1px solid var(--line)', fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.5, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <span><b style={{ color: '#3fb950' }}>DAILY PICKS</b> — C-MC (c50) & c75 agree AND over the market. 🐕 dog = plus-money value (the real EV); ⭐ fav = model over the price but chalk. Edge = c50 − market %. Auto-refresh 2 min; search filters.</span>
        <span style={{ whiteSpace: 'nowrap' }}>{btn('time', '🕐 by date/time')}{btn('edge', '📈 by edge')}</span>
      </div>
      {mode === 'edge' ? (<>
        {tbl(dogs, '🐕 DOG PICKS', '#3fb950', 'plus-money value — the real EV')}
        {tbl(favs, '⭐ FAVORITE PICKS', '#e3b341', 'model over the price, but chalk — thin edge')}
        {tbl(nomkt, '⚠ NO RELIABLE MARKET', '#f85149', 'models like the pick but the book line was corrupt/missing — edge UNVERIFIED, check the real price')}
      </>) : (
        all.length === 0 ? <div className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)', padding: 20 }}>No picks right now.</div>
        : dayOrder.map(d => (
          <div key={d} style={{ marginTop: 14 }}>
            <div className="mono" style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', borderBottom: '1px solid var(--line)', paddingBottom: 4 }}>
              {d} <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>· {byDay[d].length} picks ({byDay[d].filter(r => r.dog).length}🐕 / {byDay[d].filter(r => !r.dog && !r.nomarket).length}⭐{byDay[d].filter(r => r.nomarket).length ? ` / ${byDay[d].filter(r => r.nomarket).length}⚠` : ''})</span>
            </div>
            <div style={{ marginTop: 6 }}>{hdr()}{byDay[d].map(rowEl)}</div>
          </div>
        ))
      )}
    </div>
  )
}

// Gate for the Best tab (2026-10-05, user: "only the highest hit rate picks ... highest
// roi while having the highest hit rate"). A signal must clear ALL three on THIS match's
// gender record in the frozen live log to qualify a game. Tunable in one place.
const BEST_N = 20, BEST_HIT = 65, BEST_ROI = 4
const BEST_N_SPLIT = 12   // smaller floor for the (gender×dog/fav) cells, which carry less n
// Sweet-spot PRICES where a Best pick's edge actually pays (2026-10-05, from the full-history
// price map): MEN +100..+250 (dog value, +46%) or −600..−300 (short-chalk pocket, +8%);
// WOMEN +150..+250 only. The −110..−300 band and extreme chalk (< −600) lose, so excluded.
// A Best pick inside one of these windows historically ran +24% ROI vs +6.7% for all Best.
// ...plus a MEN-ONLY exception (2026-10-05): when ALL 10 models agree, the −150..−300 band
// flips profitable (+12.8%, 21-6, driven by −200/−300 at +16.7%) even though it loses for
// every other signal and for women's ALL-10 (−39%). So pass isAll10 to open that window.
function inSweetPrice(od, gen, isAll10) {
  if (od == null) return false
  // WOMEN marked too (2026-10-08, user "mark the women ones too"): the +100..+250 DOG
  // band only — it's the one women's band with live evidence (banded 🤝 DOG W +55%,
  // price_dog_w lane now tracks it). Women chalk / ALL-10 bands stay unmarked (no edge:
  // women's ALL-10 ran −39%).
  if (gen === 'w') return od >= 100 && od <= 250
  return (od >= 100 && od <= 250) || (od >= -600 && od <= -300)
    || (!!isAll10 && od >= -300 && od <= -140)   // −140..−300 per user (−200/−300 is the strong half)
}
function priceBand(od, gen, isAll10) {
  if (od == null) return null
  if (gen === 'w') return (od >= 100 && od <= 250) ? 'dog' : null   // women: dog band only
  if (od >= 100 && od <= 250) return 'dog'
  if (od >= -600 && od <= -300) return 'chalk'
  if (isAll10 && od >= -300 && od <= -200) return 'all10strong'
  if (isAll10 && od > -200 && od <= -140) return 'all10'
  return null
}
// Color-coded price tiers for the 💰 Prices tab (2026-10-05, user). Each cites a live
// auto-updating lane record (study[lane]). col = text/name, bd = border, bg = row tint.
const BAND = {
  all10strong: { name: 'ALL-10 −200/300', col: '#2ea043', bd: '#1a7f37', bg: 'rgba(26,127,55,0.16)', glow: '#2ea04399', lane: 'all10_200_300_m', icon: '💎', tip: 'All 10 models agree AND the pick is priced −200 to −300 — the prime ALL-10 cell.' },
  dog: { name: 'dog +100/250', col: '#58a6ff', bd: '#1f6feb', bg: 'rgba(31,111,235,0.16)', glow: '#1f6feb99', lane: 'price_dog_m', icon: '🔵', tip: 'Best pick on a plus-money dog, +100 to +250 — the highest-ROI window (but thinner).' },
  chalk: { name: 'chalk −300/600', col: '#a371f7', bd: '#8957e5', bg: 'rgba(137,87,229,0.16)', glow: '#8957e599', lane: 'price_chalk_m', icon: '🟣', tip: 'Best pick on a short favorite, −300 to −600 — the most reliable/biggest-sample window.' },
  all10: { name: 'ALL-10 −140/200', col: '#f5f13b', bd: '#caa700', bg: 'rgba(245,241,59,0.10)', glow: '#f5f13b66', lane: 'all10_140_200_m', icon: '🟡', tip: 'All 10 agree at −140 to −200 — the thin/weak half of the ALL-10 band; smallest edge.' },
}
// Do all 10 model heads agree on one side? (used for the ALL-10 price exception.)
function isAll10Agree(s) {
  if (!s) return false
  const a = [s.aP, s.bP, s.c1, s.g1, s.dP, s.dmaP, s.mcdS, s.mcS, s.c75, s.cuS]
  return a.every(x => x != null) && a.every(x => x === a[0])
}
// Elite signal predicates -- each recomputes a lane's membership from a match's model
// outputs (same conditions as the board's signal strip) and returns the pick side as a
// p1-boolean, or null if the game isn't in that lane. The gender-split live record under
// stx[key][m|w] is what actually gates it, so the list self-maintains as the log grows.
const BEST_SIGNALS = [
  // c75 SPLIT BY SIDE (2026-10-06, user): the c75 edge is ALL in the dogs; plain c75
  // favorites lose (−6.7%), so they no longer qualify via c75. The ONE +ROI c75 favorite is
  // the one recent form DISAGREES with (fade the form) — tracked as c75fav_formfade.
  { key: 'mc_c75_dog', label: 'C-MC c75 DOG', icon: '⚄', fire: s => (s.c75 != null && s.c75 === s.dog1) ? s.c75 : null },
  // c75fav_formfade is WATCH-ONLY (2026-10-06, user "watch the other positive roi signals"):
  // men −5.2% forward, women +7.4% but only n14 — tracked as a lane on Splits/$25, not a Best
  // mark. Re-add here if its forward sample firms up.
  // MC-GREEN (2026-10-06, user "mark the women's mc_green"): a plain gray pick (not gold/
  // hate/passfav) that the Monte Carlo agrees with. Only +ROI cell is WOMEN favorites
  // (+20%); the side-aware gate surfaces it there and nowhere else, so it's women-only in
  // practice. Bets the gray side.
  { key: 'mc_green', label: 'MC-GREEN', icon: '🟢', fire: s => {
      // uses the D-serve MC (mcdS), matching the backend mc_green lane exactly (2026-10-07
      // fix — was firing on the c50 MC, which the lane doesn't measure)
      if (s.mcdS == null || s.g1 == null || s.c1 == null) return null
      const star0 = (s.c1 === s.g1 && s.g1 === s.dog1)
      const passfav = (s.aP !== s.c1 && s.bP !== s.c1 && s.g1 === s.c1 && s.c1 !== s.dog1)
      return (!star0 && !s.hate && !passfav && s.mcdS === s.g1) ? s.g1 : null
    } },
  { key: 'mcc_c75_agree', label: 'c50+c75 agree', icon: '⚄', fire: s => (s.mcS != null && s.c75 != null && s.mcS === s.c75) ? s.c75 : null },
  // ⚄⚄ ALL-4 MCs ON THE DOG (2026-10-08, user: 'a +100..+250 dog like Aliona should
  // have been on the best tab over Oliynykova' — promoted on the measured cell:
  // banded 15-15 +17.3%, outside the band 0-7). Band enforced odds-side in BestPanel.
  { key: 'mc4_dog_band', label: '4-MC DOG', icon: '⚄', fire: s => (s.mcdS != null && s.mcS != null && s.c75 != null && s.cuS != null && s.mcdS === s.mcS && s.mcS === s.c75 && s.c75 === s.cuS && s.mcS === s.dog1) ? s.mcS : null },
  { key: 'dma_edge2', label: 'D-MA 2pt', icon: '📈', fire: s => s.dmaEdge ? s.dmaP : null },
  { key: 'all10_agree', label: 'ALL-10', icon: '✅', fire: s => { const a = [s.aP, s.bP, s.c1, s.g1, s.dP, s.dmaP, s.mcdS, s.mcS, s.c75, s.cuS]; return (a.every(x => x != null) && a.every(x => x === a[0])) ? a[0] : null } },
  { key: 'mc_4of4', label: 'MC 4/4 slip', icon: '⚄', fire: s => (s.aP != null && s.bP != null && s.dP != null && s.mcS != null && s.aP === s.bP && s.bP === s.c1 && s.c1 === s.dP && s.mcS === s.c1) ? s.c1 : null },
  { key: 'cvg_gray', label: 'FIGHT gray-side', icon: '⚔', fire: s => (s.c1 !== s.g1) ? s.g1 : null },
  { key: 'goldfav_d5', label: 'FADE-GOLD 5pt+', icon: '🥇', fire: s => ((s.mdog - s.gdog) >= 0.05) ? !s.dog1 : null },
  { key: 'grayhate_fav', label: 'FADE-GOLD fav', icon: '🥇', fire: s => s.hate ? !s.dog1 : null },
  { key: 'fade_a_fav', label: 'FADE-A fav', icon: '★', fire: s => (s.aP != null && s.bP != null && s.aP !== s.bP && s.bP === s.c1 && s.bP !== s.dog1) ? s.bP : null },
  { key: 'fade_a', label: 'FADE-A', icon: '★', fire: s => (s.aP != null && s.bP != null && s.aP !== s.bP && s.bP === s.c1) ? s.bP : null },
  { key: 'c_alone_gray', label: 'C-ALONE+GRAY', icon: '🔵', fire: s => (s.aP != null && s.bP != null && s.aP !== s.c1 && s.bP !== s.c1 && s.g1 === s.c1) ? s.c1 : null },
  { key: 'gold_names', label: 'GOLD NAME', icon: '🥇', fire: s => (s.c1 === s.g1 && s.g1 === s.dog1) ? s.c1 : (s.hate ? !s.dog1 : null) },
]
// Signal FAMILIES (2026-10-06, user: a ★2 of two correlated c75 signals isn't 2 reads). The
// stack count = distinct families, so ★N only rises when genuinely DIFFERENT logic agrees.
// c50+c75 and c75-dog are one family ('mc'); gold/grayhate/gold-names are one ('gold'); etc.
const SIG_FAM = {
  mc_c75_dog: 'mc', mcc_c75_agree: 'mc', mc4_dog_band: 'mc', mc4ovr_fav_band: 'mc', fight_mc4_dog: 'mc',
  mc_4of4: 'consensus', all10_agree: 'consensus', all10_price_m: 'consensus',
  dma_edge2: 'dma', cvg_gray: 'gray', mc_green: 'gray',
  goldfav_d5: 'gold', grayhate_fav: 'gold', gold_names: 'gold',
  c_alone_gray: 'calone', fade_a: 'fadea', fade_a_fav: 'fadea', cr5_coll_leanfav: 'collision',
}
const famOf = k => SIG_FAM[k] || k
function bestSig(m) {
  const c = m.model_c
  if (!c || c.p1_prob == null || c.market_aware_p1 == null || c.market_p1 == null) return null
  const c1 = c.p1_prob >= 0.5, g1 = c.market_aware_p1 >= 0.5, dog1 = c.market_p1 < 0.5
  const mc = c.mc, a = m.model_a, b = m.model_b, d = m.model_d
  const b05 = (o, f) => (o && o[f] != null) ? o[f] >= 0.5 : null
  const mdog = dog1 ? c.market_p1 : 1 - c.market_p1
  const gdog = dog1 ? c.market_aware_p1 : 1 - c.market_aware_p1
  let dmaEdge = false, dmaP = null
  if (d && d.market_aware_p1 != null) {
    dmaP = d.market_aware_p1 >= 0.5
    const ds = dmaP ? d.market_aware_p1 : 1 - d.market_aware_p1
    const mk = dmaP ? c.market_p1 : 1 - c.market_p1
    dmaEdge = (ds - mk) >= 0.02
  }
  const pf = m.pure_form
  return {
    c1, g1, dog1, mdog, gdog, dmaP, dmaEdge,
    mcS: mc && mc.sims ? mc.p1_pct >= 50 : null,
    c75: c.mc_c75_p1 != null ? c.mc_c75_p1 >= 0.5 : null,
    // c75 side is the market FAVORITE, and whether recent form DISAGREES with it (for the
    // +ROI favorite signal: a c75 favorite that form fades).
    c75fav: c.mc_c75_p1 != null ? ((c.mc_c75_p1 >= 0.5) !== dog1) : null,
    pfDis: (pf && pf.agree_c75 != null) ? (pf.agree_c75 === false) : null,
    cuS: c.mc_cutr_p1 != null ? c.mc_cutr_p1 >= 0.5 : null,
    aP: b05(a, 'p1_prob'), bP: b05(b, 'p1_prob'), dP: b05(d, 'p1_prob'),
    mcdS: d && d.mc && d.mc.sims ? d.mc.p1_pct >= 50 : null,
    hate: (mdog - gdog) >= 0.02,
    mktFav: c.market_p1 != null ? Math.max(c.market_p1, 1 - c.market_p1) : null,  // favorite's implied prob
  }
}
// 🧊 Pure-form overlay tag (2026-10-06, user "notify the bets/prices tab when it agrees or
// disagrees, positive ROI only"): the pf_c75_* contrarian lane for a card. Quality-adjusted
// last-10-on-surface recent form (NO serve stats) vs the C-MC(c75) lean. Returns a badge
// ONLY when THIS match's gender cell is currently +ROI in the live log (men disagree +18.9%).
function pureFormTag(m, study) {
  const pf = m.pure_form
  if (!pf || pf.agree_c75 == null || !study) return null
  const gen = (m.league === 'wta' || m.league === 'itf_women') ? 'w' : 'm'
  const dis = !pf.agree_c75
  const mcc = m.model_c || {}
  const c75v = mcc.mc_c75_p1
  const sideP1 = c75v != null ? c75v >= 0.5 : null      // the side to TAKE (the C-MC c75 pick)
  // Read the DOG/FAV-split lane (2026-10-06): FORM-FADE pays on dogs, loses on favorites, so
  // the +ROI gate below greens the tag only on dog picks. recon-filtered server-side.
  const dogPick = (sideP1 != null && mcc.market_p1 != null) ? (sideP1 === (mcc.market_p1 < 0.5)) : null
  const laneObj = dis
    ? (dogPick === true ? study.pf_c75_dis_dog : dogPick === false ? study.pf_c75_dis_fav : study.pf_c75_dis)
    : study.pf_c75_agr
  const rec = (laneObj || {})[gen] || {}
  const n = rec.n || 0, roi = rec.roi_pct
  // n>=12 (not 20): recon-filtering + the dog-only split legitimately shrinks the forward dog
  // sample (~n18 men). Still a real minimum; the live n is shown so thinness is visible.
  if (n < 12 || roi == null || roi <= 0) return null   // positive-ROI only (dogs clear it, favs don't)
  const pickName = sideP1 == null ? null : (sideP1 ? m.player_1 : m.player_2)
  const oppName = sideP1 == null ? null : (sideP1 ? m.player_2 : m.player_1)
  const roiTxt = `${roi > 0 ? '+' : ''}${Math.round(roi * 10) / 10}% (${rec.wins}-${n - rec.wins}, n${n})`
  return {
    dis, roi: Math.round(roi * 10) / 10, n, wins: rec.wins, sideP1, pickName,
    // The highlighted name is the one to TAKE. "FADE FORM" = recent form points at the
    // opponent; you fade that and back the model's pick. Worded so it can't read backwards.
    label: dis ? '🧊 FADE FORM · TAKE' : '🔥 FORM BACKS · TAKE',
    tip: dis
      ? `TAKE ${pickName} — bet THIS player. Recent form (last-10-on-surface, opponent quality + how close, no serve stats) actually favors the opponent (${oppName}), but the model (C-MC c75) likes ${pickName}, and fading the form narrative in this spot is live ${roiTxt} for ${gen === 'w' ? 'women' : 'men'}. The market overvalues recent form, so the model side has overperformed.`
      : `TAKE ${pickName} — recent form AND the model (C-MC c75) both back ${pickName} here; live ${roiTxt} for ${gen === 'w' ? 'women' : 'men'}.`,
  }
}
// Pre-match snapshots survive tab switches (module-level, keyed by tab+fixture) so a live
// game stays FROZEN even after you leave the Best/Prices tab and come back.
const _bestLiveSnaps = new Map()
function BestPanel({ query, laneRec, priceOnly }) {
  // The board's elite picks only (2026-10-05, user ask): every today/ITF game that fires a
  // signal currently proven on its gender in the live log (hit >=65%, ROI >=+4%, n>=20),
  // ranked by that signal's ROI. Stacked (multi-signal) games float to the top.
  const [data, setData] = useState({ today: null, itf: null })
  const [err, setErr] = useState(null)
  const [mode, setMode] = useState('roi')   // 'roi' = sample-weighted/ROI; 'time' = by start time
  const snaps = _bestLiveSnaps
  const pfx = priceOnly ? 'p·' : 'b·'        // keep Best/Prices snapshots separate
  useEffect(() => {
    const go = () => Promise.all([
      fetch('/api/tennis/today').then(r => r.json()).catch(() => ({ matches: [] })),
      fetch('/api/tennis/itf').then(r => r.json()).catch(() => ({ matches: [] })),
    ]).then(([t, i]) => setData({ today: t, itf: i })).catch(e => setErr(String(e)))
    go(); const id = setInterval(go, 120000); return () => clearInterval(id)
  }, [])
  if (err) return <div className="mono" style={{ color: 'var(--edge-neg)', padding: 20 }}>Couldn't load ({err})</div>
  if (!data.today) return <div className="mono" style={{ color: 'var(--text-secondary)', padding: 40, textAlign: 'center' }}>loading best picks…</div>
  const study = (laneRec && laneRec.study) || {}
  const q = query.trim().toLowerCase()
  const ms = [...(data.today.matches || []), ...((data.itf || {}).matches || [])]
  const seen = new Set(); const rows = []
  for (const m of ms) {
    if (!['unplayed', 'live'].includes(m.status)) continue
    const key = m.fixture_id || (m.player_1 + m.player_2)
    if (seen.has(key)) continue; seen.add(key)
    // FROZEN once live (2026-10-05, user "can't have them changing mid match"): a live game
    // is served from its pre-match snapshot, never recomputed -- so the pick/band/signals
    // don't flip when the live model updates. (Odds are already frozen at first serve.)
    if (m.status === 'live' && snaps.has(pfx + key)) {
      const snap = snaps.get(pfx + key)
      if (q && !((snap.pick || '') + ' ' + (snap.opp || '')).toLowerCase().includes(q)) continue
      rows.push({ ...snap, live: true, frozen: true })
      continue
    }
    const s = bestSig(m); if (!s) continue
    const gen = m.league === 'wta' || m.league === 'itf_women' ? 'w' : 'm'
    const hits = []
    for (const e of BEST_SIGNALS) {
      const side = e.fire(s)
      if (side == null) continue
      // ⚔→🐕 FIGHT-FLIP suppression (2026-10-08, user "gray fight favorites get
      // overpowered if all MCs are on the dog — change every bet like that to the
      // dog"): a FIGHT gray-side FAVORITE whose opponent is a banded all-4-MC dog is
      // NOT a pick — the dog is (pushed below as fight_mc4_dog).
      if (e.key === 'cvg_gray' && side !== s.dog1
          && s.mcdS != null && s.mcS != null && s.c75 != null && s.cuS != null
          && s.mcdS === s.mcS && s.mcS === s.c75 && s.c75 === s.cuS && s.mcS === s.dog1) {
        const oD = m.live_odds ? Number(s.dog1 ? m.live_odds.player_1 : m.live_odds.player_2) : null
        if (oD != null && !isNaN(oD) && oD >= 100 && oD <= 250) continue
      }
      // 4-MC DOG is a PRICE-BANDED signal: only counts when the dog is +100..+250
      if (e.key === 'mc4_dog_band') {
        const o4 = m.live_odds ? Number(side ? m.live_odds.player_1 : m.live_odds.player_2) : null
        if (o4 == null || isNaN(o4) || o4 < 100 || o4 > 250) continue
      }
      // SIDE-AWARE GATE (2026-10-06, user "change all the live signals, a lot of bets should
      // change"): judge the pick by its signal's record on the EXACT cell it lands in —
      // gender × (dog/fav). Almost every signal is +ROI on dogs and −ROI on favorites, so
      // this drops the losing favorite picks the blended gate used to let through.
      const isDog = (side === s.dog1)
      const cellKey = gen + (isDog ? '_dog' : '_fav')   // m_dog / m_fav / w_dog / w_fav
      const rec = (study[e.key] || {})[cellKey] || {}
      const n = rec.n || 0
      if (n < BEST_N_SPLIT) continue
      const hit = 100 * rec.wins / n, roi = rec.roi_pct
      // Qualify as a high-hit pick (hit≥65 & ROI≥+4) OR a high-ROI dog (ROI≥+15; dogs win
      // <65% but pay big). The cell is already side-specific so favorites can't borrow dog ROI.
      const ok = (hit >= BEST_HIT && roi >= BEST_ROI) || (roi >= 15)
      if (!ok) continue
      hits.push({ ...e, side, n, hit: Math.round(hit), roi: Math.round(roi * 10) / 10, isDog })
    }
    // MEN FAVORITE signals (2026-10-06, user "mark all10_price_m + cr5_coll_leanfav, men only"):
    // the only two favorite cells that pay. These are price/odds-dependent so they're checked
    // here (odds in hand) rather than via the odds-agnostic BEST_SIGNALS list. Men only.
    if (gen === 'm' && m.live_odds && m.live_odds.player_1 != null && m.live_odds.player_2 != null) {
      const favSide = !s.dog1
      const favOd = favSide ? m.live_odds.player_1 : m.live_odds.player_2
      const pushFav = (key, label, icon) => {
        const r2 = (study[key] || {}).m || {}
        const nn = r2.n || 0
        if (nn >= BEST_N_SPLIT && r2.roi_pct > 0) hits.push({ key, label, icon, side: favSide, n: nn, hit: Math.round(100 * r2.wins / nn), roi: Math.round(r2.roi_pct * 10) / 10, isDog: false })
      }
      // ALL-10 agree ON the favorite, priced −140..−300
      if (isAll10Agree(s) && s.c1 === favSide && favOd <= -140 && favOd >= -300) pushFav('all10_price_m', 'ALL-10 FAV −140/300', '✅')
      // COLLISION lean-fav: gray hates the dog + A,B,C,gray,D all on the favorite + fav 65–85%
      if (s.hate && s.aP === favSide && s.bP === favSide && s.c1 === favSide && s.g1 === favSide && s.dP === favSide && s.mktFav != null && s.mktFav >= 0.65 && s.mktFav <= 0.85) pushFav('cr5_coll_leanfav', 'COLLISION lean-fav', '⚖️')
    }
    // ⚄ 4-MC OVER-MARKET FAV −200..−300 (2026-10-08, user "add the −200 to −300 picks
    // to the best tab"): every sim prices the FAVORITE above the market AND the price is
    // in the one pocket that paid (6-0 +41.8% at promotion; −100/−200 loses, big sim
    // edges are 1-5 — the band is the whole mark). BOTH genders; explicit push with NO
    // n-floor (user call) — the chip shows the live lane with ⚠ while n<12.
    if (m.live_odds && m.live_odds.player_1 != null && m.live_odds.player_2 != null) {
      const cx = m.model_c || {}; const mcx = (m.model_d || {}).mc
      if (mcx && mcx.sims && cx.mc && cx.mc.sims && cx.mc_c75_p1 != null && cx.mc_cutr_p1 != null && cx.market_p1 != null) {
        const favS = !s.dog1
        const mkf = Math.max(cx.market_p1, 1 - cx.market_p1)
        const pf = [mcx.p1_pct / 100, cx.mc.p1_pct / 100, cx.mc_c75_p1, cx.mc_cutr_p1]
          .map(v => favS ? v : 1 - v)
        const favOd2 = Number(favS ? m.live_odds.player_1 : m.live_odds.player_2)
        if (pf.every(v => v > mkf) && !isNaN(favOd2) && favOd2 >= -300 && favOd2 <= -200) {
          const r4 = ((study.mc4ovr_fav_band || {})[gen] && (study.mc4ovr_fav_band || {})[gen].n ? (study.mc4ovr_fav_band || {})[gen] : (study.mc4ovr_fav_band || {}))
          const n4 = r4.n || 0
          hits.push({ key: 'mc4ovr_fav_band', label: `4-MC>MKT −200/300${n4 < 12 ? ' ⚠' : ''}`, icon: '⚄', side: favS, n: n4, hit: n4 ? Math.round(100 * r4.wins / n4) : 0, roi: n4 ? Math.round((r4.roi_pct || 0) * 10) / 10 : 0, isDog: false })
        }
      }
    }
    // ⚔→🐕 FIGHT-FLIP DOG (2026-10-08, user): gray fights C onto the FAVORITE while all
    // four sims take the +100..+250 dog -> the tab's pick IS THE DOG (10-6 +48.1% banded
    // at registration, men 7-2; outside the band 0-3 = no bet either way). Explicit
    // push, no n-floor (user mark); ⚠ while the lane is thin.
    if (m.live_odds && s.c1 != null && s.g1 != null && s.c1 !== s.g1 && s.g1 !== s.dog1
        && s.mcdS != null && s.mcS != null && s.c75 != null && s.cuS != null
        && s.mcdS === s.mcS && s.mcS === s.c75 && s.c75 === s.cuS && s.mcS === s.dog1) {
      const oD = Number(s.dog1 ? m.live_odds.player_1 : m.live_odds.player_2)
      if (!isNaN(oD) && oD >= 100 && oD <= 250) {
        const rf = ((study.fight_mc4_dog || {})[gen] && (study.fight_mc4_dog || {})[gen].n ? (study.fight_mc4_dog || {})[gen] : (study.fight_mc4_dog || {}))
        const nf = rf.n || 0
        hits.push({ key: 'fight_mc4_dog', label: `FIGHT-FLIP DOG${nf < 12 ? ' ⚠' : ''}`, icon: '⚔🐕', side: s.dog1, n: nf, hit: nf ? Math.round(100 * rf.wins / nf) : 0, roi: nf ? Math.round((rf.roi_pct || 0) * 10) / 10 : 0, isDog: true })
      }
    }
    if (!hits.length) continue
    hits.sort((x, y) => y.roi - x.roi)
    const pickSide = hits[0].side            // the top-ROI signal sets the side
    const kept = hits.filter(h => h.side === pickSide)
    const pick = pickSide ? m.player_1 : m.player_2
    const opp = pickSide ? m.player_2 : m.player_1
    if (q && !(pick + ' ' + opp + ' ' + (m.tournament || '')).toLowerCase().includes(q)) continue
    const dmx = m.model_d || {}
    const thin = !!((dmx.sutr_p1 && dmx.sutr_p1.n != null && dmx.sutr_p1.n < 12)
      || (dmx.sutr_p2 && dmx.sutr_p2.n != null && dmx.sutr_p2.n < 12))
    const od = m.live_odds ? (pickSide ? m.live_odds.player_1 : m.live_odds.player_2) : null
    // LONG DOGS DROPPED (2026-10-08, user "get rid of all the 250 to 400 greens"): a DOG
    // pick priced over +250 doesn't make the tab at all — replay: +250..+400 went 1-6
    // (−39%), and the lone +400 winner is n=1 luck. The lanes still track them in the
    // background; if long dogs ever start paying, the records will say so and this gate
    // can reopen on evidence. Unpriced picks stay (nothing to judge them by).
    if (od != null && od > 250 && pickSide === s.dog1) continue
    const a10 = isAll10Agree(s)                 // all 10 heads agree -> opens the −150/−300 men window
    const sweet = inSweetPrice(od, gen, a10)
    if (priceOnly && !sweet) continue        // 💰 Prices tab: only sweet-spot-priced picks
    const bestN = Math.max(...kept.map(g => g.n))
    // Stack count = distinct signal FAMILIES, not raw chips (so correlated c75/gold signals
    // don't inflate ★). ★2 now means two genuinely different reads agree.
    const nFam = new Set(kept.map(g => famOf(g.key))).size
    // 🤝 BOTH-TABS OVERLAP (2026-10-07, user "when the favorites overlap mark it on the
    // best tab"): does the ⭐ Picks sheet land on this SAME pick? (c50 & c75 agree AND the
    // model prices that side over the market.) 5-day replay: overlap favorites 19-3 +26.7%
    // — the only favorite cell that paid; overlap dogs +39.5%. Badge cites the live lane.
    const dbl = (() => {
      const c = m.model_c || {}; const mcx = c.mc || {}
      if (mcx.p1_pct == null || c.mc_c75_p1 == null || c.market_p1 == null) return null
      const s50 = mcx.p1_pct >= 50
      if (s50 !== (c.mc_c75_p1 >= 0.5)) return null
      const cp = s50 ? mcx.p1_pct / 100 : 1 - mcx.p1_pct / 100
      const mp = s50 ? c.market_p1 : 1 - c.market_p1
      if (!(cp > mp) || s50 !== pickSide) return null
      if (pickSide === s.dog1) {
        // DOG badge gated to +100..+250 (2026-10-08, user "I only want the +100 to +250
        // ones") — the band where the overlap-dog edge actually earned; a +614 doesn't mark.
        return (od != null && od >= 100 && od <= 250) ? 'dog' : null
      }
      return 'fav'
    })()
    const row = {
      fid: key, pick, opp, od, thin, sigs: kept, gen, lg: m.league, t: m.start_time_utc, live: m.status === 'live',
      bestRoi: kept[0].roi, bestHit: kept[0].hit, nSig: nFam, nChips: kept.length,
      bestN, core: bestN >= 50,   // CORE = a dependable big-sample edge backs it
      sweet, band: priceBand(od, gen, a10), allTen: a10, dbl,
      // 🧊 pure-form overlay (shown only when its cell is +ROI) — attach to the row ONLY when
      // this row's pick IS the form-fade side, so the glowing name = the name to take.
      pf: (() => { const t = pureFormTag(m, study); return (t && t.sideP1 === pickSide) ? t : null })(),
    }
    // Freeze the pre-match state so a live game can be served from it unchanged.
    if (m.status === 'unplayed') snaps.set(pfx + key, { ...row })
    rows.push(row)
  }
  // Drop snapshots for games that have left the slate (ended) so the map doesn't grow.
  for (const sk of [...snaps.keys()]) if (sk.startsWith(pfx) && !seen.has(sk.slice(pfx.length))) snaps.delete(sk)
  // Order: LIVE games sticky at the top (2026-10-05, user), then 'time' = by start time, else
  // sample-weighted (CORE >=50 first, then ROI; a +8%/n117 edge outranks a +67%/n12 one).
  if (mode === 'time') rows.sort((a, b) => (Number(b.live) - Number(a.live)) || (a.t || '').localeCompare(b.t || ''))
  else rows.sort((a, b) => (Number(b.live) - Number(a.live)) || (Number(b.core) - Number(a.core)) || b.bestRoi - a.bestRoi || b.nSig - a.nSig || b.bestHit - a.bestHit)
  const btn = (k, label) => (
    <button onClick={() => setMode(k)} className="mono" style={{ padding: '3px 12px', borderRadius: 12, fontSize: 10, cursor: 'pointer', marginLeft: 6, border: `1px solid ${mode === k ? '#e3b341' : 'var(--line)'}`, background: mode === k ? 'rgba(227,179,65,0.14)' : 'transparent', color: mode === k ? '#e3b341' : 'var(--text-secondary)', fontWeight: 700 }}>{label}</button>
  )
  const odfmt = v => v == null ? '' : (v > 0 ? `+${v}` : `${v}`)
  return (
    <div style={{ marginTop: 16 }}>
      <div className="mono" style={{ padding: '10px 16px', borderRadius: 6, border: `1px solid ${priceOnly ? '#e3b34155' : '#3fb95055'}`, background: priceOnly ? 'rgba(227,179,65,0.06)' : 'rgba(63,185,80,0.06)', fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.5 }}>
        {priceOnly ? (
          <><b style={{ color: '#e3b341' }}>💰 BEST PICKS · SWEET-SPOT PRICES</b> — Best-tab picks in a profitable price window. MEN: <b>+100…+250</b> (dog value), <b>−300…−600</b> (short chalk), PLUS <b>ALL-10-agree at −140…−300</b> {(() => { const a = study.all10_price_m || {}; return a.n ? <>(live <b style={{ color: a.roi_pct > 0 ? '#3fb950' : '#f85149' }}>{a.roi_pct > 0 ? '+' : ''}{Math.round(a.roi_pct)}%</b>, {a.wins}-{a.n - a.wins}, auto-updating)</> : '(tracking)' })()}. <b>WOMEN (2026-10-08): the +100…+250 dog band is marked too</b> — its own price_dog_w lane in the legend. Women's chalk/ALL-10 bands stay excluded (ALL-10 women ran −39%). On the full log the sweet spots ran <b style={{ color: '#3fb950' }}>+24% ROI</b> vs +6.7% for all Best picks. Skips the −110…−140 and under −600 dead prices. Auto-refresh 2 min.</>
        ) : (
          <><b style={{ color: '#3fb950' }}>🏆 BEST PICKS</b> — only games firing a signal proven on the <b>exact cell the pick lands in</b>: its record for this <b>gender AND side</b> (dog/fav) must be +ROI (hit ≥{BEST_HIT}% & ROI ≥+{BEST_ROI}%, OR ROI ≥+15% for high-paying dogs; n≥{BEST_N_SPLIT}). Because almost every signal only pays on <b style={{ color: '#3fb950' }}>dogs</b>, favorite picks now drop off — this tab is mostly underdogs by design. <b style={{ color: '#58a6ff' }}>CORE</b> sorts above <b style={{ color: '#8b949e' }}>THIN</b>; 2+ stacked signals rise. Auto-refresh 2 min.</>
        )}
      </div>
      {priceOnly ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 10, padding: '8px 10px', borderRadius: 6, background: 'rgba(255,255,255,0.02)', border: '1px solid var(--line)', alignItems: 'center' }}>
          <span style={{ fontSize: 9, color: 'var(--text-tertiary)', fontWeight: 700, letterSpacing: '0.04em' }}>PRICE TIERS (live · auto-updates daily):</span>
          {['all10strong', 'dog', 'chalk', 'all10'].map(k => {
            const b = BAND[k]; const o = study[b.lane] || {}; const n = o.n || 0; const roi = o.roi_pct
            // dog band is the one WOMEN band too (2026-10-08, user "mark the women ones
            // too") — the legend shows the women's own lane (price_dog_w) beside the men's.
            const ow = k === 'dog' ? ((study.price_dog_w || {}).w || {}) : null
            return (
              <span key={k} title={b.tip + (k === 'dog' ? ' Women are marked in this band too; their record is the separate price_dog_w lane shown as W.' : '')} className="mono" style={{ fontSize: 9, fontWeight: 700, padding: '2px 8px', borderRadius: 8, border: `1px solid ${b.bd}`, color: b.col, background: b.bg }}>
                {b.icon} {b.name} <span style={{ fontWeight: 400, color: 'var(--text-secondary)' }}>{n ? `M ${roi > 0 ? '+' : ''}${Math.round(roi * 10) / 10}% · ${o.wins}-${n - o.wins}` : 'M tracking'}{ow ? (ow.n ? ` · W ${ow.roi_pct > 0 ? '+' : ''}${Math.round(ow.roi_pct * 10) / 10}% · ${ow.wins}-${ow.n - ow.wins}` : ' · W tracking') : ''}</span>
              </span>
            )
          })}
        </div>
      ) : null}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
        {btn('roi', '📈 by edge')}{btn('time', '🕐 by time')}
      </div>
      {rows.length === 0 ? (
        <div className="mono" style={{ fontSize: 12, color: 'var(--text-tertiary)', padding: 24, textAlign: 'center' }}>
          {priceOnly ? 'No men Best picks are in a sweet-spot price right now (+100…+250, −300…−600, or ALL-10 at −140…−300).' : `No games right now clear the elite gate (hit ≥${BEST_HIT}%, ROI ≥+${BEST_ROI}%, n≥${BEST_N}).`}
        </div>
      ) : (
        <div style={{ marginTop: 12 }}>
          {rows.map((r, i) => {
            // Color-coded price tier (2026-10-05, user): name/row tinted by its band.
            const bd = r.band ? BAND[r.band] : null
            return (
            <div key={i} className="mono" style={{ padding: '8px 10px', borderBottom: '1px solid rgba(255,255,255,0.05)', borderLeft: bd ? `3px solid ${bd.bd}` : '3px solid transparent', background: bd ? bd.bg : (r.nSig >= 2 ? 'rgba(63,185,80,0.07)' : undefined) }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                {bd ? <span title={bd.tip} style={{ fontSize: 10 }}>{bd.icon}</span> : null}
                {r.live ? <span style={{ color: '#f85149', fontSize: 8 }}>● LIVE</span> : null}
                {r.frozen ? <span title="📌 Frozen at first serve — this in-play pick is shown exactly as it was pre-match; live model updates do NOT change it (odds were already frozen too)." style={{ fontSize: 8, color: '#e3b341' }}>📌 frozen</span> : null}
                {r.nSig >= 2 ? <span title={`${r.nSig} INDEPENDENT signal families agree on this pick${r.nChips > r.nSig ? ` (${r.nChips} chips below, but correlated ones — e.g. the two c75 signals — count once)` : ''}. More distinct families = more conviction.`} style={{ color: '#3fb950', fontSize: 9, fontWeight: 700, border: '1px solid #3fb95088', borderRadius: 4, padding: '0 5px' }}>★{r.nSig} STACK</span> : null}
                <span title={r.core ? 'CORE: a dependable edge with 50+ settled bets backs this — bet it at full unit.' : 'THIN: best backing edge has <50 settled bets. Real but high-variance — bet smaller, expect regression.'} style={{ fontSize: 8.5, fontWeight: 700, borderRadius: 4, padding: '0 5px', border: `1px solid ${r.core ? '#58a6ff88' : '#8b949e66'}`, color: r.core ? '#58a6ff' : '#8b949e' }}>{r.core ? 'CORE' : 'THIN'} n{r.bestN}</span>
                <span title={r.pf ? r.pf.tip : undefined} style={{ fontSize: r.pf ? 14 : 13, fontWeight: r.pf ? 800 : 700, color: r.pf ? '#56d4dd' : (bd ? bd.col : '#3fb950'), textShadow: r.pf ? '0 0 11px #56d4ddbb' : (bd ? `0 0 10px ${bd.glow}` : undefined) }}>{r.pf ? '🧊 ' : ''}{r.pick}</span>
                <span style={{ color: 'var(--text-tertiary)', fontSize: 11 }}>vs {r.opp.split(' ').slice(-1)[0]}</span>
                <span style={{ color: 'var(--text-tertiary)', fontSize: 9 }}>· {String(r.lg || '').toUpperCase()} · {r.gen === 'w' ? 'W' : 'M'}</span>
                {r.od != null ? <span style={{ fontSize: 11, color: r.od > 0 ? '#3fb950' : 'var(--text-secondary)' }}>{odfmt(r.od)}</span> : null}
                {(() => {
                  // ⚖ KELLY-LITE STAKE (2026-10-08): uncertainty-gated sizing, the principled
                  // version of CORE/THIN/⚠. Top backing cell's ROI is SHRUNK toward zero by
                  // sample size (n/(n+50) — a +60%/n12 lane sizes like a +12% edge), then
                  // quarter-Kelly at this pick's own price on a 25u bankroll. Thin lanes and
                  // long prices auto-size small; nothing here overrides the no-bet gates.
                  if (r.od == null || !r.sigs || !r.sigs.length) return null
                  const g0 = r.sigs[0]
                  const e = Math.min(Math.max((g0.roi / 100) * (g0.n / (g0.n + 50)), 0), 0.30)
                  if (e <= 0.005) return null
                  const dz = r.od > 0 ? 1 + r.od / 100 : 1 + 100 / Math.abs(r.od)
                  const u = Math.min(Math.max(0.25 * (e / (dz - 1)) * 25, 0.1), 1.5)
                  const us = u.toFixed(1)
                  return <span title={`⚖ Suggested stake ≈${us}u — quarter-Kelly on a 25-unit bankroll. Edge = top backing cell's live ROI (+${g0.roi}% on n=${g0.n}) shrunk by sample size to +${Math.round(e * 100)}%, divided by this price's payout. Thin lanes and long dogs size themselves down automatically; a CORE favorite at short odds sizes up (low variance — that's Kelly, not a bug). Guidance only: flat 1u is what every record on this site measures.`}
                    className="mono" style={{ fontSize: 9, fontWeight: 800, borderRadius: 4, padding: '0 6px', border: '1px solid #bc8cff66', color: '#d2a8ff', background: 'rgba(188,140,255,0.10)' }}>⚖ {us}u</span>
                })()}
                {bd ? <span title={bd.tip} style={{ fontSize: 8.5, fontWeight: 700, borderRadius: 4, padding: '0 5px', border: `1px solid ${bd.bd}`, color: bd.col, background: bd.bg }}>{bd.icon} {bd.name}</span> : null}
                {r.gen === 'm' && r.band === 'dog' && r.nSig >= 2 ? (() => { const o = study.blue2stack || {}; const n = o.n || 0; return (
                  <span title="💎 BLUE ★2+: a +100/+250 men dog with 2+ INDEPENDENT signal families agreeing — the board's best measured cell (+55.5%, 16-7 at build). Live record auto-updates as games settle." className="mono" style={{ fontSize: 9, fontWeight: 800, borderRadius: 4, padding: '0 6px', border: '1px solid #58a6ff', color: '#eaf4ff', background: 'rgba(31,111,235,0.38)', textShadow: '0 0 8px #58a6ff' }}>
                    💎 A+ {n ? `${o.roi_pct > 0 ? '+' : ''}${Math.round(o.roi_pct * 10) / 10}% ${o.wins}-${n - o.wins}` : 'tracking'}
                  </span>) })() : null}
                {r.dbl ? (() => { const c = ((study['ovl_' + r.dbl] || {})[r.gen]) || {}; const n = c.n || 0; const fav = r.dbl === 'fav'; return (
                  <span title={`🤝 BOTH TABS AGREE on this ${fav ? 'FAVORITE' : 'DOG'} — the pick also qualifies on the ⭐ Picks sheet (c50+c75 agree AND the model prices it over the market). 5-day replay at build: overlap favorites 19-3 +26.7% (the ONLY favorite cell that paid) · overlap dogs +39.5% · both-tabs union +16.5% vs Best alone +23.0% / Picks alone +20.6%. The number shown is the live ovl_${r.dbl} lane for this match's gender — auto-updates as games settle.`}
                    className="mono" style={{ fontSize: 9, fontWeight: 800, borderRadius: 4, padding: '0 6px', border: `1px solid ${fav ? '#e3b341' : '#3fb950'}`, color: fav ? '#fff7df' : '#eaffea', background: fav ? 'rgba(227,179,65,0.35)' : 'rgba(63,185,80,0.30)', textShadow: `0 0 8px ${fav ? '#e3b341' : '#3fb950'}` }}>
                    🤝 {fav ? 'FAV' : 'DOG'} {r.gen === 'w' ? 'W' : 'M'} {n ? `${c.roi_pct > 0 ? '+' : ''}${Math.round(c.roi_pct * 10) / 10}% ${c.wins}-${n - c.wins}` : 'tracking'}
                  </span>) })() : null}
                {r.pf ? <span title={r.pf.tip} style={{ fontSize: 8.5, fontWeight: 700, borderRadius: 4, padding: '0 5px', border: `1px solid ${r.pf.dis ? '#56d4dd88' : '#f0883e88'}`, color: r.pf.dis ? '#56d4dd' : '#f0883e', background: r.pf.dis ? 'rgba(86,212,221,0.10)' : 'rgba(240,136,62,0.10)' }}>{r.pf.label} {r.pf.roi > 0 ? '+' : ''}{r.pf.roi}%</span> : null}
                {r.gen === 'w' && r.sigs && r.sigs.some(g => g.key === 'mc_green') ? (() => {
                  // 🟢 MC-GREEN WOMEN mark (2026-10-07, user "mark mc green women games on the
                  // best bet tab with a warning until it settles more but I still want to bet
                  // them"): a BETTABLE mark that carries a ⚠ thin flag automatically while the
                  // women's cell is under 50 settles; the ⚠ drops itself once the sample matures.
                  const o = study.mc_green || {}; const c = o.w_fav && o.w_fav.n ? o.w_fav : (o.w || {})
                  const n = c.n || 0; const warn = n < 50
                  return (
                    <span title={`🟢 MC-GREEN WOMEN — the serve-MC agrees with a plain green (gray-line) pick on a women's match: every fire so far has been a favorite, and the cell is ${n ? `${c.wins}-${n - c.wins} (${Math.round(100 * c.wins / n)}%) ROI ${c.roi_pct > 0 ? '+' : ''}${Math.round(c.roi_pct * 10) / 10}%` : 'new'}. BETTABLE by your call (2026-10-07)${warn ? ` — but ⚠ THIN: n=${n} settles. An 89%-hit favorite lane WILL regress toward the mid-70s; bet smaller until ~50 settles (the ⚠ removes itself at n≥50). Men's half is −7.8% on 3× the sample — women only.` : '. Sample has matured past 50 settles.'}`}
                      className="mono" style={{ fontSize: 9, fontWeight: 800, borderRadius: 4, padding: '0 6px', border: `1px solid ${warn ? '#e3b341' : '#3fb950'}`, color: '#d9ffe3', background: 'rgba(63,185,80,0.28)', textShadow: '0 0 8px #3fb950' }}>
                      🟢 MC-GREEN W {n ? `${c.roi_pct > 0 ? '+' : ''}${Math.round(c.roi_pct * 10) / 10}% ${c.wins}-${n - c.wins}` : 'new'}{warn ? <span style={{ color: '#e3b341' }}> ⚠ n{n}</span> : null}
                    </span>
                  )
                })() : null}
                {r.thin ? <span title="A player's court-UTR is built on <12 matches — rating may be inflated (thin/weak-schedule sample)." style={{ fontSize: 9, color: '#e3b341' }}>⚠ thin</span> : null}
                <span style={{ marginLeft: 'auto', color: 'var(--text-tertiary)', fontSize: 9 }}>{fmtPT(r.t) || ''}</span>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 5 }}>
                {r.sigs.map((g, j) => (
                  <span key={j} className="mono" style={{ fontSize: 9, padding: '1px 6px', borderRadius: 8, border: '1px solid #3fb95044', color: '#3fb950', background: 'rgba(63,185,80,0.06)' }}>
                    {g.icon} {g.label} <span style={{ color: 'var(--text-secondary)' }}>{g.hit}% · +{g.roi} · n{g.n}</span>
                  </span>
                ))}
              </div>
            </div>
          )})}
        </div>
      )}
    </div>
  )
}
// 📈 EVERY +EV SIGNAL (2026-10-07, user "put every single positive signal on board with the
// amount of matches that signal has and roi, even the watch ones"): one chip per POSITIVE
// cell — lane × side (🐕 dog / ⭐ fav, all-gender) across the study lanes, root A/B/C lanes
// and price bands. Thin cells (n<12) grey; tooltip carries the men/women crossed cells.
// Live — recomputes with the track record every refresh.
function PositiveSignalsPanel({ laneRec }) {
  const [open, setOpen] = useState(true)
  if (!laneRec) return null
  const SKIP = new Set(['mc_c75_dog', 'mc_c75_fav', 'pf_c75_dis_dog', 'pf_c75_dis_fav'])
  const entries = []
  const cellTip = o => {
    const c = k => { const x = (o || {})[k]; return x && x.n ? `${x.roi_pct > 0 ? '+' : ''}${x.roi_pct}%/${x.n}` : '—' }
    return `M 🐕${c('m_dog')} ⭐${c('m_fav')} · W 🐕${c('w_dog')} ⭐${c('w_fav')}`
  }
  const push = (key, o) => {
    if (!o) return
    const hasSide = (o.dog && o.dog.n) || (o.fav && o.fav.n)
    if (hasSide) {
      for (const [sk, icon] of [['dog', '🐕'], ['fav', '⭐']]) {
        const c = o[sk]
        if (c && c.n && c.roi_pct > 0) entries.push({ key, icon, roi: c.roi_pct, w: c.wins, l: c.n - c.wins, n: c.n, tip: cellTip(o) })
      }
    } else if (o.n && o.roi_pct > 0) {
      const icon = /dog|blue/.test(key) ? '🐕' : (/chalk|fav|all10/.test(key) ? '⭐' : '')
      entries.push({ key, icon, roi: o.roi_pct, w: o.wins, l: o.n - o.wins, n: o.n, tip: cellTip(o) })
    }
  }
  for (const [k, o] of Object.entries(laneRec.study || {})) { if (!SKIP.has(k)) push(k, o) }
  for (const [k, o] of Object.entries(laneRec.lanes || {})) push(k, o)
  for (const k of ['cma_all', 'agree_dog', 'c_all', 'c_alone', 'c_with']) push(k, laneRec[k])
  entries.sort((a, b) => b.roi - a.roi)
  if (!entries.length) return null
  return (
    <div className="mono" style={{ margin: '14px 0', padding: '10px 12px', borderRadius: 8, border: '1px solid #3fb95044', background: 'rgba(63,185,80,0.04)' }}>
      <div style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }} onClick={() => setOpen(!open)}>
        <span style={{ fontSize: 10, fontWeight: 700, color: '#3fb950', letterSpacing: '0.05em' }}>
          📈 EVERY +EV SIGNAL CELL — {entries.length} positive right now · 🐕 dog / ⭐ fav side-specific · includes watch lanes · grey = thin (n&lt;12) · auto-updates
        </span>
        <span style={{ marginLeft: 'auto', color: 'var(--text-tertiary)', fontSize: 10 }}>{open ? '▾ hide' : '▸ show'}</span>
      </div>
      {open ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 8 }}>
          {entries.map((e, i) => {
            const thin = e.n < 12
            return (
              <span key={i} title={e.tip} style={{ fontSize: 9, fontWeight: 700, padding: '1px 7px', borderRadius: 8, border: `1px solid ${thin ? '#8b949e55' : '#3fb95055'}`, color: thin ? '#8b949e' : '#3fb950', background: thin ? 'transparent' : 'rgba(63,185,80,0.07)' }}>
                {e.icon} {e.key} <span style={{ fontWeight: 400, color: 'var(--text-secondary)' }}>+{Math.round(e.roi * 10) / 10}% · {e.w}-{e.l} · n{e.n}</span>
              </span>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}
// 🐕/⭐ SPLITS (2026-10-06, user "look at every single signal and see the rois if it's on a
// dog or fav pick"): every tracked $25 lane's live ROI split by the pick's side, sortable,
// with a gender filter. Reads the gender×side cells (m_dog/m_fav/w_dog/w_fav) the study now
// carries. The on-site version of the dog/fav scan.
function SplitsPanel() {
  const [rec, setRec] = useState(null)
  const [gender, setGender] = useState('all')   // all / m / w
  const [sortBy, setSortBy] = useState('dog')    // dog / fav / all
  useEffect(() => {
    const go = () => fetch('/api/tennis/track-record').then(r => r.json()).then(d => setRec(d.ab25 || null)).catch(() => {})
    go(); const id = setInterval(go, 120000); return () => clearInterval(id)
  }, [])
  if (!rec) return <div className="mono" style={{ color: 'var(--text-secondary)', padding: 40, textAlign: 'center' }}>loading…</div>
  const study = rec.study || {}
  const dogKey = gender === 'all' ? 'dog' : gender + '_dog'
  const favKey = gender === 'all' ? 'fav' : gender + '_fav'
  const cellOf = o => (o && o.n) ? { n: o.n, w: o.wins, roi: o.roi_pct } : null
  const rows = []
  for (const [k, o] of Object.entries(study)) {
    const dog = cellOf(o[dogKey]), fav = cellOf(o[favKey])
    const all = cellOf(gender === 'all' ? o : o[gender])
    if (!dog && !fav) continue
    rows.push({ k, dog, fav, all })
  }
  const sv = r => { const c = r[sortBy]; return c ? c.roi : -9999 }
  rows.sort((a, b) => sv(b) - sv(a))
  const col = c => !c ? 'var(--text-tertiary)' : c.roi > 3 ? '#3fb950' : c.roi < -3 ? '#f85149' : 'var(--text-secondary)'
  const cellTxt = c => c ? `${c.roi > 0 ? '+' : ''}${c.roi}%` : '—'
  const subTxt = c => c ? ` ${c.w}-${c.n - c.w} n${c.n}` : ''
  const tgl = (cur, set, k, label) => (
    <button key={k} onClick={() => set(k)} className="mono" style={{ padding: '3px 11px', borderRadius: 12, fontSize: 10, cursor: 'pointer', marginLeft: 6, fontWeight: 700, border: `1px solid ${cur === k ? '#e3b341' : 'var(--line)'}`, background: cur === k ? 'rgba(227,179,65,0.14)' : 'transparent', color: cur === k ? '#e3b341' : 'var(--text-secondary)' }}>{label}</button>
  )
  const Cell = ({ c }) => (
    <div style={{ flex: 1, textAlign: 'right' }}>
      <span style={{ color: col(c), fontWeight: 700 }}>{cellTxt(c)}</span>
      <span style={{ color: 'var(--text-tertiary)', fontSize: 9 }}>{subTxt(c)}</span>
    </div>
  )
  return (
    <div style={{ marginTop: 16 }}>
      <div className="mono" style={{ padding: '10px 16px', borderRadius: 6, border: '1px solid var(--line)', fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.5 }}>
        <b style={{ color: 'var(--text-primary)' }}>🐕/⭐ EVERY SIGNAL BY SIDE</b> — each tracked $25 lane's live ROI split by whether its pick was a market <b>DOG</b> or <b>FAVORITE</b>. The edge is almost always the <b style={{ color: '#3fb950' }}>dog</b> side; favorites are flat-to-negative (efficiently priced chalk). Forward-tracked, auto-refresh 2 min.
      </div>
      <div className="mono" style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 4, margin: '10px 0', fontSize: 10, color: 'var(--text-tertiary)' }}>
        <span style={{ fontWeight: 700 }}>GENDER:</span>{tgl(gender, setGender, 'all', 'ALL')}{tgl(gender, setGender, 'm', 'MEN')}{tgl(gender, setGender, 'w', 'WOMEN')}
        <span style={{ fontWeight: 700, marginLeft: 16 }}>SORT:</span>{tgl(sortBy, setSortBy, 'dog', '🐕 dog ROI')}{tgl(sortBy, setSortBy, 'fav', '⭐ fav ROI')}{tgl(sortBy, setSortBy, 'all', 'overall')}
      </div>
      <div className="mono" style={{ display: 'flex', fontSize: 9, color: 'var(--text-tertiary)', fontWeight: 700, padding: '4px 10px', borderBottom: '1px solid var(--line)', letterSpacing: '0.04em' }}>
        <div style={{ flex: 2 }}>SIGNAL</div><div style={{ flex: 1, textAlign: 'right' }}>🐕 DOG</div><div style={{ flex: 1, textAlign: 'right' }}>⭐ FAV</div><div style={{ flex: 1, textAlign: 'right' }}>ALL</div>
      </div>
      {rows.map(r => (
        <div key={r.k} className="mono" style={{ display: 'flex', alignItems: 'center', fontSize: 10, padding: '5px 10px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
          <div style={{ flex: 2, color: 'var(--text-secondary)' }}>{r.k}</div>
          <Cell c={r.dog} /><Cell c={r.fav} /><Cell c={r.all} />
        </div>
      ))}
      {rows.length === 0 ? <div className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)', padding: 24, textAlign: 'center' }}>no settled picks for this gender yet</div> : null}
    </div>
  )
}
function ModelXPanel() {
  const [m, setM] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    const go = () => fetch('/api/tennis/model-x').then(r => r.json()).then(setM).catch(e => setErr(String(e)))
    go()
    const id = setInterval(go, 120000)
    return () => clearInterval(id)
  }, [])
  if (err) return <div className="mono" style={{ color: 'var(--edge-neg)', padding: 20 }}>Couldn't load Model X ({err})</div>
  if (!m) return <div className="mono" style={{ color: 'var(--text-secondary)', padding: 40, textAlign: 'center' }}>loading Model X…</div>
  if (m.status && !m.active) return <div className="mono" style={{ color: 'var(--text-tertiary)', padding: 30 }}>{m.status}</div>
  const stat = (label, val, color) => (
    <div style={{ padding: '12px 16px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--panel)', minWidth: 150 }}>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>{label}</div>
      <div className="mono" style={{ fontSize: 18, fontWeight: 700, color: color || 'var(--text-primary)', marginTop: 3 }}>{val}</div>
    </div>
  )
  const lane = (L, label) => (
    <div style={{ padding: '12px 16px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--panel)', minWidth: 170 }}>
      <div className="mono" style={{ fontSize: 10, color: '#d2a8ff', fontWeight: 700 }}>{label}</div>
      {L && L.n ? (
        <>
          <div className="mono" style={{ fontSize: 16, fontWeight: 700, marginTop: 3, color: L.roi_pct >= 0 ? '#3fb950' : '#f85149' }}>{L.roi_pct > 0 ? '+' : ''}{L.roi_pct}%</div>
          <div className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{L.wins}-{L.n - L.wins}{L.pending ? ` · ${L.pending} pend` : ''}</div>
        </>
      ) : <div className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 3 }}>{L && L.pending ? `${L.pending} pending` : '0 settled'}</div>}
    </div>
  )
  const beatsMkt = m.wf_final_logloss != null && m.wf_market_logloss != null && m.wf_final_logloss < m.wf_market_logloss
  return (
    <div style={{ marginTop: 16 }}>
      <div className="mono" style={{ padding: '10px 16px', borderRadius: 6, border: '1px solid var(--line)', fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.5 }}>
        <b style={{ color: '#d2a8ff' }}>MODEL X</b> — the self-auditing meta-model. It stacks the market + A/B/C/D + gray heads + the Monte Carlos into one number, retrains nightly on every settled game, and auto-adds any frozen signal that clears a strict walk-forward gate (dropping ones that stop helping). Trained on {m.n} settled games{m.trained_at ? `, last ${m.trained_at}` : ''}. Display-only until it earns a forward record.
      </div>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700, margin: '14px 0 6px' }}>walk-forward (out-of-sample) <span style={{ fontWeight: 400, textTransform: 'none' }}>— lower log-loss = sharper; ROI = flat $1 on X's side</span></div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        {stat('market log-loss', m.wf_market_logloss ?? '—')}
        {stat('Model X log-loss', m.wf_final_logloss ?? '—', beatsMkt ? '#3fb950' : '#f85149')}
        {stat('X flat ROI', m.wf_final_roi_pct != null ? `${m.wf_final_roi_pct > 0 ? '+' : ''}${m.wf_final_roi_pct}%` : '—', (m.wf_final_roi_pct || 0) >= 0 ? '#3fb950' : '#f85149')}
        {stat('OOS sample', m.wf_final_n ?? '—')}
      </div>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 6 }}>
        {beatsMkt ? 'Model X is sharper than the raw market on calibration' : 'Model X is not beating the market yet'} — {(m.wf_final_roi_pct || 0) >= 0 ? 'and shows a flat-betting profit.' : 'but has no flat-betting edge (consistent with the dog-cells-only finding).'}
      </div>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700, margin: '14px 0 6px' }}>live lanes <span style={{ fontWeight: 400, textTransform: 'none' }}>— $25/game forward</span></div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        {lane(m.lane_all, 'X — every match')}
        {lane(m.lane_edge2, 'X — 2pt+ off market')}
      </div>
      <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700, margin: '14px 0 6px' }}>active inputs</div>
      <div className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
        {(m.active || []).map(f => (
          <span key={f} style={{ display: 'inline-block', padding: '1px 7px', margin: 2, borderRadius: 7, border: `1px solid ${(m.core || []).includes(f) ? 'var(--line)' : '#3fb95066'}`, color: (m.core || []).includes(f) ? 'var(--text-secondary)' : '#3fb950' }}>
            {f}{(m.added || []).includes(f) ? ' ⭐' : ''}
          </span>
        ))}
        <div style={{ fontSize: 9, color: 'var(--text-tertiary)', marginTop: 4 }}>grey = core (always on) · green ⭐ = auto-added after clearing the nightly walk-forward gate</div>
      </div>
      {m.audit && m.audit.length ? (
        <>
          <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700, margin: '14px 0 6px' }}>candidate audit <span style={{ fontWeight: 400, textTransform: 'none' }}>— every signal it tested last night</span></div>
          <div style={{ maxHeight: 320, overflowY: 'auto' }}>
            {m.audit.map((a, i) => (
              <div key={i} className="mono" style={{ fontSize: 10, display: 'flex', gap: 8, padding: '2px 0', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                <span style={{ minWidth: 110, color: 'var(--text-secondary)' }}>{a.cand}</span>
                <span style={{ minWidth: 54, fontWeight: 700, color: a.decision === 'ADD' ? '#3fb950' : 'var(--text-tertiary)' }}>{a.decision}</span>
                <span style={{ color: 'var(--text-tertiary)' }}>{a.ll_gain != null ? `Δlogloss ${a.ll_gain > 0 ? '+' : ''}${a.ll_gain}` : ''}{a.oos_roi != null ? ` · ROI ${a.oos_roi > 0 ? '+' : ''}${a.oos_roi}%` : ''}{a.n_oos != null ? ` · n ${a.n_oos}` : ''}{a.reason ? ` · ${a.reason}` : ''}</span>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </div>
  )
}

function HistoryPanel({ query, greenOnly = false }) {
  const [hist, setHist] = useState(null)
  const [err, setErr] = useState(null)
  const [full, setFull] = useState(false)       // false = compact rows, true = full board cards
  const [openDate, setOpenDate] = useState(null) // which day is expanded in full mode
  const [laneRec, setLaneRec] = useState(null)
  useEffect(() => {
    fetch('/api/tennis/history?limit_dates=30').then(r => r.json()).then(setHist).catch(e => setErr(String(e)))
    fetch('/api/tennis/track-record').then(r => r.json()).then(d => setLaneRec(d.ab25 || null)).catch(() => {})
  }, [])
  if (err) return <div className="mono" style={{ color: 'var(--edge-neg)', padding: 20 }}>Couldn't load history ({err})</div>
  if (!hist) return <div className="mono" style={{ color: 'var(--text-secondary)', padding: 40, textAlign: 'center' }}>loading finished matches…</div>
  const q = query.trim().toLowerCase()
  const dates = hist.dates.map(d => ({
    ...d,
    matches: q ? d.matches.filter(m => (m.p1 + ' ' + m.p2 + ' ' + m.tournament).toLowerCase().includes(q)) : d.matches,
  })).filter(d => d.matches.length)
  const odds = v => v == null ? '' : (v > 0 ? `+${v}` : `${v}`)
  const chip = (label, p, color) => {
    if (!p) return null
    return <span className="mono" title={`${label} picked player ${p.side} — ${p.hit ? 'correct' : 'wrong'}`}
      style={{ fontSize: 9, padding: '0 5px', borderRadius: 7, marginLeft: 3,
        border: `1px solid ${p.hit ? '#3fb95055' : '#f8514955'}`,
        color: p.hit ? '#3fb950' : '#f85149', background: p.hit ? '#3fb9500d' : '#f851490d' }}>
      {label}{p.side === 1 ? '◀' : '▶'}{p.hit ? '✓' : '✗'}</span>
  }
  return (
    <div style={{ marginTop: 16 }}>
      <div className="mono" style={{ padding: '10px 16px', borderRadius: 6, border: '1px solid var(--line)', fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.5, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <span>Every finished match from the frozen ledger, newest first — {hist.settled_total} settled. {full ? 'Full board cards, exactly as they looked pre-match (click a day to open).' : 'Compact rows: winner (green), frozen odds, and each model + MC pick (◀ p1 / ▶ p2; ✓ hit, ✗ miss).'} Read from the log, never recomputed.</span>
        <button onClick={() => setFull(f => !f)} className="mono" style={{ padding: '4px 12px', borderRadius: 12, fontSize: 10, cursor: 'pointer', border: '1px solid #e3b341', background: 'rgba(227,179,65,0.12)', color: '#e3b341', fontWeight: 700, whiteSpace: 'nowrap' }}>
          {full ? '☰ compact rows' : '▦ full cards'}
        </button>
      </div>
      {dates.map(d => {
        const hr = {}; const tot = {}
        const bump = (k, p) => { if (p) { tot[k] = (tot[k] || 0) + 1; hr[k] = (hr[k] || 0) + (p.hit ? 1 : 0) } }
        // 🎯 PER-DAY SIGNAL TALLY (2026-10-07, user "make sure all the new signals for
        // every board slip are added to the previous day tab so i can see how well it
        // does every day"): every board signal that fired on the day's games, with its
        // day record AND flat-1u PnL at the frozen odds (the side it bet).
        const sigT = {}
        for (const m of d.matches) {
          for (const [k, p] of Object.entries(m.models)) bump(k, p)
          bump('MC-D', m.mc); bump('C50', m.mc_c && m.mc_c.c50); bump('C75', m.mc_c && m.mc_c.c75); bump('CU', m.mc_c && m.mc_c.cutr)
          bump('OUR', m.our); bump('C-MC+c75', m.cmc_c75); bump('X', m.model_x); bump('MC2', m.mc2)
          for (const s of [...(m.signals || []), ...(m.conflicts || [])]) {
            const o = s.side === 1 ? m.p1_odds : m.p2_odds
            const dec = (o == null || o === 0) ? null : (o > 0 ? 1 + o / 100 : 1 + 100 / Math.abs(o))
            const t = sigT[s.label] || (sigT[s.label] = { w: 0, l: 0, pnl: 0, priced: 0 })
            if (s.hit) t.w++; else t.l++
            if (dec != null) { t.pnl += s.hit ? dec - 1 : -1; t.priced++ }
          }
        }
        const dayOpen = full && (openDate === d.date || q)
        const ourPct = tot['OUR'] ? Math.round(100 * hr['OUR'] / tot['OUR']) : null
        const takePct = tot['C-MC+c75'] ? Math.round(100 * hr['C-MC+c75'] / tot['C-MC+c75']) : null
        return (
          <div key={d.date} style={{ marginTop: 18 }}>
            <div className="mono" onClick={() => full && setOpenDate(openDate === d.date ? null : d.date)}
              style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', borderBottom: '1px solid var(--line)', paddingBottom: 4, display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, cursor: full ? 'pointer' : 'default' }}>
              <span>{full ? (dayOpen ? '▾ ' : '▸ ') : ''}{d.date} <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>· {d.matches.length} matches</span>
                {ourPct != null ? <span style={{ color: ourPct >= 50 ? '#3fb950' : '#f85149', marginLeft: 8 }} title="Our headline pick's win rate for the day (the favored side shown on each card).">· hit {hr['OUR']}/{tot['OUR']} ({ourPct}%)</span> : null}
                {takePct != null ? <span style={{ color: '#a78bfa', marginLeft: 8, fontWeight: 400 }} title="Your take: every game where c-MC (c50) and c75 agree — win rate for the day.">· C-MC+c75 take {hr['C-MC+c75']}/{tot['C-MC+c75']} ({takePct}%)</span> : null}
              </span>
              <span style={{ fontWeight: 400, fontSize: 10, color: 'var(--text-tertiary)' }}>
                {['A', 'B', 'C', 'gray', 'D', 'MC-D', 'C50', 'C75', 'CU', 'X', 'MC2'].filter(k => tot[k]).map(k => `${k} ${hr[k]}/${tot[k]}`).join(' · ')}
              </span>
            </div>
            {Object.keys(sigT).length ? (
              <div className="mono" style={{ fontSize: 9, marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 7, alignItems: 'center' }}
                title="🎯 THE DAY, PER SIGNAL — every board signal that fired on this day's finished games: day record (w-l) and flat-1u P/L at the frozen closing odds of the side it bet. Green = the signal made money that day, red = lost. Sorted best day first. Same frozen-log predicates as the board chips / 🏆 Best tab.">
                <span style={{ color: '#3fb950', fontWeight: 700 }}>🎯 day:</span>
                {Object.entries(sigT).sort((x, y) => y[1].pnl - x[1].pnl).map(([k, t]) => (
                  <span key={k} style={{ whiteSpace: 'nowrap', padding: '0 5px', borderRadius: 6, border: '1px solid rgba(255,255,255,0.06)', color: t.pnl > 0.02 ? '#3fb950' : t.pnl < -0.02 ? '#f85149' : 'var(--text-tertiary)' }}>
                    {k} {t.w}-{t.l}{t.priced ? ` ${t.pnl > 0 ? '+' : ''}${t.pnl.toFixed(1)}u` : ''}
                  </span>
                ))}
              </div>
            ) : null}
            {full ? (dayOpen ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 14 }}>
                {d.matches.map((m, i) => m.card ? <MatchCard key={i} match={{ ...m.card, mc2: m.card.mc2 || (m.mc2 ? { p1_prob: m.mc2.p1_pct / 100, recon: !!m.mc2.recon } : null) }} animDelay={Math.min(i * 0.03, 0.3)} laneRec={laneRec} showCMC={true} greenOnly={greenOnly} /> : null)}
              </div>
            ) : null) : d.matches.map((m, i) => (
              <div key={i} className="mono" style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 4px', borderBottom: '1px solid rgba(255,255,255,0.03)', fontSize: 11, flexWrap: 'wrap' }}>
                <span style={{ minWidth: 42, color: 'var(--text-tertiary)', fontSize: 9 }}>{m.league.toUpperCase()}</span>
                <span style={{ flex: 1, minWidth: 220 }}>
                  <span style={{ color: m.p1_won ? '#3fb950' : 'var(--text-secondary)', fontWeight: m.p1_won ? 700 : 400 }}>{m.p1} <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>{odds(m.p1_odds)}</span></span>
                  <span style={{ color: 'var(--text-tertiary)' }}> vs </span>
                  <span style={{ color: !m.p1_won ? '#3fb950' : 'var(--text-secondary)', fontWeight: !m.p1_won ? 700 : 400 }}>{m.p2} <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>{odds(m.p2_odds)}</span></span>
                  {m.score ? <span style={{ color: 'var(--text-tertiary)', fontSize: 10, marginLeft: 6 }} title="Final set score (player 1 first).">· {m.score}</span> : null}
                </span>
                <span style={{ display: 'flex', flexWrap: 'wrap' }}>
                  {chip('A', m.models.A)}{chip('B', m.models.B)}{chip('C', m.models.C)}{chip('gray', m.models.gray)}{chip('D', m.models.D)}
                  {m.model_x ? <span className="mono" title={`Model X (meta)${m.model_x.recon ? ' — walk-forward backfill, display-only (trained only on earlier games)' : ' — genuine frozen pick'}: ${m.model_x.p1_pct}% p1 — ${m.model_x.hit ? 'correct' : 'wrong'}`}
                    style={{ fontSize: 9, padding: '0 5px', borderRadius: 7, marginLeft: 3, border: `1px solid ${m.model_x.hit ? '#3fb95055' : '#f8514955'}`, color: m.model_x.hit ? '#3fb950' : '#f85149', background: m.model_x.hit ? '#3fb9500d' : '#f851490d', opacity: m.model_x.recon ? 0.6 : 1 }}>
                    {m.model_x.recon ? '~' : ''}X{m.model_x.side === 1 ? '◀' : '▶'}{m.model_x.hit ? '✓' : '✗'}</span> : null}
                  {m.mc2 ? <span className="mono" title={`🧮 MC v2${m.mc2.recon ? ' — ~ walk-forward BACKFILL: computed from the ratings as they stood the morning of the match (the result and everything after are excluded). Honest hindsight-free read, but display-only and NOT in the forward lanes' : ' (genuine frozen pre-match read)'}: ${m.mc2.p1_pct}% p1 — ${m.mc2.hit ? 'correct' : 'wrong'}. Display-only model; its real product is the 🎲 Sets tab.`}
                    style={{ fontSize: 9, padding: '0 5px', borderRadius: 7, marginLeft: 3, border: `1px solid ${m.mc2.hit ? '#bc8cff55' : '#f8514955'}`, color: m.mc2.hit ? '#d2a8ff' : '#f85149', background: m.mc2.hit ? 'rgba(188,140,255,0.06)' : '#f851490d', opacity: m.mc2.recon ? 0.6 : 1 }}>
                    {m.mc2.recon ? '~' : ''}🧮{m.mc2.side === 1 ? '◀' : '▶'}{m.mc2.hit ? '✓' : '✗'}</span> : null}
                  {m.mc ? <span className="mono" title={`Model-D serve Monte Carlo favored player ${m.mc.side} (${m.mc.p1_pct}% p1) — ${m.mc.hit ? 'correct' : 'wrong'}`}
                    style={{ fontSize: 9, padding: '0 5px', borderRadius: 7, marginLeft: 3, border: `1px solid ${m.mc.hit ? '#3fb95055' : '#f8514955'}`, color: m.mc.hit ? '#3fb950' : '#f85149', background: m.mc.hit ? '#3fb9500d' : '#f851490d' }}>⚄D{m.mc.side === 1 ? '◀' : '▶'}{m.mc.hit ? '✓' : '✗'}</span> : null}
                </span>
                {m.mc_c && (m.mc_c.c50 || m.mc_c.c75 || m.mc_c.cutr) ? (
                  <div className="mono" style={{ width: '100%', fontSize: 9, marginTop: 1, paddingLeft: 50, color: '#a78bfa', opacity: m.mc_c.recon ? 0.7 : 1 }}
                    title={`Model-C Monte Carlo, all three anchorings (p1 win %, ◀/▶ = side, ✓/✗ = result).${m.mc_c.recon ? ' ~ = reconstructed after the fact from the frozen Model C (display-only, not counted in the forward lanes).' : ' Genuine forward pick.'}`}>
                    {m.mc_c.recon ? '~' : ''}⚄ C-MC:
                    {[['c50', m.mc_c.c50], ['c75', m.mc_c.c75], ['cUTR', m.mc_c.cutr]].map(([lbl, p], j) => p ? (
                      <span key={lbl} style={{ color: p.hit ? '#3fb950' : '#f85149', marginLeft: 5 }}>
                        {j ? '· ' : ''}{lbl} {p.p1_pct}%{p.side === 1 ? '◀' : '▶'}{p.hit ? '✓' : '✗'}
                      </span>
                    ) : null)}
                  </div>
                ) : null}
                {m.conflicts && m.conflicts.length ? (
                  <div className="mono" style={{ width: '100%', fontSize: 9, marginTop: 1, paddingLeft: 50, display: 'flex', flexWrap: 'wrap', gap: 3, alignItems: 'center' }}
                    title="⚖️ Conflict-resolver verdicts (which side the gender-specific rule said to trust when signals disagreed) and whether that side won — from the frozen log, same rules as the dark-purple board badges.">
                    {m.conflicts.map((g, j) => (
                      <span key={j} style={{ fontSize: 8.5, fontWeight: 700, padding: '0 5px', borderRadius: 6, background: g.hit ? '#4c1d95' : '#3b1053', border: `1px solid ${g.hit ? '#7c3aed' : '#7c3aed66'}`, color: g.hit ? '#ddd6fe' : '#a78bfa99' }}>
                        {g.label}{g.side === 1 ? '◀' : '▶'}{g.hit ? '✓' : '✗'}
                      </span>
                    ))}
                  </div>
                ) : null}
                {m.signals && m.signals.length ? (
                  <div className="mono" style={{ width: '100%', fontSize: 9, marginTop: 1, paddingLeft: 50, display: 'flex', flexWrap: 'wrap', gap: 3, alignItems: 'center' }}
                    title="New elite board-signals that fired on this finished game (side ◀ p1 / ▶ p2, ✓ hit / ✗ miss) — read from the frozen log, same predicates as the 🏆 Best tab and the live board chips.">
                    <span style={{ color: '#3fb950', fontWeight: 700 }}>🎯</span>
                    {m.signals.map((g, j) => (
                      <span key={j} style={{ fontSize: 8.5, padding: '0 4px', borderRadius: 6, border: `1px solid ${g.hit ? '#3fb95055' : '#f8514955'}`, color: g.hit ? '#3fb950' : '#f85149', background: g.hit ? '#3fb9500d' : '#f851490d' }}>
                        {g.label}{g.side === 1 ? '◀' : '▶'}{g.hit ? '✓' : '✗'}
                      </span>
                    ))}
                  </div>
                ) : null}
                {m.postmortem ? (
                  <div className="mono" style={{ width: '100%', fontSize: 9, marginTop: 1, paddingLeft: 50, color: 'var(--text-tertiary)' }}
                    title="Model X post-mortem: who won, whether the market's favorite was right, and 'missed' = the signals we had that DID point to the actual winner when the market's favorite lost.">
                    📋 won: {m.postmortem.won_player === 1 ? m.p1.split(' ').slice(-1)[0] : m.p2.split(' ').slice(-1)[0]} ·
                    market <span style={{ color: m.postmortem.market_right ? '#3fb950' : '#f85149' }}>{m.postmortem.market_right ? 'right' : 'wrong'}</span>
                    {m.model_x ? <> · X <span style={{ color: m.model_x.hit ? '#3fb950' : '#f85149', opacity: m.model_x.recon ? 0.65 : 1 }} title={m.model_x.recon ? 'walk-forward backfill (trained only on earlier games) — display-only, not in the forward lanes' : 'genuine forward pick'}>{m.model_x.recon ? '~' : ''}{m.model_x.p1_pct}%{m.model_x.side === 1 ? '◀' : '▶'}{m.model_x.hit ? '✓' : '✗'}</span></> : null}
                    {m.mc2 ? <> · 🧮 <span style={{ color: m.mc2.hit ? '#d2a8ff' : '#f85149', opacity: m.mc2.recon ? 0.65 : 1 }} title={m.mc2.recon ? 'walk-forward backfill (pre-match ratings only; result never used) — display-only' : "MC v2's genuine frozen pre-match read"}>{m.mc2.recon ? '~' : ''}{m.mc2.p1_pct}%{m.mc2.side === 1 ? '◀' : '▶'}{m.mc2.hit ? '✓' : '✗'}</span></> : null}
                    {m.postmortem.missed_info && m.postmortem.missed_info.length
                      ? <span style={{ color: '#e3b341' }}> · missed: {m.postmortem.missed_info.join(', ')}</span> : null}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        )
      })}
      {dates.length === 0 ? <div className="mono" style={{ color: 'var(--text-tertiary)', padding: 30, textAlign: 'center' }}>No finished matches{q ? ' match that search' : ''} yet.</div> : null}
    </div>
  )
}

// 📊 TAB P/L (2026-10-08, user "a separate tab that tracks daily profit taking every bet
// on the best tab and on the prices tab and comparing which one makes more"): flat 1u on
// EVERY 🏆 Best-tab pick vs EVERY 💰 Prices-tab pick (the sweet-priced subset), per day
// from the frozen ledger, head-to-head. Server-computed (/api/tennis/tab-profit) with the
// same gates/long-dog rules as the tabs themselves.
// 🎲 SET-MARKET SCANNER (2026-10-08): MC v2's anchored distribution engine priced vs
// Polymarket's tennis derivative books. NEW + UNPROVEN: flags are logged for forward
// CLV/settlement before anyone trusts them with money — the header says so.
function SetScanPanel() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    const go = () => fetch('/api/tennis/set-scan').then(r => r.json()).then(setD).catch(e => setErr(String(e)))
    go(); const id = setInterval(go, 180000); return () => clearInterval(id)
  }, [])
  if (err) return <div className="mono" style={{ color: 'var(--edge-neg)', padding: 20 }}>Couldn't load ({err})</div>
  if (!d) return <div className="mono" style={{ color: 'var(--text-secondary)', padding: 40, textAlign: 'center' }}>pricing set markets…</div>
  const fl = d.flags || []
  return (
    <div style={{ marginTop: 16 }}>
      <div className="mono" style={{ padding: '10px 16px', borderRadius: 6, border: '1px solid #a78bfa55', background: 'rgba(167,139,250,0.06)', fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.5 }}>
        <b style={{ color: '#a78bfa' }}>🎲 SET MARKETS — MC v2 anchored engine vs Polymarket's derivative books</b> ({d.priced}/{d.scanned} matches priced). The engine takes the <b>sharp no-vig moneyline</b> (OpticOdds consensus when we have it — the [sharp] tag) and adds the validated match structure (day-form calibrated: 3-setters 33.9% vs 34.7% real, TB 27.1 vs 27.6, games 22.1 vs 22.2 on 20k score lines) → prices every set/total/handicap market. <b>BUY</b> = cross the book's ask now; <b>POST</b> = the maker price to leave as a limit order instead (on thin books, posting turns the spread into edge). <b style={{ color: '#e3b341' }}>⚠ BRAND NEW + UNPROVEN</b>: every flag is logged for forward CLV/settlement — treat as paper until the log earns a record. Auto-refresh 3 min.
      </div>
      {d.record && d.record.n ? (
        <div className="mono" style={{ marginTop: 8, padding: '7px 12px', borderRadius: 6, border: `1px solid ${d.record.pnl >= 0 ? '#3fb95055' : '#f8514955'}`, background: d.record.pnl >= 0 ? 'rgba(63,185,80,0.06)' : 'rgba(248,81,73,0.05)', fontSize: 10.5 }}
          title="The forward record: every flag auto-settles from the match's real score string once it resolves (taker basis — buying the book's ask at flag time; a maker fill at the post price can't be verified after the fact, so it isn't counted). Retirements/walkovers void. PnL is per-share units: win = 1 − buy price, loss = −buy price.">
          📒 <b>settled record:</b> <b style={{ color: d.record.pnl >= 0 ? '#3fb950' : '#f85149' }}>{d.record.wins}-{d.record.n - d.record.wins} · {d.record.pnl >= 0 ? '+' : ''}{d.record.pnl}u</b> (taker, flat 1-share)
          {Object.entries(d.record.by_market || {}).map(([k, v]) => (
            <span key={k} style={{ marginLeft: 10, color: 'var(--text-tertiary)', fontSize: 9 }}>{k}: <span style={{ color: v.pnl >= 0 ? '#3fb950' : '#f85149' }}>{v.wins}-{v.n - v.wins} {v.pnl >= 0 ? '+' : ''}{v.pnl}u</span></span>
          ))}
        </div>
      ) : null}
      <div className="mono" style={{ display: 'flex', fontSize: 9, color: 'var(--text-tertiary)', padding: '8px 10px 3px', borderBottom: '1px solid var(--line)' }}>
        <span style={{ width: 52 }}>edge</span><span style={{ flex: 1.3 }}>market · side</span><span style={{ width: 92 }}>our / buy / post</span><span style={{ flex: 1.5 }}>match</span><span style={{ width: 46 }}>anchor</span>
      </div>
      {fl.map((f, i) => (
        <div key={i} className="mono" style={{ display: 'flex', alignItems: 'center', fontSize: 10.5, padding: '5px 10px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
          <span style={{ width: 52, fontWeight: 800, color: f.edge >= 0.10 ? '#a78bfa' : '#8b949e' }}>+{Math.round(f.edge * 100)}¢</span>
          <span style={{ flex: 1.3 }}>{f.market} · <b style={{ color: 'var(--text-primary)' }}>{f.side}</b></span>
          <span style={{ width: 92, color: 'var(--text-secondary)' }}>{f.our_p.toFixed(2)} / {f.buy_at.toFixed(2)} / <b style={{ color: '#3fb950' }}>{f.post_at.toFixed(2)}</b></span>
          <span style={{ flex: 1.5, color: 'var(--text-secondary)' }}>{f.match}</span>
          <span style={{ width: 46, fontSize: 8.5, color: f.anchor === 'sharp' ? '#3fb950' : 'var(--text-tertiary)' }}>{f.anchor}</span>
        </div>
      ))}
      {!fl.length ? <div className="mono" style={{ padding: 24, textAlign: 'center', color: 'var(--text-tertiary)' }}>No liquid derivative edges right now.</div> : null}
    </div>
  )
}

function TabProfitPanel() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    const go = () => fetch('/api/tennis/tab-profit').then(r => r.json()).then(setD).catch(e => setErr(String(e)))
    go(); const id = setInterval(go, 120000); return () => clearInterval(id)
  }, [])
  if (err) return <div className="mono" style={{ color: 'var(--edge-neg)', padding: 20 }}>Couldn't load ({err})</div>
  if (!d) return <div className="mono" style={{ color: 'var(--text-secondary)', padding: 40, textAlign: 'center' }}>replaying both tabs…</div>
  const t = d.totals || {}
  const fp = v => `${v > 0 ? '+' : ''}${(v ?? 0).toFixed(1)}u`
  const pc = v => (v > 0.05 ? '#3fb950' : v < -0.05 ? '#f85149' : 'var(--text-tertiary)')
  const bb = t.best || {}, pp = t.prices || {}
  const leader = (bb.pnl ?? 0) === (pp.pnl ?? 0) ? null : ((bb.pnl ?? 0) > (pp.pnl ?? 0) ? 'best' : 'prices')
  const cell = (x) => x && x.n
    ? <span><b style={{ color: pc(x.pnl) }}>{fp(x.pnl)}</b> <span style={{ color: 'var(--text-tertiary)' }}>({x.w}-{x.n - x.w}{x.roi_pct != null ? ` · ${x.roi_pct > 0 ? '+' : ''}${x.roi_pct}%` : ''})</span></span>
    : <span style={{ color: 'var(--text-tertiary)' }}>—</span>
  return (
    <div style={{ marginTop: 16 }}>
      <div className="mono" style={{ padding: '10px 16px', borderRadius: 6, border: '1px solid #e3b34155', background: 'rgba(227,179,65,0.05)', fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.5 }}>
        <b style={{ color: '#e3b341' }}>📊 TAB P/L</b> — flat <b>1u on every pick</b>, judged at the frozen closing odds: the full <b style={{ color: '#3fb950' }}>🏆 Best tab</b> vs the <b style={{ color: '#e3b341' }}>💰 Prices tab</b> (its sweet-priced subset: men +100…+250 / −300…−600 / ALL-10 −140…−300, women +100…+250). Same gates, same long-dog exclusion as the live tabs. NOTE: the signal gates use the CURRENT lane records, so past days are a faithful reconstruction (the gate drifts a little as lanes update), and recent days keep filling in as matches settle. Auto-refresh 2 min.
      </div>
      <div className="mono" style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 12, padding: '12px 16px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--panel)', alignItems: 'center' }}>
        <div>
          <div style={{ fontSize: 9, color: 'var(--text-tertiary)' }}>🏆 BEST — {bb.n} bets</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: pc(bb.pnl) }}>{fp(bb.pnl)}</div>
          <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>{bb.w}-{(bb.n ?? 0) - (bb.w ?? 0)} · ROI {bb.roi_pct > 0 ? '+' : ''}{bb.roi_pct}%</div>
        </div>
        <div style={{ fontSize: 16, color: 'var(--text-tertiary)' }}>vs</div>
        <div>
          <div style={{ fontSize: 9, color: 'var(--text-tertiary)' }}>💰 PRICES — {pp.n} bets</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: pc(pp.pnl) }}>{fp(pp.pnl)}</div>
          <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>{pp.w}-{(pp.n ?? 0) - (pp.w ?? 0)} · ROI {pp.roi_pct > 0 ? '+' : ''}{pp.roi_pct}%</div>
        </div>
        {leader ? (
          <div className="mono" style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 800, padding: '6px 12px', borderRadius: 8, border: `1px solid ${leader === 'best' ? '#3fb950' : '#e3b341'}`, color: leader === 'best' ? '#3fb950' : '#e3b341', background: leader === 'best' ? 'rgba(63,185,80,0.10)' : 'rgba(227,179,65,0.10)' }}
            title={`Which strategy has made more total profit over the window shown, flat 1u per pick. Days won: Best ${t.best_days_won} · Prices ${t.prices_days_won}.`}>
            {leader === 'best' ? '🏆 BEST is ahead' : '💰 PRICES is ahead'} · days {t.best_days_won}-{t.prices_days_won}
          </div>
        ) : null}
      </div>
      <div className="mono" style={{ display: 'flex', fontSize: 9, color: 'var(--text-tertiary)', padding: '8px 10px 3px', borderBottom: '1px solid var(--line)', marginTop: 10 }}>
        <span style={{ width: 90 }}>date</span>
        <span style={{ flex: 1 }}>🏆 BEST (every pick)</span>
        <span style={{ flex: 1 }}>💰 PRICES (sweet only)</span>
        <span style={{ width: 70, textAlign: 'right' }}>day winner</span>
      </div>
      {(d.days || []).map((row, i) => {
        const win = row.best.pnl === row.prices.pnl ? null : (row.best.pnl > row.prices.pnl ? 'best' : 'prices')
        return (
          <div key={i} className="mono" style={{ display: 'flex', alignItems: 'center', fontSize: 11, padding: '6px 10px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
            <span style={{ width: 90, color: 'var(--text-secondary)' }}>{row.date}</span>
            <span style={{ flex: 1 }}>{cell(row.best)}</span>
            <span style={{ flex: 1 }}>{cell(row.prices)}</span>
            <span style={{ width: 70, textAlign: 'right', fontSize: 10, fontWeight: 700, color: win === 'best' ? '#3fb950' : win === 'prices' ? '#e3b341' : 'var(--text-tertiary)' }}>
              {win === 'best' ? '🏆' : win === 'prices' ? '💰' : '—'}
            </span>
          </div>
        )
      })}
      <div className="mono" style={{ fontSize: 9, color: 'var(--text-tertiary)', padding: '8px 10px' }}>
        Prices is a subset of Best — when 💰 wins a day it means the non-sweet-priced picks LOST that day (the filter earned its keep); when 🏆 wins, the extra volume outside the windows was profitable.
      </div>
    </div>
  )
}

function NoPredictionRow({ match }) {
  return (
    <div style={{
      background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 8,
      padding: '10px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap',
    }}>
      <span className="mono" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
        {match.player_1} vs {match.player_2}
        <span style={{ color: 'var(--text-tertiary)' }}> — {match.tournament}</span>
      </span>
      <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>{match.note}</span>
    </div>
  )
}

// TennisRatio context row (2026-09-25, user ask): surface form + opponent-adjusted recent
// record per player, from ingested tennisratio.com match logs. CONTEXT ONLY — backtested
// 2026-09-25: none of it beats the market's calibration (opponent-adjusted included), so it
// never colors or drives a pick; it exists so a human can eyeball who they've actually been
// beating on this surface next to the price.
function TrContextRow({ name, ctx }) {
  if (!ctx || !ctx.surface_stats) return null
  const s = ctx.surface_stats
  const vt = ctx.vs_top200
  const pool = ctx.tour ? ctx.tour.toUpperCase() : 'pool'
  return (
    <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', lineHeight: 1.5 }}>
      <span style={{ color: 'var(--text-secondary)' }}>{name}</span>
      {` — ${ctx.surface_used.toLowerCase()} ${s.window || ''}:`}
      {s.sv1 != null ? ` 1stSv ${s.sv1}%` : ''}
      {s.sv2 != null ? ` · 2ndSv ${s.sv2}%` : ''}
      {s.sgw != null ? ` · SGW ${s.sgw}%${s.sgw_pct != null ? ` (p${s.sgw_pct} ${pool})` : ''}` : ''}
      {s.rgw != null ? ` · RGW ${s.rgw}%${s.rgw_pct != null ? ` (p${s.rgw_pct} ${pool})` : ''}` : ''}
      {` · win ${(s.win * 100).toFixed(0)}% (${s.n})`}
      {vt && (vt.w + vt.l) > 0 ? ` · vs top-200: ${vt.w}-${vt.l}` : ''}
      {ctx.clutch != null ? ` · clutch ${(ctx.clutch * 100).toFixed(0)}%` : ''}
      {ctx.avg_opp_rank != null ? ` · avg opp #${ctx.avg_opp_rank}` : ''}
    </div>
  )
}

function MatchCard({ match, animDelay, laneRec, greenOnly = false, showCMC = false }) {
  const [showFeatures, setShowFeatures] = useState(false)
  const predSrc = match.prediction ? 'main' : (match.model_a ? 'A' : match.model_b ? 'B' : match.model_c ? 'C' : match.model_i ? 'I' : 'D')
  // fall through every available model so a card with only Model I/C/D (ITF gap players,
  // no A/B) still renders instead of crashing the whole tab on a null pred (2026-10-02).
  const pred = match.prediction
    || (match.model_a ? { player_1_win_prob: match.model_a.p1_prob } : null)
    || (match.model_b ? { player_1_win_prob: match.model_b.p1_prob } : null)
    || (match.model_c ? { player_1_win_prob: match.model_c.p1_prob } : null)
    || (match.model_i ? { player_1_win_prob: match.model_i.p1_prob } : null)
    || (match.model_d ? { player_1_win_prob: match.model_d.p1_prob } : null)
    || { player_1_win_prob: 0.5 }
  const leagueColor = LEAGUE_COLOR[match.league] || 'var(--amber)'
  const surfaceColor = SURFACE_COLOR[match.surface] || 'var(--text-tertiary)'

  const p1Prob = pred.player_1_win_prob
  const favoredIsP1 = p1Prob >= 0.5
  const favoredName = favoredIsP1 ? match.player_1 : match.player_2
  const favoredProb = favoredIsP1 ? p1Prob : 1 - p1Prob
  // headline is MODEL A by default now (original model retired 9/28) -- only tag the rare B fallback
  const headlineTag = predSrc !== 'B' ? null : (
    <span className="mono" style={{ fontSize: 9, color: '#d29922', marginLeft: 6 }}
      title="No Model A read for a player -- headline % is TENNIS MODEL B (display-only).">
      via MODEL B
    </span>
  )

  // Name highlights (2026-09-29, user ask): the gray line's pick (C MKT-AWARE ALL side)
  // in DARK green on every card; when C AND the gray line both land on the market DOG
  // (the ★ C+GRAY DOG cell, +13.7% in 2026), that dog's name in BRIGHT green.
  const mc3 = match.model_c
  const cmaP1 = mc3 && mc3.market_aware_p1 != null ? mc3.market_aware_p1 >= 0.5 : null
  const starDogP1 = !!(mc3 && mc3.market_aware_p1 != null && mc3.market_p1 != null
    && (mc3.p1_prob >= 0.5) === (mc3.market_aware_p1 >= 0.5)
    && ((mc3.market_aware_p1 >= 0.5) ? mc3.market_p1 < 0.5 : mc3.market_p1 >= 0.5))
  const starDogSideP1 = starDogP1 ? (mc3.market_aware_p1 >= 0.5) : null
  // RED = the pass-config (2026-09-29, user ask, the Andrade Da Silva/Olivieri case):
  // C alone against A and B, gray confirms C, but C's side is the market FAVORITE --
  // the thin half of the cell (+3% backtest at soft odds, 2-2 live). Not a take, not a
  // fade: the lane bets its $25; you pass.
  const ma3 = match.model_a
  const mb3 = match.model_b
  const passFavP1 = (() => {
    if (!mc3 || !ma3 || !mb3) return null
    if (ma3.p1_prob == null || mb3.p1_prob == null || mc3.market_aware_p1 == null || mc3.market_p1 == null) return null
    const c1 = mc3.p1_prob >= 0.5
    if ((mc3.market_aware_p1 >= 0.5) !== c1) return null
    if ((ma3.p1_prob >= 0.5) === c1 || (mb3.p1_prob >= 0.5) === c1) return null
    const sideMkt = c1 ? mc3.market_p1 : 1 - mc3.market_p1
    return sideMkt >= 0.5 ? c1 : null
  })()
  // Additional RED flags (2026-09-29, user ask: red-highlight every negative-live config):
  // C's side of a C-vs-gray FIGHT (C-side lane deep red live; covers unconfirmed C-alone and
  // most losing C-EDGE picks) and the GRAY-HATED DOG (11-37, -33% live). Greens take
  // precedence -- they are mutually exclusive with these by construction.
  const fightCSideP1 = (mc3 && mc3.market_aware_p1 != null
    && (mc3.p1_prob >= 0.5) !== (mc3.market_aware_p1 >= 0.5)) ? (mc3.p1_prob >= 0.5) : null
  const hateDogP1 = (() => {
    if (!mc3 || mc3.market_aware_p1 == null || mc3.market_p1 == null) return null
    const dog1 = mc3.market_p1 < 0.5
    const mdog = dog1 ? mc3.market_p1 : 1 - mc3.market_p1
    const gdog = dog1 ? mc3.market_aware_p1 : 1 - mc3.market_aware_p1
    return (mdog - gdog) >= 0.02 ? dog1 : null
  })()
  const nameHighlight = isP1 => {
    if (starDogSideP1 !== null && starDogSideP1 === isP1) {
      return { color: '#f5f13b', title: '★ C+GRAY DOG: Model C AND the market-aware gray line both pick this market underdog — the best backtest cell of the build (54.8% at plus prices, +13.7% in 2026). Feeds the ★ lane.' }
    }
    if (hateDogP1 !== null && hateDogP1 !== isP1) {
      return { color: '#f5f13b', title: 'TAKE — FADE the gray-hated dog: the opponent is a dog the gray line prices 2+ pts UNDER market (bait). Backing this favorite is the one favorite config that tests positive: 38-11 (+10.5%) live, +3-5% expected long-run. Thin edge — only at the listed price or better.' }
    }
    // Red name-colors only in FULL-BOARD mode (green-only hides them; lanes still run).
    if (!greenOnly && fightCSideP1 !== null && fightCSideP1 === isP1) {
      return { color: '#f85149', title: 'RED — C without gray backing: raw C picks this side but the gray line disagrees. Live: C’s side of these fights is deeply negative and unconfirmed C-alone went 0-4. Do not take.' }
    }
    if (!greenOnly && hateDogP1 !== null && hateDogP1 === isP1) {
      return { color: '#f85149', title: 'RED — GRAY-HATED DOG: the gray line prices this underdog 2+ points UNDER its market number. These dogs won 27% in backtest (−25 to −31%/bet) and are deeply negative live. The plus price is bait.' }
    }
    if (!greenOnly && passFavP1 !== null && passFavP1 === isP1) {
      return { color: '#f85149', title: 'RED — C+GRAY FAVORITE: C alone, gray confirms, but the side is the market FAVORITE. Live −6.7% on 31 settles (the C-alone+gray DOG half is +40%, the favorite half is not). No bet; do not fade either.' }
    }
    if (cmaP1 !== null && cmaP1 === isP1) {
      return { color: '#15803d', title: 'C MKT-AWARE pick: the gray line’s favored side — the best single estimate of the true win probability (the only head that beat the raw market in validation). Feeds the C MKT-AWARE ALL lane.' }
    }
    return null
  }
  const h1 = nameHighlight(true)
  const h2 = nameHighlight(false)
  // top-right CATEGORY badge (2026-09-30, user ask): which lane family this match falls
  // under, with that lane's live record + backtest. Same precedence as the name colors.
  const catBadge = (() => {
    const stx = (laneRec && laneRec.study) || {}
    const lv = v => (v && v.n ? `${v.roi_pct > 0 ? '+' : ''}${Math.round(v.roi_pct)}% (${v.wins}-${v.n - v.wins})` : '0 settled')
    // SIDE-SPLIT top badge (2026-10-07, user "the fade gold at the top doesn't split
    // favorites and underdogs"): mk takes the SIDE the badge bets; the live record is
    // that side's gender×side cell (not the gender blend) and wears its 🐕/⭐ icon.
    const mk = (txt, color, bt, liveV, tip, side) => ({
      txt, color, bt,
      live: lv(liveV) + (typeof side === 'boolean' ? ((side === dog1x) ? ' 🐕' : ' ⭐') : ''),
      tip,
    })
    if (!mc3 || mc3.market_aware_p1 == null || mc3.market_p1 == null) {
      return { txt: 'NO MODEL', color: 'var(--text-tertiary)', bt: '', live: '', tip: 'A player is missing from the TennisRatio pool — no model reads.' }
    }
    const c1x = mc3.p1_prob >= 0.5
    const g1x = mc3.market_aware_p1 >= 0.5
    const dog1x = mc3.market_p1 < 0.5
    // Fully gendered badges (2026-09-30, user ask "everything computed separate"):
    // each badge shows THIS match's gender slice of its lane.
    const bW = match.league === 'wta'
    const bg = L => (L ? (bW ? L.w : L.m) : null)
    // gender×side cell for the side the badge bets; falls back to the gender slice
    // for lanes without crossed cells.
    const bgs = (L, side) => {
      if (!L) return null
      const ck = (bW ? 'w' : 'm') + ((side === dog1x) ? '_dog' : '_fav')
      return (L[ck] && L[ck].n !== undefined) ? L[ck] : bg(L)
    }
    const gtag = bW ? 'W' : 'M'
    // Gendered bt26 in parentheses (2026-09-30): from _tennis_gender_full_bt.py.
    const b26b = (m, w) => `(bt26 ${bW ? w : m})`
    const alone = ma3 && mb3 && ma3.p1_prob != null && mb3.p1_prob != null
      && (ma3.p1_prob >= 0.5) !== c1x && (mb3.p1_prob >= 0.5) !== c1x
    if (c1x === g1x && g1x === dog1x) {
      if (alone) return mk(`★ C-ALONE+GRAY DOG ${gtag}`, '#f5f13b', b26b('+13.3%', '+44.4%'), bgs(stx.c_alone_gray_dog, dog1x), 'Best cell in the build. Gendered 2026 backtest: men +13.3% (452-437), women +44.4% (57-38). Live record = this match’s gender DOG cell.', dog1x)
      const gEdge = dog1x ? mc3.market_aware_p1 - mc3.market_p1 : mc3.market_p1 - mc3.market_aware_p1
      if (gEdge >= 0.04) return mk(`★ C+GRAY DOG 4pt+ ${gtag}`, '#f5f13b', b26b('+11.1%', '+35.1%'), bgs(laneRec && laneRec.agree_dog, dog1x), 'Gendered 2026 backtest: men +11.1% (1,027-987), women +35.1% (133-91). Positive every year. Live record = this match’s gender DOG cell.', dog1x)
      return mk(`★ C+GRAY DOG ${gtag}`, '#f5f13b', b26b('+12.0%', '+33.6%'), bgs(laneRec && laneRec.agree_dog, dog1x), 'Gendered 2026 backtest: men +12.0% (1,021-946), women +33.6% (125-87). Positive every year. Live record = this match’s gender DOG cell.', dog1x)
    }
    const mdogx = dog1x ? mc3.market_p1 : 1 - mc3.market_p1
    const gdogx = dog1x ? mc3.market_aware_p1 : 1 - mc3.market_aware_p1
    if (mdogx - gdogx >= 0.02) {
      return mk(`⭐✓ FADE-GOLD ${gtag}`, '#f5f13b', b26b('+1.0%', '+9.4%'), bgs(stx.grayhate_fav, !dog1x), `Favorite over a gray-hated dog — one of the THREE favorite cells positive in the full gender×side backtest (with C-EDGE 5pt FAV and women's D-MA 2pt FAV). Gendered 2026 backtest: men +1.0% (thin), women +9.4% — but live W is negative (watch). Live record = this match’s gender ⭐ FAVORITE cell (the badge bets the fav). The dog side is the documented loser (men bt26 −22.8, women −41.8; live ${lv(bgs(stx.grayhate_dog, dog1x))} 🐕).`, !dog1x)
    }
    if (alone && g1x === c1x && c1x !== dog1x) {
      return mk(`RED: C+GRAY FAV ${gtag}`, '#f85149', b26b('+1.5%', '+2.6%'), bgs(stx.c_alone_gray_fav, c1x), 'C alone + gray on the market FAVORITE — DEMOTED to avoid (2026-10-02, user call): live −6.7% on 31 settles. The dog half of C-alone+gray is the +40% play; the favorite half loses. No bet.', c1x)
    }
    if (c1x !== g1x) {
      return mk(`RED: C-vs-GRAY ${gtag}`, '#f85149', b26b('−1.3%', '+2.3%'), bgs(stx.cvg_c, c1x), `Raw C fights the gray line — C’s side decayed to ≈0 in 2026 (men −1.3, women +2.3 thin). Live record = C’s side’s gender×side cell. Gray’s side: men bt26 −8.0, women −6.6, live ${lv(bgs(stx.cvg_gray, g1x))}, on watch to 30 settles.`, c1x)
    }
    // Gender-aware since 2026-09-30 (user ask, matching the gold 5pt+ chips): the badge
    // shows THIS match's gender slice of the green-names lane, not the blend.
    const gnIsW = match.league === 'wta'
    return mk(`NO SIGNAL ${gnIsW ? 'W' : 'M'}`, 'var(--text-tertiary)', b26b('−8.7%', '−8.0%'), bgs(stx.green_names, g1x), 'No lane fires — market and models roughly agree. Dark green = probable winner only, NOT a bet (gendered 2026 backtest: men −8.7%, women −8.0%). Record shown is the green-names lane’s gender×side cell for gray’s side on this match.', g1x)
  })()
  // GREEN-ONLY mode (2026-10-02, user ask): a red/avoid category badge renders as a
  // neutral NO BET while live samples mature (the lanes still track in the background).
  const catShow = (greenOnly && catBadge && catBadge.color === '#f85149')
    ? { txt: 'NO BET', color: 'var(--text-tertiary)', bt: '', live: '',
        tip: 'Red/avoid signal hidden while live ROIs are small (green-only mode). No take here.' }
    : catBadge

  const odds = match.live_odds
  const marketFavoredProb = useMemo(() => {
    if (!odds) return null
    const p1Implied = americanOddsToImpliedProb(String(odds.player_1))
    const p2Implied = americanOddsToImpliedProb(String(odds.player_2))
    if (p1Implied == null || p2Implied == null) return null
    // de-vig
    const total = p1Implied + p2Implied
    const p1Fair = p1Implied / total
    return favoredIsP1 ? p1Fair : 1 - p1Fair
  }, [odds, favoredIsP1])

  const edge = marketFavoredProb != null ? favoredProb - marketFavoredProb : null

  // 🟠 MC2 5-8pt DOG-EDGE GAMES (2026-10-08, user "start highlighting those games the
  // full card orange so i can see those games"): MC2 prices the market DOG 5-8 points
  // over the market. Replay context (retro month): taking the FAVORITE here ran +5.6%
  // (114-42) — but the neighboring bands were negative (no dose-response), so this is
  // a WATCH highlight, not a bet mark; the mc2e58_fav lane is scoring it live.
  const mc2DogEdge = (() => {
    if (!match.mc2 || match.mc2.p1_prob == null || !mc3 || mc3.market_p1 == null) return null
    const d1 = mc3.market_p1 < 0.5
    return (d1 ? match.mc2.p1_prob : 1 - match.mc2.p1_prob) - (d1 ? mc3.market_p1 : 1 - mc3.market_p1)
  })()
  const orange58 = mc2DogEdge != null && mc2DogEdge >= 0.05 && mc2DogEdge < 0.08
  // 🏛 TIER-1 BEDROCK BLUE (2026-10-08, user "make sure these are full highlighted"):
  // the cells positive in BOTH the 2024-26 walk-forward backtest AND the live log —
  // GRAY 4pt+ DOG (bt26 M +11.1/W +35.1, live +11.0%), STAR/TIER-1 dogs (M +12/W +34.7,
  // live +11-14.5%), C-ALONE+GRAY DOG (M +13.3/W +44.4, live +6.1%), FADE-A DOG+GRAY
  // (M +19.8/W +23.3, live thin), and the women's C-EDGE5 FAV (+11.0% held 3 years).
  // Full-card blue; bait-green outranks it when both fire.
  // 💜 C-ALONE+GOLD SHALLOW FAV (2026-10-08, user "mark both men and women to take,
  // purple full highlighted slip"): C ALONE against A and B, gray line confirms, and
  // C's side is a -100..-150 FAVORITE. Backtest (walk-forward, archive odds): men
  // REMEASURED 2026-10-08 (true gender + single-count): men all-years +8.1%
  // (288-180, n=468), 2026 +17.0% (96-48, n=144) -- strongest 2026 fav cell;
  // women +18.6%/+21.8% in 2024-25 then -19.6% 2026 (n=13). Live all-price lane:
  // men -9.1% (62), women +7.9% (13) -- NOT yet confirmed live; the banded
  // cgf_shallow_fav lane scores this exact mark forward. User call 2026-10-08.
  const purpleCGF = (() => {
    if (!mc3 || !ma3 || !mb3 || ma3.p1_prob == null || mb3.p1_prob == null
        || mc3.p1_prob == null || mc3.market_aware_p1 == null || mc3.market_p1 == null) return null
    const c1 = mc3.p1_prob >= 0.5
    if ((ma3.p1_prob >= 0.5) === c1 || (mb3.p1_prob >= 0.5) === c1) return null
    if ((mc3.market_aware_p1 >= 0.5) !== c1) return null
    const dog1 = mc3.market_p1 < 0.5
    if (c1 === dog1) return null
    const od = match.live_odds ? Number(c1 ? match.live_odds.player_1 : match.live_odds.player_2) : null
    if (od == null || isNaN(od) || od < -150 || od > -100) return null
    const isW = match.league === 'wta' || match.league === 'itf_women'
    return { name: c1 ? match.player_1 : match.player_2, od, isW }
  })()
  // 💜 C-EDGE5 DEEP FAV (2026-10-08, user "mark both men and women games highlighted
  // purple as well with the live roi and backtested roi and how many games"): raw C
  // prices the favorite >=5pts over the market, fav at -150..-200 — the strongest
  // favorite cell in the backtest. REMEASURED 2026-10-08 (true gender + single-
  // count): MEN 2026 +10.8% (327-139, n=466), all-years +5.9% (n=1,453); WOMEN
  // 2026 +5.0% (208-106), all-years +10.8% (n=846) -- SURVIVED the correction. (old:
  // n=660, biggest positive fav sample ever scanned), WOMEN +6.9% (40-19, n=59);
  // 3yr: M +8.1% (n=1,902), W +14.3% (n=238). ce5_deep_fav lane = live judge.
  const purpleCE5 = (() => {
    if (!mc3 || mc3.p1_prob == null || mc3.market_p1 == null) return null
    const dog1 = mc3.market_p1 < 0.5
    const fav1 = !dog1
    const cf = fav1 ? mc3.p1_prob : 1 - mc3.p1_prob
    const mf = fav1 ? mc3.market_p1 : 1 - mc3.market_p1
    if (cf - mf < 0.05) return null
    const od = match.live_odds ? Number(fav1 ? match.live_odds.player_1 : match.live_odds.player_2) : null
    if (od == null || isNaN(od) || od < -200 || od > -150) return null
    const isW = match.league === 'wta' || match.league === 'itf_women'
    return { name: fav1 ? match.player_1 : match.player_2, od, isW, edge: Math.round(100 * (cf - mf)) }
  })()
  // 💜 FADE-GOLD POCKET W (2026-10-08, user order): women's FADE-GOLD (gray hates
  // the dog >=2pts) with the favorite at -200..-300 — the band where backtest AND
  // live converge. REMEASURED 2026-10-08: women -200..-300 all-years +5.9%
  // (1011-344, n=1,355), 2026 +4.4% (359-131, n=490); live pocket 22-7 +6.8%.
  // (the old +16.9%/54-13 was a WTA-only artifact of the broken gender split),
  // while the shallow slices (-100..-200) run -20..-30% live and deep chalk -11%.
  const purpleFGW = (() => {
    if (!mc3 || mc3.market_aware_p1 == null || mc3.market_p1 == null) return null
    if (!(match.league === 'wta' || match.league === 'itf_women')) return null
    const dog1 = mc3.market_p1 < 0.5
    const mdog = dog1 ? mc3.market_p1 : 1 - mc3.market_p1
    const gdog = dog1 ? mc3.market_aware_p1 : 1 - mc3.market_aware_p1
    if (mdog - gdog < 0.02) return null
    const od = match.live_odds ? Number(dog1 ? match.live_odds.player_2 : match.live_odds.player_1) : null
    if (od == null || isNaN(od) || od < -300 || od > -200) return null
    return { name: dog1 ? match.player_2 : match.player_1, od, hate: Math.round(100 * (mdog - gdog)) }
  })()
  // ⚫ WOMEN c75 DOG (2026-10-08, user "mark every women c75 dog ... highlight it black").
  // As-of backtest (production simulate_match on rebuilt historical profiles, 19,576
  // matches scored): WOMEN, c75 on the market dog, dog >= +100 -> +8.8% ROI
  // (710-952, n=1,662). It pays at EVERY price and improves as the price lengthens
  // (+100/150 +4.2%, +150/200 +10.9%, +200/250 +10.8%, +250/400 +27.8%, +400+ +64.4%),
  // but odds-on dogs (under +100) are NEGATIVE (-1.2%, n=307) -> hence the >= +100 gate.
  // Live lane mc_c75_dog women: +16.7% (14-17). Men's equivalent is weaker (+6.5%).
  const blackC75W = (() => {
    if (!mc3 || mc3.mc_c75_p1 == null || mc3.market_p1 == null) return null
    if (!(match.league === 'wta' || match.league === 'itf_women')) return null
    const dog1 = mc3.market_p1 < 0.5
    if ((mc3.mc_c75_p1 >= 0.5) !== dog1) return null
    const od = match.live_odds ? Number(dog1 ? match.live_odds.player_1 : match.live_odds.player_2) : null
    if (od == null || isNaN(od) || od < 100) return null
    return { name: dog1 ? match.player_1 : match.player_2, od,
             pct: Math.round(100 * (dog1 ? mc3.mc_c75_p1 : 1 - mc3.mc_c75_p1)) }
  })()
  const tier1Blue = (() => {
    if (!mc3 || mc3.p1_prob == null || mc3.market_aware_p1 == null || mc3.market_p1 == null) return null
    const c1 = mc3.p1_prob >= 0.5
    const g1 = mc3.market_aware_p1 >= 0.5
    const dog1 = mc3.market_p1 < 0.5
    const mdog = dog1 ? mc3.market_p1 : 1 - mc3.market_p1
    const gdog = dog1 ? mc3.market_aware_p1 : 1 - mc3.market_aware_p1
    const aP = ma3 && ma3.p1_prob != null ? ma3.p1_prob >= 0.5 : null
    const bP = mb3 && mb3.p1_prob != null ? mb3.p1_prob >= 0.5 : null
    const isW = match.league === 'wta' || match.league === 'itf_women'
    // each cell carries its OWN 2026 walk-forward backtest record + the live lane key,
    // so the tag can cite this exact cell for this exact gender (2026-10-08 user ask).
    // Every TIER-1 cell: positive in BOTH the corrected walk-forward backtest AND the
    // live frozen log. bm/bw = 2026 bt (M/W), am/aw = all-years bt, lane = live record.
    // All numbers remeasured 2026-10-08 with true gender + one row per match.
    const cells = []
    const star = c1 === g1 && g1 === dog1
    const alone = aP !== null && bP !== null && aP !== c1 && bP !== c1
    if (alone && g1 === c1 && c1 === dog1) cells.push({ n: 'C-ALONE+GRAY', bm: '+3.3% (163-188)', bw: '+17.1% (116-108)', am: '+15.9% (n=947)', aw: '+32.6% (n=601)', lane: 'c_alone_gray_dog' })
    if (star && (alone || gdog - mdog >= 0.04)) cells.push({ n: 'TIER-1', bm: '+3.2% (353-390)', bw: '+20.5% (265-219)', am: '+14.1% (n=2,079)', aw: '+28.8% (n=1,321)', lane: 'tier1' })
    else if (star) cells.push({ n: 'STAR C+GRAY DOG', bm: '+3.2% (353-390)', bw: '+20.5% (265-219)', am: '+14.1% (n=2,079)', aw: '+28.8% (n=1,321)', lane: 'stardog_prime' })
    if (g1 === dog1 && gdog - mdog >= 0.04) cells.push({ n: 'GRAY 4pt+ DOG', bm: '+3.8% (370-406)', bw: '+17.5% (284-247)', am: '+13.5% (n=2,185)', aw: '+26.5% (n=1,452)', lane: 'gray_dog4' })
    // c75 BANDED DOG (2026-10-08): promoted into the bedrock family -- the as-of sim
    // backtest (production simulate_match on rebuilt historical profiles) makes it the
    // ONLY sim cell positive in both layers for both genders: bt26 M +11.2% (n=271) /
    // W +4.6% (n=1,409) on the FULL universe; >=+100 any price M +5.1% / W +8.1%;
    // live M +24.6% (41-41) / W +16.7% (14-17).
    if (mc3.mc_c75_p1 != null && (mc3.mc_c75_p1 >= 0.5) === dog1) {
      const od75 = match.live_odds ? Number(dog1 ? match.live_odds.player_1 : match.live_odds.player_2) : null
      if (od75 != null && !isNaN(od75) && od75 >= 100 && od75 <= 200) {
        cells.push({ n: 'c75 DOG +100/+200', bm: '+1.7% (884-1125)', bw: '+4.6% (634-775)', am: '>=+100 +5.1% (n=2,308)', aw: '>=+100 +8.1% (n=1,768)', lane: 'mc_c75_dog' })
      }
    }
    if (aP !== null && bP !== null && aP !== c1 && bP === c1 && c1 === dog1 && g1 === c1) cells.push({ n: 'FADE-A DOG+GRAY', bm: '+13.6% (58-49)', bw: '+29.4% (52-35)', am: '+14.0% (n=290)', aw: '+29.6% (n=255)', lane: 'fade_a_dog_gray' })
    if (cells.length) {
      const nm2 = dog1 ? match.player_1 : match.player_2
      const od2 = match.live_odds ? Number(dog1 ? match.live_odds.player_1 : match.live_odds.player_2) : null
      return { side: dog1, name: nm2, od: isNaN(od2) ? null : od2, cells, isW, fav: false }
    }
    if (isW) {
      const favS = !dog1
      const cfav = favS ? mc3.p1_prob : 1 - mc3.p1_prob
      const mfav = favS ? mc3.market_p1 : 1 - mc3.market_p1
      if (cfav - mfav >= 0.05) {
        const nm2 = favS ? match.player_1 : match.player_2
        const od2 = match.live_odds ? Number(favS ? match.live_odds.player_1 : match.live_odds.player_2) : null
        return { side: favS, name: nm2, od: isNaN(od2) ? null : od2, isW, fav: true,
                 cells: [{ n: 'C-EDGE5 FAV (W) ⚠', bm: null, bw: '+5.6% (783-317)',
                            am: null, aw: '+9.0% (n=3,203)', lane: null,
                            lv: '-14.7% (27-21)' }] }
      }
    }
    return null
  })()
  // 🪤 BAIT-FAVORITE GREEN (2026-10-08, user "I want all these games highlighted green
  // full card on the board"): ALL FOUR sims (c50/c75/cUTR/serve-MC) price the favorite
  // >=6pts below the no-vig market (>=4pts women) AND the dog is +100..+200 -> the
  // chalk is bait, the DOG is the play. Replay month: dogs +23.4% at 6pts (51.3% win,
  // 39-37), women +40.1%, men +13.6%; the favorite decays monotonically with discount
  // depth (dose-response both directions — healthiest cell shape measured 2026-10-08).
  // +200..+250 bait dogs are a GRAVEYARD (-42.5%) — the band edge is the mark.
  // Takes precedence over the orange MC2 watch tint. bait_dog lane scores it live.
  const baitGreen = (() => {
    if (!mc3 || mc3.market_p1 == null || mc3.mc_c75_p1 == null || mc3.mc_cutr_p1 == null) return null
    const c50v = (mc3.mc && mc3.mc.sims) ? mc3.mc.p1_pct / 100 : null
    const mcdv = (match.model_d && match.model_d.mc && match.model_d.mc.sims) ? match.model_d.mc.p1_pct / 100 : null
    if (c50v == null || mcdv == null) return null
    const lo = match.live_odds || {}
    const fav1 = mc3.market_p1 >= 0.5
    const dogName = fav1 ? match.player_2 : match.player_1
    const dogOdds = Number(fav1 ? lo.player_2 : lo.player_1)
    if (isNaN(dogOdds) || dogOdds < 100 || dogOdds > 200) return null
    const mkf = fav1 ? mc3.market_p1 : 1 - mc3.market_p1
    const isW = match.league === 'wta' || match.league === 'itf_women'
    const disc = isW ? 0.04 : 0.06
    const heads = [c50v, mc3.mc_c75_p1, mc3.mc_cutr_p1, mcdv].map(v => fav1 ? v : 1 - v)
    if (!heads.every(h => h <= mkf - disc)) return null
    const gap = Math.round(100 * (mkf - Math.max(...heads)))
    // ⭐ PRIME tier (2026-10-08, user "mark the best to take"): the fattest measured
    // slice INSIDE the green cell — dog +100..+150 with the full 6pt+ discount
    // (replay +31.0%, 27-19, 58.7% win). 🔥 adds when it's a women's match (12-3,
    // +83% replay — but n=15, so the flame is a priority hint, not its own cell).
    const prime = dogOdds <= 150 && gap >= 6
    // MC CONFIRMATION (2026-10-08): does c75 actually FLIP to this dog (dog prob > 50%),
    // or does it merely discount the favorite? Measured both ways, both genders:
    //   flips      -> as-of bt M +15.6% (n=195) / W +4.6% (n=142); live M +23.1% (42) / W +59.7% (23)
    //   no flip    -> as-of bt M -12.9% (n=98)  / W -4.2% (n=74);  live M -53.0% (6)  / W -47.1% (9)
    // Four independent measurements agree, so this is a real gate, not a sub-tier.
    const c75Flip = mc3.mc_c75_p1 != null ? ((mc3.mc_c75_p1 >= 0.5) === (mc3.market_p1 < 0.5)) : null
    return { gap, dogOdds, isW, prime, dogName, c75Flip }
  })()

  return (
    <div className="game-card card-enter" style={{
      background: blackC75W ? 'rgba(8,10,14,0.92)' : baitGreen ? (baitGreen.c75Flip === false ? 'rgba(248,81,73,0.09)' : 'rgba(63,185,80,0.13)') : (purpleCGF || purpleCE5 || purpleFGW) ? 'rgba(188,140,255,0.13)' : tier1Blue ? 'rgba(88,166,255,0.11)' : orange58 ? 'rgba(240,136,62,0.10)' : 'var(--panel)',
      border: blackC75W ? '2px solid #e8e8ea' : baitGreen ? (baitGreen.c75Flip === false ? '1px solid rgba(248,81,73,0.55)' : '1px solid rgba(63,185,80,0.85)') : (purpleCGF || purpleCE5 || purpleFGW) ? '1px solid rgba(188,140,255,0.85)' : tier1Blue ? '1px solid rgba(88,166,255,0.80)' : orange58 ? '1px solid rgba(240,136,62,0.65)' : '1px solid var(--line)', borderRadius: 10,
      padding: '18px 20px 16px', borderLeft: `3px solid ${blackC75W ? '#f0f0f2' : baitGreen ? (baitGreen.c75Flip === false ? '#f85149' : '#3fb950') : (purpleCGF || purpleCE5 || purpleFGW) ? '#bc8cff' : tier1Blue ? '#58a6ff' : orange58 ? '#f0883e' : leagueColor}`,
      boxShadow: blackC75W ? '0 0 22px rgba(0,0,0,0.85), inset 0 0 40px rgba(255,255,255,0.04)' : baitGreen ? (baitGreen.c75Flip === false ? 'none' : '0 0 16px rgba(63,185,80,0.26)') : (purpleCGF || purpleCE5 || purpleFGW) ? '0 0 18px rgba(188,140,255,0.30)' : tier1Blue ? '0 0 16px rgba(88,166,255,0.25)' : orange58 ? '0 0 14px rgba(240,136,62,0.18)' : undefined,
      animationDelay: `${animDelay}s`,
    }}>
      {blackC75W ? (
        <div className="mono" title={`WOMEN c75 DOG - the single best-evidenced sim cell on the board. As-of backtest (production simulate_match replayed on rebuilt historical profiles, the FULL 20,871-match 2026 universe): women, c75 on the market underdog, dog priced +100 or longer = +8.1% ROI (748-1020, n=1,768). It pays at EVERY price and improves as the price lengthens: +100/+150 +3.1%, +150/+200 +8.0%, +200/+250 +12.3%, +250/+400 +19.4%, +400 and longer +67.1%. Odds-on dogs (under +100) are near-flat (+1.4%, n=411), so the mark starts at +100. Live lane mc_c75_dog women: +16.7% (14-17). Men's equivalent is weaker (+5.1%, n=2,308). c75 = the Monte Carlo anchored 75% to Model C; the anchor weight is what earns (serve-MC alone loses ~10%).`}
          style={{ fontSize: 9, fontWeight: 800, color: '#f0f0f2', marginBottom: 6, letterSpacing: '0.05em', background: 'linear-gradient(90deg, rgba(255,255,255,0.10), transparent)', padding: '3px 6px', borderRadius: 4, border: '1px solid rgba(255,255,255,0.35)' }}>
          {'⚫ WOMEN c75 DOG → '}
          <span style={{ fontSize: 12, fontWeight: 900, color: '#ffffff', textShadow: '0 0 10px rgba(255,255,255,0.65)' }}>
            {'TAKE '}{blackC75W.name.split(' ').slice(-1)[0].toUpperCase()}{' +'}{blackC75W.od}
          </span>
          {` · c75 ${blackC75W.pct}% · bt +8.1% (748-1020, n=1,768) · any price ≥+100 · longer = better`}
          {(() => {
            const st = ((laneRec && laneRec.study) || {}).mc_c75_dog || {}
            const c = st.w || {}
            const nn = c.n || 0
            return <span style={{ color: '#d6d6da', fontWeight: 400 }}>
              {nn ? ` · LIVE W ${c.roi_pct > 0 ? '+' : ''}${Math.round(c.roi_pct * 10) / 10}% (${c.wins}-${nn - c.wins})` : ' · LIVE W tracking'}
            </span>
          })()}
        </div>
      ) : null}
      {!baitGreen && purpleCGF ? (
        <div className="mono" title={`💜 C-ALONE+GOLD SHALLOW FAVORITE (your mark, 2026-10-08): Model C alone against A and B, the gray line confirms C, and C's side is a -100..-150 favorite. Walk-forward backtest at archive odds - MEN: -1.5% (2024) -> +10.9% (2025) -> +13.4% (2026, 122-67, n=189), improving three straight years. WOMEN: all-years +10.1% (169-103, n=272) but 2026 only +1.7% (46-34, n=80) — the women's half has faded to ~flat. HONESTY: the live all-price lane is men -9.1% (62 settles) / women +7.9% (13) - live has NOT yet confirmed the backtest; the banded cgf_shallow_fav lane now scores this exact mark forward and its record shows here as it settles.`}
          style={{ fontSize: 9, fontWeight: 800, color: '#bc8cff', marginBottom: 6, letterSpacing: '0.04em', textShadow: '0 0 8px rgba(188,140,255,0.5)' }}>
          💜 C-ALONE+GOLD FAV → <span style={{ fontSize: 12, fontWeight: 900, color: '#f3eaff', textShadow: '0 0 10px #bc8cff' }}>TAKE {purpleCGF.name.split(' ').slice(-1)[0].toUpperCase()} {purpleCGF.od}</span> · bt26 M +17.0% (96-48){purpleCGF.isW ? ' · W 2026 −19.6% ⚠' : ''} · live unconfirmed
          {(() => {
            const st = ((laneRec && laneRec.study) || {}).cgf_shallow_fav || {}
            const c = (purpleCGF.isW ? st.w : st.m) || {}
            const n = c.n || 0
            return <span style={{ color: '#e9dcff', fontWeight: 400 }}>{n ? ` · LANE ${purpleCGF.isW ? 'W' : 'M'} ${c.roi_pct > 0 ? '+' : ''}${Math.round(c.roi_pct * 10) / 10}% (${c.wins}-${n - c.wins})` : ' · LANE tracking'}</span>
          })()}
        </div>
      ) : null}
      {!baitGreen && !purpleCGF && purpleCE5 ? (
        <div className="mono" title={`💜 C-EDGE5 DEEP FAVORITE (your mark, 2026-10-08): raw Model C prices this favorite ${purpleCE5.edge} points ABOVE the no-vig market, and the price is -150..-200 — the strongest favorite cell in the entire walk-forward backtest. Backtest remeasured 2026-10-08 (true gender, single-count): MEN 2026 +10.8% (327-139, n=466), all-years +5.9% (974-479, n=1,453); WOMEN 2026 +5.0% (208-106, n=314), all-years +10.8% (593-253, n=846). Positive in both genders and both windows — this cell SURVIVED the correction. The LANE number is the live frozen-log record for this match's gender (ce5_deep_fav, frozen closing odds, auto-updating as games settle).`}
          style={{ fontSize: 9, fontWeight: 800, color: '#bc8cff', marginBottom: 6, letterSpacing: '0.04em', textShadow: '0 0 8px rgba(188,140,255,0.5)' }}>
          💜 C-EDGE5 FAV → <span style={{ fontSize: 12, fontWeight: 900, color: '#f3eaff', textShadow: '0 0 10px #bc8cff' }}>TAKE {purpleCE5.name.split(' ').slice(-1)[0].toUpperCase()} {purpleCE5.od}</span> · C +{purpleCE5.edge}pt over mkt · bt26 {purpleCE5.isW ? 'W +5.0% (208-106)' : 'M +10.8% (327-139)'} · 3yr {purpleCE5.isW ? '+10.8% (n=846)' : '+5.9% (n=1,453)'}
          {(() => {
            const st = ((laneRec && laneRec.study) || {}).ce5_deep_fav || {}
            const c = (purpleCE5.isW ? st.w : st.m) || {}
            const n = c.n || 0
            return <span style={{ color: '#e9dcff', fontWeight: 400 }}>{n ? ` · LIVE ${purpleCE5.isW ? 'W' : 'M'} ${c.roi_pct > 0 ? '+' : ''}${Math.round(c.roi_pct * 10) / 10}% (${c.wins}-${n - c.wins})` : ' · LIVE tracking'}</span>
          })()}
        </div>
      ) : null}
      {!baitGreen && !purpleCGF && !purpleCE5 && purpleFGW ? (
        <div className="mono" title={`💜 FADE-GOLD POCKET (women, your mark 2026-10-08): the gray line prices this market dog ${purpleFGW.hate} points BELOW her market number (gray HATES the dog), and the favorite sits in the -200..-300 pocket — the one price band where the backtest AND the live log agree this favorite earns. Backtest remeasured 2026-10-08 (true gender, single-count, -200..-300): women all-years +5.9% (1011-344, n=1,355), 2026 +4.4% (359-131, n=490). The old +16.9%/54-13 was a WTA-tour-only artifact of the broken gender split. Live pocket: 23-8, ~+4.5%. OUT of this band the same signal LOSES live (-20% at -100/-150, -30% at -150/-200, -11% past -300) — the band IS the mark. The LANE number is the live record of this exact banded cell (fadegold_pocket_w), auto-updating.`}
          style={{ fontSize: 9, fontWeight: 800, color: '#bc8cff', marginBottom: 6, letterSpacing: '0.04em', textShadow: '0 0 8px rgba(188,140,255,0.5)' }}>
          💜 FADE-GOLD POCKET W → <span style={{ fontSize: 12, fontWeight: 900, color: '#f3eaff', textShadow: '0 0 10px #bc8cff' }}>TAKE {purpleFGW.name.split(' ').slice(-1)[0].toUpperCase()} {purpleFGW.od}</span> · gray hates dog {purpleFGW.hate}pt · bt26 W +4.4% (359-131) · live pocket +4.5% (23-8)
          {(() => {
            const st = ((laneRec && laneRec.study) || {}).fadegold_pocket_w || {}
            const c = st.w && st.w.n ? st.w : st
            const n = c.n || 0
            return <span style={{ color: '#e9dcff', fontWeight: 400 }}>{n ? ` · LANE ${c.roi_pct > 0 ? '+' : ''}${Math.round(c.roi_pct * 10) / 10}% (${c.wins}-${n - c.wins})` : ' · LANE tracking'}</span>
          })()}
        </div>
      ) : null}
      {!baitGreen && tier1Blue && !purpleCGF && !purpleCE5 && !purpleFGW ? (
        <div className="mono" title={`🏛 TIER-1 BEDROCK — this card fires ${tier1Blue.cells.map(c => `${c.n} [bt26 ${tier1Blue.isW ? 'W ' + (c.bw || 'n/a') : 'M ' + (c.bm || 'n/a')}]`).join(' + ')}: the signal family positive in BOTH the 2024-26 walk-forward backtest AND the live log. BLUE FAMILY LIVE ROI (replay of every blue card on the frozen log, one bet per card, flat 1u at frozen odds, 2026-10-08): ALL +12.4% (103-91, +24.1u) | MEN +23.6% (51-44) | WOMEN +1.6% (52-47). Per leading cell: c75 DOG +24.4% (65-59, n=124 - carries the family), TIER-1 +11.2% (28-28), GRAY 4pt+ +11.0% (29-29), C-ALONE+GRAY +6.1% (15-17), FADE-A -0.9% (4-4, thin), and ⚠ C-EDGE5 FAV W -14.7% (27-21) - the ONE blue cell losing live despite a +5.6%/+9.0% backtest, which is why it is tagged with a warning and is the family's demotion candidate. TIER-1 = positive in BOTH the corrected backtest and the live log. Roster (2026 bt | all-years bt | live): c75 DOG +100/+200 M +1.7% (n=2,009) / W +4.6% (n=1,409) | any price >=+100 M +5.1% / W +8.1% | live M +24.6% (41-41) / W +16.7% (14-17) · GRAY 4pt+ DOG M +3.8%/W +17.5% | M +13.5% (n=2,185)/W +26.5% (n=1,452) | live M +15.1%/W +12.7% · TIER-1 M +3.2%/W +20.5% | M +14.1% (n=2,079)/W +28.8% (n=1,321) | live M +15.8%/W +13.1% · C-ALONE+GRAY M +3.3%/W +17.1% | M +15.9% (n=947)/W +32.6% (n=601) | live M +19.5%/W +6.4% · FADE-A DOG+GRAY M +13.6%/W +29.4% | M +14.0% (n=290)/W +29.6% (n=255) | live thin (n=9) · C-EDGE5 FAV W +5.6% | +9.0% (n=3,203) | live tracking. NOTE the 2026-vs-all-years gap on the men's side (+3% vs +14%): the men's dog edge has DECAYED this season while the women's held. Backtest REMEASURED 2026-10-08 — two defects fixed: (1) gender, the old split filed every women's ITF match as MEN (31% of its men's bucket) and counted only WTA women; (2) double-counting, the old rig scored both orientations of every match. True-gender, one-row-per-match 2026 numbers: GRAY 4pt+ DOG M +3.8%/W +17.5% · TIER-1 M +3.2%/W +20.5% · C-ALONE+GRAY M +3.3%/W +17.1% · FADE-A DOG+GRAY M +13.6%/W +29.4% · C-EDGE5 FAV W +5.6%. All-years (more stable): men dogs +12.7..+15.9%, women dogs +26.5..+33.1%. **The men's dog edge has decayed to ~+3% in 2026 while the women's holds at +17..+21% — the women's half is now the stronger side of every bedrock cell.** Live: gray_dog4 M +15.1%/W +12.7%, tier1 M +15.8%, priced-star-dog M +14.6%/W +26.5%, c-alone+gray M +19.5%. ${tier1Blue.fav ? 'This one is the WOMEN’S FAVORITE cell — the only favorite family that held all three years.' : 'The dog is the play — every bedrock cell bets the underdog.'} Bait-green outranks blue when both fire.`}
          style={{ fontSize: 9, fontWeight: 800, color: '#58a6ff', marginBottom: 6, letterSpacing: '0.04em', textShadow: '0 0 8px rgba(88,166,255,0.5)' }}>
          🏛 BEDROCK → <span style={{ fontSize: 12, fontWeight: 900, color: '#eaf4ff', textShadow: '0 0 10px #58a6ff' }}>TAKE {tier1Blue.name.split(' ').slice(-1)[0].toUpperCase()}{tier1Blue.od != null ? ` ${tier1Blue.od > 0 ? '+' : ''}${tier1Blue.od}` : ''}</span> · {tier1Blue.cells.map(c => c.n).join(' + ')}
          {(() => {
            const lead = tier1Blue.cells[0]
            const bt = tier1Blue.isW ? lead.bw : lead.bm
            const ba = tier1Blue.isW ? lead.aw : lead.am
            const st = lead.lane ? (((laneRec && laneRec.study) || {})[lead.lane] || {}) : {}
            const c = (tier1Blue.isW ? st.w : st.m) || {}
            const nn = c.n || 0
            const g = tier1Blue.isW ? 'W' : 'M'
            // family-level live ROI: replay of EVERY blue-highlighted card on the frozen
            // log, one bet per card, flat 1u at frozen odds (measured 2026-10-08):
            // all +12.4% (103-91, +24.1u) | men +23.6% (51-44) | women +1.6% (52-47).
            const fam = tier1Blue.isW ? '+1.6% (52-47)' : '+23.6% (51-44)'
            return <span style={{ color: '#d6e9ff', fontWeight: 400 }}>
              {bt ? ` · bt26 ${g} ${bt}` : ''}
              {ba ? ` · 3yr ${ba}` : ''}
              {nn ? ` · LIVE ${g} ${c.roi_pct > 0 ? '+' : ''}${Math.round(c.roi_pct * 10) / 10}% (${c.wins}-${nn - c.wins})`
                  : (lead.lv ? ` · LIVE ${g} ${lead.lv}` : ` · LIVE ${g} tracking`)}
              <span style={{ color: '#8ab4e8' }}>{` · BLUE ${g} fam ${fam}`}</span>
            </span>
          })()}
        </div>
      ) : null}
      {baitGreen ? (
        <div className="mono" title={`🪤 BAIT FAVORITE — every sim on this card (c50, c75, cUTR, serve-MC) prices the favorite at least ${baitGreen.isW ? 4 : 6} points BELOW the no-vig market, and the dog is in the +100..+200 window where the cell earns. The chalk is the trap; the DOG (+${baitGreen.dogOdds}) is the play. Evidence on the FULL 20,871-match as-of universe: the UNGATED cell is men -0.6% (n=2,285) / women -3.1% (n=1,784); only the c75-FLIP half pays (men +1.9% n=1,492 / women +2.4% n=1,153) while the no-flip half loses (men -5.3% / women -13.2%). Context: the same banded dogs with NO signal run -14.0% (men, n=4,756) / -10.8% (women, n=2,699), and out-of-band +200..+400 dogs run -3.6%/-8.2%. Live bait_dog lane men +11.2% (24-27) / women +29.7% (17-15). The cell is bet as ONE cell: its PRIME/REST sub-tiering is refuted (bt and live disagree on which half is better in both genders). Smallest head-gap on this card: ${baitGreen.gap}pts.`}
          style={{ fontSize: 9, fontWeight: 800, color: '#3fb950', marginBottom: 6, letterSpacing: '0.04em', textShadow: '0 0 8px rgba(63,185,80,0.5)' }}>
          🪤 BAIT FAV → <span style={{ fontSize: 12, fontWeight: 900, color: '#eaffea', textShadow: '0 0 10px #3fb950' }}>TAKE {baitGreen.dogName.split(' ').slice(-1)[0].toUpperCase()} +{baitGreen.dogOdds}</span> · discount {baitGreen.gap}pt+
          {baitGreen.c75Flip === false ? (
            <span style={{ color: '#ffd7d5', background: 'rgba(248,81,73,0.55)', borderRadius: 4, padding: '0 6px', marginLeft: 8, fontWeight: 900 }}
              title={`MC REFUSES THIS DOG - the bait pattern fires (every sim prices the favourite below the market) BUT c75 still has the FAVOURITE ahead: no sim actually flips to this dog. Measured both ways, both genders - on the FULL 20,871-match as-of universe, when c75 FLIPS the bait dog runs bt M +1.9% (n=1,492) / W +2.4% (n=1,153) with live M +23.1% (42) / W +59.7% (23); when it does NOT flip, as here, it runs bt M -5.3% (n=793) / W -13.2% (n=631) with live M -53.0% (6) / W -47.1% (9). The UNGATED cell is negative in both genders (M -0.6%, W -3.1%), so the gate is what makes this cell bettable at all. NO BET.`}>
              {baitGreen.isW
                ? '⛔ MC REFUSES · NO BET (bt W −13.2% n=631 · live W −47.1%)'
                : '⛔ MC REFUSES · NO BET (bt M −5.3% n=793 · live M −53.0%)'}
            </span>
          ) : baitGreen.c75Flip === true ? (
            <span style={{ color: '#eaffea', background: 'rgba(63,185,80,0.45)', borderRadius: 4, padding: '0 6px', marginLeft: 8, fontWeight: 900, textShadow: '0 0 8px #3fb950' }}
              title={`MC CONFIRMS - c75 does not merely discount the favourite, it FLIPS outright to this dog. That conjunction is the strongest version of the cell in both evidence layers and both genders: FULL-universe as-of bt M +1.9% (651-841, n=1,492) / W +2.4% (505-648, n=1,153); live M +23.1% (22-20) / W +59.7% (15-8), combined live +36.1% (37-28). Without the flip the same pattern LOSES (bt M -5.3%, W -13.2%; live -49.5%), and the ungated cell is negative too (M -0.6%, W -3.1%).`}>
              {'✓ MC CONFIRMS '}{baitGreen.isW ? '(bt W +2.4% n=1,153 · live W +59.7%)' : '(bt M +1.9% n=1,492 · live M +23.1%)'}
            </span>
          ) : null}
          {(() => {
            // WHOLE-CELL numbers (2026-10-08 correction): the PRIME/REST split is not
            // real -- backtest and live disagree on which half is better in BOTH genders
            // (M: bt PRIME +7.4% vs live REST +28.2%; W: bt REST +10.0% vs live PRIME
            // +83.4%). So this reads the undifferentiated bait_dog lane and the
            // whole-cell as-of backtest; the band is a label, not a ranking.
            const st = ((laneRec && laneRec.study) || {}).bait_dog || {}
            const c = (baitGreen.isW ? st.w : st.m) || {}
            const n = c.n || 0
            const nm = 'CELL'
            const tot = st.n ? ` · cell all ${st.roi_pct > 0 ? '+' : ''}${Math.round(st.roi_pct * 10) / 10}% (${st.wins}-${st.n - st.wins})` : ''
            // AS-OF BACKTEST of this cell (2026-10-08): 3-sim approximation -- the real
            // bait needs all 4 sims and cUTR can't be rebuilt historically, so this runs
            // serve-MC + c50 + c75 on as-of profiles. Whole cell: M +6.1% (130-163,
            // n=293) / W +1.6% (91-125, n=216). PRIME: M +7.4% (n=168) / W -5.5%
            // (n=117). REST: M +4.3% (n=125) / W +10.0% (n=99). Controls: the same
            // banded dogs WITHOUT the signal run -5.1% (n=1,432) and out-of-band
            // +200..+400 runs -14.5% (n=358) -> the signal and the band both earn.
            const bt3 = baitGreen.isW ? '−3.1% (716-1068)' : '−0.6% (937-1348)'
            return <span style={{ color: '#d9ffe3', fontWeight: 400 }} title={`THE WHOLE GREEN CELL, both numbers, for this match's gender. bt3 = as-of backtest of a 3-sim approximation (serve-MC + c50 + c75 replayed on rebuilt historical profiles; the live cell also needs cUTR, which anchors on current-only ratings and cannot be rebuilt), measured on the FULL 20,871-match 2026 universe: men -0.6% (937-1348, n=2,285), women -3.1% (716-1068, n=1,784). The UNGATED cell loses -- only the c75-flip half is bettable (men +1.9%, women +2.4%). Controls: the same banded dogs WITHOUT the signal run -5.1% (n=1,432) and out-of-band +200..+400 dogs run -14.5% (n=358), so both the signal and the price gate earn their keep. live = the bait_dog lane at frozen closing odds, auto-updating. NO SUB-TIERING: the old PRIME/REST split is refuted -- backtest and live disagree on which half is better in BOTH genders (men bt favours PRIME +7.4% while live favours REST +28.2%; women bt favours REST +10.0% while live favours PRIME +83.4%), which is what noise looks like. Bet the cell, not the sub-tier.`}>
              {` · ${nm} bt3 ${baitGreen.isW ? 'W' : 'M'} ${bt3}`}
              {n ? ` · ${nm} ${baitGreen.isW ? 'W' : 'M'} log ${c.roi_pct > 0 ? '+' : ''}${Math.round(c.roi_pct * 10) / 10}% (${c.wins}-${n - c.wins})` : ` · ${nm} ${baitGreen.isW ? 'W' : 'M'} tracking`}{tot}
            </span>
          })()}<span style={{ color: 'var(--text-tertiary)', fontWeight: 400, marginLeft: 6, fontSize: 8.5 }} title={`Price band, shown as a LABEL only -- it is not a ranking. The old PRIME tier (dog +100..+150 with a 6pt+ discount) was built on a 12-3 live run; the as-of backtest puts women's PRIME at -5.5% (n=117) while men's is +7.4% (n=168), and the live records point the opposite way in both genders. There is no evidence that one band of this cell beats the other, so every green card is weighted the same now.`}>{baitGreen.prime ? 'band +100/+150' : 'band +150/+200'}</span>
          {(() => {
            // TIER-1 CONFIRMATION ON GREEN CARDS (2026-10-08): green outranks blue, so a
            // bedrock cell backing the SAME player would otherwise be invisible here.
            if (!tier1Blue || tier1Blue.fav) return null
            if (tier1Blue.name !== baitGreen.dogName) return null
            const lead = tier1Blue.cells[0]
            const bt = baitGreen.isW ? lead.bw : lead.bm
            const st = lead.lane ? (((laneRec && laneRec.study) || {})[lead.lane] || {}) : {}
            const c = (baitGreen.isW ? st.w : st.m) || {}
            const nn = c.n || 0
            const names = tier1Blue.cells.map(x => x.n).join('+')
            const g = baitGreen.isW ? 'W' : 'M'
            return <span style={{ color: '#aee5ff', fontWeight: 700 }}
              title={`TIER-1 CONFIRMATION: the same player is also backed by ${names} - cells positive in BOTH the corrected backtest AND the live log. Lead cell ${lead.n}: bt26 ${g} ${bt}${nn ? `, live ${c.roi_pct > 0 ? '+' : ''}${Math.round(c.roi_pct * 10) / 10}% (${c.wins}-${nn - c.wins})` : ''}. Two independent families on one side is the strongest configuration on the board.`}>
              {' · 🏛 +TIER-1 '}{names}{bt ? ` (bt26 ${g} ${bt.split(' ')[0]}` : ''}{nn ? `, live ${c.roi_pct > 0 ? '+' : ''}${Math.round(c.roi_pct * 10) / 10}%)` : (bt ? ')' : '')}
            </span>
          })()}
        </div>
      ) : null}
      {orange58 ? (() => {
        // 🟠 WHO TO TAKE (2026-10-08, user "make the orange ones clear on who to take
        // with live roi and backtested for each gender"): measured on the replay month,
        // orange + dog +100..+200 splits by gender — MEN: take the FAVORITE (+10.0%,
        // 37-15; blind c75-following is worse at +6.1%). WOMEN: take c75's SIDE
        // (10-1, +73.4% — tiny n, ⚠; taking the fav blindly is −29.7%). Dog outside
        // +100..+200: no play (fav over long dogs ran −3%, the dogs themselves −20%).
        const lo9 = match.live_odds || {}
        const d1 = mc3 && mc3.market_p1 != null ? mc3.market_p1 < 0.5 : null
        const dOd = d1 == null ? null : Number(d1 ? lo9.player_1 : lo9.player_2)
        const isW9 = match.league === 'wta' || match.league === 'itf_women'
        const inBand = dOd != null && !isNaN(dOd) && dOd >= 100 && dOd <= 200
        let pickP1 = null
        if (inBand) {
          if (!isW9) pickP1 = !d1
          else if (mc3.mc_c75_p1 != null) pickP1 = mc3.mc_c75_p1 >= 0.5
        }
        const nm9 = pickP1 == null ? null : (pickP1 ? match.player_1 : match.player_2)
        const od9 = pickP1 == null ? null : Number(pickP1 ? lo9.player_1 : lo9.player_2)
        const st9 = ((laneRec && laneRec.study) || {}).mc2e58_fav || {}
        const c9 = (isW9 ? st9.w : st9.m) || {}
        const n9 = c9.n || 0
        return (
          <div className="mono" title={`🟠 MC2 5-8pt DOG-EDGE: MC v2 prices the market dog ${(100 * mc2DogEdge).toFixed(1)} points above the market. WHO TO TAKE (replay month, by gender): MEN — the FAVORITE (+10.0%, 37-15; the dog itself ran −34%). WOMEN — whichever side c75 holds (10-1, +73.4% — n=11, treat as a lead not a law; the favorite blindly ran −29.7%). Dog outside +100..+200 = NO PLAY (favorites over long dogs −3%, the dogs −20%). LIVE = the forward mc2e58_fav lane for this gender (favorite side), building from 2026-10-08.`}
            style={{ fontSize: 9, fontWeight: 800, color: '#f0883e', marginBottom: 6, letterSpacing: '0.04em' }}>
            🟠 MC2 DOG-EDGE 5-8 ({(100 * mc2DogEdge).toFixed(1)}pt) → {nm9 ? <span style={{ fontSize: 12, fontWeight: 900, color: '#fff3e8', textShadow: '0 0 10px #f0883e' }}>TAKE {nm9.split(' ').slice(-1)[0].toUpperCase()}{od9 != null && !isNaN(od9) ? ` ${od9 > 0 ? '+' : ''}${od9}` : ''}</span> : <span style={{ fontWeight: 700, color: 'var(--text-tertiary)' }}>NO PLAY (dog out of +100..+200)</span>}
            {nm9 ? <span style={{ color: '#ffd9b8', fontWeight: 400 }}> · {isW9 ? 'W rule: c75\u2019s side · replay +73.4% (10-1) ⚠ n=11' : 'M rule: favorite · replay +10.0% (37-15)'}{n9 ? ` · LIVE ${isW9 ? 'W' : 'M'} ${c9.roi_pct > 0 ? '+' : ''}${Math.round(c9.roi_pct * 10) / 10}% (${c9.wins}-${n9 - c9.wins})` : ' · LIVE tracking'}</span> : null}
          </div>
        )
      })() : null}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
        {(() => {
          // TIER ribbon (2026-09-30, user ask): rank every pick by the validated hierarchy.
          if (!mc3 || mc3.p1_prob == null || mc3.market_aware_p1 == null || mc3.market_p1 == null) {
            return <span className="mono" style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-tertiary)', border: '1px solid var(--line)', borderRadius: 4, padding: '2px 7px', marginRight: 8 }}>NO DATA</span>
          }
          const c1 = mc3.p1_prob >= 0.5
          const g1 = mc3.market_aware_p1 >= 0.5
          const dog1 = mc3.market_p1 < 0.5
          const mdog = dog1 ? mc3.market_p1 : 1 - mc3.market_p1
          const gdog = dog1 ? mc3.market_aware_p1 : 1 - mc3.market_aware_p1
          const aP = ma3 && ma3.p1_prob != null ? ma3.p1_prob >= 0.5 : null
          const bP = mb3 && mb3.p1_prob != null ? mb3.p1_prob >= 0.5 : null
          const star = c1 === g1 && g1 === dog1
          const alone = aP !== null && bP !== null && aP !== c1 && bP !== c1
          const hate = (mdog - gdog) >= 0.02
          const isW = match.league === 'wta'
          let tier
          if (star && (alone || (gdog - mdog) >= 0.04)) {
            // TIER 1 edge is MEN-only live (men +57% / women -13%), so only the men's
            // multi-★ dog glows; women's is demoted to a muted "weak" tag (2026-10-05).
            tier = isW
              ? { t: 'TIER 1 · W (weak)', c: '#8b949e', bg: 'transparent', tip: 'Multi-★ dog, BUT the TIER 1 edge is men-only live: men +57% (10-4) vs women −13% (5-8) on this lane. Women tier-1 dogs have lost — treat as no real edge.' }
              : { t: 'TIER 1', c: '#f5f13b', bg: '#f5f13b22', tip: 'Multi-★ dog: 2+ yellow signals stack. MEN-only edge live: +57% (10-4). The board’s best-pick tier — bet the glowing name.' }
          } else if (star) {
            tier = { t: 'TIER 2', c: '#f5f13b', bg: 'transparent', tip: 'Single ★ C+GRAY DOG (bt26 +13.7%, live-tracked). A bet — one notch below the multi-star cell.' }
          } else if (hate) {
            tier = { t: 'TIER 3', c: '#e3b341', bg: 'transparent', tip: 'FADE-GOLD favorite (bt26 +2–4%): thin but valid — only at −110..−300 and the listed price or better. The red dog opposite is never a bet.' }
          } else if ((alone && g1 === c1 && c1 !== dog1) || c1 !== g1) {
            // green-only renders these red AVOID configs as neutral NO BET; full board shows AVOID.
            tier = greenOnly
              ? { t: 'NO BET', c: 'var(--text-tertiary)', bg: 'transparent', tip: 'No take fires here (a documented-loser config shown neutral while red signals are hidden). The C-alone+gray DOG half is the play, not the favorite.' }
              : { t: 'AVOID', c: '#f85149', bg: 'transparent', tip: 'A documented-loser config (C+GRAY FAVORITE −6.7% live, or a C-vs-gray fight): no bet on either side. The C-alone+gray DOG half is the play, not the favorite.' }
          } else {
            tier = { t: 'NO BET', c: 'var(--text-tertiary)', bg: 'transparent', tip: 'No take-lane fires. Dark green = probable winner only; the market has this one priced.' }
          }
          return <span className="mono" title={tier.tip} style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.06em', color: tier.c, background: tier.bg, border: `1px solid ${tier.c}${tier.t === 'TIER 1' ? '' : '55'}`, borderRadius: 4, padding: '2px 8px', marginRight: 8 }}>{tier.t}</span>
        })()}
        {match.status === 'cancelled' ? (
          <span className="mono" title="The odds feed lists this match as CANCELLED, but its start time hasn’t long passed — feeds sometimes reinstate. Verify on your book before betting; odds here may be stale or missing. Hides automatically 3h after the listed start if it stays cancelled."
            style={{ fontSize: 10, color: 'var(--amber)', fontWeight: 700, letterSpacing: '0.05em', marginRight: 8 }}>
            ⚠ FEED SAYS CANCELLED
          </span>
        ) : null}
        {match.market_corrupt ? (() => {
          // half red (corrupt market) / half yellow (stats may be inflated: a player's
          // court-UTR is built on <12 matches, the Ghetu/Sensano padded-stats risk).
          const md = match.model_d
          const thin = !!(md && ((md.sutr_p1 && md.sutr_p1.n != null && md.sutr_p1.n < 12)
            || (md.sutr_p2 && md.sutr_p2.n != null && md.sutr_p2.n < 12)))
          return (
            <span className="mono"
              title={`The odds feed returned an IMPOSSIBLE line for this match, so we dropped it and show no market — CHECK THE REAL PRICE on your book.${thin ? ' ALSO: a player’s court-UTR is built on under 12 matches, so the model’s read may be inflated by a thin/weak-schedule sample (the Ghetu/Sensano trap) — treat the pick with extra caution.' : ''}`}
              style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.05em', marginRight: 8, borderRadius: 4, padding: '1px 6px',
                color: thin ? 'var(--text-primary)' : '#f85149',
                border: `1px solid ${thin ? '#e3b34188' : '#f8514955'}`,
                background: thin ? 'linear-gradient(90deg, rgba(227,179,65,0.28) 0 50%, rgba(248,81,73,0.28) 50% 100%)' : 'transparent' }}>
              ⚠ MARKET UNVERIFIED{thin ? ' + THIN STATS' : ''} — check price
            </span>
          )
        })() : null}
        {match.status === 'live' ? (
          <span className="mono" title="In progress — not finished. Odds shown are the frozen pre-match prices."
            style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 10, color: '#f85149', fontWeight: 700, letterSpacing: '0.05em', marginRight: 8 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#f85149', boxShadow: '0 0 6px #f85149', animation: 'livePulse 1.4s ease-in-out infinite' }} />
            LIVE
          </span>
        ) : null}
        {match.status === 'finished' ? (
          <span className="mono" title="Finished — result and all picks read from the frozen pre-match ledger."
            style={{ fontSize: 10, color: '#3fb950', fontWeight: 700, letterSpacing: '0.05em', marginRight: 8 }}>
            ✓ FINAL · {(match.p1_won ? match.player_1 : match.player_2).split(' ').slice(-1)[0]} won
          </span>
        ) : null}
        <span className="mono" style={{ fontSize: 10, color: leagueColor, fontWeight: 700, letterSpacing: '0.05em' }}>
          {match.league.toUpperCase()}
        </span>
        <span className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
          {match.tournament} · {match.round}
        </span>
        <span className="mono" style={{
          fontSize: 9, fontWeight: 700, letterSpacing: '0.05em', color: surfaceColor,
          border: `1px solid ${surfaceColor}`, borderRadius: 4, padding: '2px 6px',
        }} title={match.surface_estimated ? 'No exact tournament match in historical data — defaulted to the tour’s most common surface' : undefined}>
          {match.surface.toUpperCase()}{match.surface_estimated ? '?' : ''}
        </span>
        {fmtPT(match.start_time_utc) ? (
          <span className="mono" title={`Scheduled start, Pacific time. Cards are ordered by start time (live games on top).`}
            style={{ fontSize: 10, color: 'var(--text-secondary)', fontWeight: 700 }}>
            🕐 {fmtPT(match.start_time_utc)}
          </span>
        ) : null}
        {(() => {
          // B-over-A chip (2026-09-30, user ask): when A and B disagree, mark B's side --
          // the fully-settled mirror lanes ran B +5.4% (39-13) vs A-alone -34.1% (13-39).
          if (!ma3 || !mb3 || ma3.p1_prob == null || mb3.p1_prob == null) return null
          const aS = ma3.p1_prob >= 0.5
          const bS = mb3.p1_prob >= 0.5
          if (aS === bS) return null
          const lb0 = laneRec && laneRec.lanes && laneRec.lanes.b_alone
          // gender×side cell for B's side (2026-10-07, every top-of-slip record side-split)
          const wB = match.league === 'wta'
          const dgB = mc3 && mc3.market_p1 != null ? (mc3.market_p1 < 0.5) : null
          const ckB = (wB ? 'w' : 'm') + ((bS === dgB) ? '_dog' : '_fav')
          const lb = (dgB !== null && lb0 && lb0[ckB] && lb0[ckB].n) ? lb0[ckB]
            : (lb0 && (wB ? lb0.w : lb0.m) && (wB ? lb0.w : lb0.m).n ? (wB ? lb0.w : lb0.m) : lb0)
          const icB = dgB === null ? '' : ((bS === dgB) ? ' 🐕' : ' ⭐')
          const lvb = lb && lb.n ? `${lb.roi_pct > 0 ? '+' : ''}${lb.roi_pct.toFixed(1)}% (${lb.wins}-${lb.n - lb.wins})${icB}` : '+5.4% (39-13)'
          const bName = bS ? match.player_1 : match.player_2
          return (
            <span className="mono" title={`A and B disagree — B’s side (${bName}) has the record: fully-settled mirror lanes ran B-side ${lvb} while A-alone went 13-39 (−34.1%, the worst settled lane on the board). Thin edge, mostly “A’s dissents lose” — information, not a validated take.`}
              style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.05em', color: '#d29922', border: '1px solid #d2992244', borderRadius: 4, padding: '2px 7px', textAlign: 'right', lineHeight: 1.4 }}>
              {'B›A: '}{bName.split(' ').slice(-1)[0]}
              <div style={{ fontWeight: 400, fontSize: 8.5, color: 'var(--text-secondary)' }}>{'live '}{lvb}</div>
            </span>
          )
        })()}
        {(() => {
          if (!ma3 || !mb3 || !mc3 || ma3.p1_prob == null || mb3.p1_prob == null || mc3.p1_prob == null) return null
          const s = mc3.p1_prob >= 0.5
          if ((ma3.p1_prob >= 0.5) !== s || (mb3.p1_prob >= 0.5) !== s) return null
          const all6 = ma3.market_aware_p1 != null && mb3.market_aware_p1 != null && mc3.market_aware_p1 != null
            && (ma3.market_aware_p1 >= 0.5) === s && (mb3.market_aware_p1 >= 0.5) === s && (mc3.market_aware_p1 >= 0.5) === s
          const stx6 = laneRec && laneRec.study
          const lane6 = stx6 && (all6 ? stx6.all6_agree : stx6.abc_agree)
          // SIDE+GENDER cell (2026-10-07, user "the all 6 at the top of slips doesn't
          // split favorites and underdogs"): the record is this match's gender×side cell
          // for the agreed side (near-always the ⭐ favorite), with its icon — not the
          // all-matches blend. Falls back gender → blend when the cell is empty/no odds.
          const w6 = match.league === 'wta'
          const dg6 = mc3.market_p1 != null ? (mc3.market_p1 < 0.5) : null
          const cell6 = (() => {
            if (!lane6) return null
            if (dg6 !== null) {
              const ck = (w6 ? 'w' : 'm') + ((s === dg6) ? '_dog' : '_fav')
              if (lane6[ck] && lane6[ck].n) return lane6[ck]
            }
            const gg = w6 ? lane6.w : lane6.m
            return (gg && gg.n) ? gg : lane6
          })()
          const ic6 = dg6 === null ? '' : ((s === dg6) ? ' 🐕' : ' ⭐')
          const l = cell6
          const lvtxt = l && l.n
            ? `${l.roi_pct > 0 ? '+' : ''}${Math.round(l.roi_pct)}% (${l.wins}-${l.n - l.wins})${ic6}`
            : (all6 ? 'proxy +10% (35-9)' : '0 settled')
          return (
            <span className="mono" title={all6
              ? `ALL SIX heads agree — the three stats models AND all three market-aware gray lines. Live proxy at registration: +10.0% (35-9) on 44; the exact all6 lane freezes from 2026-09-30 and takes over this chip as it settles. 2026 backtest −2.6% on 10,826 (72.5% hit) — maximal chalk consensus riding the favorite hot streak; on the promotion watchlist if it survives a real sample.`
              : `A+B+C all pick the same side. Live lane: ${lvtxt}. 2026 backtest −2.6% on 12,256 — chalk consensus; the live number is riding the current favorite hot streak (on the promotion watchlist if it survives a real sample).`}
              style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.05em', color: all6 ? '#79c0ff' : '#58a6ff', border: `1px solid ${all6 ? '#79c0ff55' : '#58a6ff44'}`, borderRadius: 4, padding: '2px 7px', textAlign: 'right', lineHeight: 1.4 }}>
              {all6 ? 'ALL 6 ✓' : 'A+B+C ✓'}
              <div style={{ fontWeight: 400, fontSize: 8.5, color: 'var(--text-secondary)' }}>{'bt26 −2.6% · live '}{lvtxt}</div>
            </span>
          )
        })()}
        <span className="mono" title={catShow.tip} style={{
          fontSize: 9, fontWeight: 700, letterSpacing: '0.05em', color: catShow.color,
          border: `1px solid ${catShow.color === 'var(--text-tertiary)' ? 'var(--line)' : catShow.color + '55'}`,
          borderRadius: 4, padding: '2px 7px', textAlign: 'right', lineHeight: 1.4,
        }}>
          {catShow.txt}
          {(catShow.bt || catShow.live) ? (
            <div style={{ fontWeight: 400, fontSize: 8.5, color: 'var(--text-secondary)' }}>
              {catShow.bt}{' · live '}{catShow.live}
            </div>
          ) : null}
        </span>
      </div>

      <div className="mono" style={{ fontSize: 13, color: 'var(--text-primary)', marginTop: 8 }}>
        <span title={h1 ? h1.title : undefined} style={{ fontWeight: (favoredIsP1 || h1) ? 700 : 400, color: h1 ? h1.color : 'var(--text-primary)', textShadow: h1 && h1.color === '#f5f13b' ? '0 0 9px #f5f13b66' : undefined }}>{match.player_1}</span>
        <span style={{ color: 'var(--text-tertiary)' }}> vs </span>
        <span title={h2 ? h2.title : undefined} style={{ fontWeight: (!favoredIsP1 || h2) ? 700 : 400, color: h2 ? h2.color : 'var(--text-primary)', textShadow: h2 && h2.color === '#f5f13b' ? '0 0 9px #f5f13b66' : undefined }}>{match.player_2}</span>
      </div>

      {(() => {
        // FULL SIGNAL STRIP (2026-09-30, user ask: everything on each pick) -- every lane
        // this match belongs to, with 2026 backtest + that lane's LIVE record.
        if (!mc3 || mc3.p1_prob == null || mc3.market_aware_p1 == null || mc3.market_p1 == null) return null
        const stx = (laneRec && laneRec.study) || {}
        const lnx = (laneRec && laneRec.lanes) || {}
        const lv = v => (v && v.n ? `${v.roi_pct > 0 ? '+' : ''}${Math.round(v.roi_pct)}% (${v.wins}-${v.n - v.wins})` : '0stl')
        const c1 = mc3.p1_prob >= 0.5
        const g1 = mc3.market_aware_p1 >= 0.5
        const dog1 = mc3.market_p1 < 0.5
        const mdog = dog1 ? mc3.market_p1 : 1 - mc3.market_p1
        const gdog = dog1 ? mc3.market_aware_p1 : 1 - mc3.market_aware_p1
        const aP = ma3 && ma3.p1_prob != null ? ma3.p1_prob >= 0.5 : null
        const bP = mb3 && mb3.p1_prob != null ? mb3.p1_prob >= 0.5 : null
        const nm = s => (s ? match.player_1 : match.player_2).split(' ').slice(-1)[0]
        const chips = []
        // lanes already shown as a chip on THIS card (object identity) -- the ➕ +EV pass
        // below skips these so a lane never appears twice on one card (2026-10-07).
        const usedLanes = new Set()
        const wAll = match.league === 'wta'
        const gpick = L => (L ? (wAll ? L.w : L.m) : null)
        const gcol = (L, base) => (!L || !L.n || L.n < 8) ? base : (L.roi_pct > 3 ? '#3fb950' : L.roi_pct < -3 ? '#f85149' : base)
        // EVERY chip gender-split (2026-10-04, user ask "every single live roi even the
        // watch signals split men/women on each slip"): if the lane passed in carries m/w
        // sub-records, show THIS match's gender record for the live number AND recolor by
        // it (gcol keeps the base color while that gender's sample is thin). Already-
        // gendered lanes (from addG) or lanes with no split pass through unchanged.
        const add = (label, side, bt, rec2, color) => {
          // SIDE-AWARE chip records (2026-10-07, user "all the signals are for favorite roi
          // right?" — they weren't): when the lane carries gender×side cells, show the cell
          // matching THIS pick's side (🐕 dog / ⭐ fav) instead of the blended record — a
          // favorite pick must not wear a dog-earned ROI (e.g. c75-agree blend +3% vs fav −8%).
          let L
          // EVERY chip declares its pick's side (2026-10-07, user): 🐕/⭐ from the side it
          // bets, always. The record shown is the gender×side cell when the lane carries one;
          // one-sided lanes (FADE-GOLD, GRAY-2pt-FAV, price bands…) are their side's record
          // by construction, so icon + number agree there too.
          const sideTag = (typeof side === 'boolean') ? ((side === dog1) ? ' 🐕' : ' ⭐') : ''
          if (rec2 && typeof rec2 === 'object') usedLanes.add(rec2)
          if (rec2 && (rec2.m_dog !== undefined || rec2.m_fav !== undefined)
              && typeof side === 'boolean') {
            L = rec2[(wAll ? 'w' : 'm') + ((side === dog1) ? '_dog' : '_fav')] || gpick(rec2)
          } else if (rec2 && (rec2.m !== undefined || rec2.w !== undefined)) {
            L = gpick(rec2)
          } else {
            L = rec2
          }
          chips.push([label, side === null ? '' : nm(side), bt, lv(L) + sideTag, gcol(L, color)])
        }
        // Every chip gendered (2026-09-30, user ask "everything computed separate"):
        // addG appends M/W to the label and shows THAT gender's live lane, colored by it.
        const addG = (label, side, bt, Lfull, base) => {
          // pass the FULL lane through so add() can pick the gender×side cell when the lane
          // carries one (2026-10-07) — pre-picking the gender here was blocking the dog/fav split
          add(`${label} ${wAll ? 'W' : 'M'}`, side, bt, Lfull, gcol(gpick(Lfull), base))
        }
        // Gendered bt26 in parentheses (2026-09-30, user ask): numbers from the full
        // gender-split backtest (_tennis_gender_full_bt.py) — each chip cites ITS
        // gender's 2026 cell, not the blend.
        const b26 = (m, w) => `(bt26 ${wAll ? w : m})`
        const star = c1 === g1 && g1 === dog1
        const hate = (mdog - gdog) >= 0.02
        if (star) {
          addG('★ C+GRAY DOG', dog1, b26('+12.0', '+33.6'), laneRec && laneRec.agree_dog, '#f5f13b')
          if ((gdog - mdog) >= 0.04) addG('★ 4pt+', dog1, b26('+11.1', '+35.1'), stx.gray_dog4, '#f5f13b')
          if (aP !== null && bP !== null && aP !== c1 && bP !== c1) addG('★ C-ALONE+G DOG', dog1, b26('+13.3', '+44.4'), stx.c_alone_gray_dog, '#f5f13b')
          // PRICED-DOG flag (2026-10-02, backtest-corrected): star-dog ROI RISES with
          // price — bt +20.5% at 2.0-2.5, +34.6% at 2.5-3.0, +59% at 3.0-4.0; only
          // short dogs (<1.8) are dead. Flag fires at decimal ≥2.0 (plus-money).
          const dAm = match.live_odds ? Number(dog1 ? match.live_odds.player_1 : match.live_odds.player_2) : null
          const dDec = dAm != null && !isNaN(dAm) ? (dAm > 0 ? 1 + dAm / 100 : 1 + 100 / Math.abs(dAm)) : null
          if (dDec != null && dDec >= 2.0) {
            addG(`🎯 PRICED ${dDec >= 3.0 ? '+59' : dDec >= 2.5 ? '+35' : '+20'}`, dog1, 'bt↑price', stx.stardog_prime, '#3fb950')
            // APEX DOG (2026-10-02): the maximal stack — C-alone+gray dog AND priced.
            // Live +47.6% (+70.8% men's). The board's single best-pick flag.
            if (aP !== null && bP !== null && aP !== c1 && bP !== c1) addG('🔥 APEX DOG', dog1, 'lv +47.6', stx.apex_dog, '#3fb950')
          }
          // LATE-ROUND watch (2026-10-02, user ask): C+gray dog in QF/SF/F etc.
          const rnd = (match.round || '').toLowerCase()
          const lateRnd = rnd && !(rnd.includes('1st') || rnd.includes('qual') || rnd.includes('128') || rnd.includes('of 64'))
          // Watch chips color by their OWN live record (2026-10-02, user "put the
          // positive live watch signals on the board too"): gcol -> green while the lane
          // is earning (>+3% on 8+ settles), red if it decays, base while thin. Same
          // self-pruning the gendered takes use, so a positive watch stands out as positive.
          if (lateRnd) addG('LATE ROUND', dog1, 'watch', stx.cgray_dog_late, gcol(stx.cgray_dog_late, '#8b949e'))
        }
        if (hate) {
          // Depth-aware chip (2026-09-30, user ask): 4-5pt gold favorites show that
          // bucket's own live record; 5pt+ show THIS match's gender lane (men live
          // +8.2% vs women −24% at 5+, so one blended number would mislead).
          const dp = (mdog - gdog) * 100
          // ⭐✓ = one of the THREE favorite cells positive in the full gender×side
          // walk-forward backtest (2026-10-07, user "put the three positive favorite
          // cells on the board"): FADE-GOLD fav (M +2.7/W +10.4 all-yrs), C-EDGE 5pt
          // fav (M +5.3/W +10.9), D-MA 2pt fav (women +5.4). Every other favorite cell
          // backtests flat-to-negative.
          if (dp >= 5) {
            const d5g = gpick(stx.goldfav_d5)
            add(`⭐✓ FADE-GOLD 5pt+ ${wAll ? 'W' : 'M'}`, !dog1, b26('+1.0¹', '+9.4¹'), d5g, gcol(d5g, '#f5f13b'))
          } else if (dp >= 4) {
            addG('⭐✓ FADE-GOLD 4-5pt', !dog1, b26('+1.0¹', '+9.4¹'), stx.goldfav_d45, '#f5f13b')
          } else {
            addG('⭐✓ FADE-GOLD', !dog1, b26('+1.0', '+9.4'), stx.grayhate_fav, '#f5f13b')
          }
          addG('HATED DOG', dog1, b26('−22.8', '−41.8'), stx.grayhate_dog, '#f85149')
        }
        // 🥇 GOLD NAME chip (2026-10-05, user ask: chip the gold names, not just the glow).
        // Every neon-yellow name = the union of C+gray DOGs (star → g1) and gray-hated
        // FAVORITES (hate → !dog1). add() shows THIS match's gender record (men +4.1% / 201,
        // women −10.4% / 107) and recolors by it (green on men, red on women).
        if (star || hate) addG('🥇 GOLD NAME', star ? g1 : !dog1, b26('+4.1', '−10.4'), stx.gold_names, '#f5f13b')
        if (c1 !== g1) {
          addG('FIGHT C-side', c1, b26('−1.3', '+2.3'), stx.cvg_c, '#f85149')
          addG('FIGHT gray-side', g1, b26('−8.0', '−6.6'), stx.cvg_gray, '#8b949e')
        }
        if (aP !== null && bP !== null) {
          if (aP !== c1 && bP !== c1 && g1 === c1 && !dog1 === c1 && c1 !== dog1 && !star) addG('RED C+GRAY FAV', c1, b26('+1.5', '+2.6'), stx.c_alone_gray_fav, '#f85149')
          if (aP === bP && bP === c1) {
            // Gender-aware consensus chips (2026-09-30, user ask): M/W in the label and
            // that gender's own live lane (bt26 gendered where measured: men −3.2 /
            // women +1.7 for A+B+C). Live all-6: M 12-3 +3.2 vs W 3-2 −26.8 — blending hides it.
            addG('A+B+C', c1, b26('−3.2', '+1.7'), stx.abc_agree, '#58a6ff')
            if (c1 === dog1) addG('A+B+C DOG', c1, b26('−0.9', '+20.8'), stx.abc_dog, '#58a6ff')
            const am = ma3.market_aware_p1, bm = mb3.market_aware_p1
            if (am != null && bm != null && (am >= 0.5) === c1 && (bm >= 0.5) === c1 && g1 === c1) {
              addG('ALL 6', c1, b26('−3.2', '+0.9'), stx.all6_agree, '#79c0ff')
            }
          }
          // B-alone measured (2026-09-30): B's side of splits bt −5.9 all-years / −3.1
          // 2026; strict B-vs-both −15.4. The live +5% is variance — not a take.
          if (aP !== bP) addG('B›A', bP, b26('−2.1', '−12.5'), lnx.b_alone, '#d29922')
          // FADE A (2026-09-30): A against both B and C → the B&C name is the play.
          // bt +8.0% all-years on 5,080; dog half +14.8; dog+gray +20.5 (2026 +19.7).
          // Sub-cells stack like the star chips (user ask: show them all when present).
          if (aP !== bP && bP === c1) {
            addG('★ FADE A', bP, b26('+7.3', '+3.5'), stx.fade_a, '#f5f13b')
            if (bP === dog1) {
              addG('★ FADE-A DOG', bP, b26('+13.0', '+11.0'), stx.fade_a_dog, '#f5f13b')
              if (g1 === bP) addG('★ FADE-A DOG+GRAY', bP, b26('+19.8', '+23.3'), stx.fade_a_dog_gray, '#f5f13b')
            } else {
              addG('FADE-A FAV', bP, b26('+2.1', '−3.6'), stx.fade_a_fav, '#8b949e')
            }
          }
          if (aP !== c1 && bP !== c1) {
            // C-ALONE: the live-earning lane is C-alone WITH gray confirmation
            // (stx.c_alone_gray -- men +7.2% / women −6.0%). Raw c_alone isn't tracked
            // (n=0), so when gray sits on C's side read that lane; add() recolors by this
            // match's gender (men green, women red). Gray-disagrees falls back to watch.
            if (g1 === c1) addG('C-ALONE+GRAY', c1, b26('+7.2', '−6.0'), stx.c_alone_gray, '#8b949e')
            else addG('C-ALONE', c1, b26('+6.0', '+26.7'), laneRec && laneRec.c_alone, '#8b949e')
          }
        }
        // Edge chips read their side+gender cell (2026-09-30, user ask): live, these
        // lanes only earn on MEN'S FAVORITES (C-edge fav M +10.8, gray2 fav M +7.6);
        // the edge-on-DOG halves are −19..−40% live for BOTH genders (dogs only pay
        // via the star cells, where raw C and gray agree).
        const gsKey = (side) => `${wAll ? 'w' : 'm'}_${((mc3.market_p1 < 0.5) === side) ? 'dog' : 'fav'}`
        const cEdge = Math.abs(mc3.p1_prob - mc3.market_p1)
        if (cEdge >= 0.05) {
          const ceS = mc3.p1_prob - mc3.market_p1 >= 0.05
          const ceDog = (mc3.market_p1 < 0.5) === ceS
          const ceL = (laneRec && laneRec.c_edge || {})[gsKey(ceS)]
          // fav side wears ⭐✓ (validated favorite cell: bt all-yrs M +5.3 / W +10.9,
          // 2026 M +4.6 / W +11.0 — one of only three +EV favorite cells) and gold base.
          add(`${ceDog ? '' : '⭐✓ '}C-EDGE 5pt ${ceDog ? 'DOG' : 'FAV'} ${wAll ? 'W' : 'M'}`, ceS, ceDog ? b26('+2.4¹', '+18.1¹') : b26('+4.6¹', '+11.0¹'), ceL, gcol(ceL, ceDog ? '#8b949e' : '#e3b341'))
        }
        const gEdgeAbs = Math.abs(mc3.market_aware_p1 - mc3.market_p1)
        if (gEdgeAbs >= 0.02) {
          const gmS = mc3.market_aware_p1 - mc3.market_p1 >= 0.02
          const gmDog = (mc3.market_p1 < 0.5) === gmS
          const gmL = (laneRec && laneRec.cma_edge || {})[gsKey(gmS)]
          add(`GRAY 2pt ${gmDog ? 'DOG' : 'FAV'} ${wAll ? 'W' : 'M'}`, gmS, gmDog ? b26('+7.3¹', '+13.2¹') : b26('+1.0¹', '+9.4¹'), gmL, gcol(gmL, '#8b949e'))
        }
        // C-MC + c75 TAKE chip (2026-10-03, user "I'm taking every game c-MC and c75
        // agree on"): c50 (visible C-MC) and the c75 variant on the SAME side -> the
        // user's play. Colors by its own live lane (green while earning). They agree on
        // ~88% of games, so this marks most C-MC cards; the point is to spot them fast.
        if (mc3 && mc3.mc && mc3.mc.sims && mc3.mc_c75_p1 != null) {
          const s50 = mc3.mc.p1_pct >= 50
          const s75 = mc3.mc_c75_p1 >= 0.5
          if (s50 === s75) {
            addG('⚄ C-MC+c75 TAKE', s50, 'take', stx.mcc_c75_agree, gcol(stx.mcc_c75_agree, '#a78bfa'))
            // c50+c75 both on the market DOG = a validated priced-dog take (+19%, 47% vs
            // 38% implied). Shown green; the D-split flags below refine it.
            if (s50 === dog1) addG('🐕 c50+c75 DOG', dog1, 'bt +19 (47%)', stx.cc75_dog, gcol(stx.cc75_dog, '#3fb950'))
            // user hypothesis (2026-10-04): c50+c75 on a DOG + Model D agrees. Flag it and
            // whether D is on the dog (your idea) or on the fav (the backfill-stronger half).
            const dP2 = match.model_d && match.model_d.p1_prob != null ? match.model_d.p1_prob >= 0.5 : null
            if (s50 === dog1 && dP2 !== null) {
              if (dP2 === dog1) addG('🐕 c50+c75+D DOG', dog1, 'bt 46% (watch)', stx.cc75_d_dog, gcol(stx.cc75_d_dog, '#f5f13b'))
              else addG('🐕 c50+c75 DOG · D on fav', dog1, 'bt 73%', stx.cc75_nod_dog, gcol(stx.cc75_nod_dog, '#3fb950'))
            }
          }
        }
        // C75 MEN chip (2026-10-05, user ask): the c75 variant's side is live-positive on
        // the MEN's side (+8.3% / 117) but flat-negative on women, so mark the MEN's c75
        // pick specifically. Only fires on men's matches; add() auto-shows the men's lane.
        // C75 chip SPLIT BY SIDE (2026-10-06, user "split it that way"): the blended c75 ROI
        // was dog-earned; show the SIDE-specific record so a favorite pick can't borrow the
        // dogs' number. Dogs are the edge (+34% men); favorites are flat/neg (shows red).
        // UNGATED for women (2026-10-07, user "split every signal men/women"): the chip
        // fires on BOTH genders; the record is this match's gender cell of the side-split
        // lane, so a women's c75 pick shows the W number, never borrows the men's.
        if (mc3.mc_c75_p1 != null) {
          const _c75S = mc3.mc_c75_p1 >= 0.5, _dg = mc3.market_p1 < 0.5
          const _c75dog = (_c75S === _dg)
          const _lane = _c75dog ? stx.mc_c75_dog : stx.mc_c75_fav
          add(`⚄ C75 ${_c75dog ? 'DOG' : 'FAV'} ${wAll ? 'W' : 'M'}`, _c75S,
              _c75dog ? 'dogs = the edge' : 'favs flat/neg',
              _lane, gcol(gpick(_lane), '#3fb950'))
        }
        // 🧊 PURE-FORM × C75 (2026-10-06, user "wire that tracker + notify when +ROI only"):
        // quality-adjusted last-10-on-surface recent form (NO serve stats) vs the C-MC(c75)
        // lean. The live edge is in the DISAGREE cell -- the market overvalues recent form,
        // so when form fades the model's c75 pick the pick has overperformed. Shown ONLY when
        // this match's gender cell is currently +ROI (men disagree +18.9%); auto-updates.
        if (mc3.mc_c75_p1 != null && match.pure_form && match.pure_form.agree_c75 != null) {
          const _pfDis = !match.pure_form.agree_c75
          const _c75p1b = mc3.mc_c75_p1 >= 0.5
          const _dogPick = (_c75p1b === (mc3.market_p1 < 0.5))   // c75 pick is the market dog
          const _pfLane = _pfDis ? (_dogPick ? stx.pf_c75_dis_dog : stx.pf_c75_dis_fav) : stx.pf_c75_agr
          const _pfG = gpick(_pfLane)
          if (_pfG && _pfG.n >= 12 && _pfG.roi_pct > 0) {   // n>=12: dog-split sample is thinner
            // Name after the label = the side to TAKE. "FADE FORM → TAKE [name]": recent form
            // likes the opponent, you fade it and back the named (model) side.
            addG(_pfDis ? '🧊 FADE FORM → TAKE' : '🔥 FORM → TAKE', mc3.mc_c75_p1 >= 0.5,
                _pfDis ? 'form likes opp' : 'form backs pick', _pfLane, _pfDis ? '#56d4dd' : '#f0883e')
          }
        }
        // ALL-10 AGREE chip (2026-10-04, user ask): every model + MC on the same side.
        // Highest-hit marker (~80%), small +ROI (near-always a chalk favorite).
        {
          const dP3 = match.model_d && match.model_d.p1_prob != null ? match.model_d.p1_prob >= 0.5 : null
          const dmaP = match.model_d && match.model_d.market_aware_p1 != null ? match.model_d.market_aware_p1 >= 0.5 : null
          const mcS = mc3 && mc3.mc && mc3.mc.sims ? mc3.mc.p1_pct >= 50 : null
          const mcdS = match.model_d && match.model_d.mc && match.model_d.mc.sims ? match.model_d.mc.p1_pct >= 50 : null
          const c75S = mc3 && mc3.mc_c75_p1 != null ? mc3.mc_c75_p1 >= 0.5 : null
          const cuS = mc3 && mc3.mc_cutr_p1 != null ? mc3.mc_cutr_p1 >= 0.5 : null
          const all = [aP, bP, c1, g1, dP3, dmaP, mcdS, mcS, c75S, cuS]
          if (all.every(x => x !== null) && all.every(x => x === all[0])) {
            addG('✅ ALL-10 AGREE', all[0], 'bt 80% +4.4', stx.all10_agree, '#8b949e')
          }
        }
        // AGAINST A watch chip (2026-10-04, user ask): the side opposite Model A, every
        // match. Colors by its own live lane (watch grey; green if it ever earns). Hidden
        // in green-only mode while negative.
        if (aP !== null) addG('↺ AGAINST A', !aP, 'watch', stx.against_a, gcol(stx.against_a, '#8b949e'))
        // D-MA 2pt EDGE chip (2026-10-04, user ask): Model D's market-aware head is >=2pts
        // over the market on its favored side -- the only mkt-aware head +ROI when it
        // dissents (+7.5%/53 backfill). Colors by its own live lane.
        if (match.model_d && match.model_d.market_aware_p1 != null && mc3 && mc3.market_p1 != null) {
          const dmaS1 = match.model_d.market_aware_p1 >= 0.5
          const dmaSide = dmaS1 ? match.model_d.market_aware_p1 : 1 - match.model_d.market_aware_p1
          const mktSide = dmaS1 ? mc3.market_p1 : 1 - mc3.market_p1
          if (dmaSide - mktSide >= 0.02) {
            // SIDE-SPLIT (2026-10-07 gender×side backtest): the FAV half is the validated
            // cell on WOMEN (+5.4 all-yrs / +6.2 in 2026, 75% hit — one of the three +EV
            // favorite cells → ⭐✓ W); men fav is flat (bt26 −0.8). Dog half: M +1.8 / W +15.2.
            const dmaFav = dmaS1 !== dog1
            const dmaMark = dmaFav && wAll
            add(`${dmaMark ? '⭐✓ ' : '📈 '}D-MA 2pt ${dmaFav ? 'FAV' : 'DOG'} ${wAll ? 'W' : 'M'}`, dmaS1,
                dmaFav ? b26('−0.8¹', '+6.2¹') : b26('+1.8¹', '+15.2¹'), stx.dma_edge2,
                gcol(stx.dma_edge2, dmaMark ? '#e3b341' : '#3fb950'))
          }
        }
        // D + GRAY DOG and D ALONE chips (2026-10-05, user ask "add these roi%s to
        // selective men/women matches"). Both read Model D's favored side.
        if (match.model_d && match.model_d.p1_prob != null) {
          const dS = match.model_d.p1_prob >= 0.5
          // D + GRAY DOG: Model D AND the gray line both on the market underdog -- D's best
          // backtest cell, live MEN +86.5% (5-1) vs women +9% (n2). Men-focused: green on
          // men, grey watch on women (women sample is 2; the edge is men-side).
          if (dS === dog1 && g1 === dog1) {
            addG('🐕 D+GRAY DOG', dog1, b26('−0.8¹', '+5.5¹'), stx.d_gray_dog, gcol(gpick(stx.d_gray_dog), '#3fb950'))
          }
          // D ALONE: Model D dissents from A, B AND C. Thesis is "zero info," but live it's
          // MEN +5.8% (8-7, n15) / women +113% (3-0, n3 = noise). Grey watch base; add()
          // greens the gender that's actually earning on a real sample (men).
          if (aP !== null && bP !== null && aP !== dS && bP !== dS && c1 !== dS) {
            addG('🧩 D ALONE', dS, 'watch', stx.d_alone, '#8b949e')
          }
        }
        // MC BIG DOG chip (2026-10-01, user hypothesis): the sim favors the market
        // underdog by >=60%. Grey/watch color — unproven, tracked from zero.
        const mcc = match.model_d && match.model_d.mc
        if (mcc && mcc.sims) {
          const mcDogP = dog1 ? mcc.p1_pct / 100 : 1 - mcc.p1_pct / 100
          if (mcDogP >= 0.60) {
            // backtest (2026-10-02): raw MC big dog −6.0%, but +19.3% when GRAY also
            // likes the dog. Split so the gray-backed play and the trap look different.
            if (g1 === dog1) addG(`★ MC DOG+GRAY ${Math.round(mcDogP * 100)}%`, dog1, 'bt +19.3', stx.mc_biggray, '#f5f13b')
            else addG(`MC BIG DOG ${Math.round(mcDogP * 100)}% · no gray`, dog1, 'bt −6.0', stx.mc_dog_big, '#f85149')
          }
          // MC TOSS-UP (2026-10-02, user ask): MC's closest calls (conf 50-60%) are the
          // one MC bucket positive live (+15% on 13, thin). Marked green as a watch.
          const mcConf = Math.max(mcc.p1_pct, 100 - mcc.p1_pct)
          if (mcConf >= 50 && mcConf < 60) addG('MC TOSS-UP', mcc.p1_pct >= 50, 'watch', stx.mc_tossup, gcol(stx.mc_tossup, '#8b949e'))
          // MC agrees with a 4/4 slip (A=B=C=D all one side) — user ask 2026-10-02.
          // Tracked, not a take (bt −2.2%); marks the slip the user wanted flagged.
          const mcSide1 = mcc.p1_pct >= 50
          const dP = match.model_d && match.model_d.p1_prob != null ? match.model_d.p1_prob >= 0.5 : null
          if (aP !== null && bP !== null && dP !== null
              && aP === bP && bP === c1 && c1 === dP && mcSide1 === c1) {
            addG('⚄+4/4 SLIP', c1, 'bt −2.2', stx.mc_4of4, gcol(stx.mc_4of4, '#8b949e'))
          }
          // previously-unmarked positive watch lanes (2026-10-04, user audit): MC DOG =
          // serve-MC favors the market dog (+18%/34); MC+GREEN = serve-MC agrees a green
          // name (+18%/28); MC-C+MC-D = the C-MC and serve-MC land the same side (+10%/73).
          if (mcSide1 === dog1) addG('⚄ MC DOG', dog1, 'watch', stx.mc_dog, gcol(stx.mc_dog, '#8b949e'))
          if (!star && !hate && mcSide1 === g1) addG('⚄ MC+GREEN', g1, 'watch', stx.mc_green, gcol(stx.mc_green, '#8b949e'))
          if (mc3 && mc3.mc && mc3.mc.sims && (mc3.mc.p1_pct >= 50) === mcSide1) {
            addG('⚄ MC-C+MC-D', mcSide1, 'watch', stx.mc_c_and_d, gcol(stx.mc_c_and_d, '#8b949e'))
          }
        }
        // 💰 PRICE ✓ chip (2026-10-05, user ask): a gated Best-tab signal fires AND the pick
        // sits in a profitable price window (men +100..+250 or −300..−600, women +150..+250).
        // On the full log these ran +24% ROI vs +6.7% for all Best picks -- signal × price.
        {
          const bs = bestSig(match)
          const gen = wAll ? 'w' : 'm'
          let top = null
          if (bs) for (const e of BEST_SIGNALS) {
            const sideB = e.fire(bs); if (sideB == null) continue
            const rb = (stx[e.key] || {})[gen] || {}; const nb = rb.n || 0
            if (nb < BEST_N) continue
            if (100 * rb.wins / nb < BEST_HIT || rb.roi_pct < BEST_ROI) continue
            if (!top || rb.roi_pct > top.roi) top = { side: sideB, roi: rb.roi_pct }
          }
          const odB = (top && match.live_odds) ? Number(top.side ? match.live_odds.player_1 : match.live_odds.player_2) : null
          const a10B = isAll10Agree(bs)
          if (top && inSweetPrice(odB, gen, a10B))
            chips.push(['💰 PRICE ✓', nm(top.side), priceBand(odB, gen, a10B), `+${Math.round(top.roi)}% @${odB > 0 ? '+' : ''}${odB}`, '#e3b341'])
        }
        // ⚖️ CONFLICT RESOLVERS (2026-10-05, user ask): when signals point OPPOSITE ways on a
        // card, which side to trust -- gender-specific, from the live conflict lanes. Rendered
        // DARK PURPLE so they're easy to spot; each tooltip says WHEN to favor it + the live
        // edge. Priority ①→④ (① overrides the rest). Shown regardless of green-only (they're
        // directional guides, not bet lanes).
        const nmc = sd => (sd ? match.player_1 : match.player_2).split(' ').slice(-1)[0]
        const gcn = wAll ? 'w' : 'm'
        const dPc = match.model_d && match.model_d.p1_prob != null ? match.model_d.p1_prob >= 0.5 : null
        const conflicts = []   // [priority, text, tooltip, laneKey]  -- laneKey carries the LIVE record
        // ① C + gray BOTH on the market dog (men): the board's biggest edge; overrides any
        //    favorite-side signal firing against it. Women: skip (these don't work live).
        if (star && !wAll && dog1 != null)
          conflicts.push(['①', `TRUST DOG · ${nmc(dog1)}`, 'C AND the gray line both on the market DOG (men) — the board’s biggest edge; take the dog, it beats any favorite-side signal firing against it. (Women: skip — these don’t work.) Live record shown.', 'cr1_stardog'])
        // ② C vs gray disagree: men side with C, women side with gray.
        if (c1 !== g1) {
          if (!wAll) conflicts.push(['②', `TRUST C · ${nmc(c1)}`, 'C and the gray (market-aware) line disagree — MEN: side with C (C has beaten gray live here). Live record shown.', 'cr2_cvg'])
          else conflicts.push(['②', `TRUST GRAY · ${nmc(g1)}`, 'C and the gray (market-aware) line disagree — WOMEN: side with gray. Live record shown.', 'cr2_cvg'])
        }
        // ③ A dissents from B&C (men only): fade A, take the B&C side. Women: fade-A loses, no badge.
        if (aP !== null && bP !== null && aP !== bP && bP === c1 && !wAll)
          conflicts.push(['③', `FADE A → ${nmc(bP)}`, 'Model A disagrees with B & C (men): take the B&C side (fade A). (Women: leave A alone — fade-A loses.) Live record shown.', 'cr3_fadea'])
        // ④ Gray HATES a dog: men take the fav, women take the dog -- UNLESS it's the ⑤
        //    collision (every model also on the fav), where the women-dog edge disappears.
        const onfavC = x => x === !dog1
        const collision = hate && aP !== null && bP !== null && dPc !== null
          && onfavC(aP) && onfavC(bP) && onfavC(c1) && onfavC(g1) && onfavC(dPc)
        if (hate) {
          if (!wAll) conflicts.push(['④', `TRUST FAV · ${nmc(!dog1)}`, 'The gray line hates the market dog (men): take the FAVORITE — the hated dog has lost live. Live record shown.', 'cr4_grayhate'])
          else if (collision) {
            // Price-split (2026-10-05): the collision pass is NOT uniform. A 65-85% favorite
            // has been mildly +EV; coin-flip (50-65%) and extreme chalk (85%+) favorites lose.
            const favp = Math.max(mc3.market_p1, 1 - mc3.market_p1)
            if (favp >= 0.65 && favp < 0.85)
              conflicts.push(['⑤', `LEAN FAV · ${nmc(!dog1)}`, 'COLLISION (every base model on the fav + gray hates the dog) at a 65-85% favorite price: the dog edge is gone, but the FAVORITE here has been positive — but ONLY on WOMEN (+13.8% live, n10), driven by the 75-85% slice; on MEN it is flat (+0.6%). Thin samples, low conviction. This match’s gender record shown.', 'cr5_coll_leanfav'])
            else
              conflicts.push(['⑤', 'COLLISION · PASS (no edge)', 'COLLISION at a near-coin-flip (50-65%) or extreme-chalk (85%+) favorite price: NEITHER side is +EV — the dog is deeply negative and the favorite has also lost here. NO-BET, skip. NOTE: even if ✅ ALL-10 AGREE fires here (a high WIN RATE like 14-3), that is win rate, not profit — ALL-10 only makes money OUTSIDE collisions (+26.8%, 6-0 on women); inside one it loses (−3.2%, and −19% at 50-65% fav). You will usually win the match but still lose money at the price. This match’s gender record shown.', 'cr5_coll_passfav'])
          }
          else conflicts.push(['④', `TRUST DOG · ${nmc(dog1)}`, 'The gray line hates the market dog (WOMEN): take the DOG — it has paid live at the plus price. (But if every model also agrees on the favorite, rule ⑤ overrides this and says fade the dog.) Live record shown.', 'cr4_grayhate'])
        }
        // ➕ EVERY POSITIVE SIGNAL ON THE PICK IT FIRES ON (2026-10-07, user "i want them
        // on every board pick that has them not at the top"): the +EV panel's content,
        // distributed per card. For each lane in the FULL catalog (watch lanes included)
        // that FIRES on this match, read the gender×side cell for the side it bets; if
        // that cell is currently +ROI, chip it with record + n (grey while n<12, green
        // on a real sample). Lanes already chipped above are skipped (usedLanes identity
        // dedup) so nothing shows twice. KEEP CONDITIONS IN LOCKSTEP with
        // tennis_log.get_ab25_record's bet() calls.
        {
          const dP9 = match.model_d && match.model_d.p1_prob != null ? match.model_d.p1_prob >= 0.5 : null
          const dmaV9 = match.model_d && match.model_d.market_aware_p1 != null ? match.model_d.market_aware_p1 : null
          const dmaS9 = dmaV9 != null ? dmaV9 >= 0.5 : null
          const mcd9 = (match.model_d && match.model_d.mc && match.model_d.mc.sims) ? match.model_d.mc.p1_pct / 100 : null
          const mcdS9 = mcd9 != null ? mcd9 >= 0.5 : null
          const c509 = (mc3.mc && mc3.mc.sims) ? mc3.mc.p1_pct / 100 : null
          const c50S9 = c509 != null ? c509 >= 0.5 : null
          const c75S9 = mc3.mc_c75_p1 != null ? mc3.mc_c75_p1 >= 0.5 : null
          const cuS9 = mc3.mc_cutr_p1 != null ? mc3.mc_cutr_p1 >= 0.5 : null
          const pfe9 = match.pure_form && match.pure_form.edge != null ? match.pure_form.edge : null
          const mk19 = mc3.market_p1
          const favp9 = Math.max(mk19, 1 - mk19)
          const passfav9 = aP !== null && bP !== null && aP !== c1 && bP !== c1 && g1 === c1 && c1 !== dog1
          const alone9 = aP !== null && bP !== null && aP !== c1 && bP !== c1
          const lo9 = match.live_odds || {}
          const am9 = sd => { const v = Number(sd ? lo9.player_1 : lo9.player_2); return isNaN(v) ? null : v }
          const dec9 = sd => { const v = am9(sd); return v == null ? null : (v > 0 ? 1 + v / 100 : 1 + 100 / Math.abs(v)) }
          const h109 = [aP, bP, c1, g1, dP9, dmaS9, mcdS9, c50S9, c75S9, cuS9]
          const h10ok = h109.every(x => x !== null)
          const all109 = h10ok && h109.every(x => x === h109[0])
          const n1side9 = h10ok ? h109.filter(Boolean).length : null
          const lateRnd9 = (() => { const rn = (match.round || '').toLowerCase(); return rn && !(rn.includes('1st') || rn.includes('qual') || rn.includes('128') || rn.includes('of 64')) })()
          // [study key, label, fire() -> side it bets (p1-bool) or null] — mirrors bet()
          const CAT9 = [
            ['cvg_c', 'FIGHT C', () => c1 !== g1 ? c1 : null],
            ['cvg_gray', 'FIGHT GRAY', () => c1 !== g1 ? g1 : null],
            ['gray_dog4', 'GRAY 4pt+ DOG', () => (gdog - mdog >= 0.04 && g1 === dog1) ? dog1 : null],
            ['grayhate_dog', 'HATED DOG', () => hate ? dog1 : null],
            ['grayhate_fav', 'FADE-GOLD FAV', () => hate ? !dog1 : null],
            ['gold_names', 'GOLD NAME', () => star ? g1 : (hate ? !dog1 : null)],
            ['green_names', 'GREEN NAME', () => (!star && !hate && !passfav9) ? g1 : null],
            ['stardog_prime', 'PRICED STAR DOG', () => { const d = dec9(dog1); return (star && d != null && d >= 2.0) ? dog1 : null }],
            ['apex_dog', 'APEX DOG', () => { const d = dec9(dog1); return (star && d != null && d >= 2.0 && alone9) ? dog1 : null }],
            ['cgray_dog_late', 'STAR DOG LATE RND', () => (star && lateRnd9) ? dog1 : null],
            ['tier1', 'TIER 1', () => (star && (alone9 || (gdog - mdog) >= 0.04)) ? dog1 : null],
            ['tier2', 'TIER 2', () => (star && !(alone9 || (gdog - mdog) >= 0.04)) ? dog1 : null],
            ['tier3', 'TIER 3 FAV', () => (!star && hate) ? !dog1 : null],
            ['cr5_collision', 'COLLISION DOG', () => (hate && aP === !dog1 && bP === !dog1 && c1 === !dog1 && g1 === !dog1 && dP9 === !dog1) ? dog1 : null],
            ['all10_price_m', 'ALL-10 −140..−300', () => { if (wAll || !all109) return null; const o = am9(h109[0]); return (o != null && o >= -300 && o <= -140) ? h109[0] : null }],
            ['split64_fade', 'FADE 6-4 SPLIT', () => (h10ok && (n1side9 === 4 || n1side9 === 6)) ? (n1side9 === 4) : null],
            ['pf_c75_agr', 'FORM BACKS c75', () => (c75S9 !== null && pfe9 != null && ((pfe9 > 0) === c75S9)) ? c75S9 : null],
            ['pf_c75_dis_dog', 'FADE FORM DOG', () => (c75S9 !== null && pfe9 != null && ((pfe9 > 0) !== c75S9) && c75S9 === dog1) ? c75S9 : null],
            ['pf_c75_dis_fav', 'FADE FORM FAV', () => (c75S9 !== null && pfe9 != null && ((pfe9 > 0) !== c75S9) && c75S9 !== dog1) ? c75S9 : null],
            ['pf_ghfav', 'FORM+GOLD FAV', () => (pfe9 != null && ((pfe9 > 0) === !dog1) && hate) ? !dog1 : null],
            ['pf_ghfav_pr', 'FORM+GOLD FAV PR', () => (pfe9 != null && ((pfe9 > 0) === !dog1) && hate && favp9 >= 0.75 && favp9 <= 0.88) ? !dog1 : null],
            ['pf_c75fav_pr', 'FORM+c75 FAV PR', () => (pfe9 != null && ((pfe9 > 0) === !dog1) && c75S9 === !dog1 && favp9 >= 0.78 && favp9 <= 0.88) ? !dog1 : null],
            ['pf_a10fav_pr', 'FORM+ALL10 FAV PR', () => (pfe9 != null && ((pfe9 > 0) === !dog1) && all109 && h109[0] === !dog1 && favp9 >= 0.78 && favp9 <= 0.88) ? !dog1 : null],
            ['c75fav_formfade', 'c75FAV × FORM-FADE', () => (c75S9 !== null && c75S9 !== dog1 && pfe9 != null && ((pfe9 > 0) !== c75S9)) ? c75S9 : null],
            ['d_all', 'MODEL D', () => dP9],
            ['dma_all', 'D-GRAY', () => dmaS9],
            ['d_gray_dog', 'D+GRAY DOG', () => (dP9 !== null && dmaS9 !== null && dP9 === dmaS9 && dP9 === dog1) ? dP9 : null],
            ['dma_edge2', 'D-MA 2pt', () => { if (dmaS9 === null) return null; const ds = dmaS9 ? dmaV9 : 1 - dmaV9; const ms = dmaS9 ? mk19 : 1 - mk19; return (ds - ms >= 0.02) ? dmaS9 : null }],
            ['d_alone', 'D ALONE', () => (dP9 !== null && aP !== null && bP !== null && aP !== dP9 && bP !== dP9 && c1 !== dP9) ? dP9 : null],
            ['mc_all', 'MC', () => mcdS9],
            ['mc_tossup', 'MC TOSS-UP', () => { if (mcd9 == null) return null; const cf = Math.max(mcd9, 1 - mcd9); return (cf >= 0.5 && cf < 0.6) ? mcdS9 : null }],
            ['mc_dog', 'MC DOG', () => (mcdS9 !== null && mcdS9 === dog1) ? mcdS9 : null],
            ['mc_dog_big', 'MC BIG DOG', () => { if (mcdS9 === null || mcdS9 !== dog1) return null; return ((dog1 ? mcd9 : 1 - mcd9) >= 0.6) ? mcdS9 : null }],
            ['mc_biggray', 'MC DOG+GRAY', () => { if (mcdS9 === null || mcdS9 !== dog1 || g1 !== dog1) return null; return ((dog1 ? mcd9 : 1 - mcd9) >= 0.6) ? mcdS9 : null }],
            ['mc_gold', 'MC+GOLD', () => { const gs = star ? dog1 : (hate ? !dog1 : null); return (gs !== null && mcdS9 === gs) ? gs : null }],
            ['mc_green', 'MC+GREEN', () => (!star && !hate && !passfav9 && mcdS9 !== null && mcdS9 === g1) ? g1 : null],
            ['mc_4of4', 'MC+4/4', () => (aP !== null && bP !== null && dP9 !== null && aP === bP && bP === c1 && c1 === dP9 && mcdS9 === c1) ? c1 : null],
            ['mc_c_all', 'C-MC', () => c50S9],
            ['mc_c_and_d', 'C-MC+MC', () => (c50S9 !== null && mcdS9 !== null && c50S9 === mcdS9) ? c50S9 : null],
            // mc_c75_all skipped: its gender×side cell is the same population as the
            // mc_c75_dog/fav split lanes below (and the men's ⚄ C75 chip) -- would double-print.
            ['mc_c75_dog', 'c75 DOG', () => (c75S9 !== null && c75S9 === dog1) ? c75S9 : null],
            ['mc_c75_fav', 'c75 FAV', () => (c75S9 !== null && c75S9 !== dog1) ? c75S9 : null],
            ['mcc_c75_agree', 'c50+c75', () => (c50S9 !== null && c75S9 !== null && c50S9 === c75S9) ? c50S9 : null],
            ['mc4ovr_fav_band', '4-MC>MKT −200/300', () => { if (mcd9 === null || c509 === null || mc3.mc_c75_p1 == null || mc3.mc_cutr_p1 == null) return null; const favS = !dog1; const mkf = Math.max(mk19, 1 - mk19); const pf = [mcd9, c509, mc3.mc_c75_p1, mc3.mc_cutr_p1].map(v => favS ? v : 1 - v); if (!pf.every(v => v > mkf)) return null; const o = am9(favS); return (o != null && o >= -300 && o <= -200) ? favS : null }],
            ['fight_mc4_dog', '⚔🐕 FIGHT-FLIP', () => { if (c1 === g1 || g1 === dog1) return null; if (mcdS9 === null || c50S9 === null || c75S9 === null || cuS9 === null) return null; if (!(mcdS9 === c50S9 && c50S9 === c75S9 && c75S9 === cuS9 && c50S9 === dog1)) return null; const o = am9(dog1); return (o != null && o >= 100 && o <= 250) ? dog1 : null }],
            ['mc4_dog_band', '4-MC DOG +100/250', () => { if (mcdS9 === null || c50S9 === null || c75S9 === null || cuS9 === null) return null; if (!(mcdS9 === c50S9 && c50S9 === c75S9 && c75S9 === cuS9 && c50S9 === dog1)) return null; const o = am9(c50S9); return (o != null && o >= 100 && o <= 250) ? c50S9 : null }],
            ['cc75_dog', 'c50+c75 DOG', () => (c50S9 !== null && c50S9 === c75S9 && c50S9 === dog1) ? c50S9 : null],
            ['cc75_d_dog', 'c50+c75+D DOG', () => (c50S9 !== null && c50S9 === c75S9 && c50S9 === dog1 && dP9 === c50S9) ? c50S9 : null],
            ['cc75_nod_dog', 'c50+c75 DOG·D FAV', () => (c50S9 !== null && c50S9 === c75S9 && c50S9 === dog1 && dP9 !== null && dP9 !== c50S9) ? c50S9 : null],
            ['mc_cutr_all', 'cUTR', () => cuS9],
            ['all10_agree', 'ALL-10', () => all109 ? h109[0] : null],
            ['against_a', 'AGAINST A', () => aP !== null ? !aP : null],
            ['fade_a', 'FADE A', () => (aP !== null && bP !== null && aP !== bP && bP === c1) ? bP : null],
            ['fade_a_dog', 'FADE-A DOG', () => (aP !== null && bP !== null && aP !== bP && bP === c1 && bP === dog1) ? bP : null],
            ['fade_a_dog_gray', 'FADE-A DOG+GRAY', () => (aP !== null && bP !== null && aP !== bP && bP === c1 && bP === dog1 && g1 === bP) ? bP : null],
            ['fade_a_fav', 'FADE-A FAV', () => (aP !== null && bP !== null && aP !== bP && bP === c1 && bP !== dog1) ? bP : null],
            ['abc_agree', 'A+B+C', () => (aP !== null && bP !== null && aP === bP && bP === c1) ? c1 : null],
            ['abc_dog', 'A+B+C DOG', () => (aP !== null && bP !== null && aP === bP && bP === c1 && c1 === dog1) ? c1 : null],
            ['all6_agree', 'ALL 6', () => { const am = ma3 && ma3.market_aware_p1, bm = mb3 && mb3.market_aware_p1; return (aP !== null && bP !== null && am != null && bm != null && aP === bP && bP === c1 && c1 === g1 && (am >= 0.5) === c1 && (bm >= 0.5) === c1) ? c1 : null }],
            ['c_alone_gray', 'C-ALONE+GRAY', () => (alone9 && g1 === c1) ? c1 : null],
            ['c_alone_gray_dog', 'C-ALONE+GRAY DOG', () => (alone9 && g1 === c1 && c1 === dog1) ? c1 : null],
            ['c_alone_gray_fav', 'C-ALONE+GRAY FAV', () => (alone9 && g1 === c1 && c1 !== dog1) ? c1 : null],
          ]
          // root (non-study) lanes, same treatment
          const ROOT9 = [
            [lnx.a_alone, 'A›B', () => (aP !== null && bP !== null && aP !== bP) ? aP : null],
            [lnx.agree, 'A+B AGREE', () => (aP !== null && bP !== null && aP === bP) ? aP : null],
            [laneRec && laneRec.c_all, 'MODEL C', () => c1],
            [laneRec && laneRec.cma_all, 'GRAY', () => g1],
            [laneRec && laneRec.c_alone, 'C ALONE', () => alone9 ? c1 : null],
            [laneRec && laneRec.c_with, 'C+ONE', () => (aP !== null && bP !== null && aP !== bP && (c1 === aP || c1 === bP)) ? c1 : null],
            [laneRec && laneRec.agree_dog, 'STAR DOG', () => star ? dog1 : null],
          ]
          const cellOf9 = (L, side) => {
            if (!L) return null
            const ck = (wAll ? 'w' : 'm') + ((side === dog1) ? '_dog' : '_fav')
            if (L[ck] && L[ck].n !== undefined) return L[ck]
            const gg = wAll ? L.w : L.m
            if (gg && gg.n !== undefined) return gg
            return (L.n !== undefined) ? L : null
          }
          const pushEV = (L, label, side) => {
            if (side === null || side === undefined || !L || usedLanes.has(L)) return
            const cell = cellOf9(L, side)
            if (!cell || !cell.n || !(cell.roi_pct > 0)) return
            chips.push([`➕ ${label} ${wAll ? 'W' : 'M'}`, nm(side), '', `${lv(cell)} ${side === dog1 ? '🐕' : '⭐'} n${cell.n}`,
              cell.n < 12 ? '#8b949e' : '#3fb950'])
          }
          for (const [k, label, fire] of CAT9) pushEV(stx[k], label, fire())
          for (const [L9, label, fire] of ROOT9) pushEV(L9, label, fire())
          // pick-level price-band + 💎 stack lanes (men only, mirrors the Prices/Best logic)
          if (!wAll) {
            const bs9 = bestSig(match)
            let top9 = null
            const famsDog9 = new Set()
            if (bs9) for (const e of BEST_SIGNALS) {
              const sd = e.fire(bs9); if (sd == null) continue
              const rb = (stx[e.key] || {}).m || {}; const nb = rb.n || 0
              if (nb < BEST_N || 100 * rb.wins / nb < BEST_HIT || rb.roi_pct < BEST_ROI) continue
              if (!top9 || rb.roi_pct > top9.roi) top9 = { side: sd, roi: rb.roi_pct }
              if (sd === dog1) famsDog9.add(famOf(e.key))
            }
            if (top9) {
              const o9 = am9(top9.side)
              if (o9 != null && o9 >= 100 && o9 <= 250) pushEV(stx.price_dog_m, 'BEST@+100..250', top9.side)
              else if (o9 != null && o9 >= -600 && o9 <= -300) pushEV(stx.price_chalk_m, 'BEST@−300..600', top9.side)
            }
            if (all109) {
              const oA = am9(h109[0])
              if (oA != null && oA >= -300 && oA < -200) pushEV(stx.all10_200_300_m, 'ALL10@−200..300', h109[0])
              else if (oA != null && oA >= -200 && oA <= -140) pushEV(stx.all10_140_200_m, 'ALL10@−140..200', h109[0])
            }
            const oD = am9(dog1)
            if (famsDog9.size >= 2 && oD != null && oD >= 100 && oD <= 250) pushEV(stx.blue2stack, '💎 BLUE ★2 DOG', dog1)
          }
        }
        // GREEN-ONLY mode (2026-10-02, user ask): hide red/avoid signals and any chip
        // whose LIVE ROI is currently negative; keep green takes + not-yet-settled ones
        // ("until the live ROIs catch up"). Red = #f85149; live string starts with '-'.
        const shown = greenOnly
          ? chips.filter(([label, side, bt, live, color]) =>
              color !== '#f85149' && !(typeof live === 'string' && live.trim().startsWith('-')))
          : chips
        if (!shown.length && !conflicts.length) return null
        return (
          <>
            {conflicts.length ? (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}
                title="⚖️ CONFLICT RESOLVERS — when signals point opposite ways, which side to trust (gender-specific, from the live conflict lanes). ①→④ priority; ① overrides. Hover each for when to favor it.">
                {conflicts.map(([pri, txt, tip, key], i) => {
                  // LIVE auto-updating record for this resolver -- this match's GENDER cell
                  // (every resolver's edge is gender-specific, incl. the collision price
                  // split: lean-fav is women-only +13.8%, men ~flat +0.6%). Samples thin.
                  const rec = (stx[key] || {})[gcn] || {}
                  const n = rec.n || 0, roi = rec.roi_pct
                  const pos = n >= 8 && roi > 3, neg = n >= 8 && roi < -3
                  const col = neg ? '#f85149' : pos ? '#3fb950' : '#ddd6fe'
                  const bgc = neg ? '#3b1053' : pos ? '#07210f' : '#4c1d95'
                  const bd = neg ? '#f8514988' : pos ? '#3fb95088' : '#7c3aed'
                  const lvs = n ? `${roi > 0 ? '+' : ''}${Math.round(roi)}% (${rec.wins}-${n - rec.wins})` : 'new'
                  return (
                    <span key={i} className="mono" title={tip} style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.02em', padding: '2px 8px', borderRadius: 8, background: bgc, border: `1px solid ${bd}`, color: col }}>
                      ⚖️{pri} {txt} <span style={{ fontWeight: 400, opacity: 0.8 }}>· lv {lvs}</span>
                    </span>
                  )
                })}
              </div>
            ) : null}
            {shown.length ? (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}
                title="GREEN-ONLY (temporary): red/avoid signals and live-negative lanes are hidden while live samples are small. Shows green takes + lanes not yet settled. Backtest + live record per chip.">
                {shown.map(([label, side, bt, live, color], i) => (
                  <span key={i} className="mono" style={{ fontSize: 9, padding: '1px 6px', borderRadius: 8, border: `1px solid ${color}44`, color, background: `${color === '#f5f13b' ? '#f5f13b' : color}0d` }}>
                    {label}{side ? ` ${side}` : ''} <span style={{ color: 'var(--text-secondary)' }}>{bt} · lv {live}</span>
                  </span>
                ))}
              </div>
            ) : null}
          </>
        )
      })()}

      <div style={{
        marginTop: 14, padding: '14px 16px', borderRadius: 8,
        background: `linear-gradient(135deg, ${leagueColor}1c, ${leagueColor}0a)`, border: `1px solid ${leagueColor}55`,
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Favored:</span>
          <span style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1 }}>{favoredName}</span>{headlineTag}{(match.model_a && match.model_b && ((match.model_a.p1_prob >= 0.5) === (match.model_b.p1_prob >= 0.5))) ? (
            <span className="mono" style={{ fontSize: 9, color: '#3fb950', marginLeft: 6, border: '1px solid #3fb95055', borderRadius: 8, padding: '1px 6px' }}
              title="Models A and B pick the same winner — this match feeds the AGREE lane on the A vs B $25 tab.">A+B agree</span>
          ) : null}
          <span className="mono" style={{
            fontSize: 30, fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1,
            fontFamily: 'var(--font-display)', letterSpacing: '-0.02em',
          }}>
            {(favoredProb * 100).toFixed(0)}<span style={{ fontSize: 16, opacity: 0.6 }}>%</span>
          </span>
          {edge != null && <EdgeBadge edge={edge} />}
        </div>
        {match.reason && (
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6, lineHeight: 1.4 }}>
            {match.reason}
          </div>
        )}
      </div>

      {odds && (
        <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 8 }}>
          market: {match.player_1} {fmtPrice(odds.player_1)} / {match.player_2} {fmtPrice(odds.player_2)} ({odds.bookmaker}{odds.frozen ? ' · frozen pre-match' : ''})
        </div>
      )}

      {match.sr_dog ? (
        <div className="mono" style={{ marginTop: 8, fontSize: 10, color: '#e879f9', fontWeight: 700, border: '1px dashed #e879f9', borderRadius: 5, padding: '4px 8px', display: 'inline-block' }}
          title="SR-DOG pre-registered tracker (2026-09-26): the UNDERDOG (>=2.00 odds) whose last-10-on-surface serve+return composite beats the favorite's — the ONE rule that survived the flat-ROI battery at real odds in BOTH seasons (2025 +21.2% on 90, 2026 +1.2% on 89). Sole survivor of 24 tested slices, so expect the winner's-curse haircut: true edge likely single digits. Flat-1u paper tracker, judged at 50 settled — never staked by the model.">
          ★ SR-DOG: take {match.sr_dog === 'p1' ? match.player_1 : match.player_2} <span style={{ fontWeight: 400, opacity: 0.85 }}>· surface serve+return beats the favorite · pre-registered flat-1u tracker</span>
        </div>
      ) : null}

      {match.sos ? (
        <div className="mono" style={{ marginTop: 6, fontSize: 10, color: '#22d3ee', fontWeight: 700 }}
          title="SOS tracker (2026-09-26): this player's surface serve+return is not worse (within 2 pts) but their recent schedule is clearly tougher (median opponent rank ≤0.8× the other's). Backtest: they WIN 63-65% of these matches — but avg odds ~1.60 mean the market prices it almost exactly (flat ROI −3/−12%). A WIN-RATE tracker to watch, not a bet signal.">
          ◆ SOS: {match.sos === 'p1' ? match.player_1 : match.player_2} <span style={{ fontWeight: 400, opacity: 0.85 }}>· tougher slate, stats hold up — win-rate tracker</span>
        </div>
      ) : null}

      {match.mc2 ? (
        <div className="mono" style={{ marginTop: 6, fontSize: 10, color: '#c9a7fa', opacity: match.mc2.recon ? 0.75 : 1 }}
          title={`MC v2 (2026-10-08): the rebuilt Monte Carlo — surface Elo + opponent-adjusted serve/return ratings -> learned point probabilities -> exact Markov engine, with parameter uncertainty. Walk-forward 2024-26: AUC .692 vs market .722, calibration within ~1pt per decile. DISPLAY-ONLY: measured residual-vs-close == market minus vig, so it never bets alone; its mc2_* watch lanes earn (or don't) on the Splits tab, and its real product is the 🎲 Sets tab's anchored derivative prices.${match.mc2.recon ? ' THIS GAME: ~ walk-forward BACKFILL — computed from the ratings as they stood the morning of the match (result and everything after excluded); honest but not a forward pick.' : match.mc2.elo_p1 != null ? ` Components: Elo ${Math.round(100 * match.mc2.elo_p1)}% / Markov ${Math.round(100 * match.mc2.mkv_p1)}%; serve-rating samples n=${match.mc2.n1}/${match.mc2.n2}.` : ''}`}>
          {match.mc2.recon ? '~' : ''}🧮 MC2: {match.player_1.split(' ').slice(-1)[0]} <b>{Math.round(100 * match.mc2.p1_prob)}%</b> — <b>{Math.round(100 * (1 - match.mc2.p1_prob))}%</b> {match.player_2.split(' ').slice(-1)[0]}
          <span style={{ opacity: 0.75 }}>{match.mc2.recon ? ' · walk-forward backfill' : match.mc2.elo_p1 != null ? ` · elo ${Math.round(100 * match.mc2.elo_p1)} / mkv ${Math.round(100 * match.mc2.mkv_p1)}` : ''} · display-only</span>
        </div>
      ) : null}

      {match.utr ? (
        <div className="mono" style={{ marginTop: 6, fontSize: 10, color: '#93c5fd' }}
          title="REAL UTR (2026-10-07): each player's current singles UTR from utrsports.net's public ratings (fetched fresh daily), with how their 3-MONTH form rating sits vs that established level in parentheses (+ = running hot, − = cold). FORWARD tracker only — current ratings can't be honestly backtested (today's rating already contains past results), so the utr_* lanes judge it on settles from today forward (🐕/⭐ Splits tab): utr_all (higher-rated side), utr_dog (market dog is the higher-rated player), utr_mom hot vs fade (the form-fade thesis says fade the hot side).">
          📏 UTR: {match.player_1.split(' ').slice(-1)[0]} <b>{match.utr.p1}</b>{match.utr.p1_mom != null ? ` (${match.utr.p1_mom > 0 ? '+' : ''}${match.utr.p1_mom})` : ''}
          {' vs '}{match.player_2.split(' ').slice(-1)[0]} <b>{match.utr.p2}</b>{match.utr.p2_mom != null ? ` (${match.utr.p2_mom > 0 ? '+' : ''}${match.utr.p2_mom})` : ''}
          <span style={{ fontWeight: 400, opacity: 0.8 }}> · real ratings · forward tracker from today</span>
        </div>
      ) : null}

      {match.model_a ? (() => {
        const ma = match.model_a
        const pct = v => `${Math.round(100 * v)}%`
        const h = ma.h2h
        const edge = ma.edge_p1
        return (
          <div className="mono" style={{ marginTop: 6, fontSize: 11, color: 'var(--text-secondary)' }}
            title={`TENNIS MODEL A (2026-09-28): surface stats (sr10 serve/return composite, SGW/RGW, pressure points), last-10/20 form, opponent quality (median recent opponent rank, record vs top-100), rank gap, and the pair's REAL head-to-head from the full 1,760-player match database. DISPLAY-ONLY, honestly labeled: walk-forward on 109,915 priced matches the market's AUC (.71-.73) beat Model A's (.66-.68) in all three test years, and betting Model A's disagreements lost 10.6-12% flat at every edge size. When the model and the price disagree, history says the price is right${ma.trained_at ? `. Trained ${ma.trained_at}.` : '.'}`}>
            <b style={{ color: '#e3b341' }}>MODEL A</b>{' '}
            {match.player_1} {pct(ma.p1_prob)} — {pct(ma.p2_prob)} {match.player_2}
            {ma.market_p1 != null ? (
              <span style={{ color: 'var(--text-tertiary)' }}> · market {pct(ma.market_p1)}—{pct(1 - ma.market_p1)}
                {edge != null ? ` · model vs market ${edge > 0 ? '+' : ''}${Math.round(100 * edge)}pt on ${match.player_1.split(' ').slice(-1)[0]}` : ''}
              </span>
            ) : null}
            {h ? (
              <span style={{ color: '#e3b341', opacity: 0.85 }}> · H2H {h.p1_wins}-{h.p2_wins}{h.surface_n ? ` (${(h.surface || '').toLowerCase()} ${h.surface_p1_wins}-${h.surface_n - h.surface_p1_wins})` : ''}</span>
            ) : (
              <span style={{ color: 'var(--text-tertiary)' }}> · no prior H2H</span>
            )}
            <span style={{ color: 'var(--text-tertiary)', fontSize: 9 }}> · display-only (market wins disagreements)</span>
            {ma.market_aware_p1 != null ? (
              <div style={{ color: '#8b949e', fontSize: 10, marginTop: 1 }}
                title="Same Model A features refit WITH the market price as an input (market-aware head). This is what the stats add on top of the price -- validated: almost nothing (market-aware == market to the 4th decimal on 110k matches), which is itself the finding.">
                (market-aware: {pct(ma.market_aware_p1)} — {pct(1 - ma.market_aware_p1)})
              </div>
            ) : null}
          </div>
        )
      })() : null}

      {match.model_b ? (() => {
        const mb = match.model_b
        const pct = v => `${Math.round(100 * v)}%`
        const edge = mb.edge_p1
        return (
          <div className="mono" style={{ marginTop: 4, fontSize: 11, color: 'var(--text-secondary)' }}
            title={`TENNIS MODEL B (2026-09-28): ONLY the last 10 matches on this surface -- recent serve/return stat lines plus WHO those results came against, rank-adjusted: average rank faced, average rank of the players they actually beat, best win, and who they lost to. Same honest harness as Model A, same verdict: stats-only AUC .63-.65 vs the market .70-.73 in all three test years, and betting B's disagreements lost 10-11% flat. DISPLAY-ONLY${mb.trained_at ? `. Trained ${mb.trained_at}.` : '.'}`}>
            <b style={{ color: '#d29922' }}>MODEL B</b>{' '}
            {match.player_1} {pct(mb.p1_prob)} — {pct(mb.p2_prob)} {match.player_2}
            {mb.market_p1 != null ? (
              <span style={{ color: 'var(--text-tertiary)' }}> · market {pct(mb.market_p1)}—{pct(1 - mb.market_p1)}
                {edge != null ? ` · ${edge > 0 ? '+' : ''}${Math.round(100 * edge)}pt` : ''}
              </span>
            ) : null}
            <span style={{ color: 'var(--text-tertiary)', fontSize: 9 }}> · last-10-on-court only · display-only</span>
            {mb.market_aware_p1 != null ? (
              <div style={{ color: '#8b949e', fontSize: 10, marginTop: 1 }}
                title="Model B's features refit WITH the market price as an input. Validated: indistinguishable from the market alone -- the last-10 form and rank-quality story is already in the price.">
                (market-aware: {pct(mb.market_aware_p1)} — {pct(1 - mb.market_aware_p1)})
              </div>
            ) : null}
          </div>
        )
      })() : null}

      {match.model_c ? (() => {
        const mc = match.model_c
        const pct = v => `${Math.round(100 * v)}%`
        const edge = mc.edge_p1
        return (
          <div className="mono" style={{ marginTop: 4, fontSize: 11, color: 'var(--text-secondary)' }}
            title={`TENNIS MODEL C (2026-09-28): the full 52-weeks-on-this-surface profile (record, serve/return stats, aces & DFs per game, BPs created/defended/saved/converted, tiebreaks, pressure points, dominance ratio, match efficiency, odds performance), this-season block, record vs opponents in TODAY'S opponent's rank band, last-10-on-court (incl. how close their losses are), and H2H. AUDITED: no leak found, ranks verified historical — but its backtest edge (+4 to +11%/yr, decaying) is measured vs the site's AVERAGE book odds and concentrates below the main tour, so it is likely the stale-soft-price effect, NOT proof against sharp closing lines. The C-EDGE $25 lane on the A vs B tab is its live judge${mc.trained_at ? `. Trained ${mc.trained_at}.` : '.'}`}>
            <b style={{ color: '#58a6ff' }}>MODEL C</b>{' '}
            {match.player_1} {pct(mc.p1_prob)} — {pct(mc.p2_prob)} {match.player_2}
            {mc.market_p1 != null ? (
              <span style={{ color: 'var(--text-tertiary)' }}> · market {pct(mc.market_p1)}—{pct(1 - mc.market_p1)}
                {edge != null ? ` · ${edge > 0 ? '+' : ''}${Math.round(100 * edge)}pt` : ''}
              </span>
            ) : null}
            <span style={{ color: 'var(--text-tertiary)', fontSize: 9 }}> · audited, judged live in C-EDGE lane</span>
            {mc.market_aware_p1 != null ? (
              <div style={{ color: '#8b949e', fontSize: 10, marginTop: 1 }}
                title="Model C refit WITH the market price as an input. In validation this head BEAT the raw market slightly — the only model here to do so — which is why C earned a live lane instead of a flat display-only stamp.">
                (market-aware: {pct(mc.market_aware_p1)} — {pct(1 - mc.market_aware_p1)})
              </div>
            ) : null}
            {mc.mc && mc.mc.sims ? (() => {
              const cmcP1 = mc.mc.p1_pct / 100
              const disagree = (cmcP1 >= 0.5) !== (mc.p1_prob >= 0.5)
              return (
                <div style={{ color: disagree ? '#d29922' : '#58a6ff', fontSize: 10, marginTop: 1, opacity: 0.9 }}
                  title={`MODEL-C MONTE CARLO (2026-10-02, user "make it like D's — independent"): a REAL ${mc.mc.sims.toLocaleString()}-match serve-based simulation (per-point serve/return probabilities, exact game/set/tiebreak math, day-to-day form noise ±4pts) — the same engine as Model D's MC, but ANCHORED halfway toward Model C's class read instead of the court-UTR. Because the serve dynamics add their own structure, it is INDEPENDENT of C and can disagree with it (it does here when amber). Central holds ${mc.mc.p1_hold}% vs ${mc.mc.p2_hold}%; straight sets ${mc.mc.straight_sets_pct}%. Display-only context — the backtested MC-from-C added no edge over C, so this is a reality-check, not a bet signal.`}>
                  ⚄ C-MC {mc.mc.sims.toLocaleString()}: {match.player_1} {mc.mc.p1_pct}% — {(100 - mc.mc.p1_pct).toFixed(1)}% {match.player_2}
                  <span style={{ color: 'var(--text-tertiary)' }}> · serve sim anchored to C{disagree ? ' · ⚠ disagrees with C' : ''}{mc.mc.surface_fallback ? ' · ⚠ serve stats from another surface' : ''} · display-only</span>
                </div>
              )
            })() : null}
            {showCMC && (mc.mc_c75_p1 != null || mc.mc_cutr_p1 != null) ? (
              <div style={{ color: '#8b5cf6', fontSize: 9.5, marginTop: 1, opacity: 0.9 }}
                title="The two INVISIBLE C-MC variants under test (toggled on by the 'C-MC variants' button). c75 = serve sim anchored 75% toward Model C (vs 50% for the visible line). cUTR = C anchor PLUS a stronger court-UTR de-padding first (the Storm Hunter padded-serve fix). All three are tracked head-to-head in the A-vs-B $25 tab (C-MC · c50 / c75 / cUTR lanes); whichever earns the best live record can become the displayed one.">
                ⚄ C-MC tests:
                {mc.mc_c75_p1 != null ? ` c75 ${(mc.mc_c75_p1 * 100).toFixed(0)}%—${(100 - mc.mc_c75_p1 * 100).toFixed(0)}%` : ''}
                {mc.mc_cutr_p1 != null ? ` · cUTR ${(mc.mc_cutr_p1 * 100).toFixed(0)}%—${(100 - mc.mc_cutr_p1 * 100).toFixed(0)}%` : ''}
                {' '}<span style={{ color: 'var(--text-tertiary)' }}>({match.player_1.split(' ').slice(-1)[0]} — {match.player_2.split(' ').slice(-1)[0]} · hidden experiment)</span>
              </div>
            ) : null}
          </div>
        )
      })() : null}

      {match.model_i ? (() => {
        const mi = match.model_i
        const pct = v => `${Math.round(100 * v)}%`
        const edge = mi.edge_p1
        return (
          <div className="mono" style={{ marginTop: 4, fontSize: 11, color: 'var(--text-secondary)' }}
            title={`MODEL I (2026-10-02): results + market-history estimate from Tennis Explorer, for players OUTSIDE the TennisRatio stat pool (deep ITF). Recency-weighted win rate + the market's historical view of each player + surface form → rating diff → win prob. DISPLAY-ONLY: ITF 15K/25K matches carry no serve/return statlines anywhere, so this can't be Models B/C/D — it's an A-style results model. Disambiguation-gated (only runs when the Tennis Explorer profile unambiguously matches the name). Ratings ${mi.rating_p1} vs ${mi.rating_p2} on ${mi.n1}/${mi.n2} recent matches.`}>
            <b style={{ color: '#e3b341' }}>MODEL I <span style={{ fontSize: 9, opacity: 0.8 }}>TE</span></b>{' '}
            {match.player_1} {pct(mi.p1_prob)} — {pct(mi.p2_prob)} {match.player_2}
            {mi.market_p1 != null ? (
              <span style={{ color: 'var(--text-tertiary)' }}> · market {pct(mi.market_p1)}—{pct(1 - mi.market_p1)}
                {edge != null ? ` · ${edge > 0 ? '+' : ''}${Math.round(100 * edge)}pt` : ''}
              </span>
            ) : null}
            <span style={{ color: 'var(--text-tertiary)', fontSize: 9 }}> · Tennis Explorer results · display-only (no ITF statlines exist)</span>
          </div>
        )
      })() : null}

      {match.model_d ? (() => {
        const md = match.model_d
        const pct = v => `${Math.round(100 * v)}%`
        const edge = md.edge_p1
        return (
          <div className="mono" style={{ marginTop: 4, fontSize: 11, color: 'var(--text-secondary)' }}
            title={`TENNIS MODEL D (v6, 2026-10-01): HEAVY last-10 form, FULLY RANK-BLIND (user call — "ranks can be misleading"), plus our court-specific UTR as its class anchor (AUC .68 alone). No ranking is used anywhere: each of a player's last 10 opponents is judged by that opponent's OWN last-10 form at the time they played — form of the schedule faced, form of the players actually beaten, best in-form scalp, record + games-won share vs IN-FORM opponents (opp L10 ≥ 60%). PLUS (user adds): THIS-SEASON quality and volume (win rate, games share, matches played — flags players who've barely played or barely won this year), and the HOME-PLATFORM check: each player's prior-365d share of matches, win rate and games share AT TODAY'S LEVEL (tour / challenger / ITF) — catches a challenger regular stepping up against someone whose main platform this is. Also: recent win rates, form vs own 52-week baseline, loss closeness, recency-weighted (0.9/match) L10 serve & return splits, rest days. DISPLAY-ONLY${md.trained_at ? `. Trained ${md.trained_at}.` : '.'}`}>
            <b style={{ color: '#3fb950' }}>MODEL D <span style={{ fontSize: 9, opacity: 0.8 }}>v6</span></b>{' '}
            {match.player_1} {pct(md.p1_prob)} — {pct(md.p2_prob)} {match.player_2}
            {md.market_p1 != null ? (
              <span style={{ color: 'var(--text-tertiary)' }}> · market {pct(md.market_p1)}—{pct(1 - md.market_p1)}
                {edge != null ? ` · ${edge > 0 ? '+' : ''}${Math.round(100 * edge)}pt` : ''}
              </span>
            ) : null}
            <span style={{ color: 'var(--text-tertiary)', fontSize: 9 }}> · last-10 form vs own baseline · display-only</span>
            {md.market_aware_p1 != null ? (
              <div style={{ color: '#8b949e', fontSize: 10, marginTop: 1 }}
                title="Model D refit WITH the market price as an input. Validation: beat the raw market in 2024-25, lost to it slightly in 2026 — recent form is essentially priced this season.">
                (market-aware: {pct(md.market_aware_p1)} — {pct(1 - md.market_aware_p1)})
              </div>
            ) : null}
            {(md.d1 && md.d2) ? (() => {
              const pc = v => (v == null ? '—' : `${Math.round(100 * v)}%`)
              const row = (name, dd) => (
                <div style={{ color: 'var(--text-tertiary)', fontSize: 9.5, marginTop: 1 }}>
                  <span style={{ color: 'var(--text-secondary)' }}>{name.split(' ').slice(-1)[0]}</span>
                  {' '}ssn {dd.ssn || '—'} · L10 {pc(dd.l10)}{dd.form != null ? ` (${dd.form >= 0 ? '+' : ''}${Math.round(100 * dd.form)} vs usual)` : ''} · this level {pc(dd.lvl_share)} of yr, {pc(dd.lvl_win)} won · opp form faced {pc(dd.fq_faced)} / beat {pc(dd.fq_beaten)}
                </div>
              )
              return (
                <div title="What Model D actually reads (v4-v6, made visible on user ask): ssn = this season's W-L. L10 = last-10 win rate on this surface, with (±) how far above/below the player's OWN 52-week norm that is. 'this level' = share of the past year's matches at today's level (tour/challenger/ITF) and the win rate there — the home-platform check. 'opp form' = the average last-10 win rate of the opponents faced / of the opponents actually BEATEN in the last 10 — opponent quality by their real form, never ranking.">
                  {row(match.player_1, md.d1)}
                  {row(match.player_2, md.d2)}
                </div>
              )
            })() : null}
            {(md.sutr_p1 || md.sutr_p2) ? (() => {
              // THIN-RATING flag (2026-10-04, user ask, Ghetu 8-match clay case): a surface
              // cUTR built on < 12 matches is under-informed and can over-rate a player (it
              // feeds the cUTR Monte Carlo hardest). Mark it with ⚠ so you see it coming.
              const THIN = 12
              const thin1 = md.sutr_p1 && md.sutr_p1.n != null && md.sutr_p1.n < THIN
              const thin2 = md.sutr_p2 && md.sutr_p2.n != null && md.sutr_p2.n < THIN
              return (
                <div style={{ color: '#d2a8ff', fontSize: 10, marginTop: 1 }}
                  title={`COURT UTR (2026-10-01): our own per-surface UTR-style rating (performance = opponent rating ± games-won share, recency-weighted last 30 in 12 months; never a ranking). Scale ~1-16, pool median 8.1, feeds Model D + the cUTR Monte Carlo. (n) = rated matches on this surface. ⚠ = THIN sample (<${THIN} matches): the rating is under-informed and may over-rate the player — the cUTR sim leans on it hardest, so treat a ⚠ favorite with caution (the Ghetu 8-match clay case: rated above a 30-match opponent, then lost 6-1 6-0).`}>
                  cUTR {match.player_1} {md.sutr_p1 ? `${md.sutr_p1.r} (${md.sutr_p1.n})${thin1 ? ' ⚠' : ''}` : '—'} · {match.player_2} {md.sutr_p2 ? `${md.sutr_p2.r} (${md.sutr_p2.n})${thin2 ? ' ⚠' : ''}` : '—'}
                  {(thin1 || thin2) ? <span style={{ color: '#e3b341' }}> · ⚠ thin rating (under {THIN} matches — may be overrated)</span> : null}
                </div>
              )
            })() : null}
            {md.mc ? (
              <div style={{ color: '#3fb950', fontSize: 10, marginTop: 1, opacity: 0.9 }}
                title={`MONTE CARLO (2026-10-01): ${md.mc.sims.toLocaleString()} simulated matches${md.mc.best_of_5 ? ' (best of 5)' : ''}. Per-point serve-win probabilities from each player's recency-weighted L10 serve stats vs the opponent's return stats, then ${md.mc.sutr_anchored ? 'ANCHORED halfway to the court-UTR gap (opponent-adjusted class — stops stats padded against weak schedules from inflating the number; the Chwalinska 94% lesson)' : '(no cUTR anchor — one player lacks 5 rated matches on this surface)'}, plus day-to-day form noise: each simulated match draws its own serve form (±4pts), so extreme probabilities stay honest. Exact game/tiebreak/set math; central hold rates ${md.mc.p1_hold}% vs ${md.mc.p2_hold}%. Seeded by the matchup. Context, not a bet signal — the MC ALL lane on the $25 tab is its public judge.`}>
                ⚄ MC {md.mc.sims.toLocaleString()}: {match.player_1} wins {md.mc.p1_wins.toLocaleString()} ({md.mc.p1_pct}%) — {match.player_2} {md.mc.p2_wins.toLocaleString()} ({(100 - md.mc.p1_pct).toFixed(1)}%) · straight sets {md.mc.straight_sets_pct}%{md.mc.surface_fallback ? ' · ⚠ serve stats from another surface' : ''}
              </div>
            ) : null}
          </div>
        )
      })() : null}

      {match.model_x ? (() => {
        const mx = match.model_x
        const pct = v => `${Math.round(100 * v)}%`
        const edge = mx.edge_p1
        return (
          <div className="mono" style={{ marginTop: 4, fontSize: 11, color: 'var(--text-secondary)' }}
            title={`MODEL X (2026-10-03, user ask): the self-auditing META-MODEL. It stacks the market + A/B/C/D + their gray heads + the Monte Carlos — but only the inputs it has WALK-FORWARD validated as useful on the frozen log — into one win probability, and retrains every night. Each night it also tests every unused frozen signal and AUTO-ADDS any that clear a strict out-of-sample gate (and drops ones that stop helping), so it learns from every settled win/loss. Trained on ${mx.n_train || '?'} settled games${mx.trained_at ? `, ${mx.trained_at}` : ''}. DISPLAY-ONLY: currently ~market-level calibration, no flat-betting edge yet — the Model X tab tracks its live record.`}>
            <b style={{ color: '#d2a8ff' }}>MODEL X <span style={{ fontSize: 9, opacity: 0.8 }}>meta</span></b>{' '}
            {match.player_1} {pct(mx.p1_prob)} — {pct(mx.p2_prob)} {match.player_2}
            {mx.market_p1 != null ? (
              <span style={{ color: 'var(--text-tertiary)' }}> · market {pct(mx.market_p1)}—{pct(1 - mx.market_p1)}
                {edge != null ? ` · ${edge > 0 ? '+' : ''}${Math.round(100 * edge)}pt` : ''}
              </span>
            ) : null}
            <span style={{ color: 'var(--text-tertiary)', fontSize: 9 }}> · nightly self-retrain · display-only</span>
          </div>
        )
      })() : null}

      {(match.tr_context && (match.tr_context.p1 || match.tr_context.p2)) ? (
        <div style={{ marginTop: 8, paddingTop: 6, borderTop: '1px dashed var(--line)' }}
          title="TennisRatio profile context, real stat names on the site's 52-week surface window (falls back to last-20 when thin): 1stSv/2ndSv = 1st/2nd-serve points won, SGW/RGW = service/return games won (p## = percentile within OUR ingested pool for that tour), plus last-25 record vs top-200-ranked opponents, pressure-point conversion, and median recent opponent rank. DISPLAY ONLY: backtested 2026-09-25 and found fully priced into the market (opponent-adjusted included), so it never drives a pick — the validated tennis edge remains the price scanner.">
          <TrContextRow name={match.player_1} ctx={match.tr_context.p1} />
          <TrContextRow name={match.player_2} ctx={match.tr_context.p2} />
          <div className="mono" style={{ fontSize: 8, color: 'var(--text-tertiary)', opacity: 0.7, marginTop: 2 }}>
            TR CONTEXT — NOT AN EDGE (backtested priced-in; the scanner is the validated play)
          </div>
        </div>
      ) : null}

      {match.features && (
        <div style={{ marginTop: 10 }}>
          <button onClick={() => setShowFeatures(s => !s)} style={{
            background: 'none', border: 'none', color: 'var(--text-tertiary)', fontSize: 10,
            fontFamily: 'var(--font-mono)', letterSpacing: '0.03em', padding: 0,
            display: 'inline-flex', alignItems: 'center', gap: 4, opacity: 0.75,
          }}>
            <span style={{ display: 'inline-block', transition: 'transform 0.15s', transform: showFeatures ? 'rotate(90deg)' : 'none' }}>▸</span>
            {showFeatures ? 'hide' : 'show'} model inputs
          </button>
          {showFeatures && <FeatureTable features={match.features} />}
        </div>
      )}
    </div>
  )
}

function fmtPrice(p) {
  if (p == null) return '—'
  return p > 0 ? `+${p}` : `${p}`
}

function EdgeBadge({ edge }) {
  const positive = edge > 0
  const pct = Math.abs(edge * 100).toFixed(1)
  return (
    <span className="mono" style={{
      fontSize: 11, fontWeight: 600, padding: '3px 8px', borderRadius: 5, marginLeft: 'auto',
      color: positive ? 'var(--edge-pos)' : 'var(--edge-neg)',
      background: positive ? 'rgba(61,220,132,0.1)' : 'rgba(255,92,92,0.1)',
      border: `1px solid ${positive ? 'var(--edge-pos)' : 'var(--edge-neg)'}`,
      whiteSpace: 'nowrap',
    }}>
      {positive ? '+' : '-'}{pct}% edge
    </span>
  )
}

const FEATURE_LABELS = {
  elo_diff: 'overall Elo',
  surface_elo_diff: 'surface Elo',
  surface_form_diff: 'surface form',
  overall_form_diff: 'overall form',
  opponent_quality_diff: 'opponent quality',
  h2h_diff: 'head-to-head',
  rest_days_diff: 'rest days',
  best_of_5: 'best of 5',
}

function FeatureTable({ features }) {
  return (
    <div style={{ marginTop: 8, borderTop: '1px solid var(--line)', paddingTop: 8 }}>
      {Object.entries(FEATURE_LABELS).map(([key, label]) => {
        const val = features[key]
        return (
          <div key={key} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
            <span className="mono" style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{label}</span>
            <span className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
              {val == null ? '—' : typeof val === 'number' ? val.toFixed(2) : val}
            </span>
          </div>
        )
      })}
    </div>
  )
}
