"""FILL MC3 ON RECENT DAYS THE ARCHIVE HAS NOT INGESTED YET (2026-10-13).

The history backfill reads MC3 off the pre-match feature table, so it can only price a match
the TennisRatio archive already holds. That archive lags -- 37-55% same-day -- which left recent
days thin: Oct 11 at 63% and Oct 12 at 30% against 83-94% for Oct 7-10.

But MC3 does not need the match itself to be in the archive. It needs the two PLAYERS' ratings
as they stood that morning, and those come from their EARLIER matches. So instead of waiting for
the ingest, this rebuilds the rating state with a DATE CUTOFF and prices the missing rows from
it:

    for each day D:  build a state from matches strictly BEFORE D  ->  predict D's missing rows

That is leak-free by construction, and strictly MORE correct than using the current state would
be. Using today's state on an Oct 12 match would read ratings that already contain Oct 12 and
Oct 13 results -- not that match's own outcome, but future information relative to it, which is
exactly the kind of contamination the recon contract exists to avoid.

Cheap because the builder now runs in about 12 seconds, so one state per day is a minute or two.

Only fills rows that are EMPTY. A genuine forward pick is never overwritten, and existing recon
values are left alone (the nightly --rescore owns those). Output is stamped mc3_recon=True.

Run: ./venv/bin/python _mc3_asof_fill.py [--apply] [--days N]
"""
import gc
import os
import shutil
import sys

import numpy as np
import pandas as pd

import _mc2_surface_sr_sweep as SW
import tennis_context as tc
import tennis_log
import tennis_mc3 as M3
from tennis_mc3 import MC3_KS, MC3_MOV_W

APPLY = "--apply" in sys.argv
NDAYS = 6
if "--days" in sys.argv:
    NDAYS = int(sys.argv[sys.argv.index("--days") + 1])
SRC = "_mc2_stage1b_serve_return.py"
TMP_STATE = "data_cache/_mc3_asof_state.pkl"
TMP_FEAT = "data_cache/_mc3_asof_feat.parquet"

LOG = tennis_log.LOG_PATH
log = pd.read_parquet(LOG)
log["_d"] = log["date"].astype(str).str[:10]
for c in ("mc3_p1", "mc3_recon"):
    if c not in log.columns:
        log[c] = np.nan
days = sorted(log["_d"].unique())[-NDAYS:]
print("targeting the last %d logged days: %s" % (NDAYS, ", ".join(days)))

need = log[log["_d"].isin(days) & log["p1_won"].notna() & log["mc3_p1"].isna()]
print("settled rows still missing MC3 on those days: %d" % len(need))
for d in days:
    tot = int((log["_d"] == d).sum())
    st = int(((log["_d"] == d) & log["p1_won"].notna()).sum())
    have = int(((log["_d"] == d) & log["mc3_p1"].notna()).sum())
    miss = int(((log["_d"] == d) & log["p1_won"].notna() & log["mc3_p1"].isna()).sum())
    print("   %s  rows %3d  settled %3d  have %3d  missing %3d" % (d, tot, st, have, miss))
if need.empty:
    print("RESULT: nothing to fill")
    raise SystemExit(0)


def build_asof(cutoff):
    """MC3's recipe, trained only on matches strictly before `cutoff`."""
    src = open(SRC, encoding="utf-8").read()
    src = SW.apply_surface_transform(src, int(MC3_KS))
    src = SW.apply_mov_transform(src, MC3_MOV_W)
    anchor = 'm = m.sort_values("date").reset_index(drop=True)'
    assert src.count(anchor) == 1, src.count(anchor)
    src = src.replace(anchor, anchor + (
        '\nm = m[m["date"] < pd.Timestamp(%r)].reset_index(drop=True)'
        '\nprint("AS-OF CUTOFF %%s: %%d training matches" %% (%r, len(m)), flush=True)'
        % (cutoff, cutoff)))
    src = src.replace('"data_cache/_mc2_features.parquet"', '"%s"' % TMP_FEAT)
    src = src.replace('"data_cache/_mc2_state.pkl"', '"%s"' % TMP_STATE)
    for bad in ('to_parquet("data_cache/_mc2_features.parquet")',
                'open("data_cache/_mc2_state.pkl"',
                'open("data_cache/_mc3_state.pkl"'):
        assert bad not in src, "would overwrite a live artifact: %s" % bad
    g = {"__name__": "__mc3_asof__", "__file__": SRC}
    exec(compile(src, SRC + "(asof=%s)" % cutoff, "exec"), g)      # noqa: S102
    del g
    gc.collect()


vals, per_day = {}, {}
for d in days:
    sub = need[need["_d"] == d]
    if sub.empty:
        continue
    print("\n--- %s: %d row(s) to price ---" % (d, len(sub)))
    sys.stdout.flush()
    build_asof(d)
    # point the runtime at the as-of state, pinning _MT so _state() cannot reload over it
    import pickle
    with open(TMP_STATE, "rb") as f:
        M3._S = pickle.load(f)
    M3._MT = os.path.getmtime(TMP_STATE)
    got = 0
    for i, r in sub.iterrows():
        try:
            q = M3.predict(r["player_1"], r["player_2"], r.get("surface"),
                           best_of_5=bool(r.get("best_of_5")))
        except Exception:                                          # noqa: BLE001
            q = None
        if q and q.get("p1_prob") is not None:
            vals[i] = round(float(q["p1_prob"]), 4)
            got += 1
    per_day[d] = (got, len(sub))
    print("    priced %d of %d" % (got, len(sub)))
    M3._S = None
    M3._MT = None

for p in (TMP_STATE, TMP_FEAT):
    if os.path.exists(p):
        os.remove(p)

print("\n" + "=" * 70)
print("FILL RESULT")
print("=" * 70)
for d in days:
    g, n = per_day.get(d, (0, 0))
    if n:
        print("   %s  %d of %d  (%.0f%%)" % (d, g, n, 100 * g / n))
print("   total %d of %d" % (len(vals), len(need)))
if not vals:
    print("RESULT: nothing priced -- the missing players are not in the archive at all")
    raise SystemExit(0)

idxs = list(vals)
pv = np.array([vals[i] for i in idxs])
wn = log.loc[idxs, "p1_won"].astype(bool).to_numpy()
print("\n   sanity (DISPLAY-ONLY, not a forward record): picks the winner %.1f%% of %d"
      % (100 * ((pv >= 0.5) == wn).mean(), len(idxs)))

if not APPLY:
    print("\nDRY RUN -- log not written. Re-run with --apply.")
    raise SystemExit(0)

bak = LOG + ".bak_mc3asof"
shutil.copy2(LOG, bak)
log.loc[idxs, "mc3_p1"] = pv
log.loc[idxs, "mc3_recon"] = True
log.drop(columns=["_d"]).to_parquet(LOG, index=False)
chk = pd.read_parquet(LOG)
print("\nwrote %d values (backup %s)" % (len(idxs), os.path.basename(bak)))
print("verify: mc3_p1 non-null %d, recon %d"
      % (int(chk["mc3_p1"].notna().sum()),
         int(chk["mc3_recon"].fillna(False).astype(bool).sum())))
print("RESULT: OK")
