"""SWEEP THE LOG FOR pm_ TWINS, SETTLED OR NOT (2026-10-13). --apply to write.

The first pass keyed on the SCORE, so it could only see duplicates of finished matches. The
widened matcher immediately reported five more -- unsettled rows, which have no score yet and
were therefore invisible to it. Those will double-count the moment they settle.

This sweeps on identity instead of outcome: any pm_-prefixed row whose player pair matches an
OpticOdds row within +/-3 days, by the strict token-set key or the surname+initial fallback.
Same policy the live path uses -- OpticOdds is primary, the pm_ twin goes -- so this is simply
the live rule applied retroactively to rows that predate it.

Prints each pair before acting, because a retroactive delete should be readable.
"""
import shutil
import sys

import pandas as pd

import tennis_log
from tennis_log import _pair_key, _pair_keys_loose

APPLY = "--apply" in sys.argv
LOG = tennis_log.LOG_PATH
L = pd.read_parquet(LOG).reset_index(drop=True)
L["_d"] = pd.to_datetime(L["date"].astype(str).str[:10], errors="coerce")
L["_pm"] = L["fixture_id"].astype(str).str.startswith("pm_")
print("log rows %d  (pm_ %d, OpticOdds %d)"
      % (len(L), int(L["_pm"].sum()), int((~L["_pm"]).sum())))

oo = L[~L["_pm"]]
strict, loose = {}, {}
for i, r in oo.iterrows():
    strict.setdefault(_pair_key(r["player_1"], r["player_2"]), []).append(i)
    for k in _pair_keys_loose(r["player_1"], r["player_2"]):
        loose.setdefault(k, []).append(i)

drop, detail = [], []
for i, r in L[L["_pm"]].iterrows():
    if pd.isna(r["_d"]):
        continue
    cands, how = strict.get(_pair_key(r["player_1"], r["player_2"]), []), "strict"
    if not cands:
        seen = set()
        for k in _pair_keys_loose(r["player_1"], r["player_2"]):
            seen.update(loose.get(k, []))
        cands, how = sorted(seen), "surname+initial"
    near = [j for j in cands
            if pd.notna(L.at[j, "_d"]) and abs((L.at[j, "_d"] - r["_d"]).days) <= 3]
    if near:
        drop.append(i)
        detail.append((i, near[0], how))

print("\npm_ rows with an OpticOdds twin within 3 days: %d" % len(drop))
print("%-6s %-6s %-16s %-24s %-24s %-11s %-9s %s"
      % ("drop", "keep", "matched by", "pm_ name", "OO name", "date", "settled", "pm fixture"))
print("-" * 118)
for i, j, how in detail:
    a, b = L.loc[i], L.loc[j]
    print("%-6d %-6d %-16s %-24s %-24s %-11s %-9s %s"
          % (i, j, how, str(a["player_1"])[:24], str(b["player_1"])[:24],
             str(a["date"])[:10], a["settled"], str(a["fixture_id"])[:22]))

if not drop:
    raise SystemExit(0)
n_settled = int(L.loc[drop, "settled"].fillna(False).astype(bool).sum())
print("\nof those, %d are already settled (double-counting in lanes NOW) and %d are pending"
      % (n_settled, len(drop) - n_settled))

if not APPLY:
    print("\nDRY RUN -- nothing written. Re-run with --apply.")
    raise SystemExit(0)

bak = LOG + ".bak_pmsweep"
shutil.copy2(LOG, bak)
out = L.drop(index=drop).drop(columns=["_d", "_pm"])
out.to_parquet(LOG, index=False)
print("\nwrote %d rows (was %d), backup %s" % (len(out), len(L), bak.split("/")[-1]))
chk = pd.read_parquet(LOG)
assert len(chk) == len(L) - len(drop)
print("verified %d rows on disk" % len(chk))
print("RESULT: OK")
