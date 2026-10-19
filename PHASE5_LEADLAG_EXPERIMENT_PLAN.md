# Phase 5 Plan — Pinnacle Lead–Lag Paper Experiment (pre-registration, 2026-10-18)

**Status: PLAN ONLY.** Nothing in this document changes the scanner, places orders, or touches
the frozen lanes. The Oct 31 Phase 3 checkpoint closes under its original rules regardless of
anything here. Implementation is a separate task after this design is approved.

## 0. Hypothesis and why this experiment

Phases 1–4 established that no existing head knows more than the market. The one measured,
unexhausted asymmetry is **speed and venue**: Pinnacle's moves lead the exchanges by seconds
(measured 2026-10-11 from feed timestamps: Novig 3.5s, Kalshi 5.1s, Polymarket 6.4s, Betfair 28s),
and the exchanges are where the bets are actually placed. Hypothesis: *taking the stale exchange
top-of-book immediately after a qualifying Pinnacle move captures positive CLV net of costs.*
This is an execution edge, not a prediction edge — no model probabilities are involved anywhere.

## 1. Signal capture (what gets recorded, per event)

For every qualifying Pinnacle move on a tennis moneyline that both feeds carry:

- Pinnacle quote before and after the move, with the feed's own `quote_ts` for each.
- The exact market/outcome mapping used (fixture id, player ↔ outcome token), recorded at
  signal time so settlement cannot re-map it.
- Target venue (Kalshi / Polymarket) top-of-book at the last observation before the move and the
  **first observation at or after** it: bid, ask, size, and that quote's own timestamp.
- Quote freshness: age of the target quote relative to the Pinnacle move, and the observation
  lag of our own poller.
- Spread at signal time, and the first time the target market reflects the move (for the
  adverse-selection and delay analyses).
- Price-integrity flags per Phase 2 (a synthetic/post-start quote can never be a fill).

**Known design constraint, stated up front:** the current `oo_scan` poller runs on a 60-second
cycle with per-minute rate caps. 60s observations cannot certify a 3–6s window, so fills are
simulated under the conservative rule in §2, and the build step may add a short *burst-poll* mode
on signal (a scanner change that is explicitly **not** part of this plan or the Phase 4 commit,
and needs its own sign-off).

## 2. Fill simulation (realistic, conservative)

A paper fill is recorded **only** when all of the following hold:

1. The target quote used for the fill is the first one observed **at or after** the Pinnacle
   move plus a fixed latency budget (pre-set: 3 s decision + venue ack; nothing faster than the
   measured follower lag may be assumed).
2. That quote is still the *pre-move* price or better — if the first post-move observation has
   already adjusted, the fill is **rejected** and recorded as `missed_adjusted` (this is the
   honest cost of 60s polling; no interpolation, no "it was probably still there").
3. Displayed size ≥ stake; otherwise a partial fill at displayed size, flagged.
4. Fees charged at the venue's real schedule (Polymarket sports taker `0.05·p·(1−p)` per share;
   Kalshi's published fee table), plus one tick of adverse slippage on every fill.
5. One attempt per signal. No chasing, no re-quotes, no averaging down.

Every signal is logged whether it fills or not: fills, partial fills, `missed_adjusted`,
`missed_size`, `missed_stale_feed`, rejected-by-flag. Fill rate is a headline metric, because a
strategy that only "fills" when it loses is adverse selection — measured directly as the target
market's move in the 10 minutes after each fill versus after each miss.

## 3. Edge measurement

- **CLV, one definition, fixed now:** de-vigged (proportional) Pinnacle **closing** probability
  of the taken side minus the paper-fill implied probability (fee-inclusive), in percentage
  points. Positive = we beat the close.
- Net paper ROI at settlement (actual results, actual venue settlement rules), with pending
  exposure shown separately — never counted as losses.
- Win rate, average odds, exposure, drawdown; results by venue, league tier, delay bucket
  (time from Pinnacle move to our quote), move size, and **chronological week**.
- Uncertainty: mean CLV with ±2se and a paired view per venue; ROI with ±2se.

## 4. Pre-registered success criteria (fixed before any data)

1. **≥ 200 valid paper fills** (fills, not signals).
2. **Mean CLV ≥ +1.5pp** under the §3 definition, with **t ≥ 3**.
3. **Positive net paper ROI** after fees and slippage.
4. **No threshold tuning, signal re-definition, or discarding of observations after the test
   begins.** Exploratory cuts may be *reported* but cannot rescue a failed criterion.
5. **Chronological confirmation before any real-money discussion:** the first 200 fills are
   Period A. If A passes, the experiment continues into an untouched Period B of equal fill
   count; criteria 2–3 must hold in B independently. 200 fills can reveal a signal; they do not
   establish deployable profitability.
6. Evaluation happens at fixed points only (A complete, B complete) — no stopping on a good week.

**Failure = closure.** If any criterion fails, the experiment is closed and recorded in the
Tested tab like every other refuted idea.

## 5. Explicit non-goals and boundaries

- No live orders, in any mode, at any point in this experiment.
- No changes to the frozen Phase 3 lanes, the dog tab's rules, or the Oct 31 checkpoint.
- No model probabilities in the signal path — this tests *latency*, nothing else.
- The existing Polymarket paper auto-bettor keeps running unchanged; it answers a different
  question (realizable prices for the tab's picks) and its ledger stays separate.

## 6. Build steps when approved (separate task, separate commit)

1. Signal logger: extend the existing `oo_feed` capture to persist the §1 record per qualifying
   move (and, if needed, the burst-poll mode — flagged for explicit sign-off since it changes
   scanner behaviour and API usage against the per-minute rate cap).
2. Paper-fill engine implementing §2 exactly, writing an append-only ledger.
3. A read-only status view (same pattern as the auto-bet tab) showing fills, misses, CLV and the
   criteria checklist — visible progress without touching outcomes.

*Prepared after Phase 4 (commits `02ab0ea`, `632d0ff`). This plan is itself uncommitted pending
your review.*
