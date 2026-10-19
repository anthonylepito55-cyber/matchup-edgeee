# Research Specification v2 — Opportunity #1: Market-Path Features (The Odds API Historical Grid)

**Status: SPECIFICATION ONLY, revision after review. No probes run, no credits spent, no data
pulled, no models fit, no results inspected, no code changed, Period A untouched.** The six
feature families (F1–F6) are frozen exactly as in v1. Changes in v2 are design clarifications
and one structural change (two-tier confirmation) forced by item 3's honest answer.

## Review-item status

| item | status | one-line basis |
|---|---|---|
| 1 coverage of 2025/2026 | **BLOCKING — by design** | window *starts* mid-2024 (not ends), but no retained artifact proves per-period coverage; windows now coverage-derived; Phase-0 is the resolution |
| 2 T\*/freshness rules | **Resolved** | §2: exact definitions, exclusions, frozen sensitivity grid |
| 3 untouched confirmation | **Resolved (restructured)** | §3: July–Oct 2026 outcomes are analyst-exposed → demoted to Tier-1; true confirmation = post-registration Tier-2 |
| 4 statistical protocol | **Resolved** | §4: hypotheses, clustered SEs, exact meaning of t≥3, proper shuffle test |
| 5 sample-size meaning | **Resolved** | §5: unique matches, power math from Phase-4 empirical sd, design-effect requirement |
| 6 gates/denominators/cost | **Resolved** | §6: every gate with explicit numerator/denominator; header-based credit ledger (header capture verified in probe code, line 56) |

---

## 1. Historical coverage — BLOCKING, and what the evidence actually is

- **Correction of wording:** the 2026-10-11 probe conclusion was "history reaches **back to**
  mid-2024" — i.e. the vendor window is ≈ mid-2024 → present, so 2025 and 2026 lie *inside* it in
  principle. The v1 phrasing invited the opposite reading.
- **What is verified (V):** the probe *code* (`_theoddsapi_historical_probe.py`) requested
  snapshots at 0/1/2/3/4 years back and captured response headers; the subscription unlocks
  `/v4/historical/*`.
- **What is NOT verified (and why this stays blocking):** the probe's raw output was **not
  retained** — only the contemporaneous note survives; the reach-back test used a **single
  tournament key** (`tennis_atp_shanghai_masters`), and tennis keys are per-tournament, so it
  says nothing about week-by-week 2025/2026 coverage, Pinnacle presence in those months, or
  mappability to our log. Per your instruction, none of this is assumed from subscription or
  current availability.
- **Design change:** development/confirmation windows are no longer fixed dates. They are
  **derived from verified coverage** in Phase-0: let W = the set of ISO weeks passing the
  coverage gate (§6). Development = the earliest 75% of W (chronological); Tier-1 holdout = the
  remaining 25% (minimum 12 weeks, else extend by shrinking dev); Tier-2 = §3. The v1 dates
  (dev ≤ 2026-06-30) survive only if Phase-0 confirms they sit inside W.
- **Resolution path:** Phase-0 probes (on your authorization) retain **every raw response** this
  time (`data_cache/theoddsapi_hist/phase0/`, immutable), so this item's evidence is permanent.

## 2. T\*, quote freshness, and schedule handling — frozen rules

- **Scheduled start** `S` = the vendor event's `commence_time` as recorded in the **last snapshot
  ≤ S − 30 min**; cross-checked against our frozen log's `start_time_utc` (mapping requires
  agreement within ±12 h).
- **T\*** = timestamp of the latest snapshot `t_s` with `t_s ≤ S − 30 min` **and**
  `t_s ≥ S − 6 h`. No snapshot in `[S−6h, S−30min]` → row **excluded** (`no_t_star`), counted.
- **Quote freshness:** within the T\* snapshot, the Pinnacle quote's own `last_update` must
  satisfy `S − 24 h ≤ last_update ≤ t_s`; staler → row excluded (`stale_sharp`), counted. The
  F-features may use any snapshots `≤ t_s` back to the event's first appearance (the path *is*
  the feature); only the baseline quote has the freshness bound.
- **Schedule changes / postponements:** if the settled log's actual start differs from `S` by
  > 6 h → excluded (`rescheduled`). No settled result within 72 h of `S` → excluded
  (`postponed_or_lost`). Voids excluded as voids. Retirements settle to the advancing player
  (venue rule, consistent with the rest of the project).
- **Missing snapshots inside the path** are not imputed: F-features are computed from the
  snapshots that exist; per-feature missing-indicator columns as in v1. Exclusion rates are
  reported **per tour level and gender** so coverage bias is visible, not silent.
- **Preregistered sensitivity (reported, never selected on):** T\* offsets {−5 min, **−30 min
  primary**, −2 h}. Acceptance is judged **only** at −30 min; the sensitivity requirement is
  sign-consistency of the primary Δ at all three offsets. No retrospective choice.

## 3. Confirmation — two tiers, honestly labelled

**Disclosure (the direct answer to item 3):** match *outcomes* for 2026-07 → today have been
extensively analyzed in this project (the frozen log, Phases 1–4, every lane). The F1–F6
features have never been computed on any period — but the analyst's aggregate knowledge of that
period's outcomes (e.g., October favourite drawdown) is real contamination risk for a
"confirmation" claim.

- **Tier-1 (supporting, labelled exploratory-adjacent):** the chronological last 25% of the
  verified coverage window. Feature-naive but outcome-exposed to the analyst. Can support, can
  kill, cannot alone confirm.
- **Tier-2 (the true untouched confirmation, gating any promotion):** matches that **complete
  after this specification's registration date** — pulled from the same historical grid only
  after the dev+Tier-1 verdict is written, covering ≥ the first 12 weeks (and ≥1,500 unique
  mapped matches, extending until both are met) following authorization. Nobody has seen these
  outcomes today because they have not happened.

## 4. Statistical protocol — exact

- **Unit of analysis = one row per unique match** (player-1 = a fixed deterministic slot;
  `y = 1[player-1 wins]`). Repeated snapshots are inputs to that one row's features — **never**
  additional rows. No mirrored duplication.
- **Primary H1:** on identical OOS rows, mean paired per-match Δll = ll(M0) − ll(M2) > 0.
  **Co-primary H2:** mean of ll(M1) − ll(M3) > 0 (new information beyond market+MC2). Gated
  family = {H1, H2} in dev, re-tested in Tier-1 and Tier-2. Everything else (segments,
  sensitivities, ablations, Brier/AUC/accuracy/calibration) is descriptive with CIs, no gates.
- **Test statistic:** `t = mean(Δll) / SE_cluster(Δll)`, one-sided. **SE method:**
  cluster bootstrap (2,000 resamples) with clusters = **tournament × ISO-week** (matches sharing
  a tournament-week are resampled together — this is the repeated-observation treatment; the
  naive iid t is reported alongside for transparency but does not gate). Player-level
  duplication is reported (matches per player distribution) and addressed by the cluster
  structure plus a reported player-jackknife sensitivity.
- **What t ≥ 3 means here:** the clustered bootstrap-SE studentized mean of per-match paired
  log-loss differences is at least 3 (one-sided p ≈ 1.3×10⁻³), per gated hypothesis, in the
  development walk-forward. Tier-1 and Tier-2 gates are t ≥ 2 each with the same sign and
  Δll ≥ +1.0×10⁻³ (materiality floor halved for the smaller windows; dev floor stays +2.0×10⁻³).
  With 2 gated hypotheses, these thresholds leave family-wise error ≲1% in dev even before the
  confirmation tiers.
- **CIs:** 95% cluster-bootstrap percentile intervals for Δll×1000, ΔBrier×1000, calibration
  slope/intercept (slope/intercept by match-level bootstrap within folds).
- **Label-shuffle integrity check (redefined per review):** 200 runs permuting `y` across
  matches *within training folds*, full pipeline refit, OOS Δll recorded → a **null
  distribution**. Pass criteria: (a) the null mean lies within ±2 null-SE of zero (no mechanical
  gain under shuffled labels — not "literal zero"); (b) the true-label Δll exceeds the null's
  99th percentile. Run and archived **before** the true-label result is un-blinded (the
  pipeline supports blinding by computing both before printing either).

## 5. Sample sizes — what 8,000 / 4,000 actually buys

- Counts are **unique mapped matches**, never snapshot-rows (§4 unit).
- **Power basis (M, Phase 4):** per-match paired Δll had empirical sd ≈ 0.03 (e.g., c75: mean
  −0.00163, t −1.55, n 863 ⇒ sd ≈ 0.031; other heads similar). At n = 8,000 iid, SE ≈ 3.4×10⁻⁴ →
  a true Δll of +2.0×10⁻³ (the materiality floor) gives t ≈ 6; power at t≥3 is effectively 100%.
  Clustering erodes this: with tournament-week clusters we compute the **empirical design
  effect** and require **effective n ≥ 4,000 (dev) and ≥ 1,500 (each confirmation tier)**; if
  coverage can't supply it, the window extends rather than the bar dropping.
- Temporal/structural spread requirements: dev must span ≥ 9 distinct ISO-months and ≥ 3
  tournament tiers (tour/challenger/ITF as available), and no single tournament may contribute
  > 10% of dev rows (else capped by random thinning, preregistered).
- 4,000 (v1's confirmation minimum) maps to Tier-1; Tier-2's ≥ 1,500 unique matches reflects a
  shorter forward window and the t ≥ 2 gate with the halved floor; both are **effective-n**
  after the design effect.

## 6. Gates, denominators, and the credit ledger

| gate | numerator | denominator | threshold / handling of failures |
|---|---|---|---|
| weekly coverage | ISO weeks with ≥1 tennis key returning ≥1 snapshot containing ≥2 books | ISO weeks (mid-2024→pull date) with ≥20 completed tour+challenger matches in the TennisRatio archive (vendor-independent reference) | ≥60% in 2025 AND in 2026 separately; failed/missing API responses (after 2 retries) count in the denominator as uncovered |
| Pinnacle presence | T\*-eligible snapshots containing a two-way Pinnacle quote passing §2 freshness | all T\*-eligible snapshots on mapped tour matches in a stratified 4-week sample per half-year | ≥70% tour (gating); challenger measured, reported, non-gating |
| match mapping | frozen-log settled tour+challenger rows mapping to exactly ONE vendor event (both players via `name_keys`, start ±12 h) | all frozen-log settled tour+challenger rows inside covered weeks | ≥70%; ambiguous (≥2 candidates) and unmapped both count against |
| cost cap | — | — | hard abort at **2,000,000 credits cumulative**; Phase-0 budget ≤ 25,000; monitored from the API's own `x-requests-remaining/used` response headers (header capture already present in the probe code — V) with a local 10-credits-per-historical-call counter as fallback; usage checkpointed to a ledger JSONL every 100 calls; a run refuses to start if the ledger shows ≥ 95% of any budget consumed |

Every excluded or failed record is **counted and categorized** (`no_t_star, stale_sharp,
rescheduled, postponed_or_lost, unmapped, ambiguous, api_missing`), never silently dropped.

## 7. Unchanged from v1

Feature families F1–F6 (frozen, no additions after results); model set M0–M3 and the expanding
monthly walk-forward; proportional de-vig on Pinnacle at T\*; calibration-slope acceptance band
0.9–1.1; full separation from Phase 5 (different vendor, offline, own immutable raw store, no
shared state or services); failure = closure into the Tested tab; success earns only the next
preregistration (forward shadow scoring — still no betting claim).

## 8. What happens on your authorization (and only then)

Phase-0 coverage probes exactly as §6, retaining raw responses; then a Phase-0 report with each
gate's measured value against its threshold; **no feature computation and no model fitting until
the Phase-0 report is reviewed.**
