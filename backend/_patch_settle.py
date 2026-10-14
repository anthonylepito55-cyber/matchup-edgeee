"""FIX THE TWO SETTLEMENT GAPS (2026-10-14).

41 rows had never settled, spread evenly across every league (93-98% settle rate each) and every
day back to 2026-09-07. Each one sits in its lanes as "pending" forever, so its outcome never
reaches any record. Two distinct causes, only one of which is a bug in this file.

BUG -- THE RETRY WINDOW. settle() does `sorted(todo["date"].unique())[-max_dates:]` with
max_dates=10. There are 20 distinct dates holding unsettled rows, so the OLDEST TEN
(2026-09-07 through 2026-09-29) are never retried and never can be: every run picks the same
most-recent ten and the backlog is permanently out of reach. The cap exists to bound the number
of API calls per run, which is reasonable, but taking the newest dates is backwards -- the newest
are the ones most likely to settle on the next run anyway. Now it walks the OLDEST first, so the
backlog drains instead of accumulating, and the cap is raised since the fetch is cached per date.

NOT A BUG -- RETIREMENTS. Djokovic v De Minaur (Beijing final, 2026-10-06) comes back
status="completed" with home total 1, away total 1 and periods 7-6 then 0-1: the match was
abandoned one game into the second set. The payload carries NO winner field, so the set totals
genuinely cannot say who won -- a retiring player loses regardless of the score. settle() is
right to skip it rather than guess, and widening the `h == a` guard would invent results. These
need a second source (TennisExplorer or the Polymarket resolution already used for pm_ rows),
which is a separate piece of work and is left alone here.

ALSO FIXED -- CANCELLED FIXTURES. The feed returned 4 cancelled fixtures for 2026-10-06 alone.
A cancelled match has no winner and never will, so leaving it unsettled means it is counted as a
pending bet indefinitely. Those are now marked settled with p1_won left null and void=True.
Every lane reads `settled = bool(r["settled"]) and pd.notna(r["p1_won"])`, so a void row counts
as neither a win nor a loss -- it simply stops being pending.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tennis_log.py")
s = io.open(P, encoding="utf-8").read()
assert '"void"' not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:95])
    s = s.replace(old, new)


# 1. drain the backlog oldest-first instead of re-reading the same newest ten
rep('''def settle(max_dates: int = 10):''', '''def settle(max_dates: int = 40):''')
rep('''    for date in sorted(todo["date"].unique())[-max_dates:]:''',
    '''    # OLDEST FIRST (2026-10-14). This took the NEWEST max_dates, so with 20 dates holding
    # unsettled rows the oldest ten were never retried on any run -- 2026-09-07 through
    # 2026-09-29 were permanently stranded. The newest dates settle on the next run regardless;
    # it is the backlog that needs the retries.
    for date in sorted(todo["date"].unique())[:max_dates]:''')

# 2. cancelled fixtures can never settle -- stop counting them as pending bets
rep('''        for f in fixtures:
            if f.get("status") != "completed":
                continue''',
    '''        for f in fixtures:
            if f.get("status") in ("cancelled", "canceled", "postponed", "abandoned"):
                # no winner exists and none ever will, so mark it void rather than leaving it
                # to sit in every lane as a pending bet forever. p1_won stays null and each
                # lane reads `settled and p1_won.notna()`, so it scores as neither win nor loss.
                _vm = log["fixture_id"] == f.get("id")
                if _vm.any() and not bool(log.loc[_vm, "settled"].iloc[0]):
                    log.loc[_vm, "settled"] = True
                    log.loc[_vm, "void"] = True
                    changed = True
                continue
            if f.get("status") != "completed":
                continue''')

# 3. register the column so it round-trips
rep('''           "bookmaker", "logged_at", "settled", "p1_won", "sr_dog", "sos",''',
    '''           "bookmaker", "logged_at", "settled", "p1_won", "void", "sr_dog", "sos",''')
rep('''            "bookmaker": odds.get("bookmaker"), "logged_at": now, "settled": False, "p1_won": None,''',
    '''            "bookmaker": odds.get("bookmaker"), "logged_at": now, "settled": False, "p1_won": None,
            "void": False,''')

io.open(P, "w", encoding="utf-8", newline="").write(s)
import ast

ast.parse(s)
print("patched tennis_log.py -- syntax OK")
print("   max_dates 10 -> 40, oldest-first")
print("   cancelled/postponed/abandoned -> settled + void")
print("RESULT: OK")
