"""NIGHTLY REBUILD OF THE TENNIS RATING STATES (2026-10-13, user: "do the night rebuild").

Nothing was rebuilding them. _mc2_state.pkl sat at 2026-10-08 while the match data it is built
from refreshed on 2026-10-12, and the measured cost of four days was: 41% of players stale,
median card moving 0.72pt, 47% of cards moving over 1pt, 42% over 2pt -- which is the brown
marks' own gate -- and MC2's pick flipping side on 9 of 171 cards. See _mc2_staleness_cost.py.

Rebuilds BOTH heads from the same source, every night:

  MC2  the canonical builder, source-transformed ONLY to redirect its two output paths, so the
       recipe is bit-for-bit what MC2 has always used. Written to temp, validated, then swapped
       in with os.replace, which is atomic on one filesystem -- a crash mid-build can therefore
       never leave the live site reading a half-written pickle.
  MC3  via _mc3_build.py, which already writes through sk-named files and os.replace, and which
       asserts MC2's artifacts unchanged by fingerprint on its own.

SAFETY, shaped by what has gone wrong here before:
  * Every state is backed up to .bak before the swap, so a bad build is one copy from undone.
  * A new state must PASS validation before it is swapped in: sane player count against the
    outgoing one, and real predictions on recent fixtures off the live log.
  * The age of the SOURCE parquet is printed loudly. daily_retrain once silently reverted its
    training data and nobody noticed for weeks; a rebuild from stale input is the same failure,
    so staleness is reported rather than assumed away.
  * Exits non-zero on any failure and prints a single marked result line, because the run log is
    mixed-encoding and gets scanned for exit markers rather than read.
  * Never run this under sudo. It writes into data_cache, and root-owned parquet files there
    have broken the site before.

Run: ./venv/bin/python nightly_tennis_ratings.py [--dry-run]
"""
import os
import pickle
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(_HERE)

SRC = "_mc2_stage1b_serve_return.py"
MC2_STATE = "data_cache/_mc2_state.pkl"
MC2_FEAT = "data_cache/_mc2_features.parquet"
MC3_STATE = "data_cache/_mc3_state.pkl"
SOURCE = "data_cache/tennisratio/all_match_logs.parquet"
DRY = "--dry-run" in sys.argv

FAILED = []


def say(m):
    print("[%s] %s" % (datetime.now(timezone.utc).strftime("%H:%M:%S"), m), flush=True)


def age_days(p):
    return (time.time() - os.path.getmtime(p)) / 86400.0 if os.path.exists(p) else None


# ---------------------------------------------------------------- source check
if not os.path.exists(SOURCE):
    print("RESULT: FAIL -- source parquet missing: %s" % SOURCE)
    raise SystemExit(2)
src_age = age_days(SOURCE)
say("source %s is %.1f days old" % (os.path.basename(SOURCE), src_age))
if src_age > 2.5:
    # NOT fatal: rebuilding off 3-day-old matches still beats a 5-day-old rating state. But it
    # is said plainly, because _full_site_ingest.py has no timer and only refreshes when it is
    # run by hand, so this is the likeliest reason a nightly rebuild quietly stops helping.
    say("WARNING: source data is stale. _full_site_ingest.py has no schedule; "
        "the ratings can only be as fresh as it is.")

# how many recent fixtures to validate predictions against
try:
    import tennis_log
    _L = pd.read_parquet(tennis_log.LOG_PATH)
    _L = _L[_L["player_1"].notna() & _L["player_2"].notna()]
    PAIRS = [(r["player_1"], r["player_2"], r.get("surface"))
             for _, r in _L.tail(40).iterrows()]
except Exception:                                                  # noqa: BLE001
    PAIRS = []
say("validation fixtures taken from the live log: %d" % len(PAIRS))


def validate(module, state_path, old_players):
    """A new state must load, keep a sane roster, and actually price real fixtures."""
    try:
        with open(state_path, "rb") as f:
            st = pickle.load(f)
    except Exception as e:                                         # noqa: BLE001
        return False, "state will not unpickle: %s" % e
    if not isinstance(st, dict) or "players" not in st or "base" not in st:
        return False, "state is missing the players/base keys"
    n = len(st["players"])
    if old_players and (n < 0.9 * old_players):
        return False, "roster collapsed: %d players against %d before" % (n, old_players)
    module._S = st
    module._MT = None
    if hasattr(module, "_anchor"):
        module._anchor.cache_clear()
    ok = bad = 0
    for p1, p2, sf in PAIRS:
        try:
            q = module.predict(p1, p2, sf)
        except Exception:                                          # noqa: BLE001
            bad += 1
            continue
        if q is None:
            continue
        v = q.get("p1_prob")
        if v is None or not (0.0 < float(v) < 1.0) or not np.isfinite(float(v)):
            bad += 1
        else:
            ok += 1
    if bad:
        return False, "%d fixtures priced to an invalid probability" % bad
    if PAIRS and ok == 0:
        return False, "priced none of %d recent fixtures" % len(PAIRS)
    return True, "%d players, %d/%d recent fixtures priced" % (n, ok, len(PAIRS))


def board_drift(module, old_state, new_state):
    """Mean absolute probability change on the latest logged day -- the useful signal that the
    rebuild did something, and the number to watch if it ever does something alarming."""
    if not PAIRS:
        return None
    out = {}
    for tag, st in (("old", old_state), ("new", new_state)):
        module._S = st
        module._MT = None
        if hasattr(module, "_anchor"):
            module._anchor.cache_clear()
        vals = []
        for p1, p2, sf in PAIRS:
            try:
                q = module.predict(p1, p2, sf)
            except Exception:                                      # noqa: BLE001
                q = None
            vals.append(q["p1_prob"] if q else np.nan)
        out[tag] = np.array(vals, dtype=float)
    m = ~np.isnan(out["old"]) & ~np.isnan(out["new"])
    if not m.any():
        return None
    d = 100 * np.abs(out["new"][m] - out["old"][m])
    flips = int(((out["old"][m] >= 0.5) != (out["new"][m] >= 0.5)).sum())
    return "mean |change| %.2fpt, max %.2fpt, pick flips %d of %d" % (
        d.mean(), d.max(), flips, int(m.sum()))


# ------------------------------------------------------------------- MC2
say("=" * 70)
say("MC2: canonical builder, outputs redirected then swapped in atomically")
say("=" * 70)
try:
    import tennis_mc2 as M2
    old2 = None
    old2_n = 0
    if os.path.exists(MC2_STATE):
        with open(MC2_STATE, "rb") as f:
            old2 = pickle.load(f)
        old2_n = len(old2["players"])
        _a2 = age_days(MC2_STATE)
        say("current MC2 state: %d players, %.1f days old" % (old2_n, _a2))
        if _a2 > 3.0:
            # The silent-failure guard. If this job is being killed (OOM) or erroring every
            # night, nothing else announces it -- the site keeps serving the old state happily.
            # An outgoing state older than the schedule means previous runs did not land.
            say("WARNING: the state being replaced is %.1f days old. On a nightly schedule it "
                "should never exceed ~1. Check earlier runs in _nightly_ratings.log." % _a2)
    tmp_state = "data_cache/_mc2_state.rebuild.pkl"
    tmp_feat = "data_cache/_mc2_features.rebuild.parquet"
    src = open(SRC, encoding="utf-8").read()
    for lit, tmp in (('"%s"' % MC2_STATE, tmp_state), ('"%s"' % MC2_FEAT, tmp_feat)):
        assert src.count(lit) == 1, "expected exactly one %s in the builder" % lit
        src = src.replace(lit, '"%s"' % tmp)
    if DRY:
        say("dry run: builder transform verified, not executing")
    else:
        t0 = time.time()
        g = {"__name__": "__nightly_mc2__", "__file__": SRC}
        exec(compile(src, SRC + "(nightly)", "exec"), g)           # noqa: S102
        del g
        say("built in %.0fs" % (time.time() - t0))
        good, why = validate(M2, tmp_state, old2_n)
        say("validation: %s -- %s" % ("PASS" if good else "FAIL", why))
        if not good:
            for p in (tmp_state, tmp_feat):
                if os.path.exists(p):
                    os.remove(p)
            raise RuntimeError("MC2 validation failed, live state left alone: %s" % why)
        with open(tmp_state, "rb") as f:
            new2 = pickle.load(f)
        drift = board_drift(M2, old2, new2) if old2 else None
        if drift:
            say("board drift: %s" % drift)
        if os.path.exists(MC2_STATE):
            shutil.copy2(MC2_STATE, MC2_STATE + ".bak")
        os.replace(tmp_state, MC2_STATE)
        if os.path.exists(tmp_feat):
            if os.path.exists(MC2_FEAT):
                shutil.copy2(MC2_FEAT, MC2_FEAT + ".bak")
            os.replace(tmp_feat, MC2_FEAT)
        M2._S = None
        M2._MT = None
        say("MC2 state swapped in (previous kept as .bak)")
except Exception as e:                                             # noqa: BLE001
    FAILED.append("MC2: %s" % e)
    say("MC2 FAILED: %s" % e)
    traceback.print_exc()

# ------------------------------------------------------------------- MC3
say("=" * 70)
say("MC3: _mc3_build.py (already atomic, asserts MC2 untouched)")
say("=" * 70)
try:
    import tennis_mc3 as M3
    old3 = None
    old3_n = 0
    if os.path.exists(MC3_STATE):
        with open(MC3_STATE, "rb") as f:
            old3 = pickle.load(f)
        old3_n = len(old3["players"])
        say("current MC3 state: %d players, %.1f days old" % (old3_n, age_days(MC3_STATE)))
        shutil.copy2(MC3_STATE, MC3_STATE + ".bak")
    if DRY:
        say("dry run: skipping MC3 build")
    else:
        t0 = time.time()
        rc = os.system("%s _mc3_build.py" % sys.executable)         # noqa: S605
        if rc != 0:
            raise RuntimeError("_mc3_build.py exited %d" % rc)
        say("built in %.0fs" % (time.time() - t0))
        good, why = validate(M3, MC3_STATE, old3_n)
        say("validation: %s -- %s" % ("PASS" if good else "FAIL", why))
        if not good:
            if os.path.exists(MC3_STATE + ".bak"):
                shutil.copy2(MC3_STATE + ".bak", MC3_STATE)
                say("MC3 rolled back to .bak")
            raise RuntimeError("MC3 validation failed: %s" % why)
        with open(MC3_STATE, "rb") as f:
            new3 = pickle.load(f)
        drift = board_drift(M3, old3, new3) if old3 else None
        if drift:
            say("board drift: %s" % drift)
        M3._S = None
        M3._MT = None
except Exception as e:                                             # noqa: BLE001
    FAILED.append("MC3: %s" % e)
    say("MC3 FAILED: %s" % e)
    traceback.print_exc()

# ------------------------------------------------------- MC3 history rescore
# Rebuilding MC3's features invalidates every recon row scored off the previous artifact.
# Model G taught this the hard way: its history silently moved because ~1,257 rows had been
# scored by a superseded model and nobody rescored them. So the recon refresh belongs in the
# same job that does the rebuild, not in a separate one that can drift out of step.
say("=" * 70)
say("MC3 history: rescoring recon rows against the freshly built features")
say("=" * 70)
try:
    if DRY:
        say("dry run: skipping the recon rescore")
    elif FAILED:
        say("skipped: a rebuild failed above, so the features are not trustworthy")
    else:
        rc = os.system("%s _mc3_history_recon.py --rescore" % sys.executable)   # noqa: S605
        if rc != 0:
            raise RuntimeError("_mc3_history_recon.py exited %d" % rc)
        say("recon rescored")
except Exception as e:                                             # noqa: BLE001
    # Not fatal to the run: the rating states are already in and serving. A stale history
    # display is worth reporting, not worth rolling a good rebuild back for.
    say("MC3 recon rescore FAILED (states are fine, history may be stale): %s" % e)
    FAILED.append("mc3_recon: %s" % e)

# ------------------------------------------------------------------ verdict
say("=" * 70)
if FAILED:
    print("RESULT: FAIL -- %s" % " | ".join(FAILED))
    raise SystemExit(1)
print("RESULT: OK -- MC2 and MC3 rating states rebuilt%s" % (" (dry run)" if DRY else ""))
