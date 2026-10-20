"""DQU — manual, append-only archive snapshot capture.

Each capture stores one archive file verbatim and appends one hash-chained manifest entry.
Nothing is ever overwritten and nothing is ever silently repaired: a capture that fails its
integrity check is recorded AS a failure and the run aborts, leaving the earlier captures
and the chain intact.

MANUAL ONLY. This module creates no timer, no cron entry and no scheduled job, and it is
never invoked by the board, the beta pass or any production path. It runs when a person
runs it.

    python dqu_capture.py capture --source <path> [--from "where it came from"]
    python dqu_capture.py verify            # re-hash every stored capture, re-walk the chain
    python dqu_capture.py list              # the manifest, newest last

Why the chain. The point of these captures is to establish what was knowable on a past day.
That claim is only as good as the guarantee that a capture has not been edited since, so
each manifest entry carries the hash of the one before it: changing or removing any entry
breaks every entry after it, and `verify` says so.

Read-only with respect to everything else: the frozen model, the beta ledgers, the official
trial and all production files are untouched.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

STORE = os.path.join(HERE, "dqu_captures")
MANIFEST = os.path.join(STORE, "manifest.jsonl")
MIN_PLAYERS = 1000          # a full-breadth capture; the degraded local subset has 157
GENESIS = "0" * 64


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def entry_hash(prev, body):
    """Hash of the previous entry plus this entry's canonical body."""
    payload = prev + "|" + json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


CHECKPOINTS = os.path.join(STORE, "checkpoints.jsonl")


def read_checkpoints():
    """Checkpoints are stored in their own file, separate from the manifest.

    An append-only chain cannot detect its own TAIL being removed: drop the last N entries
    and what remains is still internally consistent. The fix is a record kept OUTSIDE the
    chain saying how long it was and what its head hash was. Deleting the tail then
    contradicts the checkpoint, and deleting the checkpoint too is itself conspicuous
    because checkpoints are numbered consecutively.

    This file is append-only like the manifest, and `checkpoint` never rewrites history --
    it only states what the chain looked like at a moment in time.
    """
    if not os.path.exists(CHECKPOINTS):
        return []
    out = []
    with open(CHECKPOINTS, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def cmd_checkpoint(_args):
    entries = read_manifest()
    if not entries:
        print("no manifest to checkpoint")
        return 0
    prior = read_checkpoints()
    rec = {"seq": len(prior) + 1,
           "checkpoint_ts_utc": dt.datetime.now(dt.timezone.utc)
                                  .strftime("%Y-%m-%dT%H:%M:%SZ"),
           "entry_count": len(entries),
           "chain_head": entries[-1]["entry_hash"],
           "captures": sum(1 for e in entries if e.get("kind") == "capture"),
           "manifest_sha256": sha256_file(MANIFEST),
           "note": "independent record of the chain length and head; stored outside the "
                   "manifest so that removing the manifest tail becomes detectable"}
    os.makedirs(STORE, exist_ok=True)
    with open(CHECKPOINTS, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    print("checkpoint %d recorded: %d entries, head %s"
          % (rec["seq"], rec["entry_count"], rec["chain_head"][:16]))
    return 0


def read_manifest():
    if not os.path.exists(MANIFEST):
        return []
    out = []
    with open(MANIFEST, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def append_entry(body):
    """Append one chained entry. The only writer in this module."""
    entries = read_manifest()
    prev = entries[-1]["entry_hash"] if entries else GENESIS
    rec = dict(body)
    rec["prev_hash"] = prev
    rec["entry_hash"] = entry_hash(prev, body)
    os.makedirs(STORE, exist_ok=True)
    with open(MANIFEST, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def describe(path):
    """Measured facts about an archive file, read before it is copied anywhere."""
    import pandas as pd
    df = pd.read_parquet(path, columns=["date", "player_slug"])
    return {"rows": int(len(df)),
            "players": int(df["player_slug"].nunique()),
            "watermark": str(df["date"].max())[:10],
            "earliest": str(df["date"].min())[:10]}


def cmd_capture(args):
    src = os.path.abspath(args.source)
    if not os.path.exists(src):
        raise SystemExit("source does not exist: %s" % src)
    now = dt.datetime.now(dt.timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H%M%SZ")

    print("reading source ...")
    src_sha = sha256_file(src)
    meta = describe(src)
    print("  watermark %s  rows %d  players %d  sha256 %s"
          % (meta["watermark"], meta["rows"], meta["players"], src_sha[:16]))

    if meta["players"] < MIN_PLAYERS:
        raise SystemExit(
            "REFUSED: %d players (< %d). This looks like the degraded local subset, not a "
            "full archive. Capturing it would poison the as-of record."
            % (meta["players"], MIN_PLAYERS))

    # duplicate detection -- by CONTENT, not by name or date
    prior = read_manifest()
    dup = next((e for e in prior
                if e.get("kind") == "capture" and e.get("source_sha256") == src_sha), None)
    if dup is not None:
        rec = append_entry({
            "kind": "duplicate",
            "capture_ts_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_path": src, "source_sha256": src_sha,
            "duplicate_of": {"capture_ts_utc": dup["capture_ts_utc"],
                             "stored_path": dup["stored_path"],
                             "entry_hash": dup["entry_hash"]},
            "watermark": meta["watermark"],
            "note": "byte-identical to an existing capture; nothing new was stored"})
        print("\nDUPLICATE of the capture taken %s. Nothing stored."
              % dup["capture_ts_utc"])
        print("manifest entry %s" % rec["entry_hash"][:16])
        return 0

    stored_name = "archive_%s_%s.parquet" % (meta["watermark"], src_sha[:12])
    stored = os.path.join(STORE, stored_name)
    if os.path.exists(stored):
        raise SystemExit("REFUSED: %s already exists. Captures are never overwritten."
                         % stored_name)

    os.makedirs(STORE, exist_ok=True)
    print("storing %s ..." % stored_name)
    shutil.copy2(src, stored)

    # integrity verification AFTER the copy, on the stored bytes
    out_sha = sha256_file(stored)
    out_meta = describe(stored)
    ok = (out_sha == src_sha and out_meta == meta)
    body = {
        "kind": "capture" if ok else "failed_capture",
        "capture_ts_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stored_path": os.path.relpath(stored, HERE),
        "stored_sha256": out_sha,
        "source_path": src,
        "source_sha256": src_sha,
        "source_mtime_utc": dt.datetime.fromtimestamp(
            os.path.getmtime(src), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_watermark": meta["watermark"],
        "earliest_row": meta["earliest"],
        "rows": meta["rows"], "players": meta["players"],
        "bytes": os.path.getsize(stored),
        "provenance": args.frm,
        "integrity_verified": bool(ok),
        "tool": "dqu_capture.py/1", "manual": True,
        "schedule": "none -- this module creates no timer, cron entry or scheduled job",
    }
    if not ok:
        body["mismatch"] = {"stored_sha256": out_sha, "source_sha256": src_sha,
                            "stored_meta": out_meta, "source_meta": meta}
    rec = append_entry(body)
    if not ok:
        print("\nINTEGRITY CHECK FAILED. The failure is recorded in the manifest as "
              "kind=failed_capture and the stored file is left in place for inspection. "
              "Nothing was repaired.")
        return 2
    print("\ncaptured OK")
    print("  stored        %s" % body["stored_path"])
    print("  sha256        %s" % out_sha)
    print("  watermark     %s   rows %d   players %d"
          % (meta["watermark"], meta["rows"], meta["players"]))
    print("  provenance    %s" % args.frm)
    print("  manifest      entry %s (prev %s)"
          % (rec["entry_hash"][:16], rec["prev_hash"][:16]))
    return 0


def cmd_verify(_args):
    entries = read_manifest()
    if not entries:
        print("no manifest yet")
        return 0
    bad = []
    prev = GENESIS
    for i, e in enumerate(entries):
        body = {k: v for k, v in e.items() if k not in ("prev_hash", "entry_hash")}
        if e["prev_hash"] != prev:
            bad.append("entry %d: prev_hash does not match the entry before it" % i)
        if entry_hash(e["prev_hash"], body) != e["entry_hash"]:
            bad.append("entry %d: entry_hash does not match its own body" % i)
        prev = e["entry_hash"]
        if e.get("kind") != "capture":
            continue
        p = os.path.join(HERE, e["stored_path"])
        if not os.path.exists(p):
            bad.append("entry %d: stored file missing (%s)" % (i, e["stored_path"]))
            continue
        if sha256_file(p) != e["stored_sha256"]:
            bad.append("entry %d: stored file has CHANGED since capture (%s)"
                       % (i, e["stored_path"]))
    # tail-deletion check against the independently stored checkpoints
    cps = read_checkpoints()
    heads = {e["entry_hash"]: i for i, e in enumerate(entries)}
    for cp in cps:
        if cp["chain_head"] not in heads:
            bad.append("checkpoint %d (%s) recorded head %s, which is NOT in the manifest "
                       "-- entries have been removed or replaced"
                       % (cp["seq"], cp["checkpoint_ts_utc"], cp["chain_head"][:16]))
        elif heads[cp["chain_head"]] + 1 != cp["entry_count"]:
            bad.append("checkpoint %d recorded %d entries at that head, manifest now has "
                       "%d up to it" % (cp["seq"], cp["entry_count"],
                                        heads[cp["chain_head"]] + 1))
        elif len(entries) < cp["entry_count"]:
            bad.append("checkpoint %d recorded %d entries, manifest now has only %d -- the "
                       "TAIL has been removed" % (cp["seq"], cp["entry_count"],
                                                  len(entries)))
    if cps:
        last = cps[-1]
        if len(entries) < last["entry_count"]:
            bad.append("the manifest is SHORTER than the latest checkpoint (%d < %d)"
                       % (len(entries), last["entry_count"]))

    caps = [e for e in entries if e.get("kind") == "capture"]
    print("manifest entries %d  (captures %d, duplicates %d, failed %d)"
          % (len(entries), len(caps),
             sum(1 for e in entries if e.get("kind") == "duplicate"),
             sum(1 for e in entries if e.get("kind") == "failed_capture")))
    print("chain head %s   checkpoints %d%s"
          % (entries[-1]["entry_hash"][:16], len(cps),
             ("  (latest: %d entries at %s)"
              % (cps[-1]["entry_count"], cps[-1]["checkpoint_ts_utc"])) if cps else ""))
    if not cps:
        print("  no checkpoint recorded yet -- a removed manifest TAIL would not be "
              "detectable; run `dqu_capture.py checkpoint`")
    if bad:
        print("\nFAILED:")
        for b in bad:
            print("  -", b)
        return 1
    print("every entry chains correctly and every stored file still matches its hash")
    return 0


def cmd_list(_args):
    for e in read_manifest():
        if e.get("kind") == "capture":
            print("%s  %-10s wm=%s rows=%-7d players=%-5d %s  %s"
                  % (e["capture_ts_utc"], e["kind"], e["source_watermark"], e["rows"],
                     e["players"], e["stored_sha256"][:12], e.get("provenance", "")))
        else:
            print("%s  %-10s %s" % (e["capture_ts_utc"], e.get("kind"),
                                    e.get("note", "")))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("capture", help="store one archive snapshot (manual)")
    c.add_argument("--source", required=True, help="path to the archive parquet to capture")
    c.add_argument("--from", dest="frm", default="unspecified",
                   help="provenance, e.g. 'scp ec2-user@3.22.236.36 production archive'")
    sub.add_parser("verify", help="re-hash every capture and re-walk the chain")
    sub.add_parser("checkpoint",
                   help="record the chain length and head outside the manifest, so a "
                        "removed tail becomes detectable")
    sub.add_parser("list", help="print the manifest")
    a = ap.parse_args()
    if a.cmd == "capture":
        return cmd_capture(a)
    if a.cmd == "verify":
        return cmd_verify(a)
    if a.cmd == "checkpoint":
        return cmd_checkpoint(a)
    if a.cmd == "list":
        return cmd_list(a)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
