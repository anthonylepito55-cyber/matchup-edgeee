# OPP1 Gated-Hypothesis Registration Ledger

Durable record required by the registered protocols. Each entry freezes a protocol version at
registration time; the registered file's exact bytes are the thinning-seed source and may never
change (any byte change breaks the hash match and requires a new version).

## Entry 1 — OPP1 v3.5 (REGISTERED)

- **Protocol file:** OPP1_SPEC_V3_5_PROPOSAL.md
- **Registered SHA-256:** 7539adbbafc84d2257dfafd52982f3f756e52cfb83aa974db3366243c90ba56e
- **t_reg (UTC):** 2026-10-19T08:10:37Z
- **Registered by:** owner approval in session (Anthony Lepito), recorded at registration time;
  hash verified byte-exact against the approved value immediately before this entry was written.
- **Gated hypotheses:** 2 (H1, H2 — E-family; see the registered file, Section 4).
- **Development clock:** matches completing at or after t_reg only; store rows of
  2026-10-11 through 2026-10-19 are excluded from development and both confirmation tiers.
- **Thinning seed source:** the registered file bytes
  (seed = int(sha256(registered_file_bytes).hexdigest()[:16], 16)).
- **Status:** registered; accrual NOT started (separate authorization required).
- **Related (correlated, never independent confirmation):** Phase 5 lead-lag, Period A
  (its own preregistered family; see the registered file, Section 5).

Prior versions (never registered, no alpha spent): v2 (OPP1_MARKET_PATH_SPEC.md,
sha256 309f6c7e15f6c80a9cdbd75ca457a91547372af2be4ab0a63c9b8e0580328c86, frozen original,
Phase-0 coverage gates failed pre-outcome); v3.0-v3.4 (superseded proposal texts; v3.4 preserved
in OPP1_SPEC_V3_PROPOSAL.md, sha256 9badaac529cf27117df1f38970c11f00def04b94a83401daad8cc7c683bd5422).
