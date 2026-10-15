"""IN-PLAY PRICES NEVER REACH THE BOARD, AND TENNIS LOGGING IS PACED BY TENNIS (2026-10-15).

User: "Yo markets move after game starts" / "Asked u to fix this multiple times" /
"Shevchenko one market moved".

They are right that this was patched narrowly before. 2026-10-14 fixed the ITF path on the
FRONTEND by freezing each ITF card's price at first sight. That left the real hole open, which is
in the backend and applies to every league.

WHAT ACTUALLY HAPPENS. tennis_today() freezes a started match's price by looking up its frozen
pre-match log row. When that row exists the card gets {"frozen": True} and never moves. When it
does NOT exist, the code only set model_p = None and tagged live_odds {"inplay": True} -- and
then served the in-play price anyway. So the card kept the live market, and every price-based
mark on it (bands, EV gates, the dog cells) recomputed off a number that moves while the match is
being played.

Alexander Shevchenko vs Jay Dylan Hara Friend, atp_challenger, start 2026-10-15T04:00:00Z:
status live, live_odds -176/+132 with inplay:true and no frozen flag. It is the only started
match on the board without a frozen line, and it is the one the user saw move.

WHY IT HAD NO PRE-MATCH ROW -- the second defect, and the reason this recurs:

    mlb.service restarted 03:46:06 UTC (my own deploy), the match started 04:00:00Z.
    log_predictions only logs a match carrying BOTH a prediction and live odds, and it freezes
    started matches out. The background loop's cadence comes from _seconds_to_next_first_pitch --
    MLB first pitch. With no MLB game imminent that is BACKGROUND_REFRESH_SECONDS = 3600, so
    tennis gets one pass an hour. Tennis runs around the clock. A thin challenger that prices
    late can go from "no odds yet" to "already started" with no pass in between, and then no
    pre-match row can ever exist for it.

TWO FIXES.

1. WITHHOLD, DON'T SUBSTITUTE. A started match with no frozen pre-match line now has its price
   nulled: {"player_1": None, "player_2": None, "inplay": True, "withheld": True}. Nulling at the
   source is deliberate -- roughly thirty consumers read live_odds.player_1/player_2 and all of
   them already guard for null, so one change removes the moving number AND every mark derived
   from it, instead of thirty call sites each needing to remember. fmtPrice(null) renders "—",
   and the existing "IN-PLAY price" warning still shows because `inplay` is kept.

2. PACE TENNIS BY TENNIS. A dedicated loop refreshes the tennis slate every 10 minutes
   regardless of the MLB schedule, so a fixture gets a pre-match snapshot while it is still
   pre-match. tennis_today() is removed from the MLB-paced loop so the work is not doubled.

The honest limit of fix 2: if a market first prices a match AFTER it has started, no pre-match
line exists and fix 1 correctly shows no price rather than inventing one.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
s = io.open(P, encoding="utf-8").read()
assert '"withheld": True' not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:90])
    s = s.replace(old, new)


WHY = (
    "                    # WITHHOLD THE PRICE, DO NOT SUBSTITUTE THE IN-PLAY ONE (2026-10-15,\n"
    "                    # user \"markets move after game starts\" / \"Shevchenko one market moved\").\n"
    "                    # This branch means the match started with no frozen pre-match row, so\n"
    "                    # there IS no line -- what the feed offers now is an in-play price that\n"
    "                    # moves point by point. Previously it was tagged inplay:true and served\n"
    "                    # anyway, so the card and every price-based mark on it kept moving.\n"
    "                    # Nulling here rather than at the ~30 call sites that read\n"
    "                    # live_odds.player_1/2: they all already guard for null, so this removes\n"
    "                    # the number and every mark derived from it in one place.\n")

# ---- the board ----
rep("""                if _lr is None:
                    r["model_p"] = None   # started, never logged pre-match: in-play price
                    if isinstance(r.get("live_odds"), dict):
                        r["live_odds"]["inplay"] = True""",
    """                if _lr is None:
                    r["model_p"] = None   # started, never logged pre-match: in-play price
""" + WHY + """                    if isinstance(r.get("live_odds"), dict):
                        r["live_odds"] = {"player_1": None, "player_2": None,
                                          "bookmaker": r["live_odds"].get("bookmaker"),
                                          "inplay": True, "withheld": True}""")

# ---- the ITF / Best-tab cards ----
rep("""            if _lr is None:
                # started but never logged pre-match: its price is IN-PLAY, not a line.
                c["model_p"] = None
                if isinstance(c.get("live_odds"), dict):
                    c["live_odds"]["inplay"] = True
                continue""",
    """            if _lr is None:
                # started but never logged pre-match: its price is IN-PLAY, not a line.
                # Withheld, not substituted -- see the board branch above (2026-10-15).
                c["model_p"] = None
                if isinstance(c.get("live_odds"), dict):
                    c["live_odds"] = {"player_1": None, "player_2": None,
                                      "bookmaker": c["live_odds"].get("bookmaker"),
                                      "inplay": True, "withheld": True}
                continue""")

# ---- pace tennis by tennis, not by MLB first pitch ----
rep("""        try:
            await loop.run_in_executor(None, tennis_today)
        except Exception as e:
            print(f"[background refresh] tennis_today() failed: {e}")


@app.on_event("startup")
async def _start_background_refresh():
    asyncio.create_task(_background_refresh_loop())""",
    """        # tennis_today() is NOT called here any more -- it has its own loop below, because this
        # one's cadence comes from MLB first pitch and tennis does not keep MLB hours.


# TENNIS IS PACED BY TENNIS (2026-10-15, user "markets move after game starts").
#
# The loop above sleeps on _seconds_to_next_first_pitch -- MLB. With no MLB game imminent that is
# BACKGROUND_REFRESH_SECONDS = 3600, so the tennis slate was refreshed once an hour while tennis
# plays around the clock. log_predictions only logs a match that has BOTH a prediction and live
# odds, and it refuses started matches, so a thin challenger that prices late could go from "no
# odds yet" to "already started" with no pass in between -- after which no pre-match row can ever
# exist for it and the board had nothing to freeze. That is exactly how Shevchenko vs Hara Friend
# (04:00:00Z, 14 minutes after a deploy restart at 03:46:06Z) ended up showing a live in-play
# price. A fixed 10-minute cadence means a fixture gets its pre-match snapshot while it is still
# pre-match, whatever MLB is doing.
TENNIS_REFRESH_SECONDS = 600


async def _tennis_refresh_loop():
    loop = asyncio.get_event_loop()
    while True:
        await asyncio.sleep(TENNIS_REFRESH_SECONDS)
        try:
            await loop.run_in_executor(None, tennis_today)
        except Exception as e:
            print(f"[tennis refresh] tennis_today() failed: {e}")


@app.on_event("startup")
async def _start_background_refresh():
    asyncio.create_task(_background_refresh_loop())
    asyncio.create_task(_tennis_refresh_loop())""")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched main.py")
for k in ('"withheld": True', "_tennis_refresh_loop", "TENNIS_REFRESH_SECONDS"):
    print("   %-24s %d" % (k, s.count(k)))
import py_compile
py_compile.compile(P, doraise=True)
print("compiles: OK")
print("RESULT: OK")
