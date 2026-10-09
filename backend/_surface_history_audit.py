"""Historical surface audit (2026-10-09, user "yes"): every logged match before 10-08 checked
against TennisExplorer's schedule for its own date (same resolve() the live board uses).
Writes data_cache/_surface_history_audit.csv with every mismatch."""
from datetime import datetime, timezone
import pandas as pd
import tennis_surface_check as S

L = pd.read_parquet("data_cache/_ec2_log_now.parquet")
L["d"] = L.date.astype(str).str[:10]
L = L[L.d < "2026-10-08"]
out, n_ok, n_un = [], 0, 0
for d, g in L.groupby("d"):
    S.refresh(days=(0, 1, -1), base=datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc, hour=12))
    for i, r in g.iterrows():
        s, src = S.resolve(r.player_1, r.player_2, r.get("tournament"))
        if not s:
            n_un += 1
            continue
        if str(r.surface).title() != s:
            out.append({"idx": i, "date": d, "fixture_id": r.fixture_id, "league": r.league, "tournament": r.tournament,
                        "p1": r.player_1, "p2": r.player_2, "logged": r.surface, "true": s, "src": src, "settled": r.settled})
        else:
            n_ok += 1
    print(f"{d}: rows {len(g)} | mismatches so far {len(out)}", flush=True)
O = pd.DataFrame(out)
O.to_csv("data_cache/_surface_history_audit.csv", index=False)
print(f"\nchecked: correct {n_ok} | WRONG {len(O)} | unverifiable {n_un}")
if len(O):
    print(O.groupby(["tournament", "logged", "true"]).size().sort_values(ascending=False).head(25).to_string())
