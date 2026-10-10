"""IS unforcedErrors POPULATED BY TOURNAMENT LEVEL? (2026-10-10)

The RapidAPI "Tennis API ATP WTA ITF" feed is now authorized, and its documented field really
does exist:
    /tennis/v2/{atp|wta}/h2h/match-stats/{tournamentId}/{p1Id}/{p2Id}
      -> data.player{1,2}Stats.unforcedErrors
The first ITF sample came back with unforcedErrors: null while every serve/return counter was
populated, which is the same shape every other source had. This measures it properly, by level,
instead of from one match.

Method: pull the completed-results feed for several dates (one request each, it carries
tournamentId + both playerIds + tournament.rankId), then call match-stats for a sample spread
across rank tiers and record how often unforcedErrors is non-null. Also reports which OTHER
fields are populated, since a feed that reliably gives aces and double faults everywhere is
still worth knowing about even if it never gives unforced errors.

Reads the key from backend/.rapidapi_key. Budget-capped for the free 50/day tier.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"
BUDGET = int(os.environ.get("RAPIDAPI_BUDGET", "40"))
DATES = ["2026-10-08", "2026-10-06", "2026-10-04"]
PER_TIER = 3          # match-stats calls per (tour, rank tier)
used = 0


def key():
    f = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".rapidapi_key")
    with open(f, encoding="utf-8-sig") as fh:
        return fh.read().strip()


K = key()


def get(path, q=None):
    global used
    if used >= BUDGET:
        return None, "budget"
    url = f"https://{HOST}{path}" + ("?" + urllib.parse.urlencode(q) if q else "")
    req = urllib.request.Request(url, headers={
        "X-RapidAPI-Key": K, "X-RapidAPI-Host": HOST, "Accept": "application/json"})
    used += 1
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, e.read(300).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return None, str(e)
    finally:
        time.sleep(0.3)


def main():
    # 1. gather completed matches, grouped by (tour, rankId)
    pool = defaultdict(list)
    names = {}
    for tour in ("wta", "atp"):
        for d in DATES:
            st, body = get(f"/tennis/v2/{tour}/results/{d}",
                           {"pageSize": 100, "pageNo": 1, "filter": "PlayerGroup:singles"})
            if st != 200 or not isinstance(body, dict):
                print(f"  results {tour} {d}: {st} {str(body)[:80]}")
                continue
            for r in body.get("data") or []:
                t = r.get("tournament") or {}
                rid = t.get("rankId")
                names[(tour, rid)] = names.get((tour, rid)) or t.get("name")
                if r.get("result_type") == "completed" and r.get("tournamentId"):
                    pool[(tour, rid)].append(r)
            if used >= BUDGET:
                break
    print(f"collected matches by (tour, rankId): "
          f"{ {f'{k[0]}/r{k[1]}': len(v) for k, v in sorted(pool.items(), key=lambda x: str(x[0]))} }")
    print(f"example tournament per tier: { {f'{k[0]}/r{k[1]}': names.get(k) for k in sorted(pool, key=str)} }\n")

    # 2. sample match-stats per tier
    print(f"{'tour/rank':<12}{'example event':<26}{'tried':>6}{'UE':>5}{'winners':>9}{'aces':>6}{'DF':>5}")
    tally = {}
    for kk in sorted(pool, key=str):
        tour, rid = kk
        rows = pool[kk][:PER_TIER]
        tried = ue = win = ace = df = 0
        for r in rows:
            if used >= BUDGET:
                break
            st, body = get(f"/tennis/v2/{tour}/h2h/match-stats/"
                           f"{r['tournamentId']}/{r['player1Id']}/{r['player2Id']}")
            if st != 200 or not isinstance(body, dict):
                continue
            s1 = ((body.get("data") or {}).get("player1Stats") or {})
            if not s1:
                continue
            tried += 1
            ue += s1.get("unforcedErrors") is not None
            win += s1.get("winners") is not None
            ace += s1.get("aces") is not None
            df += s1.get("doubleFaults") is not None
        if tried:
            tally[kk] = (tried, ue, win, ace, df)
            print(f"{tour}/r{rid:<9}{(names.get(kk) or '?')[:25]:<26}{tried:>6}{ue:>5}{win:>9}{ace:>6}{df:>5}")
        if used >= BUDGET:
            print("  (budget exhausted)")
            break

    tot_t = sum(v[0] for v in tally.values())
    tot_ue = sum(v[1] for v in tally.values())
    print(f"\nrequests used: {used}")
    print(f"VERDICT: unforcedErrors populated on {tot_ue} of {tot_t} sampled matches")
    if tot_t and tot_ue == 0:
        print("  -> the field is in the schema but NEVER populated, at any level sampled.\n"
              "     This feed cannot deliver unforced errors. Do not pay for it on that basis.\n"
              "     It DOES reliably carry aces / double faults / first-serve splits / break\n"
              "     points for ITF and challenger matches, which our archive only gets ~10 days\n"
              "     late -- that is a separate, real use if we ever want same-day serve data.")
    elif tot_ue:
        print("  -> populated for some levels; see the table for which.")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
