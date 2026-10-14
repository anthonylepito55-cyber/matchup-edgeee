"""FLAG THE ROWS PRICED OFF THE WRONG PLAYER (2026-10-13).

Tier 5 of the name resolver was substituting a different human when a player was absent from the
rating pool (see _patch_tier5.py). 15 of 1,120 logged players were affected, all ITF, several
borrowing a tour player's ratings outright:

    Ekaterina Agureeva         -> EkaterinaAlexandrova  (WTA top-20)
    Pedro Henrique Chabalgoity -> PedroCachin           (ATP)
    Maia Ilinca Burcescu       -> BeatrizHaddadMaia     (WTA top-30)
    Daniel Aleksandar Amarandei-> DanielAltmaier        (ATP)
    aoyi li                    -> AnnLi                 (WTA)
    Adan Freire Da Silva       -> LucasAndradeDaSilva
    ... and 9 more

The resolver is fixed, so this cannot recur. But the frozen rows already carry model numbers
computed from a stranger's ratings, and a frozen pick is never recomputed -- so they are flagged
instead, exactly as wrong-surface and in-play-contaminated rows are: the ROW IS KEPT (the price
and the result are real), and every live lane skips it, because the pick it implies was never a
pick about these players.

Writes `resolve_bad = True`. Nothing else is touched -- no model column is altered.

Run: ./venv/bin/python _flag_resolve_bad.py [--apply]
"""
import os
import shutil
import sys

import numpy as np
import pandas as pd

import tennis_context as tc
import tennis_log

APPLY = "--apply" in sys.argv
c = tc._load()
NI = c["name_index"]


def is_stranger(nm):
    """True when this name ONLY resolved via tier 5 and tier 5 was wrong about it."""
    import difflib
    n = tc._norm_name(nm)
    if n in NI:
        return False
    qt = set(n.split())
    if len(qt) < 2:
        return False
    h = [s for k, s in NI.items() if qt <= set(k.split())]
    if len(h) != 1:
        h = [s for k, s in NI.items() if len(set(k.split())) >= 2 and set(k.split()) <= qt]
    if len(h) != 1:
        def cov(pt, t):
            return t in pt or any(t[:i] in pt and cov(pt, t[i:]) for i in range(1, len(t)))
        h = [s for k, s in NI.items() if all(cov(set(k.split()), t) for t in qt)]
    if len(h) != 1:
        cl = difflib.get_close_matches(n, list(NI), n=2, cutoff=0.88)
        if len(cl) == 1:
            h = [NI[cl[0]]]
        elif len(cl) == 2:
            r = [difflib.SequenceMatcher(None, n, x).ratio() for x in cl]
            if r[0] - r[1] >= 0.06:
                h = [NI[cl[0]]]
    if len(h) == 1:
        return False                       # an earlier tier owns it; tier 5 never ran
    q = n.split()
    sur, ini = q[-1], q[0][0]
    h = [v for k, v in NI.items()
         if (lambda p: len(p) >= 2 and p[-1] == sur and p[0][:1] == ini)(k.split())]
    if len(h) != 1:
        return False                       # tier 5 abstained anyway
    return not tc._t5_same_person(n, [k for k, v in NI.items() if v == h[0]])


LOG = tennis_log.LOG_PATH
log = pd.read_parquet(LOG)
if "resolve_bad" not in log.columns:
    log["resolve_bad"] = np.nan

names = pd.unique(pd.concat([log.player_1.astype(str), log.player_2.astype(str)]))
bad = {nm for nm in names if is_stranger(nm)}
print("distinct logged players: %d   resolving to a stranger: %d" % (len(names), len(bad)))
for nm in sorted(bad):
    print("   %s" % nm)

m = log.player_1.astype(str).isin(bad) | log.player_2.astype(str).isin(bad)
print("\nrows to flag: %d" % int(m.sum()))
mod = [c0 for c0 in ("mc2_p1", "mc3_p1", "mc5_p1", "model_p_ev", "model_x_p1") if c0 in log.columns]
sub = log[m]
print("   of those, carrying a model number: %d"
      % int(sub[mod].notna().any(axis=1).sum()) if mod else 0)
print("   settled: %d   unsettled: %d"
      % (int(sub.p1_won.notna().sum()), int(sub.p1_won.isna().sum())))
already = int(log["resolve_bad"].fillna(False).astype(bool).sum())
print("   already flagged: %d" % already)

if not APPLY:
    print("\nDRY RUN -- log not written.")
    raise SystemExit(0)
bak = LOG + ".bak_resolvebad"
shutil.copy2(LOG, bak)
log.loc[m, "resolve_bad"] = True
log.to_parquet(LOG, index=False)
chk = pd.read_parquet(LOG)
print("\nwrote %d flags (backup %s)" % (int(m.sum()), os.path.basename(bak)))
print("verify: resolve_bad True = %d" % int(chk["resolve_bad"].fillna(False).astype(bool).sum()))
print("RESULT: OK")
