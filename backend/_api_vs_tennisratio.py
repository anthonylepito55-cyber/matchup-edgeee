"""CAN THE RAPIDAPI FEED REPRODUCE TENNISRATIO'S FEATURES? (2026-10-10, user "Yes")

The feed is far faster (same-day stat lines vs TennisRatio's 38% after two days) but carries a
different field set. Before scoping a wiring job, verify field by field against TennisRatio on
the SAME matches. Anything that does not reconcile here cannot be trusted later.

Direct mappings to check:
    first_serve_accuracy  <- firstServe / firstServeOf
    first_serve_points    <- winningOnFirstServe / winningOnFirstServeOf
    second_serve_points   <- winningOnSecondServe / winningOnSecondServeOf
    aces, double_faults   <- aces, doubleFaults
    BP saved%             <- breakPointSavedGm / breakPointFacedGm
    BP converted%         <- breakPointWonGm / breakPointChanceGm
Derived, and the real question:
    return_1st_serve_points  <- 100 - opponent's first-serve-won rate  (the head-to-head
                                identity measured in _what_wins_matches.py)
    hold%                    <- 1 - (opponent's breakPointWonGm / own service games), with
                                service games taken from the set scores
Known absent: serve/return pressure points (c_sp / c_rp), unforcedErrors, winners.

Dates chosen where TennisRatio coverage is HIGH (62-64%) so the comparison is not starved.
Budget-capped; keys read from the gitignored file at run time and never printed.
"""
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

import tennis_model_a as MA

HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"
HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, ".rapidapi_key"), encoding="utf-8-sig") as fh:
    K = fh.read().strip()
H = {"X-RapidAPI-Key": K, "X-RapidAPI-Host": HOST, "Accept": "application/json"}
BUDGET = [26]
DATES = ("2026-10-05", "2026-10-03")
MAX_MATCHES = 16


def get(path, label):
    if BUDGET[0] <= 0:
        return None
    BUDGET[0] -= 1
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://{HOST}{path}", headers=H),
                                    timeout=60) as r:
            b = r.read().decode("utf-8", "replace")
            return json.loads(b) if b.strip().startswith(("{", "[")) else None
    except urllib.error.HTTPError as e:
        print(f"   {label}: HTTP {e.code}")
    except Exception as e:  # noqa: BLE001
        print(f"   {label}: {type(e).__name__}")
    return None


def rows_of(d):
    r = d.get("data") if isinstance(d, dict) else d
    if isinstance(r, dict):
        r = r.get("results") or r.get("data") or []
    return r if isinstance(r, list) else []


def pname(v):
    if isinstance(v, dict):
        return v.get("name") or v.get("fullName") or ""
    return str(v or "")


def frac(s):
    m = re.match(r"^(\d+)/(\d+)$", str(s))
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


def games_served(score, first_server_is_p1):
    """Service games each player held the serve for, from the set scores. Games alternate, so
    the player serving first in a set takes ceil(total/2) of that set's games."""
    g1 = g2 = 0
    for st in re.findall(r"(\d+)-(\d+)", str(score)):
        a, b = int(st[0]), int(st[1])
        tot = a + b
        first = math.ceil(tot / 2)
        second = tot - first
        if first_server_is_p1:
            g1 += first
            g2 += second
        else:
            g2 += first
            g1 += second
    return g1, g2


# ---- TennisRatio side -----------------------------------------------------------------
MA._load()
A = pd.read_parquet("data_cache/tennisratio/all_match_logs.parquet",
                    columns=["date", "player_slug", "rival_slugname", "result", "score",
                             "first_serve_accuracy", "first_serve_points",
                             "second_serve_points", "return_1st_serve_points",
                             "return_2nd_serve_points", "aces", "double_faults",
                             "service_games_won", "breakpoints_saved_count",
                             "breakpoints_converted_count"])
A["date"] = pd.to_datetime(A["date"], errors="coerce")
A["dstr"] = A["date"].dt.strftime("%Y-%m-%d")
A["player_slug"] = A["player_slug"].astype(str)
TR = {}
for r in A.itertuples():
    TR[(r.dstr, r.player_slug)] = r

cmp_rows = []
for date in DATES:
    for tour in ("atp", "wta"):
        q = urllib.parse.urlencode({"pageNo": 1, "pageSize": 500,
                                    "filter": "PlayerGroup:singles"})
        d = get(f"/tennis/v2/{tour}/results/{date}?{q}", f"{tour} {date}")
        if not d:
            continue
        for row in rows_of(d):
            if len(cmp_rows) >= MAX_MATCHES:
                break
            n1, n2 = pname(row.get("player1")), pname(row.get("player2"))
            s1, s2 = MA.resolve(n1), MA.resolve(n2)
            if not s1 or not s2:
                continue
            t1, t2 = TR.get((date, s1)), TR.get((date, s2))
            if t1 is None or t2 is None:
                continue
            if frac(t1.service_games_won)[1] is None:
                continue                      # no TennisRatio stat line to compare against
            mid = row.get("matchId") or row.get("id")
            st = get(f"/tennis/v2/matches/{mid}/stats?type={tour}", f"stats {mid}")
            if not st:
                continue
            dd = st.get("data") or {}
            a1, a2 = dd.get("player1Stats") or {}, dd.get("player2Stats") or {}
            if not a1 or not a2:
                continue
            cmp_rows.append({"date": date, "m": f"{n1} vs {n2}", "score": row.get("result"),
                             "tr1": t1, "tr2": t2, "a1": a1, "a2": a2})
print(f"matches comparable in BOTH sources: {len(cmp_rows)}  (requests left {BUDGET[0]})")


def pct(a, b):
    a, b = (float(a) if a is not None else None), (float(b) if b is not None else None)
    return 100.0 * a / b if (a is not None and b not in (None, 0)) else None


FIELDS = []
for c in cmp_rows:
    for api, tr, orv in ((c["a1"], c["tr1"], c["a2"]), (c["a2"], c["tr2"], c["a1"])):
        row = {
            "1st serve in%": (pct(api.get("firstServe"), api.get("firstServeOf")),
                              tr.first_serve_accuracy),
            "1st serve won%": (pct(api.get("winningOnFirstServe"), api.get("winningOnFirstServeOf")),
                               tr.first_serve_points),
            "2nd serve won%": (pct(api.get("winningOnSecondServe"), api.get("winningOnSecondServeOf")),
                               tr.second_serve_points),
            "aces": (api.get("aces"), tr.aces),
            "double faults": (api.get("doubleFaults"), tr.double_faults),
            "BP saved%": (pct(api.get("breakPointSavedGm"), api.get("breakPointFacedGm")),
                          pct(*frac(tr.breakpoints_saved_count))),
            "BP converted%": (pct(api.get("breakPointWonGm"), api.get("breakPointChanceGm")),
                              pct(*frac(tr.breakpoints_converted_count))),
            # DERIVED: my return-vs-1st is the complement of the opponent's 1st-serve-won
            "return vs 1st% (derived)": (
                (100 - pct(orv.get("winningOnFirstServe"), orv.get("winningOnFirstServeOf")))
                if pct(orv.get("winningOnFirstServe"), orv.get("winningOnFirstServeOf")) is not None
                else None, tr.return_1st_serve_points),
        }
        # DERIVED hold%: breaks conceded = opponent's converted BPs; service games from score
        sgw, sga = frac(tr.service_games_won)
        gs = games_served(c["score"], True)
        for guess in (gs[0], gs[1]):
            if sga is not None and abs(guess - sga) <= 1:
                row["hold% (derived)"] = (pct(guess - (orv.get("breakPointWonGm") or 0), guess),
                                          pct(sgw, sga))
                break
        FIELDS.append(row)

print("\n" + "=" * 90)
print("FIELD-BY-FIELD: RapidAPI against TennisRatio, same match, same player")
print("=" * 90)
print(f"   {'field':26s} {'n':>4s} {'mean |diff|':>12s} {'median':>9s} {'max':>8s} "
      f"{'within 1pt':>11s} {'verdict':>10s}")
for f in ("1st serve in%", "1st serve won%", "2nd serve won%", "aces", "double faults",
          "BP saved%", "BP converted%", "return vs 1st% (derived)", "hold% (derived)"):
    d = [(a, b) for r in FIELDS if (p := r.get(f)) for a, b in [p]
         if a is not None and b is not None and not pd.isna(b)]
    if not d:
        print(f"   {f:26s} {'0':>4s}  no comparable rows")
        continue
    diff = np.array([abs(float(a) - float(b)) for a, b in d])
    tol = 1.0 if "%" in f else 0.5
    ok = 100 * float((diff <= tol).mean())
    verdict = "MATCH" if ok >= 90 else ("close" if ok >= 65 else "MISMATCH")
    print(f"   {f:26s} {len(d):4d} {diff.mean():12.2f} {np.median(diff):9.2f} "
          f"{diff.max():8.2f} {ok:10.0f}% {verdict:>10s}")
print("\n   tolerance: 1.0 for percentages, 0.5 for counts. MATCH needs 90%+ inside it.")
print("   Not available from the API at all: serve/return PRESSURE points (c_sp / c_rp),")
print("   unforcedErrors, winners.")
