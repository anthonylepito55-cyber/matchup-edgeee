"""MC6 WATCH LANES, STAMPED SO THE REPLAY CANNOT BE MISTAKEN FOR A FORWARD TEST (2026-10-15).

MC6 is logged but not yet judged. These lanes are how it gets judged, mirroring MC3's and MC5's
so the four heads are measured on identical rules and rows:

    mc6_all          back MC6's side on every card
    mc6_edge2        back it when it sits 2pt+ over the de-vigged market on its own side
    mc6_dog_band     back it when its side is the dog at +100..+250
    mc6_vs_mc2       back MC6 only where MC6 and MC2 take DIFFERENT sides   <- the one that counts
    mc2_vs_mc6       back MC2 on those same rows

mc6_vs_mc2 / mc2_vs_mc6 are the pair that matters, for the same reason mc3_vs_mc2 does: MC6 is
MC2's blend plus two terms, so the heads agree on most cards and those rows feed identical results
to both records, making a pooled comparison mostly noise cancelling. Only the disagreements can
separate them, and they are paired by construction -- same match, same price, opposite sides -- so
the two ROIs are a zero-sum read on each other.

MC6_LIVE_FROM IS THE POINT OF THIS PATCH. A newly registered lane replays the frozen rows it can
see, and MC6's rule was written TODAY, so that replay is in-sample for the rule even though the
probabilities themselves were frozen pre-match. Stamping the lane means it starts at n=0 and every
pick in it is a genuine forward pick. Expect nothing for a couple of weeks; that is correct, not
broken.

Deliberately NOT added: any board mark. MC6 beats MC2 by +0.0043 AUC walk-forward, and that is a
prediction claim, not a betting one -- every MC head measured -8.7% to -9.7% at every edge gate.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tennis_log.py")
s = io.open(P, encoding="utf-8").read()
assert "mc6_vs_mc2" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:80])
    s = s.replace(old, new)


# ---- the live-from stamp ----
rep('''ASYM_LIVE_FROM = "2026-10-13T22:00:00Z"''',
    '''ASYM_LIVE_FROM = "2026-10-13T22:00:00Z"

# MC6 (2026-10-15) = MC2 + recency-weighted H2H + surface-form residual. The RULE was written
# today, so a replay over the frozen rows would be in-sample for the rule even though each
# probability was frozen pre-match -- see the 2026-10-13 lesson that a new lane's replay is not a
# forward test. Stamped, so these lanes open at n=0 and every pick in them is genuinely forward.
MC6_LIVE_FROM = "2026-10-15T22:00:00Z"''')

# ---- register the lane names ----
rep('''              "mc3_vs_mc2", "mc2_vs_mc3",''',
    '''              "mc3_vs_mc2", "mc2_vs_mc3",
              # MC6 watch lanes, mirroring MC3's and MC5's. mc6_vs_mc2 / mc2_vs_mc6 are the
              # pair that can actually separate them -- MC6 is MC2 plus two terms, so they
              # agree on most cards and only the disagreements carry information.
              "mc6_all", "mc6_edge2", "mc6_dog_band", "mc6_vs_mc2", "mc2_vs_mc6",''')

# ---- the scoring block, placed beside MC5's ----
rep('''                if pd.notna(_m39) and not _m3rec and (float(_m39) >= 0.5) != _m5b:
                    bet("mc5_vs_mc3", _m5b)''',
    '''                if pd.notna(_m39) and not _m3rec and (float(_m39) >= 0.5) != _m5b:
                    bet("mc5_vs_mc3", _m5b)
            # 🧮⁶ MC v6 watch lanes (2026-10-15): MC2's blend plus a recency-weighted H2H term
            # and a surface-form residual. Same three reads as MC2/MC3/MC5 so the four are
            # comparable on identical rules, plus the paired head-to-head against MC2.
            #
            # GATED ON MC6_LIVE_FROM: the rule was written today, so the frozen rows before the
            # stamp are in-sample for it. These lanes open at n=0 on purpose.
            _m69 = r.get("mc6_p1")
            _m6rec = bool(r.get("mc6_recon")) if pd.notna(r.get("mc6_recon")) else False
            if (pd.notna(_m69) and not _m6rec
                    and str(r.get("start_time_utc") or "") >= MC6_LIVE_FROM):
                _m6b = float(_m69) >= 0.5
                bet("mc6_all", _m6b)
                _ms6 = float(_m69) if _m6b else 1 - float(_m69)
                _mk6 = mk1 if _m6b else 1 - mk1
                if _ms6 - _mk6 >= 0.02:
                    bet("mc6_edge2", _m6b)
                if _m6b == dog1:
                    _od6 = r.get("p1_odds") if _m6b else r.get("p2_odds")
                    if pd.notna(_od6) and 100 <= float(_od6) <= 250:
                        bet("mc6_dog_band", _m6b)
                # the head-to-head, only where MC6 and MC2 actually differ
                if pd.notna(_m29) and not _m2rec:
                    _m2s6 = float(_m29) >= 0.5
                    if _m2s6 != _m6b:
                        bet("mc6_vs_mc2", _m6b)
                        bet("mc2_vs_mc6", _m2s6)''')

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched tennis_log.py")
for k in ("MC6_LIVE_FROM", "mc6_vs_mc2", "mc6_all", "mc6_dog_band"):
    print("   %-18s %d" % (k, s.count(k)))
import py_compile
py_compile.compile(P, doraise=True)
print("compiles: OK")
print("RESULT: OK")
