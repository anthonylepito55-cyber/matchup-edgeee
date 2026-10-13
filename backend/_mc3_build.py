"""Build MC3's rating state. Safe to re-run nightly.

MC3's ratings come from MC2's Stage-1b builder with ONE transform -- per-surface serve/return
ratings shrunk toward career at MC3_KS. The transform is not duplicated here: it is the same
validated function the sweep used (`_mc2_surface_sr_sweep.build`), so when MC2's builder is
improved MC3 inherits the improvement instead of silently diverging from it.

MC3_KS is imported from tennis_mc3, which is also what the runtime blends with, so the trained
expectation and the serving expectation can never fall out of step.

Writes data_cache/_mc3_state.pkl and data_cache/_mc3_features.parquet. Asserts MC2's own
artifacts are untouched, by fingerprint, before and after.

Run: ./venv/bin/python _mc3_build.py
"""
import hashlib
import os

import _mc2_surface_sr_sweep as SW
from tennis_mc3 import MC3_KS

KS = int(MC3_KS)
MC2_STATE = "data_cache/_mc2_state.pkl"
MC2_FEAT = "data_cache/_mc2_features.parquet"
OUT_STATE = "data_cache/_mc3_state.pkl"
OUT_FEAT = "data_cache/_mc3_features.parquet"


def _fp(p):
    if not os.path.exists(p):
        return None
    h = hashlib.md5()                                              # noqa: S324
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


before = {p: _fp(p) for p in (MC2_STATE, MC2_FEAT)}
print("MC3 build: KS=%d  (MC2 state fingerprint %s)" % (KS, before[MC2_STATE]))

SW.build(KS)

src_state = "data_cache/_mc2_state_sk%d.pkl" % KS
src_feat = SW.FEAT % KS
for a, b in ((src_state, OUT_STATE), (src_feat, OUT_FEAT)):
    assert os.path.exists(a), "builder did not produce %s" % a
    os.replace(a, b)
    print("   -> %s  (%.1f MB)" % (b, os.path.getsize(b) / 1e6))

after = {p: _fp(p) for p in (MC2_STATE, MC2_FEAT)}
for p in before:
    assert before[p] == after[p], "MC3 BUILD TOUCHED MC2 ARTIFACT: %s" % p
print("MC2 artifacts verified unchanged: %s" % ", ".join(
    "%s %s" % (os.path.basename(p), (after[p] or "absent")[:8]) for p in before))

# smoke test: the runtime must be able to read what the builder just wrote
import tennis_mc3 as M3                                            # noqa: E402

st = M3._state()
assert st, "MC3 state did not load"
n_surf = sum(1 for v in st["players"].values() if "S_s" in v)
print("MC3 state: %d players, %d carry per-surface ratings" % (len(st["players"]), n_surf))
assert n_surf == len(st["players"]), "some players lack the per-surface fields"
