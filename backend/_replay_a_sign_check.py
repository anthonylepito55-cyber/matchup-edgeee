"""WHY DOESN'T THE REPLAY REPRODUCE MODEL A? (2026-10-09)

The wrong-court replay reproduces the frozen Model B / C / c75 / D almost exactly (0.0-1.5pt
mean difference, 93-100% same side) but Model A is 10.2pt off and picks the same side only 48.5%
of the time. Hypothesis: those 33 rows were all logged BEFORE the 2026-10-09 rank-sign fix
(every one has ac_v = null), so the frozen A was computed with the rank gap the wrong way round
while the replay uses the corrected code.

Test: recompute A for those rows twice -- with today's (fixed) sign and with the rank feature
negated back to the buggy convention -- and see which one lands on the frozen number. If the
negated version matches, the discrepancy is the old bug and the replay's A is the better figure.
"""
import numpy as np
import pandas as pd

import tennis_model_a as A
import tennis_surface_replay as R

F = pd.read_parquet("data_cache/_surface_fix_history.parquet")
G = F[F.model_a_p1.notna()].copy()
G["d"] = G.date.astype(str).str[:10]
d = G.d.value_counts().index[0]
S = G[G.d == d]
print(f"testing {len(S)} rows from {d} (the date with the most frozen-A wrong-court rows)\n")

_orig = A._feats


def flipped(p1, p2, surface, h):
    f = _orig(p1, p2, surface, h)
    f["d_lrank"] = -f["d_lrank"]          # back to the pre-fix convention
    return f


R.set_asof(d)
rows = []
for _, r in S.iterrows():
    A._feats = _orig
    fixed = A.predict(r.player_1, r.player_2, r.surface_logged, None)
    A._feats = flipped
    buggy = A.predict(r.player_1, r.player_2, r.surface_logged, None)
    A._feats = _orig
    rows.append({"p1": r.player_1, "frozen": float(r.model_a_p1),
                 "fixed_sign": (fixed or {}).get("p1_prob"),
                 "buggy_sign": (buggy or {}).get("p1_prob")})
D = pd.DataFrame(rows).dropna()
D["err_fixed"] = (D.fixed_sign - D.frozen).abs()
D["err_buggy"] = (D.buggy_sign - D.frozen).abs()
print(D.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
print(f"\nmean |replay - frozen| with TODAY'S (fixed) sign : {100 * D.err_fixed.mean():.1f}pt")
print(f"mean |replay - frozen| with the OLD (buggy) sign : {100 * D.err_buggy.mean():.1f}pt")
print(f"same side as frozen -- fixed {100 * ((D.fixed_sign >= .5) == (D.frozen >= .5)).mean():.0f}% | "
      f"buggy {100 * ((D.buggy_sign >= .5) == (D.frozen >= .5)).mean():.0f}%")
verdict = ("the OLD BUGGY sign reproduces the frozen numbers -> the gap is the pre-10-09 "
           "rank-sign bug, and the replay's A is the corrected one"
           if D.err_buggy.mean() < D.err_fixed.mean() else
           "NEITHER sign explains it -- something else differs; do not trust the replay's A")
print(f"\nVERDICT: {verdict}")
R.release()
