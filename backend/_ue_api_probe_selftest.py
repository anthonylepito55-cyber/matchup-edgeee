"""DRY-RUN THE RAPIDAPI PROBE WITHOUT A KEY (2026-10-10).

_ue_api_probe.py has never executed its main path -- it has only ever hit the "no key" branch.
This exercises everything except the network by swapping the probe's `call()` for canned
payloads, so that the moment a key is in place the real run either answers the question or fails
for a reason that is genuinely about the API, not about our code.

Two scenarios are simulated, because they are the two outcomes that matter:
  POPULATED -- every level returns a real unforcedErrors number  -> expect a "worth pricing" verdict
  NULL      -- tour levels return numbers, ITF and challenger return null (what every other
               source did) -> expect a "do not subscribe" verdict
"""
import sys

import _ue_api_probe as P

PAYLOAD_OK = {"data": {"player1Stats": {"unforcedErrors": 18, "winners": 22},
                       "player2Stats": {"unforcedErrors": 31, "winners": 14}}}
PAYLOAD_NULL = {"data": {"player1Stats": {"unforcedErrors": None, "winners": None},
                         "player2Stats": {"unforcedErrors": None, "winners": None}}}


def run(scenario):
    calls = {"n": 0}

    def fake_call(path, params=None):
        calls["n"] += 1
        P.used += 1
        if scenario == "populated":
            return 200, PAYLOAD_OK
        # tour levels carry it, below-tour does not -- the shape every other source had
        tour = "/wta/" in path or "/atp/" in path
        itf_ish = any(t in path.lower() for t in ("itf", "challenger"))
        return 200, (PAYLOAD_NULL if itf_ish or not tour else PAYLOAD_OK)

    P.call = fake_call
    P.KEY = "dry-run"
    P.used = 0
    print(f"\n{'=' * 70}\nSCENARIO: {scenario}\n{'=' * 70}")
    P.main()
    print(f"[simulated requests: {calls['n']}]")


if __name__ == "__main__":
    # find_ue must distinguish a real number from a null -- that is the whole verdict
    assert P.find_ue(PAYLOAD_OK) and any(v is not None for _, v in P.find_ue(PAYLOAD_OK))
    assert P.find_ue(PAYLOAD_NULL) and all(v is None for _, v in P.find_ue(PAYLOAD_NULL))
    print("find_ue() distinguishes populated from null: OK")
    for s in ("populated", "null"):
        run(s)
    sys.stdout.flush()
