"""DQU — the genuine as-of snapshot registry.

Everything in the DQU system rests on one rule (owner requirement 7): the "available at
prediction time" side may only ever come from a REAL archive capture whose watermark
predates the match being predicted. Today's completed archive is the comparison target and
is never treated as having been available.

Only full-breadth captures (1,760 players) count. The local `all_match_logs.parquet` in
this checkout is a 157-player subset and is deliberately NOT registered: it would silently
halve every history and look like sparse data rather than a broken file.

Read-only. Loads parquet, contacts nothing.
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
CACHE = os.path.join(HERE, "..", "..", "data_cache", "tennisratio")

# label -> (path, the watermark we EXPECT). The expected watermark is asserted on load, so
# a file being replaced underneath us is a loud failure and not a quiet re-dating.
REGISTRY = [
    ("S0", os.path.join(CACHE, "_all_match_logs_pre_sync_1008.parquet"), "2026-09-28"),
    ("S2", os.path.join(HERE, "dryrun_data", "archive_2026-10-19.parquet"), "2026-10-19"),
    ("S3", os.path.join(HERE, "dqu_data", "archive_2026-10-20.parquet"), "2026-10-20"),
]

MIN_PLAYERS = 1000          # a full-breadth capture; the degraded subset has 157


def sha256(path, cap=None):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
            if cap and h.name and fh.tell() > cap:
                break
    return h.hexdigest()


def inventory(require_all=True):
    """-> [{label, path, watermark, rows, players, sha256}] for every registered capture."""
    import pandas as pd
    out = []
    for label, path, expect in REGISTRY:
        if not os.path.exists(path):
            if require_all:
                raise SystemExit("missing registered snapshot %s at %s" % (label, path))
            continue
        df = pd.read_parquet(path, columns=["date", "player_slug"])
        wm = str(df["date"].max())[:10]
        players = int(df["player_slug"].nunique())
        if wm != expect:
            raise SystemExit("snapshot %s watermark is %s, registry expects %s -- the file "
                             "changed; update the registry deliberately" % (label, wm, expect))
        if players < MIN_PLAYERS:
            raise SystemExit("snapshot %s has only %d players; this is the degraded subset, "
                             "not a full capture" % (label, players))
        out.append({"label": label, "path": path, "watermark": wm,
                    "rows": int(len(df)), "players": players,
                    "sha256": sha256(path)})
    out.sort(key=lambda s: s["watermark"])
    return out


def pairs(inv):
    """Usable (available, truth) pairs: every capture against every strictly later one."""
    return [(a, b) for i, a in enumerate(inv) for b in inv[i + 1:]]


if __name__ == "__main__":
    import json
    inv = inventory()
    print(json.dumps(inv, indent=1))
    print("\nusable (available -> truth) pairs:")
    for a, b in pairs(inv):
        print("  %s (%s) -> %s (%s)" % (a["label"], a["watermark"],
                                        b["label"], b["watermark"]))
