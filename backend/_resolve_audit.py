"""WHICH TIER RESOLVED "Adan Freire Da Silva" TO Lucas Andrade Da Silva, AND HOW OFTEN? (2026-10-13)

Found while answering "what was Silva after the change". MC2 priced Adan Freire Da Silva vs Leo
Borg at 70.9% on Silva against a 24.3% market -- because Adan Freire Da Silva is NOT in the
rating pool at all and the resolver silently substituted LucasAndradeDaSilva, a different player
whose Elo (1445.7) sits ABOVE Borg's (1336.8).

The coincidence that hid it: Lucas Andrade Da Silva has nS = 19, exactly the "19 career matches"
the card displayed, so the stat line looked self-consistent while belonging to someone else.

This prints the tier that fires per name and then sweeps the whole live board for the same
failure shape: a resolution whose SURNAME TOKENS do not overlap the query's, which is the
signature of a wrong player rather than an abbreviation or a transliteration.

Tier 5 is the prime suspect by construction. It takes the LAST token as the surname and the first
token's initial, which is wrong for compound Iberian surnames -- "Adan Freire Da Silva" reduces to
surname "silva" + initial "a", and anything indexed as "Andrade Da Silva" then matches uniquely.
Its original validation (recovers 1 of 47 misses, disagrees with 0 of 344 existing resolutions)
could not see this: a player ABSENT from the pool has no existing resolution to disagree with, so
a wrong answer is invisible to that test. Absence is precisely when tier 5 runs.
"""
import difflib
import json
import sys

import tennis_context as tc

c = tc._load()
NI = c["name_index"]
print("pool: %d indexed names -> %d profiles" % (len(NI), len(c["profiles"])))


def tiers(name):
    """Re-run get_context's chain, reporting which tier produces the hit."""
    nm = tc._norm_name(name)
    if nm in NI:
        return "exact", NI[nm]
    qt = set(nm.split())
    if len(qt) < 2:
        return None, None
    h = [s for k, s in NI.items() if qt <= set(k.split())]
    if len(h) == 1:
        return "t1 query<=profile", h[0]
    h = [s for k, s in NI.items() if len(set(k.split())) >= 2 and set(k.split()) <= qt]
    if len(h) == 1:
        return "t2 profile<=query", h[0]

    def covers(pt, t):
        if t in pt:
            return True
        return any(t[:i] in pt and covers(pt, t[i:]) for i in range(1, len(t)))

    h = [s for k, s in NI.items() if all(covers(set(k.split()), t) for t in qt)]
    if len(h) == 1:
        return "t3 fusion", h[0]
    close = difflib.get_close_matches(nm, list(NI), n=2, cutoff=0.88)
    if len(close) == 1:
        return "t4 difflib", NI[close[0]]
    if len(close) == 2:
        r = [difflib.SequenceMatcher(None, nm, x).ratio() for x in close]
        if r[0] - r[1] >= 0.06:
            return "t4 difflib", NI[close[0]]
    q = nm.split()
    sur, ini = q[-1], q[0][0]
    h = [v for k, v in NI.items()
         if (lambda p: len(p) >= 2 and p[-1] == sur and p[0][:1] == ini)(k.split())]
    if len(h) == 1:
        return "t5 surname+initial", h[0]
    return None, None


BAR = "=" * 96
print("\n" + BAR)
print("THE CASE AT HAND")
print(BAR)
for nm in ("Adan Freire Da Silva", "Leo Borg", "Marina Bassols Ribera", "Ida Wobker"):
    t, s = tiers(nm)
    g = tc.get_context(nm, "Hard")
    print("   %-24s tier %-20s -> %-30s (get_context: %s)"
          % (nm, t or "NONE", s or "-", (g or {}).get("slug", "None")))
# what the pool actually indexes under "silva"
print("\n   names in the pool whose last token is 'silva':")
for k, v in sorted(NI.items()):
    if k.split() and k.split()[-1] == "silva":
        print("      %-34s -> %s" % (k, v))

# --------------------------------------------------------------------- board-wide sweep
print("\n" + BAR)
print("BOARD SWEEP -- every resolution, by tier, flagging ones with NO surname-token overlap")
print(BAR)
names = []
if len(sys.argv) > 1:
    board = json.load(open(sys.argv[1]))
    ms = board.get("matches") or board.get("games") or board
    for m in ms:
        for k in ("player_1", "player_2"):
            if m.get(k):
                names.append(str(m[k]))
names = sorted(set(names))
print("board players: %d" % len(names))
if not names:
    print("   (pass a board json path to sweep it)")
    raise SystemExit(0)

from collections import Counter                                      # noqa: E402

cnt = Counter()
bad = []
for nm in names:
    t, s = tiers(nm)
    cnt[t or "unresolved"] += 1
    if not s:
        continue
    # the resolved profile's own indexed name(s)
    pn = [k for k, v in NI.items() if v == s]
    qt = set(tc._norm_name(nm).split())
    # a legitimate abbreviation/transliteration shares a substantive token; a WRONG player
    # typically shares only generic particles
    generic = {"da", "de", "del", "dos", "van", "von", "la", "le", "di", "el", "bin", "al"}
    sub_q = qt - generic
    ok = False
    for k in pn:
        sub_p = set(k.split()) - generic
        if sub_q & sub_p:
            ok = True
    if not ok:
        bad.append((nm, t, s, pn[:2]))
for t, n in cnt.most_common():
    print("   %-22s %4d" % (t, n))
print("\n   SUSPECT resolutions (no substantive token shared with the match): %d" % len(bad))
for nm, t, s, pn in bad:
    print("      %-26s tier %-20s -> %-28s indexed as %s" % (nm, t, s, pn))
