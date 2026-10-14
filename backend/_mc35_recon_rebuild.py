"""REBUILD THE MC3 AND MC5 RECON WITH AS-OF STATES (2026-10-14).

User: "yes run it".

MC2's recon was rebuilt today and the result changed verdicts -- the old values had been priced
with a STALE state rather than an as-of one ([[project_recon_was_state_contaminated]]). MC3's and
MC5's recon were never rebuilt, so they are still contaminated the same way, which is why neither
head could be tested: their FROZEN samples are only 92 and 31 settled rows.

HOW. For each date holding recon rows, the head's rating state is rebuilt from the canonical
builder with a HARD DATE CUTOFF (training strictly before that date), then that date's rows are
re-priced. Using today's state would hand a September card ratings that already contain October.

The per-head recipes are copied verbatim from _mc3_asof_fill.py and _mc5_asof_fill.py, including
their asserts: if either recipe changes upstream, the anchor assertions fail loudly rather than
silently building a different model.

SAFETY
  * writes to its OWN parquet (_mc3_recon2 / _mc5_recon2), NEVER to the log. The stored mc3_p1 /
    mc5_p1 are left untouched so old and new can be compared.
  * asserts it cannot overwrite a live artifact before exec'ing the builder.
  * temp state/feature files are removed per date and the injected state is unpinned.

Run: ./venv/bin/python _mc35_recon_rebuild.py --head mc3 [--days N]
     ./venv/bin/python _mc35_recon_rebuild.py --head mc5 [--days N]
"""
import gc
import os
import pickle
import sys

import numpy as np
import pandas as pd

import _mc2_surface_sr_sweep as SW
import tennis_log

SRC = "_mc2_stage1b_serve_return.py"
HEAD = sys.argv[sys.argv.index("--head") + 1] if "--head" in sys.argv else "mc3"
assert HEAD in ("mc3", "mc5"), HEAD

if HEAD == "mc3":
    import tennis_mc3 as M
    from tennis_mc3 import MC3_KS as KS, MC3_MOV_W as MOVW
else:
    import tennis_mc5 as M
    from tennis_mc5 import MC5_KS as KS, MC5_MOV_W as MOVW

assert hasattr(M, "_S") and hasattr(M, "_MT"), "head module has no injectable state"
TMP_STATE = "data_cache/_%s_recon2_state.pkl" % HEAD
TMP_FEAT = "data_cache/_%s_recon2_feat.parquet" % HEAD
OUT = "data_cache/_%s_recon2.parquet" % HEAD

log = pd.read_parquet(tennis_log.LOG_PATH)
log["_d"] = log["date"].astype(str).str[:10]
RCOL, PCOL = HEAD + "_recon", HEAD + "_p1"
RC = (log[RCOL].fillna(False).astype(bool).to_numpy()
      if RCOL in log.columns else np.zeros(len(log), bool))
todo = log[RC & log[PCOL].notna()].copy()
days = sorted(todo["_d"].unique())
if "--days" in sys.argv:
    days = days[-int(sys.argv[sys.argv.index("--days") + 1]):]
print("%s recon rows to re-price: %d across %d dates (%s .. %s)"
      % (HEAD.upper(), len(todo), len(days), days[0], days[-1]), flush=True)


def build_asof(cutoff):
    """The head's exact recipe, trained only on matches strictly before `cutoff`."""
    src = open(SRC, encoding="utf-8").read()
    src = SW.apply_surface_transform(src, int(KS))
    src = SW.apply_mov_transform(src, MOVW)

    if HEAD == "mc5":
        # --- verbatim from _mc5_asof_fill.py: six-field history, cap 40, season tally ---
        old = "    # ---- updates ----"
        assert src.count(old) == 1
        src = src.replace(old, """    _h5won = float(won)
    _h5srv = float(spw_a - (bs + Sa - Rb)) if not np.isnan(spw_a) else 0.0
""" + old)
        old = 'st9["hist"].append((t.date, _ns9, _rt9))'
        assert src.count(old) == 1
        src = src.replace(old, 'st9["hist"].append((t.date, _ns9, _rt9, _h5won, _h5srv, s))')
        old = '''        if len(st9["hist"]) > 12:
            st9["hist"] = st9["hist"][-12:]'''
        assert src.count(old) == 1
        src = src.replace(old, '''        if len(st9["hist"]) > 40:
            st9["hist"] = st9["hist"][-40:]''')
        old = '              "pw": 0.0, "pa": 0.0,'
        assert src.count(old) == 1
        src = src.replace(old, old + '\n              "seas": {},')
        old = '    a["n"] += 1; b["n"] += 1; a["ns"][s] += 1; b["ns"][s] += 1'
        assert src.count(old) == 1
        src = src.replace(old, old + """
    _yk = (int(t.date.year), s)
    for _st9, _w9 in ((a, won), (b, 1.0 - won)):
        _t9 = _st9["seas"].setdefault(_yk, [0.0, 0])
        _t9[0] += float(_w9)
        _t9[1] += 1""")

    anchor = 'm = m.sort_values("date").reset_index(drop=True)'
    assert src.count(anchor) == 1
    src = src.replace(anchor, anchor + (
        '\nm = m[m["date"] < pd.Timestamp(%r)].reset_index(drop=True)'
        '\nprint("  as-of %%s: %%d training matches" %% (%r, len(m)), flush=True)'
        % (cutoff, cutoff)))
    src = src.replace('"data_cache/_mc2_features.parquet"', '"%s"' % TMP_FEAT)
    src = src.replace('"data_cache/_mc2_state.pkl"', '"%s"' % TMP_STATE)
    for bad in ('to_parquet("data_cache/_mc2_features.parquet")',
                'open("data_cache/_mc2_state.pkl"', 'open("data_cache/_mc3_state.pkl"',
                'open("data_cache/_mc5_state.pkl"'):
        assert bad not in src, "would overwrite a live artifact: %s" % bad
    g = {"__name__": "__%s_recon2__" % HEAD, "__file__": SRC}
    exec(compile(src, SRC + "(asof=%s)" % cutoff, "exec"), g)      # noqa: S102
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
            M._S = pickle.load(f)
        M._MT = os.path.getmtime(TMP_STATE)   # pin, or _state() reloads over the injection
    except Exception as e:                                         # noqa: BLE001
        print("    BUILD FAILED (%s: %s) -- skipping this date"
              % (type(e).__name__, str(e)[:120]), flush=True)
        continue
    got = 0
    for idx, r in sub.iterrows():
        try:
            q = M.predict(r["player_1"], r["player_2"], r.get("surface"),
                          best_of_5=bool(r.get("best_of_5")))
        except Exception:                                          # noqa: BLE001
            q = None
        rows.append({"i": idx, "date": d, "league": r.get("league"),
                     "p1_odds": r.get("p1_odds"), "p2_odds": r.get("p2_odds"),
                     "p1_won": r.get("p1_won"),
                     "old": float(r[PCOL]),
                     "new": (round(float(q["p1_prob"]), 4)
                             if q and q.get("p1_prob") is not None else None)})
        got += q is not None and q.get("p1_prob") is not None
    print("    re-priced %d of %d" % (got, len(sub)), flush=True)
    M._S = None
    M._MT = None
    for p in (TMP_STATE, TMP_FEAT):
        if os.path.exists(p):
            os.remove(p)
    gc.collect()

out = pd.DataFrame(rows)
out.to_parquet(OUT, index=False)
ok = out[out["new"].notna()] if len(out) else out
print("\n" + "=" * 96)
print("WROTE %s -- %d rows, %d re-priced" % (OUT, len(out), len(ok)))
print("=" * 96)
if len(ok):
    dd = (ok["new"] - ok["old"]).abs() * 100
    print("   |new - old| in %s's p1 probability:" % HEAD.upper())
    print("      median %.2fpt   p75 %.2fpt   p90 %.2fpt   max %.2fpt"
          % (dd.median(), dd.quantile(.75), dd.quantile(.90), dd.max()))
    print("      share moving >1pt %.0f%%   >2pt %.0f%%   >4pt %.0f%%"
          % (100 * (dd > 1).mean(), 100 * (dd > 2).mean(), 100 * (dd > 4).mean()))
print("\nRESULT: OK")
