# Decision Note — F4 (sharp-vs-soft gap): collect retail books vs spec v3 substitution

**UNCOMMITTED. Nothing implemented. Spec v2 remains frozen and unedited; this note compares the
two paths and changes nothing.** Context: the archive audit showed F4 is not computable from the
current store — the retail group (`RETAIL_BOOKS = FanDuel, DraftKings, bet365`) is defined in
`oo_feed.py` but never polled. F1/F2/F3/F5/F6 computability is unaffected.

## Option A — add the retail book-group to collection (after Period A), keep F4 as specified

- **Operational cost:** one additional book-group per poll pass → API calls +~50% (2→3 groups
  per ≤5 fixtures; current whole-feed usage is far below the 8,000/min cap, so headroom is not a
  concern). Storage: retail books re-price frequently; row growth est. +50–120% on tennis
  (measured at enable, not assumed). Requires editing `oo_feed.py` + restarting `oo-poll` —
  **both frozen until Period A (and any Period B) completes**, because the scanner's byte-identity
  is a Phase-5 readiness invariant (R1).
- **Expected coverage:** forward-only from the enable date — no retroactive F4. Retail coverage
  of challenger/ITF is unverified (FanDuel lists some challengers; ITF presence doubtful) —
  day-one measurement required; plausible outcome is F4 existing mainly on tour/challenger.
- **Hypothesis:** unchanged — F1–F6 exactly as preregistered.
- **Statistical plan implications:** two preregistered-compatible ways to handle the pre-enable
  gap, to be fixed in writing before any OPP1 data work: (i) start the dev window at the enable
  date (delays the clock by nothing extra if enabled together with the WTA addition), or
  (ii) use the spec's existing missing-data rule (F4 → 0 + missing-indicator) over the full
  window. (ii) preserves sample size but makes F4's coefficient partly an era indicator; (i) is
  cleaner. Either way the 8,000-effective-match minimum stands.

## Option B — spec v3 substituting F4′ = sharp-vs-exchange gap

- **Operational cost:** zero. Computable on the entire existing store from day 1 (exchanges are
  two-sided on 98–100% of fixtures).
- **Expected coverage:** full, all tiers, immediately.
- **Hypothesis change (the real cost):** the construct's meaning changes. Sharp-vs-**soft**
  measures where retail/public prices lag the sharp — a persistent-mispricing story.
  Sharp-vs-**exchange** measures where the *bettable venues* lag Pinnacle — which overlaps the
  mechanism Phase 5 is already testing at seconds-scale, and will correlate with F3 (whose
  dispersion is computed mostly across the same exchanges). F4′ is a weaker, partially redundant
  cousin, and a null on F4′ would not settle the original F4 question.
- **Statistical plan implications:** legitimate *only* because no OPP1 feature has ever been
  computed or inspected — a pre-data substitution, issued as a separately versioned spec v3 with
  a new hash, original v2 preserved untouched. Hypotheses, T\*, bars, and windows otherwise carry
  over verbatim; the multiple-testing family is unchanged (F-families were never separate gates).

## Comparison summary

| | A: collect retail | B: v3 substitution |
|---|---|---|
| available when | after Period A + enable + accrual | immediately on existing data |
| tiers covered | likely tour-skewed, measure at enable | all tiers now |
| construct fidelity | exactly as preregistered | changed; overlaps F3 and the Phase-5 mechanism |
| plan impact | none (choose window rule in advance) | new spec version required |
| cost | +50% calls, more storage, scanner edit + restart | none |

**Recommendation (yours to accept or reject):** do both, in different roles — issue **v3 with
F4′** so the experiment can run on the full store when the sample matures, **and** enable retail
collection post-Period A anyway (cheap optionality), reserving *true F4 as preregistered* for a
later spec version evaluated purely on post-enable data. This keeps v2's F4 question alive and
untainted rather than quietly replaced.
