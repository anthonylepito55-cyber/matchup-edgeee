"""REBUILD THE MC2 RECON WITH CORRECTED SURFACES (2026-10-14).

User: "wasnt the surface stats wrong till a few days ago / so wouldnt that have messed up the
recon" -- and the answer was yes, enough to matter:

    recon window    918 rows, 119 flagged surface_bad  (13.0%)
    forward window  691 rows,   4 flagged surface_bad  ( 0.6%)
    the wrong-court fix landed 2026-10-09; the recon window is 2026-09-06..10-08
    MC2's probability moves a median 2.1pt across surfaces (p90 4.0pt, max 4.6pt), which is
    large next to a 4pt or 6pt threshold -- a wrong surface can move a card across the boundary
    and change which bets a rule even contains

So every recon-based conclusion in this session rests on numbers that may have been computed with
the wrong court. This recomputes them.

HOW. For each date holding recon rows, MC2's rating state is rebuilt from the canonical builder
with a HARD DATE CUTOFF (training on matches strictly before that date), then each row is
re-priced with the surface the log holds TODAY, i.e. post-correction. That is the same as-of
discipline `_mc5_asof_fill.py` uses, and the only correct one: using today's state would hand a
September card ratings that already contain October.

SAFETY
  * writes to its OWN parquet (_mc2_recon2.parquet), never to the log. The stored mc2_p1 /
    mc2_recon values are left untouched so the old and new can be compared.
  * asserts it cannot overwrite a live artifact before exec'ing the builder.
  * temp state/feature files are removed as it goes, and the state is unpinned between dates.

Run: ./venv/bin/python _mc2_recon_rebuild.py [--days N]
"""
import gc
import os
import pickle
import sys

import numpy as np
import pandas as pd

import tennis_log
import tennis_mc2 as M2

SRC = "_mc2_stage1b_serve_return.py"
TMP_STATE = "data_cache/_mc2_recon2_state.pkl"
TMP_FEAT = "data_cache/_mc2_recon2_feat.parquet"
OUT = "data_cache/_mc2_recon2.parquet"

log = pd.read_parquet(tennis_log.LOG_PATH)
log["_d"] = log["date"].astype(str).str[:10]
RC = (log["mc2_recon"].fillna(False).astype(bool).to_numpy()
      if "mc2_recon" in log.columns else np.zeros(len(log), bool))
todo = log[RC & log["mc2_p1"].notna()].copy()
days = sorted(todo["_d"].unique())
if "--days" in sys.argv:
    days = days[-int(sys.argv[sys.argv.index("--days") + 1]):]
print("recon rows to re-price: %d across %d dates (%s .. %s)"
      % (len(todo), len(days), days[0], days[-1]), flush=True)


def build_asof(cutoff):
    """MC2's canonical recipe, trained only on matches strictly before `cutoff`."""
    src = open(SRC, encoding="utf-8").read()
    old = 'm = m.sort_values("date").reset_index(drop=True)'
    assert src.count(old) == 1
    src = src.replace(old, old + (
        '\nm = m[m["date"] < pd.Timestamp(%r)].reset_index(drop=True)'
        '\nprint("  as-of %%s: %%d training matches" %% (%r, len(m)), flush=True)'
        % (cutoff, cutoff)))
    src = src.replace('"data_cache/_mc2_features.parquet"', '"%s"' % TMP_FEAT)
    src = src.replace('"data_cache/_mc2_state.pkl"', '"%s"' % TMP_STATE)
    for bad in ('to_parquet("data_cache/_mc2_features.parquet")',
                'open("data_cache/_mc2_state.pkl"', 'open("data_cache/_mc3_state.pkl"',
                'open("data_cache/_mc5_state.pkl"'):
        assert bad not in src, "would overwrite a live artifact: %s" % bad
    g = {"__name__": "__mc2_recon2__", "__file__": SRC}
    exec(compile(src, SRC + "(asof=%s)" % cutoff, "exec"), g)   # noqa: S102
    del g
    gc.collect()


rows = []
for i, d in enumerate(days, 1):
    sub = todo[todo["_d"] == d]
    if sub.empty:
        continue
    print("\n--- [%d/%d] %s: %d row(s) ---" % (i, len(days), d, len(sub)), flush=True)
    try:
        build_asof(d)
        with open(TMP_STATE, "rb") as f:
            M2._S = pickle.load(f)
        M2._MT = os.path.getmtime(TMP_STATE)     # pin, or _state() reloads over the injection
    except Exception as e:                                        # noqa: BLE001
        print("    BUILD FAILED (%s) -- skipping this date" % type(e).__name__, flush=True)
        continue
    got = 0
    for idx, r in sub.iterrows():
        try:
            q = M2.predict(r["player_1"], r["player_2"], r.get("surface"),
                           best_of_5=bool(r.get("best_of_5")))
        except Exception:                                          # noqa: BLE001
            q = None
        rows.append({"i": idx, "date": d, "p1": r["player_1"], "p2": r["player_2"],
                     "surface": r.get("surface"), "league": r.get("league"),
                     "p1_odds": r.get("p1_odds"), "p2_odds": r.get("p2_odds"),
                     "p1_won": r.get("p1_won"), "surface_bad": r.get("surface_bad"),
                     "old": float(r["mc2_p1"]),
                     "new": (round(float(q["p1_prob"]), 4) if q and q.get("p1_prob") is not None
                             else None)})
        got += q is not None and q.get("p1_prob") is not None
    print("    re-priced %d of %d" % (got, len(sub)), flush=True)
    M2._S = None
    M2._MT = None
    for p in (TMP_STATE, TMP_FEAT):
        if os.path.exists(p):
            os.remove(p)
    gc.collect()

out = pd.DataFrame(rows)
out.to_parquet(OUT, index=False)
ok = out[out["new"].notna()]
print("\n" + "=" * 96)
print("WROTE %s -- %d rows, %d re-priced" % (OUT, len(out), len(ok)))
print("=" * 96)
if len(ok):
    d = (ok["new"] - ok["old"]).abs() * 100
    print("   |new - old| in MC2's p1 probability:")
    print("      median %.2fpt   p75 %.2fpt   p90 %.2fpt   max %.2fpt"
          % (d.median(), d.quantile(.75), d.quantile(.90), d.max()))
    print("      share moving >1pt %.0f%%   >2pt %.0f%%   >4pt %.0f%%"
          % (100 * (d > 1).mean(), 100 * (d > 2).mean(), 100 * (d > 4).mean()))
    sb = ok["surface_bad"].fillna(False).astype(bool)
    if sb.any():
        print("   on rows FLAGGED surface_bad (n=%d): median %.2fpt" % (int(sb.sum()), d[sb].median()))
    print("   on rows NOT flagged        (n=%d): median %.2fpt" % (int((~sb).sum()), d[~sb].median()))
print("\nRESULT: OK -- run _mc2_recon2_compare.py to re-test the rules")
