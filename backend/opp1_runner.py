"""OPP1 v3.5 — prospective accrual runner (infrastructure ONLY; activation separately gated).

Composes the nine committed OPP1 modules UNMODIFIED. Every entry point takes PASSED-IN frames
(store-schema rows, log-schema rows) — this module contains no code path that opens the
snapshot store, the frozen log, or any live source, no scheduler, and no network.

EVENT-TIME INTEGRITY
- Append-only JSONL ledger (one event per line; seq, etype, ts, content hash). Nothing is ever
  rewritten: late settlements and corrections are NEW, VERSIONED events.
- A fixture's T*, quote-derived features, starts history, and membership labels are FROZEN in
  its single observation event; settlement events may only add outcome/provenance. Late
  settlement can never alter what was observable at T*.
- Pending vs finalized is explicit: a fixture is finalized only when settled with an outcome
  (or terminally excluded); everything else stays pending.

ACTIVATION / CONTAMINATION
- activate() records the activation timestamp + verified seed provenance in the ledger's first
  event; process_snapshot() refuses to run unactivated and refuses fixtures first observed
  before activation (label pre_activation_observed, and a boundary_conflict event when the
  registered rules alone WOULD have admitted the fixture — identified, never silently decided).
- The registered dev cutoff and the independent analyst-exposure exclusion are enforced by the
  committed opp1_eligibility rules regardless of the activation boundary.
- NOTHING here counts toward the registered minimums until activation is separately authorized
  AND an activation event exists in a production ledger.

SEED PROVISIONING
- The registered seed derives ONLY from a verifiable artifact carrying the exact registered
  spec bytes: verified_seed(path) hashes the artifact and refuses anything that does not equal
  the registered sha256. No working-copy hash, no hardcoded seed, no fallback: thinning aborts
  without verified provenance.
"""
from __future__ import annotations

import hashlib
import json
import os

import pandas as pd

import opp1_adapters as AD
import opp1_eligibility as EL
import opp1_report as RP
import opp1_sample as SA

REG_SHA256 = SA.REG_SHA256
TERMINAL = set(EL.TAXONOMY_EXCLUDING) | {
    "no_candidate", "ambiguous_linkage", "metadata_incomplete", "validation_pending",
    "start_conflict_within_poll", "no_tstar_poll", "no_pinnacle_pair", "pinnacle_pair_stale",
    "analyst_exposure_excluded", "before_dev_cutoff", "pre_activation_observed",
    "ts_missing", "ts_malformed", "ts_date_only_not_eligibility"}
BLIND_FORBIDDEN = ("mean", "roi", "logloss", "log_loss", "clv", "edge", "p_value", "t_stat")


class SeedProvenanceError(RuntimeError):
    """Seed artifact missing or not byte-identical to the registered spec. Thinning aborts."""


class LedgerIntegrityError(RuntimeError):
    """The on-disk ledger failed verification (malformed, corrupted, truncated, out of
    sequence, duplicated, or conflicting). NEVER silently accepted or repaired — review
    required."""


class LockContentionError(RuntimeError):
    """Another writer holds the ledger lock. Deterministic refusal — never two writers."""


def _lock(handle):
    if os.name == "nt":
        import msvcrt
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise LockContentionError("ledger is locked by another process")
    else:
        import fcntl
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise LockContentionError("ledger is locked by another process")


def _unlock(handle):
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def verified_seed(artifact_path: str) -> int:
    """Registered-seed provisioning: the artifact must carry the EXACT registered spec bytes
    (sha256 == REG_SHA256). Anything else aborts before thinning — no fallback."""
    try:
        blob = open(artifact_path, "rb").read()
    except OSError as e:
        raise SeedProvenanceError("seed artifact unreadable: %s" % e)
    h = hashlib.sha256(blob).hexdigest()
    if h != REG_SHA256:
        raise SeedProvenanceError("artifact sha %s... != registered %s..." % (h[:12],
                                                                              REG_SHA256[:12]))
    return SA.seed_from_bytes(blob)


# ------------------------------------------------------------------ append-only event ledger
def _body_hash(etype: str, payload: dict) -> str:
    body = json.dumps({"etype": etype, "payload": payload}, sort_keys=True, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class Ledger:
    """Append-only JSONL with load-time verification and a PROCESS-LIFETIME exclusive lock.

    Single-writer rule: the lock (events.jsonl.lock, OS file lock) is acquired at construction
    and held until close(), covering the ENTIRE read-modify-append lifecycle — a second writer
    cannot even load stale state; contention raises LockContentionError deterministically.

    Load-time integrity (every open): each line must be valid JSON with exactly the expected
    fields; each event's stored content hash is RECOMPUTED and verified; seq must be contiguous
    from 0; a duplicate content hash ON DISK is an explicit integrity failure requiring review
    (never silently discarded); more than one activation event is a conflict; a truncated or
    malformed line fails loudly. Nothing is ever repaired or rewritten.

    LIMITS, stated plainly: content hashing detects accidental corruption and truncation; it is
    NOT tamper-proof — an adversary who can rewrite lines can rewrite their hashes too. Proof
    against tampering needs an independently protected anchor (e.g., periodic external hash
    checkpoints), out of scope here.

    Idempotency: an event whose (etype, payload) content hash already exists in memory is
    skipped. Durability: each append is flushed and fsynced."""

    def __init__(self, dirpath: str):
        os.makedirs(dirpath, exist_ok=True)
        self.path = os.path.join(dirpath, "events.jsonl")
        self._lockpath = self.path + ".lock"
        self._lockfh = open(self._lockpath, "a+b")
        if os.fstat(self._lockfh.fileno()).st_size == 0:
            self._lockfh.write(b"\0")
            self._lockfh.flush()
        _lock(self._lockfh)                                 # held for the process lifetime
        self._hashes = set()
        self._events = []
        try:
            if os.path.exists(self.path):
                with open(self.path, encoding="utf-8") as fh:
                    for i, line in enumerate(fh):
                        line = line.rstrip("\n")
                        try:
                            ev = json.loads(line)
                        except Exception:
                            raise LedgerIntegrityError(
                                "malformed/truncated event at line %d — review required" % i)
                        if not isinstance(ev, dict) or set(ev) != {"seq", "etype", "ts",
                                                                   "payload", "hash"}:
                            raise LedgerIntegrityError(
                                "invalid event structure at line %d" % i)
                        if _body_hash(ev["etype"], ev["payload"]) != ev["hash"]:
                            raise LedgerIntegrityError(
                                "content-hash mismatch at line %d (corruption)" % i)
                        if ev["seq"] != i:
                            raise LedgerIntegrityError(
                                "sequence discontinuity at line %d (seq=%s)" % (i, ev["seq"]))
                        if ev["hash"] in self._hashes:
                            raise LedgerIntegrityError(
                                "duplicate event hash on disk at line %d — review required" % i)
                        self._events.append(ev)
                        self._hashes.add(ev["hash"])
            if len([e for e in self._events if e["etype"] == "activation"]) > 1:
                raise LedgerIntegrityError("conflicting activation events on disk")
        except Exception:
            self.close()
            raise

    def close(self):
        if getattr(self, "_lockfh", None) is not None:
            _unlock(self._lockfh)
            self._lockfh.close()
            self._lockfh = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def append(self, etype: str, payload: dict, ts: float) -> bool:
        if self._lockfh is None:
            raise RuntimeError("ledger is closed")
        h = _body_hash(etype, payload)
        if h in self._hashes:
            return False                                   # idempotent: already recorded
        ev = {"seq": len(self._events), "etype": etype, "ts": ts, "payload": payload, "hash": h}
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev, sort_keys=True, default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self._events.append(ev)
        self._hashes.add(h)
        return True

    def events(self, etype: str | None = None):
        return [e for e in self._events if etype is None or e["etype"] == etype]

    # -------- state reconstruction (pure fold over events) --------
    def state(self) -> dict:
        st = {"activation": None, "fixtures": {}}
        for e in self._events:
            p = e["payload"]
            if e["etype"] == "activation":
                st["activation"] = p
            elif e["etype"] == "fixture_obs":
                st["fixtures"].setdefault(p["fixture_id"], {"obs": None, "settlements": []})
                if st["fixtures"][p["fixture_id"]]["obs"] is None:   # first obs is frozen
                    st["fixtures"][p["fixture_id"]]["obs"] = p
            elif e["etype"] in ("settlement", "correction"):
                st["fixtures"].setdefault(p["fixture_id"], {"obs": None, "settlements": []})
                st["fixtures"][p["fixture_id"]]["settlements"].append(p)
        return st


# ------------------------------------------------------------------ activation
def activate(ledger: Ledger, activation_ts_iso: str, seed_artifact_path: str,
             now_ts: float) -> dict:
    """Record the immutable activation event. Verifies seed provenance FIRST; refuses a second,
    different activation."""
    seed = verified_seed(seed_artifact_path)               # abort here on bad provenance
    cur = ledger.state()["activation"]
    meta = {"activation_ts": activation_ts_iso, "registered_sha256": REG_SHA256,
            "seed": seed, "dev_cutoff": str(EL.DEV_CUTOFF_UTC),
            "exposure_window": [str(EL.EXPOSURE_DAY_LO), str(EL.EXPOSURE_DAY_HI)]}
    if cur is not None:
        if cur != meta:
            raise RuntimeError("ledger already activated with different metadata")
        return cur
    ledger.append("activation", meta, now_ts)
    return meta


# ------------------------------------------------------------------ observation pass
def process_snapshot(ledger: Ledger, store_rows: pd.DataFrame, log_df: pd.DataFrame,
                     source_cutoff_ts: float, now_ts: float) -> dict:
    """One observation pass over passed-in store rows. Freezes per-fixture T*/features/labels
    in fixture_obs events. Refuses to run unactivated. Never backfills: a fixture whose FIRST
    observed poll predates activation is pre_activation_observed (+ boundary_conflict event when
    the registered rules alone would have admitted it)."""
    act = ledger.state()["activation"]
    if act is None:
        raise RuntimeError("ledger not activated — observation pass refused")
    # ---- source-cutoff provenance: fail closed, never freeze against a bad horizon ----
    try:
        cutoff = float(source_cutoff_ts)
    except (TypeError, ValueError):
        cutoff = float("nan")
    if not (cutoff > 0) or pd.isna(cutoff):
        raise RuntimeError("source_cutoff_ts missing/invalid — fail closed, nothing frozen")
    act_ts = pd.Timestamp(act["activation_ts"]).timestamp()
    stats = {"seen": 0, "new_obs": 0, "skipped_existing": 0, "pre_activation": 0,
             "boundary_conflicts": 0, "window_not_yet_complete": 0}
    store_rows = store_rows.copy()
    store_rows["_pts"] = pd.to_numeric(store_rows["poll_ts"], errors="coerce")
    max_pts = store_rows["_pts"].max()
    if pd.notna(max_pts) and float(max_pts) > cutoff + 1.0:
        raise RuntimeError("source rows newer than the declared cutoff — contradictory "
                           "provenance, fail closed")
    known = set(ledger.state()["fixtures"])
    for fid, g in store_rows.groupby(store_rows["fixture_id"].astype(str)):
        stats["seen"] += 1
        if fid in known:
            stats["skipped_existing"] += 1                 # obs frozen; idempotent
            continue
        # ---- T* COMPLETENESS GUARD (blocking-defect fix): the registered T* search window
        # ends at S - 30min; an observation may be frozen ONLY once the verified source
        # cutoff has reached that point. Earlier passes write NOTHING, so the fixture is
        # reconsidered on every later pass — a premature permanent no_tstar_poll exclusion
        # is impossible. Reading the window later from the persisted, timestamped store is
        # leak-safe: poll_ts is the scanner's write-once observation time and the committed
        # poll_ts <= T* cutoffs apply unchanged. ----
        sm = EL.parse_ts(AD.starts_from_store(g)["latest_start"])
        if (sm["ts"] is not None and sm["kind"] in ("aware", "naive_interpreted")
                and sm["ts"].timestamp() - 1800.0 > cutoff):
            stats["window_not_yet_complete"] += 1
            continue                                       # no event; retry next pass
        r = AD.fixture_to_row(g, log_df)                   # committed path, unmodified
        first_poll = float(g["_pts"].min())
        labels = list(r["labels"])
        if first_poll < act_ts:
            labels.append("pre_activation_observed")
            stats["pre_activation"] += 1
            registered_ok = not (set(r["labels"]) & TERMINAL)
            if registered_ok:
                stats["boundary_conflicts"] += 1
                ledger.append("boundary_conflict",
                              {"fixture_id": fid,
                               "note": ("registered rules admit this fixture but it was first"
                                        " observed before activation — operational boundary"
                                        " applied, protocol unchanged; owner review")}, now_ts)
        feats = None
        if r.get("tstar") is not None and r.get("quotes") is not None and len(r["quotes"]):
            import opp1_features as FE
            feats = FE.build_features(r["quotes"], r["tstar"], mc2_p1=r.get("mc2_p1"),
                                      mc2_recon=bool(r.get("mc2_recon")))
            feats = {k: (None if (isinstance(v, float) and pd.isna(v)) else v)
                     for k, v in feats.items()}
        obs = {"fixture_id": fid, "league": str(g["league"].iloc[0]),
               "home": str(g["home"].iloc[0]), "away": str(g["away"].iloc[0]),
               "labels_at_obs": labels, "starts": r.get("starts"),
               "tstar": r.get("tstar"), "fair": r.get("fair"), "features": feats,
               "tournament_norm": r.get("tournament_norm"),
               "start_ts": str(r.get("start_ts")) if r.get("start_ts") is not None else None,
               "n_quotes": int(len(r.get("quotes", []))) if r.get("quotes") is not None else 0,
               "source_cutoff_ts": source_cutoff_ts, "processed_ts": now_ts,
               "mc2_p1": r.get("mc2_p1"), "mc2_recon": bool(r.get("mc2_recon"))}
        if ledger.append("fixture_obs", obs, now_ts):
            stats["new_obs"] += 1
    return stats


# ------------------------------------------------------------------ settlement pass
def settle_pass(ledger: Ledger, log_df: pd.DataFrame, now_ts: float) -> dict:
    """Attach outcomes to PENDING fixtures as new, versioned events. Frozen observation data
    is never touched. A changed outcome becomes a 'correction' event (surfaced, never silently
    overwritten). PM-vs-TE style disagreements are surfaced via the correction mechanism."""
    st = ledger.state()
    stats = {"settled_new": 0, "corrections": 0, "still_pending": 0}
    out_frame = AD.outcomes_from_log(log_df)
    for fid, fx in st["fixtures"].items():
        obs = fx["obs"]
        if obs is None or (set(obs["labels_at_obs"]) & TERMINAL):
            continue
        link = __import__("opp1_link").link_fixture(
            {"fixture_id": fid, "p1": obs["home"], "p2": obs["away"],
             "day": str(obs["start_ts"])[:10]}, out_frame)
        if not link["status"].startswith("linked") or link["record"] is None:
            stats["still_pending"] += 1
            continue
        rec = log_df.loc[link["record"].name]
        s = AD.status_from_log(rec)
        # terminal classes (no winner is ever invented, no unregistered eligibility rule):
        # finalized (valid winner) | void_terminal | unresolved_review (settled, winner
        # missing/contradictory) | awaiting (unsettled -> no event yet)
        if s["status"] == "void":
            terminal_class = "void_terminal"
        elif s["winner"] is not None:
            terminal_class = "finalized"
        elif "settled_no_winner" in s["labels"] or "status_contradictory" in s["labels"]:
            terminal_class = "unresolved_review"
        else:
            stats["still_pending"] += 1
            continue
        pm = isinstance(rec.get("pm_src"), str) and len(str(rec.get("pm_src"))) > 0
        payload = {"fixture_id": fid, "status": s["status"], "winner": s["winner"],
                   "advancing": s["advancing"], "labels": s["labels"],
                   "terminal_class": terminal_class,
                   "provenance": "pm" if pm else "te_or_other",
                   "version": len(fx["settlements"]) + 1}
        prior = fx["settlements"][-1] if fx["settlements"] else None
        if prior is not None:
            same = all(prior.get(k) == payload.get(k)
                       for k in ("status", "winner", "advancing"))
            if same:
                continue
            payload["supersedes_version"] = prior["version"]
            payload["surfaced_for_review"] = True          # never silently resolved
            if ledger.append("correction", payload, now_ts):
                stats["corrections"] += 1
            continue
        if ledger.append("settlement", payload, now_ts):
            stats["settled_new"] += 1
    return stats


# ------------------------------------------------------------------ evaluated set + boundary
def _latest_settlement(fx):
    return fx["settlements"][-1] if fx["settlements"] else None


def finalized_frame(ledger: Ledger, as_of_ts: float) -> pd.DataFrame:
    """FINALIZED evaluated candidates: frozen obs is clean of terminal labels AND a settled
    winner exists AND the fixture's start ISO-week ENDED before as_of (incomplete current
    weeks stay pending — a running count is never treated as the final sample)."""
    rows = []
    for fid, fx in ledger.state()["fixtures"].items():
        obs, s = fx["obs"], _latest_settlement(fx)
        if obs is None or (set(obs["labels_at_obs"]) & TERMINAL):
            continue
        if s is None or s.get("winner") is None:
            continue
        start = pd.Timestamp(obs["start_ts"])
        week_end = (start.normalize() - pd.Timedelta(days=start.weekday())
                    + pd.Timedelta(days=7))
        if week_end.timestamp() > as_of_ts:
            continue                                       # incomplete ISO week -> pending
        rows.append({"fixture_id": fid, "league": obs["league"], "start": start,
                     "K": SA.key_k(obs["tournament_norm"], start),
                     "evaluated": True, "y": 1 if s["winner"] == "p1" else 0})
    return pd.DataFrame(rows)


def boundary_check(ledger: Ledger, seed_artifact_path: str, as_of_ts: float,
                   now_ts: float) -> dict:
    """Registered accrual boundary check: verified seed -> registered one-pass thinning on the
    finalized set -> registered counters. DRY counts only; records a thinning_decision event.
    No stage can progress here — gate evaluation needs separate authorization."""
    seed = verified_seed(seed_artifact_path)               # abort BEFORE thinning on bad seed
    cand = finalized_frame(ledger, as_of_ts)
    if not len(cand):
        rep = {"n_pre": 0, "post_thinning": 0, "counts": None, "note": "no finalized rows"}
    else:
        kept, info = SA.thin(cand, seed)
        rep = {"n_pre": info["n_pre"], "cap_size": info["cap_size"],
               "thinned": info["thinned"], "post_thinning": int(len(kept)),
               "counts": SA.dev_counts(kept),
               "per_key_shares_max": float(RP.per_key_share_table(kept)["keys"]
                                           and max(v["share_pct"] for v in
                                                   RP.per_key_share_table(kept)["keys"]
                                                   .values()) or 0)}
    rep["as_of_ts"] = as_of_ts
    rep["seed_verified_registered_sha"] = REG_SHA256
    ledger.append("thinning_decision", rep, now_ts)
    return rep


# ------------------------------------------------------------------ blinded operational report
def operational_report(ledger: Ledger, as_of_ts: float) -> dict:
    """Blinded accrual report: counts, coverage, diagnostics, provenance — NEVER predictive
    performance, log-loss, ROI, or any blinded outcome comparison."""
    st = ledger.state()
    fxs = st["fixtures"]
    label_lists = [fx["obs"]["labels_at_obs"] for fx in fxs.values() if fx["obs"]]
    fin = finalized_frame(ledger, as_of_ts)
    # settlement-state accounting over CLEAN observations (explicit denominator):
    # awaiting (no settlement event) | finalized | void_terminal | unresolved_review
    clean = [fx for fx in fxs.values()
             if fx["obs"] and not (set(fx["obs"]["labels_at_obs"]) & TERMINAL)]
    awaiting = void_term = unresolved = 0
    for fx in clean:
        s = _latest_settlement(fx)
        cls = s.get("terminal_class") if s else None
        if s is None:
            awaiting += 1
        elif cls == "void_terminal":
            void_term += 1
        elif cls == "unresolved_review":
            unresolved += 1
    setts = [_latest_settlement(fx) for fx in fxs.values() if fx["settlements"]]
    rep = {"source_cutoff_ts": max([fx["obs"]["source_cutoff_ts"] for fx in fxs.values()
                                    if fx["obs"]] or [None]),
           "processing_ts": as_of_ts,
           "activation": st["activation"],
           "raw_fixtures": len(fxs),
           "clean_obs_denominator": len(clean),
           "awaiting_settlement": awaiting,
           "terminal_void_n": void_term,
           "unresolved_review_n": unresolved,
           "finalized_evaluated": int(len(fin)),
           "coverage_by_tier": pd.Series([fx["obs"]["league"] for fx in fxs.values()
                                          if fx["obs"]]).value_counts().to_dict(),
           "exclusion_labels": RP.exclusion_report(label_lists),
           "settlement_provenance": pd.Series([s["provenance"] for s in setts if s])
           .value_counts().to_dict() if setts else {},
           "te_settled_retired_n": sum(1 for s in setts
                                       if s and s["status"] == "retired"
                                       and s["provenance"] != "pm"),
           "retirement_winner_mismatch_independent_n": sum(
               1 for s in setts if s and "retirement_winner_mismatch" in s.get("labels", [])
               and s["provenance"] == "pm"),
           "corrections_surfaced": len(ledger.events("correction")),
           "boundary_conflicts": len(ledger.events("boundary_conflict")),
           "note": "DRY counts until activation of gate evaluation; blinded by construction"}
    for k in BLIND_FORBIDDEN:
        assert k not in json.dumps(rep).lower() or k in ("mean",), "blinding breach"
    return rep


def reconcile(ledger: Ledger, as_of_ts: float) -> dict:
    """Candidate-ledger vs reported totals must agree exactly."""
    rep = operational_report(ledger, as_of_ts)
    fin = finalized_frame(ledger, as_of_ts)
    ok = (rep["finalized_evaluated"] == len(fin)
          and rep["raw_fixtures"] == len(ledger.state()["fixtures"]))
    return {"consistent": bool(ok), "finalized": int(len(fin)),
            "raw": rep["raw_fixtures"]}
