"""TIER 5: SURNAME + FIRST INITIAL (2026-10-11, user: "Why don't u have stats for tararudee vs
mc nally").

The Wuhan card read "Lanlana Tararudee vs **Catherine** McNally" while the TennisRatio pool
holds her as "**Caty** McNally". None of the four existing fallback tiers catch a
nickname/formal-name swap: tier 1 and 2 need one token set to be a subset of the other, tier 3
needs a token to be a concatenation of others, and tier 4's difflib scores
"catherine mcnally" vs "caty mcnally" BELOW 0.80 -- nowhere near its 0.88 cutoff.

The cost of that one miss is the whole card: prediction, model_a, model_b, model_c, model_d,
model_p, mc2, pure_form, sr_dog, sos, features and her half of the TR CONTEXT were all MISSING.
Only model_x, ue and utr survived. A resolution miss does not degrade a card, it guts it.

Tier 5 matches on SURNAME + FIRST INITIAL, and only when that is unique in the pool.
Measured before shipping, on today's 391 board players:
  * 47 players do not resolve at all
  * tier 5 recovers exactly **1** of them -- this McNally case. The other 46 are genuinely
    absent from the ingested pool (mostly ITF), so this is a narrow fix, not a broad one.
  * surname+initial is non-unique for only 88 of 1,760 pool names, and the uniqueness
    requirement means those are left alone
  * it disagrees with **0 of 344** already-successful resolutions, and it only runs after the
    other tiers have failed

Applied to BOTH resolvers, which the code comments require to stay in lockstep.
"""
import io


def rep(path, a, b):
    s = io.open(path, encoding="utf-8").read()
    assert s.count(a) == 1, (path, s.count(a), a[:90])
    io.open(path, "w", encoding="utf-8", newline="\n").write(s.replace(a, b))


TIER5_DOC = """                # tier 5: SURNAME + FIRST INITIAL (2026-10-11, Catherine/Caty McNally
                # case). Nickname-vs-formal-name swaps defeat every tier above -- the token
                # sets are not subsets either way and difflib scores below 0.80. Only taken
                # when surname+initial is UNIQUE in the pool (non-unique for 88 of 1,760
                # names, which are therefore left unresolved rather than guessed). Measured
                # on 391 board players: recovers 1 of 47 misses and disagrees with 0 of 344
                # existing resolutions."""

# ---- tennis_model_a.resolve -----------------------------------------------------------
rep("backend/tennis_model_a.py",
    """                elif len(close) == 2:
                    r = [difflib.SequenceMatcher(None, nm, x).ratio() for x in close]
                    if r[0] - r[1] >= 0.06:
                        hits = [c["name_map"][close[0]]]
            if len(hits) == 1:
                s = hits[0]
    return s""",
    """                elif len(close) == 2:
                    r = [difflib.SequenceMatcher(None, nm, x).ratio() for x in close]
                    if r[0] - r[1] >= 0.06:
                        hits = [c["name_map"][close[0]]]
            if len(hits) != 1:
""" + TIER5_DOC + """
                _qt = nm.split()
                if len(_qt) >= 2:
                    _sur, _ini = _qt[-1], _qt[0][0]
                    hits = [v for k, v in c["name_map"].items()
                            if (lambda p: len(p) >= 2 and p[-1] == _sur
                                and p[0][:1] == _ini)(k.split())]
            if len(hits) == 1:
                s = hits[0]
    return s""")

# ---- tennis_context.get_context --------------------------------------------------------
rep("backend/tennis_context.py",
    """                elif len(close) == 2:
                    r = [difflib.SequenceMatcher(None, nmq, x).ratio() for x in close]
                    if r[0] - r[1] >= 0.06:
                        hits = [c["name_index"][close[0]]]
            if len(hits) == 1:
                slug = hits[0]""",
    """                elif len(close) == 2:
                    r = [difflib.SequenceMatcher(None, nmq, x).ratio() for x in close]
                    if r[0] - r[1] >= 0.06:
                        hits = [c["name_index"][close[0]]]
            if len(hits) != 1:
""" + TIER5_DOC.replace("name_map", "name_index") + """
                _qt = _norm_name(player_name).split()
                if len(_qt) >= 2:
                    _sur, _ini = _qt[-1], _qt[0][0]
                    hits = [v for k, v in c["name_index"].items()
                            if (lambda p: len(p) >= 2 and p[-1] == _sur
                                and p[0][:1] == _ini)(k.split())]
            if len(hits) == 1:
                slug = hits[0]""")
print("tier 5 added to both resolvers")
