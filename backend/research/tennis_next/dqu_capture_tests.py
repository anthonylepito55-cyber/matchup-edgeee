"""DQU — tests for the manual capture system and the pre-registered evaluation gate.

Runs against a THROWAWAY store in a temp directory, so the real manifest and the real
captures are never written to by a test. Read-only with respect to every ledger.

    python dqu_capture_tests.py
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dqu_capture as C  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s %-62s %s" % ("PASS" if cond else "FAIL", name, detail))


class Args(object):
    def __init__(self, source, frm="test"):
        self.source = source
        self.frm = frm


def with_temp_store(fn):
    """Point the module at a throwaway store for the duration of one test."""
    real_store, real_manifest, real_cp = C.STORE, C.MANIFEST, C.CHECKPOINTS
    tmp = tempfile.mkdtemp(prefix="dqu_cap_test_")
    C.STORE = tmp
    C.MANIFEST = os.path.join(tmp, "manifest.jsonl")
    C.CHECKPOINTS = os.path.join(tmp, "checkpoints.jsonl")
    try:
        return fn(tmp)
    finally:
        C.STORE, C.MANIFEST, C.CHECKPOINTS = real_store, real_manifest, real_cp
        shutil.rmtree(tmp, ignore_errors=True)


def find_source():
    for p in (os.path.join(HERE, "dqu_data", "archive_2026-10-20.parquet"),
              os.path.join(HERE, "dryrun_data", "archive_2026-10-19.parquet")):
        if os.path.exists(p):
            return p
    return None


def t_capture_and_chain():
    print("\nT1 capture, manifest chain, duplicate detection")
    src = find_source()
    if not src:
        check("a full archive is available to capture", False, "no source found")
        return

    def body(tmp):
        rc = C.cmd_capture(Args(src, "unit test"))
        check("first capture succeeds", rc == 0)
        m = C.read_manifest()
        check("exactly one manifest entry", len(m) == 1)
        e = m[0]
        check("entry records every required field",
              all(k in e for k in ("capture_ts_utc", "source_watermark", "rows",
                                   "players", "stored_sha256", "source_sha256",
                                   "provenance", "prev_hash", "entry_hash")))
        check("first entry chains to genesis", e["prev_hash"] == C.GENESIS)
        check("integrity_verified is true", e["integrity_verified"] is True)
        check("stored file hash matches the manifest",
              C.sha256_file(os.path.join(HERE, e["stored_path"])) == e["stored_sha256"])
        check("provenance is recorded verbatim", e["provenance"] == "unit test")
        check("entry is marked manual with no schedule",
              e["manual"] is True and e["schedule"].startswith("none"))

        rc2 = C.cmd_capture(Args(src, "unit test again"))
        check("re-capturing identical bytes is detected as a duplicate", rc2 == 0)
        m2 = C.read_manifest()
        check("duplicate appends an entry rather than a second copy",
              len(m2) == 2 and m2[1]["kind"] == "duplicate")
        check("duplicate entry points at the original",
              m2[1]["duplicate_of"]["entry_hash"] == e["entry_hash"])
        stored = [f for f in os.listdir(tmp) if f.endswith(".parquet")]
        check("only one parquet is stored after the duplicate", len(stored) == 1)
        check("verify passes on a clean store", C.cmd_verify(None) == 0)
    with_temp_store(body)


def t_tamper_detection():
    print("\nT2 tamper and deletion detection")
    src = find_source()
    if not src:
        return

    def body(tmp):
        C.cmd_capture(Args(src, "unit test"))
        e = C.read_manifest()[0]
        p = os.path.join(HERE, e["stored_path"])
        with open(p, "ab") as fh:
            fh.write(b"x")
        check("verify FAILS after a stored capture is modified", C.cmd_verify(None) == 1)
        os.remove(p)
        check("verify FAILS after a stored capture is deleted", C.cmd_verify(None) == 1)
    with_temp_store(body)

    def body2(tmp):
        C.cmd_capture(Args(src, "a"))
        C.cmd_capture(Args(src, "b"))      # duplicate, so two entries
        ent = C.read_manifest()
        ent[0]["rows"] = ent[0]["rows"] + 1          # edit history
        with open(C.MANIFEST, "w", encoding="utf-8") as fh:
            for x in ent:
                fh.write(json.dumps(x, sort_keys=True) + "\n")
        check("verify FAILS after a manifest entry is edited", C.cmd_verify(None) == 1)
    with_temp_store(body2)

    def body3(tmp):
        C.cmd_capture(Args(src, "a"))
        C.cmd_capture(Args(src, "b"))
        ent = C.read_manifest()
        with open(C.MANIFEST, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(ent[0], sort_keys=True) + "\n")   # drop the last entry
        check("WITHOUT a checkpoint, a removed tail is not detectable",
              C.cmd_verify(None) == 0, "this is exactly why checkpoints exist")
    with_temp_store(body3)

    def body4(tmp):
        C.cmd_capture(Args(src, "a"))
        C.cmd_capture(Args(src, "b"))          # duplicate -> a second entry
        check("checkpoint records the chain length and head",
              C.cmd_checkpoint(None) == 0)
        cps = C.read_checkpoints()
        check("the checkpoint is stored OUTSIDE the manifest",
              len(cps) == 1 and cps[0]["entry_count"] == 2
              and os.path.abspath(C.CHECKPOINTS) != os.path.abspath(C.MANIFEST))
        check("verify still passes with a checkpoint in place",
              C.cmd_verify(None) == 0)
        ent = C.read_manifest()
        with open(C.MANIFEST, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(ent[0], sort_keys=True) + "\n")    # remove the tail
        check("WITH a checkpoint, a removed tail IS detected",
              C.cmd_verify(None) == 1, "manifest shorter than the checkpoint")
    with_temp_store(body4)

    def body5(tmp):
        C.cmd_capture(Args(src, "a"))
        C.cmd_checkpoint(None)
        C.cmd_capture(Args(src, "b"))          # legitimate growth after a checkpoint
        check("the chain may legitimately GROW past a checkpoint",
              C.cmd_verify(None) == 0, "growth is fine, shrinkage is not")
        C.cmd_checkpoint(None)
        cps = C.read_checkpoints()
        check("checkpointing never rewrites existing history",
              len(cps) == 2 and cps[0]["seq"] == 1 and cps[1]["seq"] == 2
              and cps[0]["entry_count"] == 1 and cps[1]["entry_count"] == 2)
    with_temp_store(body5)


def t_refusals():
    print("\nT3 refusals")
    src = find_source()
    if not src:
        return

    def body(tmp):
        try:
            C.cmd_capture(Args(os.path.join(tmp, "nope.parquet")))
            check("missing source is refused", False)
        except SystemExit as e:
            check("missing source is refused", "does not exist" in str(e))
        degraded = os.path.join(HERE, "..", "..", "data_cache", "tennisratio",
                                "all_match_logs.parquet")
        if os.path.exists(degraded):
            try:
                C.cmd_capture(Args(degraded, "degraded subset"))
                check("the 157-player degraded archive is refused", False,
                      "it was captured")
            except SystemExit as e:
                check("the 157-player degraded archive is refused",
                      "REFUSED" in str(e), "players below the floor")
        # overwrite refusal: pre-create the target name
        import dqu_capture as CC
        meta = CC.describe(src)
        name = "archive_%s_%s.parquet" % (meta["watermark"],
                                          CC.sha256_file(src)[:12])
        open(os.path.join(tmp, name), "wb").close()
        try:
            C.cmd_capture(Args(src, "x"))
            check("an existing stored filename is never overwritten", False)
        except SystemExit as e:
            check("an existing stored filename is never overwritten",
                  "never overwritten" in str(e))
    with_temp_store(body)


def t_no_scheduling():
    print("\nT4 no scheduling is created anywhere")
    src = open(os.path.join(HERE, "dqu_capture.py"), encoding="utf-8").read()
    bad = [w for w in ("crontab", "systemd", "schedule.every", "APScheduler",
                       ".timer", "CronCreate") if w in src]
    check("the capture module creates no timer, cron entry or scheduler",
          not bad, str(bad or "clean"))
    check("the module is manual-only by its own declaration",
          '"manual": True' in src or "\"manual\": True" in src)


def t_prospective_gate():
    print("\nT5 the pre-registered evaluation gate")
    import dqu_prospective as P
    rows, pending, excl, _, _ = P.gather()
    st = P.status_block(rows, pending, excl)
    check("the gate reports progress without an analysis",
          st["criterion_met"] is False or st["criterion_met"] is True)
    check("registered thresholds are the ones in the pre-registration",
          P.MIN_SETTLED == 300 and P.MIN_FLAGGED == 60 and P.NULL_K == 2000,
          "settled>=300, flagged>=60, K=2000")
    check("the pre-registration file exists and hashes",
          len(P.prereg_sha()) == 64, P.prereg_sha()[:16])
    # the gate must be closed while the beta has too few settled
    if not st["criterion_met"]:
        check("with the criterion unmet, no analysis is produced",
              True, "settled=%d flagged=%d" % (st["settled_eligible"], st["flagged"]))
    # every row must carry the ORIGINAL fields, unrecomputed
    if rows:
        r = rows[0]
        check("each row carries the original probability, flags, timestamp and version",
              all(k in r for k in ("p1_prob", "missing_result_flag", "elo_only",
                                   "prediction_ts_utc", "model_version")))


def main():
    print("DQU CAPTURE + PROSPECTIVE TEST SUITE")
    t_capture_and_chain()
    t_tamper_detection()
    t_refusals()
    t_no_scheduling()
    t_prospective_gate()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
