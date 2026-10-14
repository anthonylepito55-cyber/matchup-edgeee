"""TIGHTEN RESOLVER TIER 5 SO IT STOPS SUBSTITUTING A DIFFERENT PLAYER (2026-10-13).

THE BUG, found while answering "what was Silva after the change". MC2 priced
Adan Freire Da Silva vs Leo Borg at 70.9% on Silva against a 24.3% market. Adan Freire Da Silva
is NOT in the rating pool; tier 5 resolved him to LucasAndradeDaSilva -- a real, separate, active
player (won 6-4 6-2 on Oct 10, lost 4-6 3-6 on Oct 11) whose Elo 1445.7 sits ABOVE Borg's 1336.8.
That is the whole reason the card was inverted. Silva lost 4-6 6-4 4-6.

WHY TIER 5 IS STRUCTURALLY BROKEN. `_norm_name` SORTS tokens ("Ruud, Casper" == "Casper Ruud"),
so tier 5's `p[-1]` is the alphabetically-LAST token and `p[0][:1]` the alphabetically-FIRST
token's initial. Neither is the surname or the first initial:

    query   "adan freire da silva"   -> sorted first token "adan",    initial "a"
    profile "andrade da lucas silva" -> sorted first token "andrade", initial "a"
    both reduce to (surname "silva", initial "a") -> unique -> WRONG HIT

And tier 5 only ever runs when a player is ABSENT from the pool, which is exactly when it cannot
be checked: its original validation measured disagreements with EXISTING resolutions (0 of 344),
but an absent player has no existing resolution to disagree with, so every wrong answer was
invisible to the test that cleared it.

THE TIGHTENING. Keep tier 5's candidate generation, then require that EVERY substantive query
token (particles like da/de/van dropped) has a prefix-compatible partner among the candidate's
substantive tokens, where prefix-compatible means identical or sharing a 3+ character prefix.

    Caty McNally  -> Catherine McNally   caty~catherine ("cat"), mcnally~mcnally   ACCEPT
    Adan Freire Da Silva -> Lucas Andrade Da Silva
                                         silva~silva, but adan vs {andrade,lucas} shares
                                         only "a", and freire matches nothing            REJECT

Validated three ways below: the two named cases, every board player, and a pool-wide sweep that
checks the rule still recovers nickname-style perturbations while rejecting same-surname siblings.
"""
import difflib
import os
from collections import Counter

import tennis_context as tc

c = tc._load()
NI = c["name_index"]
PARTICLES = {"da", "de", "del", "dos", "das", "van", "von", "la", "le", "di", "el",
             "bin", "al", "ben", "der", "den", "do", "dela"}


def subst(key):
    return [t for t in key.split() if t not in PARTICLES]


def compat(a, b):
    """identical, a 3+ char shared prefix (caty~catherine), or a close spelling
    (Deigo~Diego, Giorgia~Georgia, Yulia~Yuliia) -- which a prefix rule cannot catch
    because those differ at character 2."""
    if a == b or len(os.path.commonprefix([a, b])) >= 3:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.75


def tier5_old(nm):
    q = nm.split()
    if len(q) < 2:
        return []
    sur, ini = q[-1], q[0][0]
    return [v for k, v in NI.items()
            if (lambda p: len(p) >= 2 and p[-1] == sur and p[0][:1] == ini)(k.split())]


def tier5_new(nm):
    hits = tier5_old(nm)
    if len(hits) != 1:
        return hits
    qs = subst(nm)
    if not qs:
        return []
    # DIRECTION MATTERS. Requiring every QUERY token to have a partner was tried and
    # destroyed four correct board resolutions -- boards legitimately ADD tokens
    # ("Arklon Huertas Del Pino Cordova" for ArklonHuertasDelPino, "Mateus De Carvalho
    # Cardoso Alves" for MateusAlves). The PROFILE name is the canonical one, so it is
    # every PROFILE token that must be accounted for in the query. A stranger fails this
    # on their given name: Lucas/Andrade match nothing in "adan freire da silva", and
    # Alex matches nothing in "ariana geerlings martinez".
    keys = [k for k, v in NI.items() if v == hits[0]]
    for k in keys:
        ps = subst(k)
        if ps and all(any(compat(p, t) for t in qs) for p in ps):
            return hits
    return []                                # candidate is a different person


BAR = "=" * 94
print(BAR)
print("1. THE TWO NAMED CASES")
print(BAR)
for nm, want in (("Adan Freire Da Silva", "REJECT"), ("Caty McNally", "ACCEPT"),
                 ("Catherine McNally", "ACCEPT"), ("Yulia Starodubtseva", "ACCEPT")):
    n = tc._norm_name(nm)
    o, w = tier5_old(n), tier5_new(n)
    got = "ACCEPT" if len(w) == 1 else "REJECT"
    exact = n in NI
    print("   %-22s old %-24s new %-24s  %s %s%s"
          % (nm, (o[0] if len(o) == 1 else "(%d hits)" % len(o)),
             (w[0] if len(w) == 1 else "(%d hits)" % len(w)), got,
             "OK" if (got == want or exact) else "** WANTED %s **" % want,
             "  [resolves exactly, tier 5 never runs]" if exact else ""))

print("\n" + BAR)
print("2. EVERY BOARD PLAYER -- does the tightening change any resolution?")
print(BAR)
import json
import sys

names = []
if len(sys.argv) > 1:
    b = json.load(open(sys.argv[1]))
    ms = b.get("matches") or b.get("games") or b
    for m in ms:
        for k in ("player_1", "player_2"):
            if m.get(k):
                names.append(str(m[k]))
names = sorted(set(names))
chg = []
for nm in names:
    n = tc._norm_name(nm)
    if n in NI:
        continue
    o, w = tier5_old(n), tier5_new(n)
    if (len(o) == 1) != (len(w) == 1):
        chg.append((nm, o[0]))
print("   board players: %d   tier-5 resolutions now REJECTED: %d" % (len(names), len(chg)))
for nm, s in chg:
    print("      %-26s no longer resolves to %s" % (nm, s))

print("\n" + BAR)
print("3. POOL SWEEP -- the rule must still recover nickname-style forms, and must reject")
print("   same-surname siblings. Both measured over all %d pool names." % len(NI))
print(BAR)
keep = Counter()
for k, v in NI.items():
    ts = subst(k)
    if len(ts) < 2:
        continue
    # a nickname-style perturbation of the alphabetically-first substantive token
    pert = sorted([ts[0][:4] + "y" if len(ts[0]) > 4 else ts[0]] + ts[1:])
    n = " ".join(pert)
    if n in NI:
        keep["already exact"] += 1
        continue
    w = tier5_new(n)
    keep["recovered" if (len(w) == 1 and w[0] == v) else "lost"] += 1
for lab, n in keep.most_common():
    print("   nickname perturbation: %-16s %5d" % (lab, n))

sib = Counter()
for k, v in NI.items():
    ts = k.split()
    if len(ts) < 2:
        continue
    # a DIFFERENT person sharing the alphabetically-last token and first initial
    n = " ".join(sorted(["zzqplausible"] + [t for t in ts if t != ts[0]]))
    n = " ".join(sorted([ts[0][0] + "qxwrong"] + ts[1:]))
    o, w = tier5_old(n), tier5_new(n)
    sib["OLD would accept a stranger" if len(o) == 1 else "old rejects"] += 1
    sib["NEW would accept a stranger" if len(w) == 1 else "new rejects"] += 1
for lab in ("OLD would accept a stranger", "NEW would accept a stranger",
            "old rejects", "new rejects"):
    if lab in sib:
        print("   same-surname stranger: %-30s %5d" % (lab, sib[lab]))
print("\n" + BAR)
print("READ: ship only if (1) Silva is rejected, (2) no board resolution is lost except Silva,")
print("(3) nickname recovery is preserved, (4) stranger acceptance drops.")
print(BAR)
