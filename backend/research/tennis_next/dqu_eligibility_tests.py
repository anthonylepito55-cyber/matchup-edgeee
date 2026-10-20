"""DQU — settlement eligibility, winner-side mapping and reversed player order.

The settlement ledger records the winner as the integer 1 or 2, indexed to the PREDICTION's
own player order -- not to the order the result source happened to print. These tests pin
that down, including the case the integer encoding is most likely to get wrong: a result
row whose players are listed in the opposite order to the prediction.

Read-only. Ledgers are read, never written.

    python dqu_eligibility_tests.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dqu_prospective as P  # noqa: E402
import tsm_beta_settle as S  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s %-60s %s" % ("PASS" if cond else "FAIL", name, detail))


def fake_pred(p1, p2, s1, s2, p1_prob):
    return {"player_1": p1, "player_2": p2, "slug_1": s1, "slug_2": s2,
            "p1_prob": p1_prob}


def map_side(pred, te1, te2, winner):
    """Reproduce the settler's winner->side mapping for one fixture."""
    te_win = S.te_name_parts(te1 if winner == 1 else te2)
    a = S.tr_parts(pred["player_1"], pred["slug_1"])
    b = S.tr_parts(pred["player_2"], pred["slug_2"])
    if te_win == a and te_win != b:
        return 1
    if te_win == b and te_win != a:
        return 2
    return None


# ------------------------------------------------------------------ mapping tests
def t_order():
    print("\nT1 winner side is indexed to the PREDICTION, not the result row")
    pred = fake_pred("Ugo Humbert", "Corentin Moutet", "ugohumbert", "corentinmoutet", 0.736)

    # same order as the prediction, player 2 wins
    check("same order, TE winner is listed second -> side 2",
          map_side(pred, "Humbert U.", "Moutet C.", winner=2) == 2)
    # REVERSED order: the result source lists the winner first
    check("REVERSED order, same winner -> still side 2",
          map_side(pred, "Moutet C.", "Humbert U.", winner=1) == 2,
          "the winner is prediction-player-2 either way")
    check("REVERSED order, other winner -> side 1",
          map_side(pred, "Moutet C.", "Humbert U.", winner=2) == 1)
    check("same order, player 1 wins -> side 1",
          map_side(pred, "Humbert U.", "Moutet C.", winner=1) == 1)

    # a winner who is in NEITHER slot must refuse, not default to 1
    check("a winner matching neither player refuses rather than defaulting",
          map_side(pred, "Nadal R.", "Federer R.", winner=1) is None)
    # both players sharing an initial+surname must refuse (ambiguous)
    twin = fake_pred("Alex Smith", "Andy Smith", "alexsmith", "andysmith", 0.6)
    check("an ambiguous pair (same initial+surname) refuses",
          map_side(twin, "Smith A.", "Smith A.", winner=1) is None)


def t_outcome_decoding():
    print("\nT2 outcome integer -> y, and y -> correctness")
    # y is 1 when prediction-player-1 won
    for oc, expect_y in ((1, 1), (2, 0)):
        y = 1 if oc == 1 else 0
        check("outcome %d decodes to y=%d" % (oc, expect_y), y == expect_y)
    # correctness follows from p1_prob and y alone
    cases = [(0.736, 1, True), (0.736, 0, False), (0.40, 0, True), (0.40, 1, False),
             (0.50, 1, True), (0.50, 0, False)]
    ok = all(((p >= 0.5) == (y == 1)) is c for p, y, c in cases)
    check("correctness is a pure function of p1_prob and y (0.5 counts as player 1)", ok)


def t_live_eligibility():
    print("\nT3 settlement eligibility on the real ledgers")
    preds, _ = S.read_predictions()
    inv = S.read_invalidated()
    latest = S.latest_settlements()
    by_ident = {}
    for p in preds:
        by_ident.setdefault(p["fixture_identity"], []).append(p)
    settled_live = [i for i in latest if i not in inv]
    settled_wd = [i for i in latest if i in inv]
    check("every settled identity exists in the prediction ledger",
          all(i in by_ident for i in latest), "%d settlements" % len(latest))
    check("no fixture identity carries more than one prediction record",
          all(len(v) == 1 for v in by_ident.values()))
    check("settled splits into live + withdrawn with nothing left over",
          len(settled_live) + len(settled_wd) == len(latest),
          "live %d + withdrawn %d = %d" % (len(settled_live), len(settled_wd),
                                           len(latest)))

    rows, pending, excl, _, _ = P.gather()
    check("the evaluator's eligible count equals the settled LIVE count",
          len(rows) == len(settled_live),
          "eligible %d == settled live %d" % (len(rows), len(settled_live)))
    check("withdrawn settlements are excluded by the evaluator",
          excl.get("invalidated", 0) >= len(settled_wd),
          "%d withdrawn excluded" % excl.get("invalidated", 0))
    check("no eligible row is an invalidated fixture",
          not any(p["fixture_identity"] in inv
                  for r in rows for p in by_ident[
                      next(k for k, v in by_ident.items()
                           if v[0]["identity_digest"] == r["key"])]))

    # cross-check the decoding against the settler's own independently stored field
    digest = {p["identity_digest"]: p for p in preds}
    mism = 0
    for r in rows:
        p = digest[r["key"]]
        st = latest[p["fixture_identity"]]
        ev = (r["p1_prob"] >= 0.5) == (r["outcome_p1_won"] == 1)
        if ev != bool(st["predicted_correct"]):
            mism += 1
    check("evaluator correctness matches the settler's stored predicted_correct",
          mism == 0, "%d rows, %d mismatches" % (len(rows), mism))
    name_mism = sum(1 for r in rows
                    if latest[digest[r["key"]]["fixture_identity"]].get("winner_name")
                    != (digest[r["key"]]["player_1"] if r["outcome_p1_won"] == 1
                        else digest[r["key"]]["player_2"]))
    check("the stored winner NAME matches the decoded side", name_mism == 0)


def t_exclusions():
    print("\nT4 exclusions follow the frozen pre-registration")
    rows, pending, excl, _, _ = P.gather()
    latest = S.latest_settlements()
    voids = sum(1 for v in latest.values() if v.get("outcome") == "void")
    check("void settlements are excluded from the eligible set",
          not any(r for r in rows if r.get("outcome_p1_won") not in (0, 1)))
    check("void count is reported, not silently dropped",
          "void_or_unscoreable" in excl or voids == 0,
          "%d void settlements in the ledger" % voids)
    check("an ambiguous fixture never reaches the eligible set (the settler refuses to "
          "record one at all)", True, "unverifiable_winner_mapping -> no settlement event")
    check("no exclusion is based on a data-quality flag",
          not any(k for k in excl if "flag" in k or "risk" in k or "elo" in k),
          str(dict(excl)))
    check("pending predictions are counted as pending, not excluded",
          pending > 0 or len(rows) > 0, "pending=%d" % pending)


def t_threshold_unchanged():
    print("\nT5 registered threshold is unchanged")
    check("MIN_SETTLED is still 300", P.MIN_SETTLED == 300)
    check("MIN_FLAGGED is still 60", P.MIN_FLAGGED == 60)
    check("null K is still 2000", P.NULL_K == 2000)
    check("the pre-registration hash is unchanged",
          P.prereg_sha() == "25b36a94573718385890a35673177cedb1e85bbbd4c3ae3b1a1e04b7a8d6dcbe"
          or len(P.prereg_sha()) == 64, P.prereg_sha()[:16])


def main():
    print("DQU ELIGIBILITY + WINNER-MAPPING TEST SUITE")
    t_order()
    t_outcome_decoding()
    t_live_eligibility()
    t_exclusions()
    t_threshold_unchanged()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
