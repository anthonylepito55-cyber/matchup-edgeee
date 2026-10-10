"""SECOND PASS for the wrong-court fix (2026-10-09). _surface_history_audit.py only checked
rows dated before 2026-10-08, so ten flagged rows from 10-08/10-09 -- the Villena and Samsun
matches, the Stefanini one among them -- had no audited true court and _surface_fix_history.py
skipped them. This resolves those against TennisExplorer the same way (schedule for their own
date; falling back to the court the audit already verified for that same tournament) and appends
their two-court replay to data_cache/_surface_fix_history.parquet.

Run AFTER _surface_fix_history.py: it appends to that file.
"""
from datetime import datetime, timezone

import pandas as pd

import tennis_surface_check as S
import tennis_surface_replay as R

LOG = "data_cache/tennis_prediction_log.parquet"
AUD = "data_cache/_surface_history_audit.csv"
OUT = "data_cache/_surface_fix_history.parquet"
COLS = ["model_a_p1", "model_ama_p1", "model_b_p1", "model_bma_p1", "model_c_p1", "model_cma_p1",
        "model_d_p1", "model_dma_p1", "mc_p1", "mc_c_p1", "mc_c75_p1", "mc_cutr_p1",
        "c_rp_diff_p1", "c_sp_diff_p1", "model_p_dog", "model_p_prob", "model_p_ev", "model_p_fev"]

L = pd.read_parquet(LOG)
F = pd.read_parquet(OUT)
A = pd.read_csv(AUD, dtype=str)
# courts the historical audit already verified, per tournament -- our fallback when the
# schedule page for a very recent date no longer lists the match
by_tourn = {}
for t, g in A.groupby(A.tournament.astype(str)):
    v = g["true"].value_counts()
    by_tourn[t] = v.index[0]

B = L[L["surface_bad"] == True].copy()  # noqa: E712
todo = B[~B.fixture_id.astype(str).isin(F.fixture_id.astype(str))].copy()
todo["d"] = todo.date.astype(str).str[:10]
print(f"rows still unfixed: {len(todo)}", flush=True)

rows = []
for d, g in todo.groupby("d"):
    try:
        S.refresh(days=(0, 1, -1), base=datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc, hour=12))
    except Exception as e:  # noqa: BLE001
        print(f"  {d}: TE refresh failed ({e}) -- falling back to the audited court", flush=True)
    for _, r in g.iterrows():
        true_s, src = None, ""
        try:
            true_s, src = S.resolve(r.player_1, r.player_2, r.get("tournament"))
        except Exception:  # noqa: BLE001
            pass
        if not true_s:
            true_s = by_tourn.get(str(r.get("tournament")))
            src = "audited court for this tournament"
        if not true_s:
            print(f"  SKIP {d} {r.player_1} vs {r.player_2}: court still unresolved", flush=True)
            continue
        if str(true_s).title() == str(r.surface).title():
            print(f"  {d} {r.player_1} vs {r.player_2}: logged court matches TE after all "
                  f"({true_s}) -- nothing to fix", flush=True)
            continue
        kw = dict(league=r.get("league"), best_of_5=bool(r.get("best_of_5")),
                  p1_odds=r.get("p1_odds"), p2_odds=r.get("p2_odds"))
        w = R.recompute(d, r.player_1, r.player_2, r.surface, **kw)
        f = R.recompute(d, r.player_1, r.player_2, true_s, **kw)
        rec = {c: r.get(c) for c in L.columns}
        rec.update({"surface_logged": r.surface, "surface_true": str(true_s).title(),
                    "surface_src": src})
        rec.update({f"w_{c}": w.get(c) for c in COLS})
        rec.update({f"f_{c}": f.get(c) for c in COLS})
        rows.append(rec)
        print(f"  fixed {d} {r.player_1} vs {r.player_2}: {r.surface} -> {true_s} ({src})", flush=True)
R.release()
if rows:
    D = pd.concat([F, pd.DataFrame(rows)], ignore_index=True)
    D = D.drop_duplicates(["fixture_id"], keep="last")
    D.to_parquet(OUT, index=False)
    print(f"\nappended {len(rows)} rows -> {OUT} now holds {len(D)}", flush=True)
else:
    print("\nnothing appended", flush=True)
