"""OPP1 v3.5 daily entry point (repository-tracked, 2026-10-19).

Seeded byte-for-byte from the audited EC2 deployment artifact (sha256 58390789e5c8e03d…) and
then hardened on the owner's ruling and the pre-activation audit's notes. It composes the
committed runner; no committed runtime module is modified.

OWNER RULING ENFORCED HERE AND IN THE RUNNER
  Any fixture whose FIRST VERIFIED source observation predates the OPP1 activation timestamp is
  permanently excluded from prospective accrual, even if the registered development cutoff would
  admit it (labels pre_activation_observed + a boundary_conflict event, both reported).
  AND: where the available source history CANNOT ESTABLISH whether that first observation
  predates activation, the fixture is NOT quietly treated as new. It is flagged
  (first_obs_unverifiable) and held out of accrual pending review -- nothing is written for it,
  so a later pass with better evidence can still process it.

WHY A PROVENANCE INDEX RATHER THAN A ROLLING LOOKBACK
  The first version read the last four day-files and let the runner take the earliest poll it
  could see as the fixture's first-ever poll. That is unsound: a fixture listed weeks ago and
  rescheduled, a start that moved several times across more than four days, or any outage longer
  than the window would hand the runner a truncated history and could make a pre-activation
  fixture look new. This version builds a PROVENANCE INDEX over EVERY store file ever retained
  (cached per file by name+size+mtime in the OPP1 ledger directory, so each file is scanned
  once), and then passes the runner the candidate's COMPLETE row history. First-observation and
  observed-start-range decisions therefore rest on all persisted evidence, not on a window.

COVERAGE / OUTAGE HANDLING (fail closed, never silent)
  Missing day-files between the earliest and latest retained file are detected as gaps. A
  candidate is held out as first_obs_unverifiable when its earliest observation sits in the
  oldest retained file (history may have been rotated away) or when a gap falls at or before
  that observation. Every fixture lands in exactly one reported bucket: processed,
  pending_tstar, first_obs_unverifiable, or already_in_ledger.

FAILS CLOSED ON ACTIVATION. The committed runner refuses every observation pass until an
activation event exists, and this script checks that BEFORE reading any production record, so a
start before authorization reads nothing and accrues nothing.

Reads (read-only): the snapshot-store day files and the frozen prediction log.
Writes: only inside the dedicated OPP1 ledger directory (events.jsonl, provenance/, reports/).
No collectors, no API calls, no model evaluation, no Phase-5 contact, no boundary/stage work --
boundary checks need the owner's blinded inputs and are run by hand under their own
authorization.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(os.path.dirname(HERE), "lib"), HERE):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
sys.path.append(os.environ.get("OPP1_APP_DIR", "/home/ec2-user/mlb-predictor/backend"))

import opp1_adapters as AD                                           # noqa: E402
import opp1_eligibility as EL                                        # noqa: E402
import opp1_runner as RN                                             # noqa: E402

LEDGER = os.environ.get("OPP1_LEDGER_DIR", "/home/ec2-user/opp1/ledger")
STORE = os.environ.get("OPP1_STORE_DIR",
                       "/home/ec2-user/mlb-predictor/backend/data_cache/oo_snapshots")
LOG = os.environ.get("OPP1_LOG_PATH",
                     "/home/ec2-user/mlb-predictor/backend/data_cache/tennis_prediction_log.parquet")
LEAGUES = ("atp", "atp_challenger", "itf_men")
LOG_COLS = ["fixture_id", "league", "tournament", "player_1", "player_2", "start_time_utc",
            "best_of_5", "settled", "p1_won", "void", "score", "mc2_p1", "mc2_recon",
            "mc6_p1", "mc6_recon", "date", "pm_src"]
IDX_COLS = ["fixture_id", "league", "start_date", "poll_ts", "market"]
TSTAR_END_S = EL.TSTAR_HI_S          # the registered window end: S - 30 min


# ------------------------------------------------------------------ provenance index
def _file_key(path: str) -> dict:
    st = os.stat(path)
    return {"size": int(st.st_size), "mtime": int(st.st_mtime)}


def _scan_file(path: str) -> dict:
    """Per-fixture aggregate for ONE store file: earliest/latest poll and every distinct
    scheduled start observed in it. Column-pruned so a full-history scan stays cheap."""
    df = pd.read_parquet(path, columns=IDX_COLS)
    df = df[df["league"].astype(str).isin(LEAGUES) & (df["market"].astype(str) == "moneyline")]
    if not len(df):
        return {}
    df = df.assign(_p=pd.to_numeric(df["poll_ts"], errors="coerce")).dropna(subset=["_p"])
    out = {}
    for fid, g in df.groupby(df["fixture_id"].astype(str)):
        out[fid] = {"first_poll": float(g["_p"].min()), "last_poll": float(g["_p"].max()),
                    "starts": sorted({str(s) for s in g["start_date"]}),
                    "league": str(g["league"].iloc[0])}
    return out


def build_index(store_dir: str, cache_dir: str) -> dict:
    """Provenance over EVERY retained store file, cached per file by name+size+mtime.
    Returns dict(fixtures, files, coverage). Fails closed if the store is unreadable/empty."""
    if not os.path.isdir(store_dir):
        raise RuntimeError("store directory missing: %s (fail closed)" % store_dir)
    files = sorted(glob.glob(os.path.join(store_dir, "*.parquet")))
    if not files:
        raise RuntimeError("no store files found in %s (fail closed)" % store_dir)
    os.makedirs(cache_dir, exist_ok=True)
    cpath = os.path.join(cache_dir, "index.json")
    cache = {}
    if os.path.exists(cpath):
        try:
            cache = json.load(open(cpath, encoding="utf-8"))
        except Exception as e:                       # a corrupt cache is rebuilt, never trusted
            print("OPP1: provenance cache unreadable (%s) — rebuilding from source" % e)
            cache = {}
    per_file = cache.get("per_file") or {}
    changed = False
    for f in files:
        base, key = os.path.basename(f), _file_key(f)
        have = per_file.get(base)
        if have and have.get("key") == key:
            continue
        per_file[base] = {"key": key, "fixtures": _scan_file(f)}
        changed = True
    for stale in [b for b in per_file if b not in {os.path.basename(f) for f in files}]:
        per_file.pop(stale)                          # file rotated away: drop, then report the gap
        changed = True
    if changed:
        tmp = cpath + ".tmp"
        json.dump({"per_file": per_file}, open(tmp, "w", encoding="utf-8"))
        os.replace(tmp, cpath)                       # atomic
    # ---- fold per-file aggregates into one per-fixture provenance record ----
    days = sorted(b[:10] for b in per_file)
    expected = ([d.strftime("%Y-%m-%d") for d in pd.date_range(days[0], days[-1], freq="D")]
                if days else [])
    gaps = [d for d in expected if d not in set(days)]
    fixtures: dict = {}
    for base in sorted(per_file):
        day = base[:10]
        for fid, agg in (per_file[base].get("fixtures") or {}).items():
            e = fixtures.setdefault(fid, {"first_poll": agg["first_poll"],
                                          "last_poll": agg["last_poll"],
                                          "starts": [], "days": [], "league": agg["league"]})
            e["first_poll"] = min(e["first_poll"], agg["first_poll"])
            e["last_poll"] = max(e["last_poll"], agg["last_poll"])
            e["starts"] = sorted(set(e["starts"]) | set(agg["starts"]))
            e["days"].append(day)
    return {"fixtures": fixtures, "files": [os.path.basename(f) for f in files],
            "coverage": {"earliest_day": days[0] if days else None,
                         "latest_day": days[-1] if days else None,
                         "retained_days": len(days), "missing_days": gaps}}


def classify(index: dict, known: set, cutoff: float) -> dict:
    """Bucket every indexed fixture. Exactly one bucket each, nothing silently dropped."""
    cov = index["coverage"]
    earliest, gaps = cov["earliest_day"], set(cov["missing_days"])
    b = {"already_in_ledger": [], "pending_tstar": [], "first_obs_unverifiable": [],
         "processable": []}
    for fid, e in index["fixtures"].items():
        if fid in known:
            b["already_in_ledger"].append(fid)
            continue
        first_day = min(e["days"])
        # history may have been rotated away, or a gap sits at/before the first observation ->
        # provenance for the activation test cannot be established: HOLD OUT (owner ruling)
        if first_day == earliest or any(g <= first_day for g in gaps):
            b["first_obs_unverifiable"].append(fid)
            continue
        if any(first_day <= g <= max(e["days"]) for g in gaps):
            b["first_obs_unverifiable"].append(fid)      # gap inside its observation span
            continue
        starts = [EL.parse_ts(s) for s in e["starts"]]
        ts = [m["ts"] for m in starts if m["ts"] is not None
              and m["kind"] in ("aware", "naive_interpreted")]
        if not ts:
            b["first_obs_unverifiable"].append(fid)      # no usable scheduled start observed
            continue
        if max(ts).timestamp() - TSTAR_END_S > cutoff:
            b["pending_tstar"].append(fid)               # T* window not complete yet
            continue
        b["processable"].append(fid)
    return b


def rows_for(store_dir: str, index: dict, fids: set) -> pd.DataFrame:
    """COMPLETE row history for the given fixtures, from every file that holds them -- so the
    runner's first-observation test and the adapter's observed-start range see all the
    evidence, independent of any rolling window."""
    if not fids:
        return pd.DataFrame()
    want_files = sorted({d for f in fids for d in index["fixtures"][f]["days"]})
    parts = []
    for day in want_files:
        p = os.path.join(store_dir, "%s.parquet" % day)
        if not os.path.exists(p):
            continue
        df = pd.read_parquet(p)
        df = df[df["fixture_id"].astype(str).isin(fids)
                & df["league"].astype(str).isin(LEAGUES)
                & (df["market"].astype(str) == "moneyline")]
        if len(df):
            parts.append(df)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


# ------------------------------------------------------------------ one daily pass
def main() -> int:
    led = RN.Ledger(LEDGER)                      # single-writer lock for the whole pass
    try:
        if led.state()["activation"] is None:
            print("OPP1: ledger not activated — nothing read, nothing processed (by design). "
                  "Activation is a separate authorized step.")
            return 0
        index = build_index(STORE, os.path.join(LEDGER, "provenance"))
        cutoff = max(e["last_poll"] for e in index["fixtures"].values())
        known = set(led.state()["fixtures"])
        buckets = classify(index, known, cutoff)
        store = rows_for(STORE, index, set(buckets["processable"]))
        obs = {"seen": 0, "new_obs": 0, "skipped_existing": 0, "pre_activation": 0,
               "boundary_conflicts": 0, "window_not_yet_complete": 0}
        if len(store):
            log = pd.read_parquet(LOG, columns=LOG_COLS)
            obs = RN.process_snapshot(led, store, log, cutoff, time.time())
            st = RN.settle_pass(led, log, time.time())
        else:
            log = pd.read_parquet(LOG, columns=LOG_COLS)
            st = RN.settle_pass(led, log, time.time())
        now = time.time()
        rep = RN.operational_report(led, now)
        rep["source_coverage"] = index["coverage"]
        rep["buckets"] = {k: len(v) for k, v in buckets.items()}
        rep["held_out_first_obs_unverifiable"] = sorted(buckets["first_obs_unverifiable"])[:200]
        rep["observation_pass"] = obs
        rep["settlement_pass"] = st
        out = os.path.join(LEDGER, "reports")
        os.makedirs(out, exist_ok=True)
        name = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
        json.dump(rep, open(os.path.join(out, "report_%s.json" % name), "w"),
                  indent=1, default=str)
        print("OPP1 pass: buckets=%s | obs=%s | settle=%s | coverage=%s"
              % (rep["buckets"], obs, st, index["coverage"]))
        if index["coverage"]["missing_days"]:
            print("OPP1 WARNING: store coverage gaps %s — affected fixtures held out as "
                  "first_obs_unverifiable, not accrued" % index["coverage"]["missing_days"])
        return 0
    finally:
        led.close()


if __name__ == "__main__":
    sys.exit(main())
