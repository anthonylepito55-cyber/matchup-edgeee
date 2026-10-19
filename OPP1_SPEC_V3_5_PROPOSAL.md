# OPP1 Spec v3.5 PROPOSAL — Sharp-vs-Exchange Structure (revised per design review + four preregistration audits)

**Status: PROPOSAL, UNCOMMITTED, awaiting approval. Editing of this file only was authorized;
no experiment execution, data collection, feature computation, outcome inspection, or model
fitting has occurred.** Spec v2 (`OPP1_MARKET_PATH_SPEC.md`, sha256 `309f6c7e…328c86`) remains
the frozen original preregistration. The design review (`OPP1_V3_DESIGN_REVIEW.md`, unchanged)
documents v3.0's defects; the first preregistration audit (reported in chat, 2026-10-19)
produced findings B1–B3 (blocking) and N1–N5 (non-blocking), applied in v3.1→v3.2; a second
adversarial gate (2026-10-19) found one blocker (per-contrast DE ambiguity) and five
clarifications, applied as D1–D6 in v3.3; a third readiness check (2026-10-19) found two
thinning blockers and a calibration clarification, applied as Q1–Q3 in v3.4; a fourth design
check (2026-10-19) led to the shared tournament×ISO-week key, the cap's registered rationale,
and the missing-value normalization, applied here as V1–V3. This
v3.5 supersedes the v3.0–v3.4 text — v3.4 is preserved unchanged as the prior version in its
own file (`OPP1_SPEC_V3_PROPOSAL.md`, sha256 `9badaac5…5422`) — and the change log in §7
records every difference. Evidence cited throughout: the committed archive audit (`ba5745f`) and the
read-only input-coverage counts (`v3_computability_counts.json`).

---

## 1. Hypothesis

Does the structure of the gap between the sharp price (Pinnacle) and the bettable exchanges,
measured over the final pre-match hours, carry **match-winner** information beyond the sharp
price itself at a fixed pre-match decision time? A different hypothesis from v2 (market-path /
retail-gap family), tracked in the same ledger (§5).

## 2. Conventions (all frozen; A1/A2 applied)

- **Implied probability:** American price → prob via the project's `am_to_prob`.
- **Sharp fair** `fair_P(t)`: proportional de-vig of Pinnacle's **paired** two-sided quote —
  both selections sharing one `quote_ts` (the `oo_steam.fair_series` discipline; unpaired sides
  invent movement). Latest such pair observed by time *t*.
- **Venue mid** for exchange v and selection s: `mid_v(s,t) = (ask_v(s,t) + 1 − ask_v(s̄,t)) / 2`
  where `ask` is the implied prob of the stored top-of-book price for that selection.
- **Observation cutoff (leak-safe):** every feature input must satisfy **`poll_ts ≤ T*`** — what
  our poller had actually observed — never merely `quote_ts ≤ T*`.
- **T\***: timestamp of the last stored poll in `[S−6h, S−30min]`; Pinnacle pair at T\* with
  `last quote_ts ≥ S−24h` required for row eligibility; v2 §2's exclusion taxonomy
  (reschedules >6h, postponed, voids, retirements→advancing player) carries over verbatim.
- **Orientation:** player-1 (fixed deterministic slot); one row per unique match.
- **Staleness and denominators (N5):** venue quote ages at T\* are recorded; the results report
  MUST include, per tier: quote-age **median and p90** per venue, per-feature missingness
  percentages, and the **eligible-denominator counts** behind every percentage (numerator and
  denominator together, never a bare rate). No age cap (a stale quote *is* the phenomenon), but
  age is never hidden.
- **Documented coverage fact (A3 evidence, measured 2026-10-19 on 883 T\*-fixtures):**
  **Polymarket has ZERO two-sided ATP-challenger markets** (0.0% of 369; Kalshi 87.8%) while
  ATP/ITF-men both-venue coverage is 97.7%/95.1%. Any venue-averaged feature would therefore
  silently change meaning by tier — the reason for §3's per-venue design.

## 3. The frozen v3.5 feature family (A3/A4/A5 applied)

Per-venue columns, each with its own missing-indicator; z-scored on training folds only.

| id | definition | missing rule |
|---|---|---|
| E1_K, E1_PM | `fair_P(T*) − mid_v(T*)` | venue not two-sided by T\* → missing + indicator |
| E2_K, E2_PM | time-weighted mean of the same gap on the poll grid over `[T*−6h, T*]` (last-known quotes carried) | observed common span < 2h → missing + indicator |
| E3 | median over Pinnacle re-prices *j* in the window of `min(next venue re-stamp, T*) − qts_P,j` — **right-censored at T\*** (min over venues present) | **no Pinnacle re-price in window → missing + indicator. Missing is NEVER coded as zero — zero would assert instant adjustment, the opposite of "unobserved".** |
| E5_K, E5_PM | `(mid_v(T*) − mid_v(t₀)) − (fair_P(T*) − fair_P(t₀))` with **common `t₀` = later of the two series' first stored quotes**; requires ≥2h common span | else missing + indicator |
| E6_K, E6_PM | top-of-book spread change: `[ask_v(1)+ask_v(2)]_{T*} − [·]_{t₀}` (same t₀ rule) | **requires the venue two-sided at BOTH endpoints** — both selections' top-of-book prices observed with `poll_ts ≤` that endpoint at t₀ AND at T\* — plus the ≥2h common span; any endpoint one-sided or absent → missing + indicator (N4) |

**E4 (Kalshi−PM disagreement) is REMOVED from the gated family** — see §3.1. It may appear in
descriptive readouts only, labelled as such, and any future gated use requires a new ledger
version on fresh data.

**E3 sparsity, disclosed up front (measured):** median **4** paired Pinnacle re-prices in the
window; **17.1–19.5% of fixtures have zero** (E3 missing); ≥3 re-prices on 63–75% of fixtures by
tier. Per-feature, per-tier coverage tables (from the counts JSON, refreshed at analysis time)
— each cell carrying its raw numerator and denominator, with quote-age median/p90 per venue per
tier (N5) — are a mandatory part of the results report, before any metric.

**Prespecified robustness readout (non-gating):** H1/H2 re-estimated using the Kalshi-only
feature subset (uniformly available across all three leagues) — published alongside the primary
result so no conclusion can rest on venue-availability indicators.

### 3.1 The challenger-coverage decision (review item 2) — options compared, one recommended

*Option A — venue-specific features with prespecified eligibility.* Adopted for **E1/E2/E5/E6**
(mandatory under either option: a pooled venue-mean is incoherent when the venue set differs by
tier). For **E4**, eligibility-scoping cannot save it: E4 exists on ~0% of challengers by PM
listing policy, so inside a pooled gated model its indicator is a tournament-tier dummy, and
restricting the *whole* gated test to non-challenger rows would discard ~42% of the population
(369/883 fixtures), stretching the development clock by ~1.7× for one feature.

*Option B — remove E4 from the primary hypothesis family.* Preserves the full population for
H1/H2, keeps exactly 2 gated hypotheses over one family computable on effectively all eligible
rows, and loses only the cross-exchange disagreement construct — which is partially expressed
already by the signed per-venue gaps (E1_K vs E1_PM carry the same information jointly).

**Recommendation: B for E4, A for everything else** — on construct validity (no hidden tier
proxy), sample-size (no 42% population cut), and plan simplicity (no league-conditional
hypotheses). No predictive performance was computed or consulted.

## 4. Protocol, research clock, and evidence boundaries (A7 applied)

- **Registration:** on approval of this v3.5, the registration timestamp and this file's sha256
  are recorded in the ledger; that instant is **t_reg** (and that sha256 is the seed source for
  B3's thinning rule).
- **Development data: matches completing at or after t_reg only.** The analyst-exposed store
  rows of 2026-10-11 → 2026-10-19 are **excluded from development AND from both confirmation
  tiers** — they served coverage measurement only and are spent.
- **Evaluated rows vs training-only rows (B2):** the walk-forward's first 6 months of dev data
  are training-only and are never scored; the **evaluated (OOS) rows** are the rows actually
  scored out-of-sample by the expanding walk-forward. **Every minimum in this section counts
  evaluated OOS rows only** — the dev pool is necessarily larger (evaluated rows plus the
  initial training-only window). H1/H2 are computed on evaluated rows exclusively.
- **Design effect, defined per contrast; one governing value (B1 + D1/D2):** for each gated
  contrast c ∈ {H1: Δll(M0−M2), H2: Δll(M1−M3)}, **DE_c = V_clust,c / V_iid,c**, where V_clust,c
  is the registered cluster-bootstrap (clusters = the tournament×ISO-week key **K** exactly as
  defined in the thinning bullet below, 2,000 resamples) variance estimate
  of the mean paired per-match Δll_c on the evaluated rows, and V_iid,c = s_c²/n is the ordinary
  iid variance estimate of that same mean — same rows, same units, same convention on both sides
  of each ratio. **The single governing design effect is DE = max(DE_H1, DE_H2), floored at 1**
  (clustering can never inflate effective sample size), and this one value is used for EVERY
  effective-sample-size calculation, every development and confirmation-tier minimum, and every
  permitted extension decision. **No analyst discretion to select a contrast exists.**
  Effective n = n_evaluated / DE. **Degenerate cases (D2):** if either contrast's required
  variance is undefined, or either iid denominator s_c² is zero, the DE calculation STOPS and
  the event is a **data-integrity abort requiring documented review** — never permission to use
  the other contrast alone, to omit a contrast, or to continue accrual.
- **Accrual rule, executable before any model is fitted (B1):** the planning assumption
  **DE_plan = 1.5** is preregistered here (the same value used in §6's projections). Dev accrues
  until BOTH (a) raw evaluated-row count **n_evaluated ≥ 8,000 × DE_plan = 12,000** and
  (b) ≥9 distinct ISO-months among evaluated rows, with ≥3 tiers represented and every
  tournament×ISO-week key thinned to its registered cap of 10% of the pre-thinning denominator
  (deterministic thinning, next bullet — see its honesty note on what this does and does not
  bound in the final set). **All minimum
  counts in this section — raw rows, effective n, ISO-month/ISO-week durations, and tier
  representation — are computed on the final post-thinning evaluated set; the per-key
  caps alone are computed against the fixed PRE-thinning denominator N_pre defined in the
  thinning bullet (Q1); training-only rows never count toward any evaluated minimum (D4).**
  These are pure
  counts requiring no fit and no outcome. Only when they are met may outcome analysis begin. At
  evaluation, the actual governing DE is measured as defined above; **if effective n < 8,000,
  dev is extended chronologically by whole ISO-weeks until effective n ≥ 8,000 (recomputing the
  governing DE on the extended set) — this fixed rule is the only permitted interim extension,
  and no outcome quantity other than the DE computation itself may influence any extension
  decision.** **Blinding at extension (D6):** the extension decision consumes and reports only
  V_clust,c, V_iid,c, the governing DE, and effective n. Where computing those variances
  necessarily computes the underlying contrasts, the signed/mean Δll values, ROI, p-values,
  calibration numbers, and every other performance summary remain masked — not displayed,
  reported, or written into any decision document — until the accrual/extension decision is
  finalized. This masking is procedural only and changes nothing in the registered mathematical
  rule.
- **Tournament thinning, deterministic at byte level (B3 + D3):**
  **seed = `int(sha256(registered_file_bytes).hexdigest()[:16], 16)`** — SHA-256 over the exact
  registered bytes of this file, the standard lowercase hexadecimal digest, first 16 hex
  characters read as a base-16 integer. No concatenation step is retained (v3.2's `‖ ":thinning"`
  second hash is dropped as an unnecessary layer); if any future version reintroduces
  concatenation it must specify UTF-8 byte encoding for every concatenated part.
  **The shared key K (V1):** the snapshot store carries NO tournament column (schema verified
  2026-10-19: `fixture_id, league, start_date, home, away, sportsbook, selection,
  norm_selection, market, price, limit_max, top_size, order_book, quote_ts, deep_link,
  poll_ts`), so the tournament identifier is read from the **`tournament` column of the linked
  outcome record** — the frozen tennis log row (or a registered successor outcome store) that
  supplies the row's settled winner. **tournament_norm** = that value cast to string, then
  whitespace-trimmed, then lowercased — in that order, so stringified missing values are caught.
  **If tournament_norm ∈ {"", "none", "nan"} the row is metadata-incomplete (V3):** excluded
  from the evaluated set, from N_pre, and from all clusters, under the existing
  metadata-incomplete rule, with such exclusions counted and reported. Every other evaluated
  row has a tournament by construction (no linked outcome → no label → not an evaluated row).
  **K = (tournament_norm, ISO year-week of the fixture's scheduled `start_date`, interpreted in
  UTC, formatted `%G-W%V`).** Every eligible row has a parseable `start_date` by construction —
  T\* (§2) is defined from it, so a row without one was never eligible; no other date source or
  timezone is ever used. **This single K definition serves BOTH the 10% cap and the
  tournament×ISO-week cluster bootstrap; the cap and the clusters are never keyed differently.**
  **Cap arithmetic (Q1):** at each registered boundary-check date, **N_pre** = the number of
  otherwise-eligible evaluated-candidate rows BEFORE tournament thinning — i.e. after every
  other eligibility and exclusion rule has been applied (§2's taxonomy, the t_reg clock, the
  Oct 11–19 exclusion, metadata-completeness, and one-row-per-unique-match deduplication).
  Each key K's cap is **cap_size = floor(0.10 × N_pre)**, computed ONCE against this fixed
  denominator and applied in ONE deterministic pass: N_pre and the caps are never recomputed
  after thinning, and there is no fixed-point iteration. A key with ≤ cap_size rows is
  left untouched and no sampling call is made for it. If cap_size = 0 (i.e. N_pre < 10), no
  thinning is performed and the boundary check simply fails — no registered minimum can be met
  at that size. **Constraint stated honestly:** this caps each key at 10% of the
  PRE-thinning candidate universe. It does NOT mathematically guarantee a ≤10% share of the
  final post-thinning set — removing other keys' excess rows shrinks that set, so a
  capped key's final share can exceed 10% (bounded by cap_size / N_post). The registered
  constraint is the N_pre version; final per-key shares of the post-thinning set are
  reported with results as a disclosed limitation, never silently equated with the cap.
  **Registered rationale (V2):** Purpose of the cap: a representativeness guard limiting any
  single tournament×ISO-week key's contribution to the candidate universe. Protection of
  inference against concentration is provided by the identically keyed cluster bootstrap and
  governing design effect, not by the cap itself. The cap is not expected to bind under
  ordinary tennis schedules at the registered sample-size floors, but this is an empirical
  expectation rather than a mathematical guarantee. If a key exceeds its cap, the registered
  deterministic thinning applies unchanged; final per-key shares of the post-thinning evaluated
  set must be reported in every results report.
  **Procedure:** keys are processed in ascending lexicographic order of the ordered pair
  (tournament_norm, then the ISO year-week string) — tuple ordering, with no concatenation or
  serialization, so no delimiter collision is possible; within each key above the cap, rows are
  sorted by ascending lexicographic `fixture_id`; one `numpy.random.default_rng(seed)` instance,
  created once, draws `rng.choice(n_rows, size=cap_size, replace=False)` on that sorted array
  for each such key in that fixed order — **the drawn indices are the rows KEPT**; all other
  rows of that key are thinned. The same registered bytes therefore always reproduce the
  exact same sample.
  **Fate of thinned rows (Q2):** rows removed by tournament thinning are excluded from
  EVALUATION only. They remain eligible as training observations for later expanding-window
  folds, provided they satisfy the registered chronology, data-quality, and
  training-eligibility rules — in particular, **no row may serve as training data for a model
  used to score any prediction made at or before the time that row's outcome became available**
  (the existing temporal-leakage protections are unchanged by this rule). This does not alter
  the one-row-per-match evaluation rule and cannot leak an evaluated row's outcome into its own
  prediction: every row, thinned or not, is scored only by a fold whose training window closed
  before that row's match.
- **Immutable chronological splits, fixed by rule (never adjusted after results):** dev = the
  first qualifying matches completing at or after t_reg, until the accrual rule above is
  satisfied. **Tier-1 = the next chronological window, ending at the first date on which BOTH
  of its minimums are met (N3):** ≥1,500 effective evaluated matches (same governing-DE
  machinery and extension rule, DE_plan applied to its raw target: ≥2,250 raw) and ≥12 distinct
  ISO-weeks. Tier-2 = matches completing **after the dev+Tier-1 verdict document is written**,
  same minimums as Tier-1, ending by the same first-date-both-met rule.
- **Models and gates (v3.0/v2 machinery except the league terms, N2):** **all four models
  include symmetric league fixed effects** — two dummy columns (`atp_challenger`, `itf_men`;
  `atp` = reference), fitted exclusively within each training fold like every other coefficient.
  M0 `y~logit(fair_P(T*)) + league`; M1 `+logit(MC2)`; M2 `+E-family`; M3 `M1+E`. L2 C=1.0
  fixed; per-fold z-scores/imputation/logistic recalibration fitted on each fold's training
  window only; expanding monthly walk-forward, minimum train = first 6 months. Gated: **H1**
  mean paired per-match Δll(M0−M2) > 0; **H2** mean Δll(M1−M3) > 0. Cluster-bootstrap
  (2,000 resamples) studentized means, one-sided: dev t ≥ 3 with floor +2.0×10⁻³; each tier
  t ≥ 2, same sign, floor +1.0×10⁻³; calibration slopes 0.9–1.1 — **specified (Q3): the gated
  slopes are those of the candidate models, M2 for H1 and M3 for H2; each slope is the
  coefficient of a logistic regression of the outcome on that model's OOS predicted logit,
  measured on the same post-thinning evaluated rows its hypothesis is tested on (dev, then each
  tier); conjunctive with H1/H2 and the integrity condition exactly as in the inherited v2
  machinery — no threshold changed**; 95% percentile CIs;
  200-permutation label-shuffle null — **an additional NECESSARY integrity condition, never
  sufficient for promotion and never a substitute for H1 or H2; promotion requires every
  registered primary gate to pass (D5)** — (blinded, pass = null mean within ±2 null-SE of zero
  and true result above the null's 99th percentile).
- **What N2 changes and does not change (documented, not silent):** the league dummies appear
  symmetrically in M0–M3, so both sides of each paired Δll comparison carry identical league
  information and H1/H2 become tests of **E-family information beyond (sharp market + league
  identity)** — a strictly harder estimand than "beyond the market alone". This is the intended
  estimand: no E-column or missing-indicator can win by proxying tournament tier (the residual
  risk flagged for the PM indicators, which correlate ≈1 with challenger). Consequences stated
  plainly: (i) Δll magnitudes under this baseline are **not comparable** to numbers computed
  under a market-only M0 — none exist (nothing has been fitted) and none may be claimed
  comparable without a registered side-by-side readout; (ii) the hypothesis count, gates,
  clustering, floors, and permutation machinery are unchanged by this addition.

## 5. Cross-experiment dependence and the ledger (A6/A8/A9 applied)

| version | gated hypotheses | data/mechanism | status | alpha spent |
|---|---|---|---|---|
| OPP1 v2 | 2 (F-family, vendor grid) | The Odds API history | Phase-0 gates failed pre-outcome | none |
| **Phase 5 lead–lag** | its own preregistered criteria (≥200 fills, CLV ≥ +1.5pp t ≥ 3, ROI > 0, Period B) | **same OpticOdds store; same Pinnacle re-prices; exchange-follows-sharp mechanism** | Period A running | its own family |
| OPP1 v3.5 (this) | 2 (E-family, our store) | same store, coarser timescale, winner outcome | proposed | none yet |

- **Correlated-evidence clause:** E3 is Phase 5's venue-adjust-latency measured at 65s
  resolution; E1/E2 are the size/persistence of the gap Phase 5's fill rule trades. A v3.5
  positive and a Phase-5 positive are **correlated findings about one mechanism, never two
  independent confirmations**, and must be presented that way in any synthesis.
- **Prespecified E3-ablation (non-gating):** M2/M3 re-estimated without E3, published with the
  primary result, to separate gap-structure information from raw venue slowness.
- **Reflexivity safeguard:** if any live (non-paper) execution on Kalshi/Polymarket begins, our
  own orders would move the quotes the E-features are built from. From the first live order, the
  accrual window is annotated as contaminated; dev/tier boundaries are re-drawn to exclude
  contaminated spans **before** any outcome analysis touching them, and the annotation is itself
  registered. (Statement only — Phase 5 remains paper-only and untouched.)
- Rules unchanged: ≤2 gated hypotheses per version; an executed-and-failed version is closed
  permanently; never-executed versions spend no alpha but stay listed.
- **Global never-gate rule (N1, restored from v3.0):** descriptive and robustness readouts — the
  E4 descriptive readouts, the Kalshi-only re-estimate, the E3-ablation, correlation tables, and
  all coverage/staleness tables — **never gate any decision in this or any future version.**
  Promoting any of them to gated status requires a new ledger version evaluated on data not yet
  collected at the time of that promotion.

## 6. Part B — v2/F4 forward path (v2 unchanged) + time-to-sample projection (A10)

Requirements as before: retail group enabled only post-Period A/B bundled with the WTA change;
**dev clock starts at the enable date** (fixed prospectively); coverage gates measured without
outcomes (≥4 weeks accrual; retail on ≥50% of tour fixtures at T\*; median ≥2 retail books;
challenger/ITF coverage measured; the committed audit script is the instrument).

**Time-to-sample PROJECTION (labelled as such; assumptions stated, measured inputs cited):**
measured usable throughput (Pinnacle-two-sided at T\*, 9-day audit): tour ≈ 7.8/day
(87 fixtures·80.5%/9d), challenger ≈ 33.7/day, ITF-men ≈ 39.4/day. Let r = fraction of those
fixtures retail books also cover at T\* (unknown until enable; gate minimum 0.5 on tour), and
assume design effect **1.5** (stated assumption; measured at analysis time).

| scope for the v2/F4 test | effective matches/day = raw·r/1.5 | days to 8,000 effective |
|---|---|---|
| tour only, r=0.5 | ≈2.6 | **≈3,100 days (~8.5 yrs) — infeasible** |
| tour only, r=1.0 | ≈5.2 | ≈1,540 days (~4.2 yrs) — infeasible |
| tour+challenger, r=0.5 | ≈13.8 | ≈580 days (~1.6 yrs) |
| tour+challenger, r=1.0 | ≈27.7 | ≈290 days (~10 mo) |
| + WTA/ITF-W after feed addition (≈2× slate), r=0.5 | ≈27.7 | ≈290 days (~10 mo) |

**Consequence, stated plainly:** a tour-only F4 test is presumptively infeasible; the v2/F4 path
is viable only if retail books meaningfully cover challengers (unknown — to be measured in the
first 4 post-enable weeks). The go/no-go for v2 therefore requires the measured r by tier plus
this table recomputed with real numbers, filed before any v2 outcome work. Coverage gates passing
does **not** imply power; the two are assessed separately.

## 7. Change log (A- and B/N-dispositions)

### v3.0 → v3.1 (design-review amendments)

A1 venue-mid formula + price conventions — **applied** (§2). A2 `poll_ts ≤ T*` cutoff —
**applied** (§2). A3 per-venue features; E4's disposition — **applied**; comparison + Option B
recommended for E4 (§3, §3.1); PM-challenger zero coverage documented (§2). A4 E3 right-censored
median, minimum-observation and missing≠zero rules — **applied** (§3). A5 common-t₀ for E5/E6 —
**applied** (§3). A6 Phase 5 in the ledger + correlated-evidence clause — **applied** (§5).
A7 dev clock at registration; Oct 11–19 rows excluded from dev and confirmation — **applied**
(§4). A8 reflexivity safeguard — **applied** (§5). A9 E3-ablation readout — **applied** (§5).
A10 time-to-sample computation requirement + projection table — **applied** (§6).
Also: Kalshi-only robustness readout added (§3); v2 preserved untouched throughout.

### v3.1 → v3.2 (final preregistration-audit dispositions, applied on approval 2026-10-19)

**B1** design effect defined mathematically (DE = V_clust/V_iid on the mean paired Δll) and the
accrual rule made executable pre-fit: raw evaluated-row target 8,000 × DE_plan = **12,000** with
preregistered DE_plan = 1.5, measured DE at evaluation, and a fixed whole-ISO-week extension
rule as the only permitted interim extension — **applied** (§4).
**B2** every minimum (8,000 effective; 9 ISO-months; 3 tiers; 10% cap; tier minimums) bound to
the **evaluated OOS rows**, with training-only rows explicitly distinguished and excluded from
all counts — **applied** (§4).
**B3** tournament thinning made deterministic: seed derived from the registration sha256 via a
specified hash construction, fixed sort order, fixed sampler — **applied** (§4).
**N1** global rule restored: descriptive/robustness readouts never gate in this or any future
version; promotion requires a new ledger version on not-yet-collected data — **applied** (§5).
**N2** symmetric league fixed effects (`atp_challenger`, `itf_men` dummies) added to all of
M0–M3, fitted within training folds only; estimand consequence documented explicitly (tests are
now "beyond market + league identity"; no comparability claim to a market-only baseline without
a registered side-by-side) — **applied** (§4).
**N3** Tier-1 (and Tier-2) end fixed at the first date both registered minimums are met —
**applied** (§4).
**N4** E6's two-sided-at-both-endpoints requirement and missing-data handling stated explicitly
— **applied** (§3).
**N5** quote-age median and p90 by tier, per-feature missingness, and eligible-denominator
counts mandated in every results report — **applied** (§2, §3).

### v3.2 → v3.3 (second adversarial gate dispositions, applied 2026-10-19)

**D1 (the blocker)** DE defined per gated contrast (DE_H1 on Δll(M0−M2), DE_H2 on Δll(M1−M3));
the single governing **DE = max(DE_H1, DE_H2)** used for every effective-sample-size
calculation, every development and confirmation-tier minimum, and every extension decision; no
analyst discretion to select a contrast — **applied** (§4).
**D2** governing DE floored at 1 (clustering can never inflate effective n); undefined variance
or zero iid denominator on either contrast = data-integrity abort requiring documented review —
never contrast-dropping, contrast-selection, or continued accrual — **applied** (§4).
**D3** byte-level seed `int(sha256(registered_file_bytes).hexdigest()[:16], 16)` (lowercase
hex, no concatenation retained; UTF-8 mandated if any future version reintroduces one);
tournament identifier named exactly — the linked outcome record's `tournament` column, because
the snapshot store itself has no tournament column (schema verified and listed); sort order and
single-RNG procedure fixed — **applied** (§4).
**D4** all raw-row, effective-n, duration, tier, and per-tournament-cap calculations use the
final post-thinning evaluated set; training-only rows never count toward evaluated minima —
**applied** (§4).
**D5** permutation null labelled an additional NECESSARY integrity condition, never sufficient
for promotion and never a substitute for H1 or H2; promotion requires every registered primary
gate to pass — **applied** (§4).
**D6** extension decisions expose only V_clust,c / V_iid,c / governing DE / effective n;
signed or averaged Δll, ROI, p-values, and all other performance summaries masked until the
accrual/extension decision is finalized; procedural only, registered rule unchanged —
**applied** (§4).

### v3.3 → v3.4 (third readiness-check dispositions, applied 2026-10-19)

**Q1 (blocker)** cap arithmetic defined closed-form: N_pre = otherwise-eligible
evaluated-candidate rows before thinning (after all other exclusions and one-row-per-match
dedup); cap_size = floor(0.10 × N_pre), computed once against that fixed denominator, applied
in one deterministic pass, no recomputation and no fixed-point iteration; ≤-cap tournaments
untouched; cap_size = 0 means no thinning and an automatically failed boundary check. The
constraint is stated honestly as a bound on the PRE-thinning universe that does NOT guarantee a
≤10% share of the final post-thinning set (final shares reported as a disclosed limitation);
§4's accrual wording and the D4 count-basis sentence were reconciled accordingly — minimum
counts and effective n on the post-thinning set, caps alone on N_pre — **applied** (§4).
**Q2 (blocker)** fate of thinned rows fixed: excluded from evaluation only; eligible as
training observations for later expanding folds subject to the registered chronology,
data-quality, and training-eligibility rules; the temporal-leakage protections restated (no row
trains a model scoring predictions made at or before that row's outcome was available); the
one-row-per-match evaluation rule unchanged and self-leakage impossible — **applied** (§4).
**Q3** calibration gate specified: the gated slopes are M2's (for H1) and M3's (for H2), each
the logistic-regression coefficient of the outcome on the model's OOS predicted logit, measured
on the same post-thinning evaluated rows the hypothesis is tested on, conjunctive with H1/H2
and the integrity condition; no threshold changed — **applied** (§4).
Preserved untouched in v3.4: governing DE = max(DE_H1, DE_H2) floored at 1, degenerate-case
abort, hypotheses, t-gates and floors, minimum durations, tier logic, seed derivation, and all
Phase-5 text.

### v3.4 → v3.5 (fourth design-check dispositions, applied 2026-10-19; v3.4 preserved in its own file)

**V1** one shared key for the cap and the inference clusters:
K = (tournament_norm, ISO year-week `%G-W%V` of the scheduled `start_date` in UTC);
tournament_norm = linked outcome record's `tournament`, cast to string → trimmed → lowercased;
every eligible row has a parseable `start_date` by the T\* rule, and no other date source or
timezone is used; cap and cluster bootstrap reference this one definition; key ordering fixed
as tuple ordering (no serialization, no delimiter collisions) — **applied** (§4). Motivation
(verified 2026-10-19 on log metadata): the bare tournament string carries no edition number for
recurring ITF venues and includes qualifying, so one string could aggregate many weekly
editions; the measured consequence was that no provable per-tournament row bound existed and
the tier-scale cap could realistically bind on the bare-string key.
**V2** the cap's registered rationale added verbatim (representativeness guard on the candidate
universe; inference protection carried by the identically keyed cluster bootstrap and governing
DE; empirical expectation of non-binding, not a guarantee; deterministic thinning if it ever
binds; final per-key shares reported always) — **applied** (§4).
**V3** missing-value normalization: tournament_norm ∈ {"", "none", "nan"} → metadata-incomplete,
excluded from the evaluated set, N_pre, and all clusters, counted and reported — **applied**
(§4).
Unchanged in v3.5: Option A cap algorithm (floor(0.10 × N_pre), one fixed denominator, one
deterministic pass, kept-row semantics, same seed derivation and RNG rules), the honesty note
on pre-thinning caps vs final-set shares, chronological OOS rules, DE/bootstrap machinery and
floors, extension logic, tier gates, H1/H2/calibration/permutation gates, and all Phase-5 text.

**Unresolved blockers remaining:** (1) formal registration (t_reg) awaits your approval of this
v3.5; (2) sample accrual — dev cannot begin before minimums are met (months away by §6-style
arithmetic on the men-only slate); (3) v2/F4 feasibility awaits post-enable retail coverage
measurement; (4) WTA/ITF-W absence caps v3.5's population until the deferred feed plan executes.
