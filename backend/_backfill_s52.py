"""BACKFILL THE FROZEN SEASONAL HOLD/BREAK COLUMNS (2026-10-11).

The two 🔵 s52 band lanes read four frozen columns that only exist for rows logged from today
forward. Without a backfill the lanes would start at n=0, the blue mark's live gate would never
pass, and nothing would appear on the board -- even though the cell was measured on exactly
these rows.

So this writes s52_sgw_p1/p2 and s52_rgw_p1/p2 for every existing row using
`tennis_context.context_asof`, i.e. ONLY matches strictly before that row's date. That is the
same function the measurement used, so the lane's record reproduces it rather than re-deriving
it from today's profiles (which would be hindsight).

Idempotent: rows that already carry all four values are skipped.
"""
import pandas as pd

import tennis_context as TC

PATH = "data_cache/tennis_prediction_log.parquet"
COLS = ("s52_sgw_p1", "s52_rgw_p1", "s52_sgw_p2", "s52_rgw_p2")

d = pd.read_parquet(PATH)
for c in COLS:
    if c not in d.columns:
        d[c] = None
d["_dt"] = pd.to_datetime(d["date"], errors="coerce")
print(f"log rows: {len(d)}")

cache = {}


def s52(nm, surf, asof):
    k = (str(nm), str(surf), str(asof)[:10])
    if k not in cache:
        sgw = rgw = None
        try:
            st = (TC.context_asof(nm, surf, asof) or {}).get("surface_stats") or {}
            sgw, rgw = st.get("sgw"), st.get("rgw")
        except Exception:
            pass
        cache[k] = (None if sgw is None else float(sgw),
                    None if rgw is None else float(rgw))
    return cache[k]


done = skipped = filled = 0
for i, r in d.iterrows():
    if all(pd.notna(r.get(c)) for c in COLS):
        skipped += 1
        continue
    if pd.isna(r["_dt"]):
        continue
    a = s52(r["player_1"], r["surface"], r["_dt"])
    b = s52(r["player_2"], r["surface"], r["_dt"])
    d.at[i, "s52_sgw_p1"], d.at[i, "s52_rgw_p1"] = a
    d.at[i, "s52_sgw_p2"], d.at[i, "s52_rgw_p2"] = b
    done += 1
    if all(v is not None for v in (a[0], a[1], b[0], b[1])):
        filled += 1

for c in COLS:
    d[c] = pd.to_numeric(d[c], errors="coerce")
d = d.drop(columns=["_dt"])
d.to_parquet(PATH, index=False)
print(f"computed {done} rows ({skipped} already had values); "
      f"{filled} got all four values ({100 * filled / max(done, 1):.0f}% coverage)")
cov = d[list(COLS)].notna().all(axis=1).sum()
print(f"log rows now carrying the full seasonal pair: {cov} of {len(d)} "
      f"({100 * cov / len(d):.0f}%)")
