"""COVERAGE + UE CHECK on the RapidAPI feed (2026-10-10).

Established: the user's key returns completed matches for TODAY with a full serve/BP stat line,
where TennisRatio had 8% of today's matches and 37-38% stat lines after two days.

Two things left to settle before this is worth wiring:
  1. COVERAGE -- how many completed matches per day does it actually have, and does it include
     the ITF level the board is full of? Compared against our own logged count.
  2. UNFORCED ERRORS -- the `winners` and `unforcedErrors` fields EXIST but came back null on
     the two matches tested. Memory says the UE edge is WTA-tour hard-court, so the question is
     whether they populate at TOUR level. If they do, that reopens the whole UE line.
Spends at most 5 requests.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".rapidapi_key"),
          encoding="utf-8-sig") as fh:
    K = fh.read().strip()
H = {"X-RapidAPI-Key": K, "X-RapidAPI-Host": HOST, "Accept": "application/json"}


def get(path, label):
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://{HOST}{path}", headers=H),
                                    timeout=60) as r:
            b = r.read().decode("utf-8", "replace")
            return json.loads(b) if b.strip().startswith(("{", "[")) else None
    except urllib.error.HTTPError as e:
        print(f"   {label}: HTTP {e.code} -- {e.read().decode('utf-8', 'replace')[:150]}")
    except Exception as e:  # noqa: BLE001
        print(f"   {label}: {type(e).__name__}: {e}")
    return None


def rows_of(d):
    if not d:
        return []
    r = d.get("data") if isinstance(d, dict) else d
    if isinstance(r, dict):
        r = r.get("results") or r.get("data") or []
    return r if isinstance(r, list) else []


print("=" * 88)
print("1. COVERAGE -- completed singles matches per day, vs our own logged count")
print("=" * 88)
print(f"   {'date':12s} {'tour':5s} {'returned':>9s} {'hasNextPage':>12s}   levels seen")
tour_ids = {}
for date in ("2026-10-09", "2026-10-10"):
    for tour in ("atp", "wta"):
        q = urllib.parse.urlencode({"pageNo": 1, "pageSize": 500,
                                    "filter": "PlayerGroup:singles"})
        d = get(f"/tennis/v2/{tour}/results/{date}?{q}", f"{tour} {date}")
        rs = rows_of(d)
        nxt = (d or {}).get("hasNextPage") if isinstance(d, dict) else None
        if isinstance(d, dict) and "data" in d and isinstance(d["data"], dict):
            nxt = d["data"].get("hasNextPage", nxt)
        names = {}
        for r in rs:
            t = (r.get("tournament") or {})
            nm = t.get("name") if isinstance(t, dict) else str(t)
            names[str(nm)] = names.get(str(nm), 0) + 1
            if date == "2026-10-09" and isinstance(t, dict):
                tour_ids.setdefault(str(nm), r.get("matchId"))
        top = sorted(names.items(), key=lambda kv: -kv[1])[:4]
        print(f"   {date:12s} {tour:5s} {len(rs):9d} {str(nxt):>12s}   "
              f"{', '.join(f'{k}({v})' for k, v in top)}")
print("\n   our board logged: 2026-10-09 = 85 matches, 2026-10-10 = 142")

print("\n" + "=" * 88)
print("2. UNFORCED ERRORS -- do `winners` / `unforcedErrors` populate at TOUR level?")
print("=" * 88)
cands = [(nm, mid) for nm, mid in tour_ids.items() if mid and not any(
    w in nm.upper() for w in ("ITF", "M15", "M25", "W15", "W35", "W50", "W75", "CHALL"))][:3]
print(f"   tour-looking events found: {[c[0] for c in cands]}")
for nm, mid in cands:
    d = get(f"/tennis/v2/matches/{mid}/stats", f"stats {mid}")
    if not d:
        continue
    s = (d.get("data") or {}).get("player1Stats") or {}
    print(f"   {nm[:44]:44s} UE={s.get('unforcedErrors')}  winners={s.get('winners')}  "
          f"aces={s.get('aces')}  netApp={s.get('netApproaches')}")
print("\n   (UE non-null anywhere would reopen the unforced-error line, which every other")
print("    source refused -- see reference_ue_source_audit)")
