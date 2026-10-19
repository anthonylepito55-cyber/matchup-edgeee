# OPP1 v3.5 — Registered Implementation Addendum (ledger entry 1a)

Registered against **OPP1 v3.5** (`OPP1_SPEC_V3_5_PROPOSAL.md`, sha256
`7539adbbafc84d2257dfafd52982f3f756e52cfb83aa974db3366243c90ba56e`, t_reg
2026-10-19T08:10:37Z, registration commit `b0f59fb`). This addendum resolves three
implementation ambiguities the registered specification leaves open, each owner-ratified on
2026-10-19. It changes **no** registered hypothesis, gate, threshold, floor, key, seed, or
clock; the registered file's bytes remain frozen and are not edited by this addendum.

## A-O1 — Development/tier membership rule (DISCLOSED DEVIATION, owner-approved)

The registered criterion is "matches completing at or after t_reg". A read-only audit
(2026-10-19) found **no completion timestamp in any available source** (frozen log: settled
flag only, no settle time; snapshot store: pre-match stamps only; TennisExplorer and
TennisRatio: day granularity), so exact compliance is unimplementable from recorded data.

- **Operational cutoff:** eligible development fixtures are those with scheduled
  **`start_date` ≥ 2026-10-20T00:00:00Z** (the snapshot store's write-once pre-match field,
  interpreted in UTC). This is a **conservative operational proxy under the ordinary assumption
  that a match cannot complete before it starts** — not an absolute mathematical guarantee.
  Under that assumption no admitted row can violate the registered completion-time criterion;
  the proxy's deviation acts in one direction only (exclusion of matches starting between t_reg
  and 2026-10-19T23:59:59Z).
- **The registered 2026-10-11 → 2026-10-19 analyst-exposure exclusion remains a separate,
  independently enforced rule.** The start-date cutoff does not replace, subsume, or weaken it;
  both rules are applied, each on its own terms, and each exclusion is reported under its own
  label.
- **Timestamp parsing and normalization:** the eligibility cutoff is evaluated **only** on the
  snapshot store's `start_date` (the registered write-once pre-match field). Both scheduled
  start-time fields are parsed as ISO-8601: a value carrying a timezone offset is converted to
  UTC; a timezone-naive value is interpreted as UTC per each source's documented convention
  (the store's `start_date` and the log's `start_time_utc` are both emitted in UTC), and every
  naive-interpreted value is counted and reported as such, never silently assumed. A
  **date-only** value cannot serve as the eligibility timestamp; it is usable solely for the
  calendar-day cross-check below. A **missing, malformed/unparseable, or unresolved
  contradictory** timestamp means the fixture is **flagged and excluded**; no timestamp is ever
  silently coerced into eligibility.
- **Cross-source validation:** when the store `start_date` and the linked outcome record's
  start time disagree on the **UTC calendar day**, this **triggers validation and exclusion
  pending resolution** — the disagreement is a flag, not conclusive proof that either source is
  wrong. A resolution must **record the fixture, both values, the source of truth adopted, and
  the reason**, in the accrual report, before the row can be (re)admitted; an unresolved
  disagreement stays excluded. **No discretionary rule may select whichever timestamp makes a
  fixture eligible.** Validation exclusions and resolutions are each counted and reported under
  their own labels in every accrual and results report.
- **Tier membership uses the same disclosed start-time basis.** All registered tier thresholds,
  minimums, first-date-both-met stopping rules, and extension rules are preserved unchanged.

## A-O2 — MC2 input: frozen-only (owner-ratified)

M1/M3 read the **frozen pre-match `mc2_p1`** logged at card time. Rows with `mc2_recon = True`
take the registered missing-value path (training-fold imputation + missing-indicator). MC2 is
**never reconstructed or recomputed** for this protocol. The count of affected rows is reported
with every accrual report, and a dedicated test covers the behavior.

## A-O3 — Outcome-linkage ties (owner-ratified)

Where `fixture_id` linkage is unavailable and name/date matching yields **more than one**
candidate outcome record, the fixture is **UNLINKED**: excluded from the evaluated set, from
N_pre, and from all clusters. Ambiguous-linkage counts are reported **separately** from
metadata-incomplete counts in every accrual and results report.
