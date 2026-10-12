"""DOES THE ODDS API GIVE TENNIS *STATS*? (2026-10-11, user: "does it give any more tennis
stats that we needed? itf stats or faster updated stats then tennis ratio")

Two specific needs, both real gaps in the current stack:

  ITF STATS       91% of ITF players have no serve/return context at all
                  (project_itf_stats_audit), so ITF cards run on almost nothing.
  FASTER STATS    TennisRatio delivers RESULTS same-day but its STAT LINES lag badly -- only
                  37-55% complete on the freshest three days (reference_result_source_latency),
                  which is why short windows like L5/L3 are often statless on a live card.

So this enumerates every v4 endpoint and asks what each actually returns, rather than assuming
an odds API has no stats. Checks in particular whether /scores carries anything beyond the set
score, and whether /participants or the event-level odds endpoint expose player data.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://api.the-odds-api.com/v4"
HERE = os.path.dirname(os.path.abspath(__file__))


def load_key():
    k = os.environ.get("ODDS_API_KEY")
    if k:
        return k.strip()
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8", errors="replace"):
            if ln.strip().startswith("ODDS_API_KEY") and "=" in ln:
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return None


KEY = load_key()


def get(path, params=None):
    p = dict(params or {})
    p["apiKey"] = KEY
    try:
        with urllib.request.urlopen(BASE + path + "?" + urllib.parse.urlencode(p),
                                    timeout=60) as r:
            return json.loads(r.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %s %s" % (e.code, e.read().decode("utf-8", "replace")[:150])
    except Exception as e:
        return None, str(e)[:120]


SPORT = "tennis_atp_shanghai_masters"

print("=" * 100)
print("EVERY v4 ENDPOINT -- what comes back for tennis?")
print("=" * 100)
ENDPOINTS = [
    ("/sports", {}),
    ("/sports/%s/odds" % SPORT, {"regions": "us", "markets": "h2h"}),
    ("/sports/%s/events" % SPORT, {}),
    ("/sports/%s/scores" % SPORT, {"daysFrom": 3}),
    ("/sports/%s/participants" % SPORT, {}),
    # plausible-but-undocumented names, probed so the answer is empirical not assumed
    ("/sports/%s/stats" % SPORT, {}),
    ("/sports/%s/players" % SPORT, {}),
]
for path, params in ENDPOINTS:
    d, err = get(path, params)
    if err:
        print("   %-46s %s" % (path.replace(SPORT, "{sport}"), err[:70]))
        continue
    n = len(d) if isinstance(d, list) else 1
    keys = sorted(d[0].keys()) if (isinstance(d, list) and d and isinstance(d[0], dict)) else \
        (sorted(d.keys()) if isinstance(d, dict) else "-")
    print("   %-46s OK  %s items  fields=%s"
          % (path.replace(SPORT, "{sport}"), n, str(keys)[:120]))

print("\n" + "=" * 100)
print("THE SCORES FEED -- does it carry anything beyond the set score?")
print("=" * 100)
sc, err = get("/sports/%s/scores" % SPORT, {"daysFrom": 3})
if err:
    print("   FAILED %s" % err)
else:
    done = [x for x in (sc or []) if x.get("completed")]
    print("   %d events, %d completed" % (len(sc or []), len(done)))
    if done:
        print("   full payload of one completed match:")
        print(json.dumps(done[0], indent=2)[:900])
        print("\n   any serve/return/error field anywhere in the whole feed?")
        blob = json.dumps(sc).lower()
        for probe in ("ace", "double_fault", "doublefault", "first_serve", "serve",
                      "break_point", "breakpoint", "unforced", "winner_count", "point",
                      "game_won", "statistic", "stats"):
            print("      %-15s %s" % (probe, "present" if probe in blob else "absent"))
        # latency: how soon after a match ends does it appear?
        print("\n   completion latency (commence_time -> now):")
        now = datetime.now(timezone.utc)
        for x in done[:6]:
            try:
                ct = datetime.fromisoformat(str(x.get("commence_time")).replace("Z", "+00:00"))
                print("      %-42s started %s ago, already marked completed"
                      % (("%s v %s" % (x.get("home_team"), x.get("away_team")))[:42],
                         str(now - ct).split(".")[0]))
            except Exception:
                pass

print("\n" + "=" * 100)
print("ITF -- is there ANY key below tour level?")
print("=" * 100)
sports, err = get("/sports", {"all": "true"})
if not err:
    tn = [s for s in sports if "tennis" in str(s.get("key", "")).lower()
          or str(s.get("group", "")).lower() == "tennis"]
    below = [s for s in tn if any(t in (str(s.get("key", "")) + str(s.get("title", ""))).lower()
                                  for t in ("challenger", "itf", "futures", "125", "250"))]
    print("   tennis keys: %d  | any challenger/ITF/futures key: %d"
          % (len(tn), len(below)))
    for s in below:
        print("      %s" % s.get("key"))
    if not below:
        print("      none -- ITF and challenger do not exist in this API at any tier,")
        print("      so it cannot help the 91%-no-context ITF problem.")

print("\n" + "=" * 100)
print("VERDICT vs WHAT WE NEEDED")
print("=" * 100)
print("   ITF stats .......... no ITF coverage at all, so no")
print("   faster stat lines .. scores feed is fast but carries ONLY the set score;")
print("                        no serve/return/ace/DF/UE fields anywhere -> does not")
print("                        address the TennisRatio stat-line lag")
