"""FIX RESOLVER TIER 5: stop substituting a different player (2026-10-13).

Found while answering "what was Silva after the change". MC2 priced Adan Freire Da Silva vs Leo
Borg at 70.9% on Silva against a 24.3% market, because Adan Freire Da Silva is NOT in the rating
pool and tier 5 resolved him to LucasAndradeDaSilva -- a real, separate, active player (won
6-4 6-2 on Oct 10, lost 4-6 3-6 on Oct 11) whose Elo 1445.7 sits ABOVE Borg's 1336.8. Silva lost
4-6 6-4 4-6. The tilt shipped earlier today took the card 70.9% -> 66.0%; the remaining ~42pt
error was this, not the model.

WHY TIER 5 WAS BROKEN. `_norm_name` SORTS tokens, so `p[-1]` is the alphabetically-last token and
`p[0][:1]` the alphabetically-first token's initial -- neither is the surname or the first
initial. "adan freire da silva" and "andrade da lucas silva" both reduce to (silva, a).

And tier 5 only runs when a player is ABSENT from the pool, which is exactly when it cannot be
checked. Its original validation measured disagreements with EXISTING resolutions (0 of 344), but
an absent player has no existing resolution to disagree with, so every wrong answer was invisible
to the test that cleared it.

THE TIGHTENING. Keep tier 5's candidate generation, then require that every substantive token of
the CANDIDATE PROFILE has a partner in the query. Partner = identical, 3+ character shared prefix
(caty~catherine), or difflib ratio >= 0.75 (Deigo~Diego, Giorgia~Georgia -- these differ at
character 2, so a prefix rule alone cannot catch them).

DIRECTION MATTERS, and the other direction was tried first and rejected. Requiring every QUERY
token to have a partner destroyed four CORRECT board resolutions, because boards legitimately ADD
tokens: "Arklon Huertas Del Pino Cordova" -> ArklonHuertasDelPino, "Mateus De Carvalho Cardoso
Alves" -> MateusAlves. The profile name is the canonical one, so it is the profile's tokens that
must be accounted for. A stranger fails on their given name -- Lucas and Andrade match nothing in
"adan freire da silva"; Alex matches nothing in "ariana geerlings martinez".

MEASURED (_tier5_fix_test.py, pool of 1,760 names, live board of 321 players):
    Adan Freire Da Silva           now REJECTED (was LucasAndradeDaSilva)
    Catherine McNally              still ACCEPTED -- the case tier 5 was built for
    board resolutions lost         1, and it is Ariana Geerlings Martinez -> AlexMartinez,
                                   also a stranger. All four legitimate ones preserved.
    nickname-form recovery         1,380 of 1,468 -- identical to the stricter variant, so
                                   flipping the direction cost nothing here
    same-surname strangers accepted  1,620 -> 19  (-98.8%)

Applied to BOTH resolvers, which tier 4's own comment already says to keep in lockstep:
tennis_context.get_context (feeds MC2/MC3/MC5 and every card stat line) and
tennis_model_a.resolve. tennis_itf_settle.py already handles compound surnames correctly and is
untouched.
"""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))

HELPER = '''
# Tier-5 safety check (2026-10-13). See _patch_tier5.py: tier 5 reduces a name to
# (alphabetically-last token, alphabetically-first token's initial), which collides across
# different people -- "adan freire da silva" and "andrade da lucas silva" both give
# (silva, a). This confirms the candidate is the SAME PERSON before tier 5 is trusted.
_T5_PARTICLES = {"da", "de", "del", "dos", "das", "van", "von", "la", "le", "di", "el",
                 "bin", "al", "ben", "der", "den", "do", "dela"}


def _t5_same_person(query_norm, profile_keys):
    """True when every substantive token of the profile has a partner in the query.

    Partner = identical, a 3+ character shared prefix (caty~catherine), or a close spelling
    (Deigo~Diego, Giorgia~Georgia, which differ at character 2 so a prefix rule misses them).
    Checked in this direction because boards legitimately ADD tokens to a name; requiring
    every QUERY token to match was measured and destroyed four correct resolutions.
    """
    import difflib
    import os as _os
    sub = lambda k: [t for t in k.split() if t not in _T5_PARTICLES]
    qs = sub(query_norm)
    if not qs:
        return False

    def partner(p):
        for t in qs:
            if p == t or len(_os.path.commonprefix([p, t])) >= 3:
                return True
            if difflib.SequenceMatcher(None, p, t).ratio() >= 0.75:
                return True
        return False

    for k in profile_keys:
        ps = sub(k)
        if ps and all(partner(p) for p in ps):
            return True
    return False

'''

TARGETS = [
    ("tennis_context.py", "name_index", "_norm_name(player_name)", "def _slug_to_name(slug):"),
    ("tennis_model_a.py", "name_map", "nm", None),
]

for fname, idx, qexpr, anchor in TARGETS:
    p = os.path.join(HERE, fname)
    s = io.open(p, encoding="utf-8").read()
    assert "_t5_same_person" not in s, "%s already patched" % fname

    # 1. insert the helper
    if anchor is None:
        # place it just before the function that contains tier 5
        anchor = "def _feats(p1, p2, surface, h):"
    assert s.count(anchor) == 1, "%s: anchor %r x%d" % (fname, anchor, s.count(anchor))
    s = s.replace(anchor, HELPER + "\n" + anchor)

    # 2. gate tier 5's hit list
    old = '''                    hits = [v for k, v in c["%s"].items()
                            if (lambda p: len(p) >= 2 and p[-1] == _sur
                                and p[0][:1] == _ini)(k.split())]''' % idx
    assert s.count(old) == 1, "%s: tier-5 block x%d" % (fname, s.count(old))
    new = '''                    hits = [v for k, v in c["%s"].items()
                            if (lambda p: len(p) >= 2 and p[-1] == _sur
                                and p[0][:1] == _ini)(k.split())]
                    # (silva, a) matches strangers, so confirm it is the same person
                    if len(hits) == 1 and not _t5_same_person(
                            %s, [k for k, v in c["%s"].items() if v == hits[0]]):
                        hits = []''' % (idx, qexpr, idx)
    s = s.replace(old, new)

    io.open(p, "w", encoding="utf-8", newline="").write(s)
    print("patched %s" % fname)

for fname in ("tennis_context.py", "tennis_model_a.py"):
    s = io.open(os.path.join(HERE, fname), encoding="utf-8").read()
    assert s.count("_t5_same_person") == 2, fname
    print("   %-20s helper + gate present" % fname)
print("RESULT: OK")
