"""Build MC5's rating state. Safe to re-run nightly.

MC5 inherits MC3's recipe -- per-surface serve/return shrunk at KS, margin-aware Elo -- and adds
nothing to the TRAINING pass except a richer per-player history, because its two new terms are
computed at PREDICT time from that history rather than trained into a weight:

    hist rows become (date, nsets, is_ret, won, spw_resid, surf)
    the 12-entry cap rises to 40, so a per-surface last-five has material to filter

Pressure needs no change at all: the builder already accumulates pw/pa per player, and
tennis_mc5._clutch reads them straight off the state.

So MC5's state is MC3's state plus a longer, richer history. The weights live in tennis_mc5.py
and are imported here, so the build and the runtime cannot disagree.

Asserts MC2's and MC3's artifacts are untouched, by fingerprint, before and after.
"""
import hashlib
import os

import _mc2_surface_sr_sweep as SW
from tennis_mc5 import MC5_KS, MC5_MOV_W

SRC = "_mc2_stage1b_serve_return.py"
GUARD = ["data_cache/_mc2_state.pkl", "data_cache/_mc3_state.pkl",
         "data_cache/_mc2_features.parquet", "data_cache/_mc3_features.parquet"]
OUT_STATE = "data_cache/_mc5_state.pkl"
OUT_FEAT = "data_cache/_mc5_features.parquet"
TMP_STATE = "data_cache/_mc5_state.build.pkl"
TMP_FEAT = "data_cache/_mc5_features.build.parquet"


def _fp(p):
    if not os.path.exists(p):
        return None
    h = hashlib.md5()                                              # noqa: S324
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


before = {p: _fp(p) for p in GUARD}
print("MC5 build: KS=%g, MOV_W=%g (inherited from MC3)" % (MC5_KS, MC5_MOV_W))

src = open(SRC, encoding="utf-8").read()
src = SW.apply_surface_transform(src, int(MC5_KS))
src = SW.apply_mov_transform(src, MC5_MOV_W)

# the richer history: result, opponent-adjusted serve residual, and the surface
old = "    # ---- updates ----"
assert src.count(old) == 1
src = src.replace(old, """    _h5won = float(won)
    _h5srv = float(spw_a - (bs + Sa - Rb)) if not np.isnan(spw_a) else 0.0
""" + old)
# the per-(year, surface) season tally. Initialised on the state dict and updated AFTER the
# feature row is emitted, so what a match reads is strictly its prior season.
old = '              "pw": 0.0, "pa": 0.0,'
assert src.count(old) == 1
src = src.replace(old, old + '\n              "seas": {},')
old = "    a[\"n\"] += 1; b[\"n\"] += 1; a[\"ns\"][s] += 1; b[\"ns\"][s] += 1"
assert src.count(old) == 1, src.count(old)
src = src.replace(old, old + """
    _yk = (int(t.date.year), s)
    for _st9, _w9 in ((a, won), (b, 1.0 - won)):
        _t9 = _st9["seas"].setdefault(_yk, [0.0, 0])
        _t9[0] += float(_w9)
        _t9[1] += 1""")

old = 'st9["hist"].append((t.date, _ns9, _rt9))'
assert src.count(old) == 1
src = src.replace(old, 'st9["hist"].append((t.date, _ns9, _rt9, _h5won, _h5srv, s))')
old = '''        if len(st9["hist"]) > 12:
            st9["hist"] = st9["hist"][-12:]'''
assert src.count(old) == 1
src = src.replace(old, '''        if len(st9["hist"]) > 40:
            st9["hist"] = st9["hist"][-40:]''')

src = src.replace('"data_cache/_mc2_features.parquet"', '"%s"' % TMP_FEAT)
src = src.replace('"data_cache/_mc2_state.pkl"', '"%s"' % TMP_STATE)
for bad in ('to_parquet("data_cache/_mc2_features.parquet")',
            'open("data_cache/_mc2_state.pkl"', 'open("data_cache/_mc3_state.pkl"'):
    assert bad not in src, "would overwrite a live artifact: %s" % bad

g = {"__name__": "__mc5_build__", "__file__": SRC}
exec(compile(src, SRC + "(mc5)", "exec"), g)                       # noqa: S102
del g

for a, b in ((TMP_STATE, OUT_STATE), (TMP_FEAT, OUT_FEAT)):
    assert os.path.exists(a), "builder did not produce %s" % a
    os.replace(a, b)
    print("   -> %s  (%.1f MB)" % (b, os.path.getsize(b) / 1e6))

after = {p: _fp(p) for p in GUARD}
for p in GUARD:
    assert before[p] == after[p], "MC5 BUILD TOUCHED %s" % p
print("MC2/MC3 artifacts verified unchanged")

import tennis_mc5 as M5                                            # noqa: E402

st = M5._state()
assert st, "MC5 state did not load"
pl = st["players"]
rich = sum(1 for v in pl.values()
           if v.get("hist") and len(v["hist"][-1]) > 5)
deep = sum(1 for v in pl.values() if len(v.get("hist") or []) > 12)
seas = sum(1 for v in pl.values() if v.get("seas"))
print("MC5 state: %d players | %d carry the 6-field history | %d have >12 entries | %d have a season tally"
      % (len(pl), rich, deep, seas))
assert rich > 0.9 * len(pl), "the richer history did not land on most players"
