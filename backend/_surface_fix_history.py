"""FIX THE WRONG-COURT DAYS (2026-10-09, user: "fix the wrongs for previous days so i can see
what i would have chosen if it was the correct court and put who u told me to take that day").

For every logged row flagged surface_bad=True (150: the 140 historical mismatches from
_surface_history_audit.py plus a handful from 10-08/09), recompute the whole card twice with
tennis_surface_replay -- once on the court we HAD on the card, once on the court the match was
actually played on -- using only archive matches from before that match's date.

Writes data_cache/_surface_fix_history.parquet, one row per fixture:
    surface_logged / surface_true / surface_src
    w_*   models recomputed on the WRONG (logged) court   -- the reconstruction
    f_*   models recomputed on the TRUE court             -- "what you would have chosen"
plus every frozen column from the log, so the serving code can show the ORIGINAL pick
("who I told you to take") beside the corrected one.

Only 43 of the 150 rows have frozen model columns at all -- the rest were logged in September
before those columns existed, so for them no pick was ever frozen and the w_* reconstruction is
the only picture of what the wrong court produced. The validation block below reports how closely
w_* reproduces the frozen numbers on the 43 rows that have both, which is the check on whether
the replay can be trusted.
"""
import sys
import time

import numpy as np
import pandas as pd

import tennis_surface_replay as R

LOG = "data_cache/tennis_prediction_log.parquet"
AUD = "data_cache/_surface_history_audit.csv"
OUT = "data_cache/_surface_fix_history.parquet"

COLS = ["model_a_p1", "model_ama_p1", "model_b_p1", "model_bma_p1", "model_c_p1", "model_cma_p1",
        "model_d_p1", "model_dma_p1", "mc_p1", "mc_c_p1", "mc_c75_p1", "mc_cutr_p1",
        "c_rp_diff_p1", "c_sp_diff_p1", "model_p_dog", "model_p_prob", "model_p_ev", "model_p_fev"]

L = pd.read_parquet(LOG)
B = L[L["surface_bad"] == True].copy()  # noqa: E712
A = pd.read_csv(AUD, dtype=str)
true_by_fx = dict(zip(A.fixture_id.astype(str), A.true))
src_by_fx = dict(zip(A.fixture_id.astype(str), A.src))
B["surface_true"] = B.fixture_id.astype(str).map(true_by_fx)
B["surface_src"] = B.fixture_id.astype(str).map(src_by_fx)
unresolved = B[B.surface_true.isna()]
B = B[B.surface_true.notna()].copy()
B["d"] = B.date.astype(str).str[:10]
print(f"rows to fix: {len(B)} over {B.d.nunique()} dates "
      f"({len(unresolved)} flagged rows have no audited true court -- left alone)", flush=True)

rows, t0 = [], time.time()
for d, g in B.groupby("d"):
    t1 = time.time()
    for _, r in g.iterrows():
        kw = dict(league=r.get("league"), best_of_5=bool(r.get("best_of_5")),
                  p1_odds=r.get("p1_odds"), p2_odds=r.get("p2_odds"))
        w = R.recompute(d, r.player_1, r.player_2, r.surface, **kw)
        f = R.recompute(d, r.player_1, r.player_2, r.surface_true, **kw)
        rec = {c: r.get(c) for c in L.columns}
        rec.update({"surface_logged": r.surface, "surface_true": r.surface_true,
                    "surface_src": r.surface_src})
        rec.update({f"w_{c}": w.get(c) for c in COLS})
        rec.update({f"f_{c}": f.get(c) for c in COLS})
        rows.append(rec)
    print(f"  {d}: {len(g)} rows in {time.time() - t1:.0f}s "
          f"(elapsed {(time.time() - t0) / 60:.1f}m)", flush=True)
R.release()
D = pd.DataFrame(rows)
D.to_parquet(OUT, index=False)
print(f"\nwrote {OUT}: {len(D)} rows", flush=True)

# ---- VALIDATION: does the logged-court replay reproduce the frozen numbers? ----------------
print("\n=== REPLAY TRUST CHECK (logged-court replay vs the frozen column) ===")
for c in ("model_a_p1", "model_b_p1", "model_c_p1", "model_d_p1", "mc_c75_p1"):
    ok = D[D[c].notna() & D[f"w_{c}"].notna()]
    if not len(ok):
        print(f"  {c:14s} no overlap")
        continue
    diff = (ok[f"w_{c}"].astype(float) - ok[c].astype(float)).abs()
    same_side = ((ok[f"w_{c}"].astype(float) >= .5) == (ok[c].astype(float) >= .5)).mean()
    print(f"  {c:14s} n={len(ok):3d} | mean abs diff {diff.mean() * 100:4.1f}pt | "
          f"median {diff.median() * 100:4.1f}pt | same side {100 * same_side:5.1f}%")

# ---- WHAT THE COURT CHANGED ----------------------------------------------------------------
print("\n=== WHAT THE CORRECT COURT CHANGES (wrong-court replay -> right-court replay) ===")
for c in ("model_c_p1", "model_d_p1", "mc_c75_p1", "model_cma_p1"):
    ok = D[D[f"w_{c}"].notna() & D[f"f_{c}"].notna()]
    if not len(ok):
        continue
    sw = (ok[f"f_{c}"].astype(float) - ok[f"w_{c}"].astype(float))
    flip = ((ok[f"f_{c}"].astype(float) >= .5) != (ok[f"w_{c}"].astype(float) >= .5))
    print(f"  {c:14s} n={len(ok):3d} | mean |move| {sw.abs().mean() * 100:4.1f}pt | "
          f"max {sw.abs().max() * 100:4.1f}pt | SIDE FLIPS {int(flip.sum())} ({100 * flip.mean():.0f}%)")

pw = D[D.w_model_p_ev.notna()]
pf = D[D.f_model_p_ev.notna()]
print(f"\n  Model P fired on the wrong court: {len(pw)} rows | on the right court: {len(pf)} rows")
both = D[D.w_model_p_ev.notna() & D.f_model_p_ev.notna()]
if len(both):
    print(f"  both: EV moved {((both.f_model_p_ev - both.w_model_p_ev) * 100).abs().mean():.1f}pt "
          f"on average, max {((both.f_model_p_ev - both.w_model_p_ev) * 100).abs().max():.1f}pt")
sys.stdout.flush()
