"""MC v3 HISTORY RECON (2026-10-13): walk-forward backfill of mc3_p1 onto settled log rows.

HONESTY CONTRACT, and it differs from MC2's version in one way that matters:

  * Every value comes from `_mc3_features.parquet`'s PRE-MATCH columns (p_elo, pa_pt/pb_pt,
    nS_a/nS_b). That table is produced by one chronological pass that folds a match's result in
    only AFTER emitting its feature row, so a row knows nothing about its own match or anything
    after it.
  * There is NO fallback to tennis_mc3.predict(). MC2's recon script used its live state for
    rows after the state's cutoff, which was sound because MC2's state ENDED at that cutoff.
    MC3's state is rebuilt nightly and is therefore CURRENT -- using it on a settled match would
    read ratings that already contain that match's result. So rows the feature table cannot
    cover are simply left empty rather than filled with a leaky number.
  * The result column is never read, except once at the end to print a sanity hit rate that is
    explicitly labelled as display-only.
  * Output is stamped mc3_recon=True, so it renders dimmed with a leading "~" and is EXCLUDED
    from every mc3_* forward lane -- same contract as mc2_recon / model_g_recon.

Best-of-five is taken from the log's own best_of_5 column rather than guessed from the score.

--rescore recomputes rows that already carry a recon value. Needed because the nightly job
rebuilds MC3's features, and a recon row scored off an older artifact is stale -- the same trap
that silently moved Model G's history until it was rescored.

Run: ./venv/bin/python _mc3_history_recon.py [--rescore] [--dry-run]
"""
import math
import os
import shutil
import sys

import numpy as np
import pandas as pd

import tennis_context as tc
import tennis_log
import tennis_mc3 as m3
from tennis_mc2 import _NODES, _rnd

RESCORE = "--rescore" in sys.argv
DRY = "--dry-run" in sys.argv
FEAT = "data_cache/_mc3_features.parquet"
if not os.path.exists(FEAT):
    raise SystemExit("missing %s -- run _mc3_build.py" % FEAT)

LOG = tennis_log.LOG_PATH
log = pd.read_parquet(LOG)
log["_d"] = log["date"].astype(str).str[:10]
for c in ("mc3_p1", "mc3_recon"):
    if c not in log.columns:
        log[c] = np.nan
is_recon = log["mc3_recon"].fillna(False).astype(bool)
has_val = log["mc3_p1"].notna()
settled = log["p1_won"].notna()
# never touch a FORWARD row: a real pre-match pick outranks any reconstruction
target = settled & (~has_val | (is_recon if RESCORE else False))
target = target & ~(has_val & ~is_recon)
print("log rows %d | settled %d | already forward-priced %d | recon now %d"
      % (len(log), int(settled.sum()), int((has_val & ~is_recon).sum()), int(is_recon.sum())))
print("rows to fill%s: %d" % (" (incl. rescore)" if RESCORE else "", int(target.sum())))

F = pd.read_parquet(FEAT, columns=["date", "a", "b", "p_elo", "pa_pt", "pb_pt",
                                   "nS_a", "nS_b"])
F["dd"] = F["date"].astype(str).str[:10]
idx = {}
for r in F.itertuples():
    idx.setdefault((r.a, r.b, r.dd), r)
print("feature rows indexed: %d  (%s .. %s)" % (len(F), F["dd"].min(), F["dd"].max()))

_slug_memo = {}


def slug(name, surf):
    k = (str(name), str(surf))
    if k not in _slug_memo:
        try:
            g = tc.get_context(name, surf)
        except Exception:                                          # noqa: BLE001
            g = None
        _slug_memo[k] = g["slug"] if g else None
    return _slug_memo[k]


def lg(p):
    p = max(min(float(p), 1 - 1e-6), 1e-6)
    return math.log(p / (1 - p))


def score(sa, sb, day, bo5):
    """MC3's live math off the pre-match feature row. +/-1 day, as fixture dates drift."""
    if not sa or not sb:
        return None, "unresolved"
    for d2 in (day,
               (pd.Timestamp(day) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
               (pd.Timestamp(day) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")):
        r = idx.get((sa, sb, d2))
        flip = False
        if r is None:
            r = idx.get((sb, sa, d2))
            flip = True
        if r is None:
            continue
        if (r.nS_a < 4 or r.nS_b < 4 or pd.isna(r.p_elo)
                or pd.isna(r.pa_pt) or pd.isna(r.pb_pt)):
            return None, "unrated"
        pa, pb = float(r.pa_pt), float(r.pb_pt)
        sga = 0.10 / max(float(r.nS_a), 4.0) ** 0.5
        sgb = 0.10 / max(float(r.nS_b), 4.0) ** 0.5
        pm = 0.0
        for xi, wi in _NODES:
            for xj, wj in _NODES:
                pm += wi * wj * m3.p_match(_rnd(pa + xi * sga), _rnd(pb + xj * sgb), bo5)
        p = 1 / (1 + math.exp(-(0.5 * lg(r.p_elo) + 0.5 * lg(pm))))
        return (round(1 - p, 4) if flip else round(p, 4)), "ok"
    return None, "no feature row"


vals, why = {}, {"ok": 0, "unresolved": 0, "unrated": 0, "no feature row": 0}
tgt = log[target]
for i, r in tgt.iterrows():
    v, reason = score(slug(r["player_1"], r.get("surface")),
                      slug(r["player_2"], r.get("surface")),
                      r["_d"], bool(r.get("best_of_5")))
    why[reason] = why.get(reason, 0) + 1
    if v is not None:
        vals[i] = v
print("\nfill outcome: %s" % ", ".join("%s %d" % (k, v) for k, v in why.items() if v))
print("filled %d of %d (%.0f%%)"
      % (len(vals), len(tgt), 100 * len(vals) / max(len(tgt), 1)))

if not vals:
    print("RESULT: nothing to write")
    raise SystemExit(0)

# sanity, display-only: this is NOT a forward record
idxs = list(vals)
pv = np.array([vals[i] for i in idxs])
wn = log.loc[idxs, "p1_won"].astype(bool).to_numpy()
print("\nsanity (DISPLAY-ONLY, not a forward record): recon picks the winner %.1f%% of %d"
      % (100 * ((pv >= 0.5) == wn).mean(), len(idxs)))
if "mc2_p1" in log.columns:
    m2v = pd.to_numeric(log.loc[idxs, "mc2_p1"], errors="coerce").to_numpy(dtype=float)
    ok = ~np.isnan(m2v)
    if ok.sum():
        agree = ((pv[ok] >= 0.5) == (m2v[ok] >= 0.5)).mean()
        print("   agrees with MC2's value on the same rows: %.0f%% of %d"
              % (100 * agree, int(ok.sum())))

if DRY:
    print("RESULT: dry run, log not written")
    raise SystemExit(0)

bak = LOG + ".bak_mc3recon"
shutil.copy2(LOG, bak)
log.loc[idxs, "mc3_p1"] = pv
log.loc[idxs, "mc3_recon"] = True
log.drop(columns=["_d"]).to_parquet(LOG, index=False)
print("\nwrote %d recon values (backup at %s)" % (len(idxs), os.path.basename(bak)))
chk = pd.read_parquet(LOG)
print("verify: mc3_p1 non-null %d, of which recon %d"
      % (int(chk["mc3_p1"].notna().sum()),
         int(chk["mc3_recon"].fillna(False).astype(bool).sum())))
print("RESULT: OK")
