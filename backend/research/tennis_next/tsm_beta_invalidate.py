"""TSM paper beta — append an INVALIDATION record for parser-corrupted predictions.

Prediction records are immutable: they are never rewritten. When a prediction is found to
have been made against a corrupted input, the only honest remedy is to APPEND an
invalidation event naming it and the reason, and to exclude it from every performance
figure thereafter. The original record stays in the chain exactly as written.

    python tsm_beta_invalidate.py --scan     # report what would be invalidated
    python tsm_beta_invalidate.py --apply    # append the invalidation event

Cause being remedied (2026-10-20): the permitted-source parser captured the placeholder
avatar filename "default" from each img's onerror fallback. In compact schedule rows, which
carry no /players/ link, that phantom became player 2's identity, so those fixtures were
priced against a player who does not exist (default Elo, no serve/return history). The
parser is fixed and covered by regression tests; these records predate the fix.
"""
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from exp2_paper import Ledger  # noqa: E402

LEDGER = os.path.join(HERE, "beta_paper_ledger")
BASE_STATE = os.path.join(HERE, "tsm_beta_base_state.json")
REASON = ("parser captured the placeholder avatar 'default' from an img onerror fallback, "
          "so this fixture was priced against a non-existent player")


def scan():
    base = json.load(open(BASE_STATE, encoding="utf-8"))
    elo = base["elo_g"]
    led = Ledger(LEDGER)
    try:
        preds = [e for e in led.events if e["type"] == "beta_prediction"]
        already = set()
        for e in led.events:
            if e["type"] == "beta_invalidation":
                already.update(e["fixture_identities"])
    finally:
        led.close()
    bad = []
    for p in preds:
        why = None
        for side in ("slug_1", "slug_2"):
            s = p.get(side)
            if s == "default":
                why = "%s resolved to the placeholder 'default'" % side
            elif s not in elo and why is None:
                why = "%s=%r is absent from the model state" % (side, s)
        if why:
            bad.append({"fixture_identity": p["fixture_identity"],
                        "identity_digest": p["identity_digest"],
                        "p1": p["player_1"], "p2": p["player_2"],
                        "slug_1": p["slug_1"], "slug_2": p["slug_2"],
                        "confidence": p["confidence"], "why": why,
                        "already_invalidated": p["fixture_identity"] in already})
    return preds, bad, already


def apply_():
    preds, bad, already = scan()
    todo = [b for b in bad if not b["already_invalidated"]]
    if not todo:
        return {"new": 0, "note": "nothing to invalidate"}
    led = Ledger(LEDGER)
    try:
        led.append("beta_invalidation", {
            "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "reason": REASON,
            "remedy": "parser anchored to the src attribute; 'default' added to the "
                      "unresolvable list; 4 regression tests added",
            "note": "the original prediction records are UNCHANGED; they are excluded "
                    "from every performance figure from this point on",
            "count": len(todo),
            "fixture_identities": [b["fixture_identity"] for b in todo]})
        head = led.events[-1]["hash"]
    finally:
        led.close()
    return {"new": len(todo), "chain_head": head}


if __name__ == "__main__":
    preds, bad, already = scan()
    print("predictions in ledger : %d" % len(preds))
    print("corrupted             : %d" % len(bad))
    print("already invalidated   : %d" % sum(1 for b in bad if b["already_invalidated"]))
    for b in bad[:6]:
        print("   %-24s vs %-24s  slugs %s/%s  conf %.1f%%"
              % (str(b["p1"])[:24], str(b["p2"])[:24], b["slug_1"], b["slug_2"],
                 100 * b["confidence"]))
    if len(bad) > 6:
        print("   ... %d more" % (len(bad) - 6))
    if "--apply" in sys.argv:
        print()
        print("applied:", json.dumps(apply_()))
    else:
        print("\n(scan only -- pass --apply to append the invalidation event)")
