"""THE DECISIVE TEST (2026-10-10): does the user's RapidAPI key return a STAT LINE for a match
that finished TODAY?

The results endpoint already beat TennisRatio on speed -- 50 completed matches for 2026-10-10,
one finishing 19:03 UTC, against TennisRatio's 8% -- but carried no serve/return numbers. The
MCP tool listing documents `/tennis/v2/matches/{matchId}/stats` as "completed-match statistics
for both players (all plans)". If that works on the user's key for a match from today, it is a
same-day stat line, which nothing we have provides (TennisRatio runs 37-38% after two days).

Spends at most 3 requests of the ~50/day free tier.
"""
import json
import os
import urllib.error
import urllib.request

HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".rapidapi_key"),
          encoding="utf-8-sig") as fh:
    K = fh.read().strip()
H = {"X-RapidAPI-Key": K, "X-RapidAPI-Host": HOST, "Accept": "application/json"}


def get(path, label):
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://{HOST}{path}", headers=H),
                                    timeout=45) as r:
            b = r.read().decode("utf-8", "replace")
            print(f"{label}: HTTP {r.status}, {len(b)} bytes")
            return json.loads(b) if b.strip().startswith(("{", "[")) else None
    except urllib.error.HTTPError as e:
        print(f"{label}: HTTP {e.code} -- {e.read().decode('utf-8', 'replace')[:180]}")
    except Exception as e:  # noqa: BLE001
        print(f"{label}: {type(e).__name__}: {e}")
    return None


for mid, tour, note in (("46442733", "wta", "WTA, finished 2026-10-10 15:25 UTC"),
                        ("58819840", "atp", "ATP, finished 2026-10-10 19:03 UTC")):
    print("=" * 84)
    d = get(f"/tennis/v2/matches/{mid}/stats?type={tour}", f"stats for {mid} ({note})")
    if not d:
        continue
    s = json.dumps(d)
    print(f"   payload: {s[:700]}")
    low = s.lower()
    print("\n   WHICH STATS ARE PRESENT:")
    for want in ("ace", "double", "first serve", "firstserve", "second serve", "break",
                 "winner", "unforced", "error", "point", "service game", "return"):
        print(f"      {want:16s} {'YES' if want in low else '--'}")
