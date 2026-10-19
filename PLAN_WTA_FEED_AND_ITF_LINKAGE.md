# Deferred Implementation Plans — WTA/ITF-W feed coverage & ITF-men outcome linkage

**QUEUED, NOT EXECUTED. No feed changes, restarts, backfills, API calls, or record-altering jobs
are authorized now.** Both plans wait for Period A (and any Period B) to complete plus explicit
approval. Both are written to be one-change, one-rollback operations with Phase-5 isolation
demonstrated up front.

---

## Plan 1 — add WTA and ITF-women to the OpticOdds feed

**Change:** exactly one line in `oo_feed.py`: append `"wta", "itf_women"` to `DEFAULT_LEAGUES`
(line ~56). Then `sudo systemctl restart oo-poll.timer`'s service once.

**Why deferred / Phase-5 dependency analysis:**
- `oo_feed.py`'s byte-identity is a Phase-5 readiness invariant (R1), and the burst loop imports
  it. Editing it mid-experiment would make the running experiment's provenance ambiguous even
  though behaviour wouldn't change (see next point). It waits.
- Behavioural isolation, demonstrated: Phase 5's burst loop selects fixtures itself from
  `CONFIG["leagues"] = [atp, atp_challenger, itf_men]` (frozen hash `3a252d79dd5e1da1`) and polls
  explicit fixture ids — extra leagues in the snapshot store are invisible to it. The dog
  tab/lanes don't read the snapshot store at all. So the only true coupling is the file-identity
  invariant and the one-off service restart.
- The restart creates a ≤2-minute gap in the 60s store (one observed 15-min gap already exists);
  scheduled between tournament days to keep T\*-window loss ≈ 0.

**Expected effect (from the audit's same-span references):** roughly doubles tennis fixtures
(~+71 WTA matches/9d at tour level + an ITF-W slate comparable to ITF-men's 431). API volume:
2 book-groups × ceil(fixtures/5) extra calls — still far under the 8,000/min cap. Storage growth
measured in week one, not assumed.

**Day-one validation (part of the task):** per-league fixture counts, exchange/Pinnacle presence
for WTA and ITF-W specifically (unverified today), T\*-window coverage replay of the audit script
(`_oo_archive_audit.py`, already written, read-only).

**Rollback:** revert the one line, restart once.

---

## Plan 2 — ITF-men outcome linkage via the existing TE settler (processing only)

**Problem:** only 18.6% of stored ITF-men fixtures link to the board log for outcomes; OPP1 needs
settled winners for every usable fixture.

**Change:** a **new, standalone** batch script (e.g. `oo_outcomes_build.py`) that:
1. reads the snapshot store's fixture list (home/away names, start, league) — read-only;
2. matches each fixture to TennisExplorer results using the already-proven settler primitives
   (`tennis_itf_settle.fetch_day` + `name_keys`, both-players match, exactly-one-candidate-per-day
   rule, retirements → advancing player, undecidable → unmapped);
3. writes outcomes to a **new file** `data_cache/oo_outcomes.parquet` — **never** touching the
   frozen log, the snapshot store, or any lane input.

**Phase-5 isolation, demonstrated:** no shared state — Phase 5 settles its paper fills from the
frozen log via its own `settle()`; this plan writes a separate parquet nobody currently reads.
No services, no timers (run manually or a new independent timer later), no scanner contact. TE
fetches are polite single-day HTML pulls the settler already performs daily.

**Validation gate before trust:** on the ~18.6% of ITF fixtures that ARE in the board log, the
TE-derived winner must agree with the log's settled winner ≥99% (disagreements investigated, not
averaged away). Coverage target from prior measurement: TE publishes ITF results ~95–100%
same-day, so usable ITF-men linkage should rise from ~18% toward challenger's ~80%+.

**Rollback:** delete the new parquet; nothing else changes.

---

**Sequencing when approved:** Plan 2 first (zero scanner contact, raises OPP1 throughput
immediately on existing data), Plan 1 at the Period-A/B boundary alongside the F4 decision so the
scanner is touched exactly once.
