"""MARGIN-AWARE ELO FOR MC2/MC3 (2026-10-13, user: "yes but dont ship unless it helps").

Elo is updated on the BINARY result alone:

    a["elo"] += K * (won - p_elo)

so 6-0 6-0 and 7-6 7-6 move a rating identically, and the score -- present on 100% of 170,000
rows -- is discarded. Elo carries half of MC2/MC3's blended probability, and Tier 3's fit said
it arguably deserves 0.7, so this is the largest piece of information either head throws away.

METHOD: margin-of-victory as a MULTIPLIER on K, not as a replacement for the outcome.

    mov  = |games_won - games_lost| / total_games      in (0, 1]
    mult = clip(1 + MOV_W * (mov - MOV_REF), 0.5, 2.0)

A win stays a win -- only the SIZE of the rating move changes -- which is the standard
margin-of-victory treatment and the conservative one. Replacing the outcome with a games share
would let a 6-0 6-0 loss score above a 7-6 7-6 win, which is simply wrong.

Deliberately uses |mov|, not a signed margin, so both players' updates scale by the same factor
and the result cannot depend on which side the score string is written from. A dominant win
moves the winner up more AND the loser down more, which is the intent.

MOV_REF = 0.25 is roughly the typical match (6-4 6-4 is 12-8, i.e. 0.20), so mult sits near 1
for an ordinary result and the sweep is centred rather than inflating every update.

    MOV_W = 0   is the CONTROL and must reproduce shipped MC3 to four decimals
    MOV_W = 0.5 / 1.0 / 1.5 / 2.0

Everything else is shipped MC3: per-surface serve/return at KS=20, best-of-five from the score,
the same sigma and the same 50/50 blend. Scoring reuses the engine-faithful live_blend.

Abandoned matches and unparseable scores get mult = 1.0: a match nobody finished has no
meaningful margin, and inventing one would feed the exact garbage the abandonment audit found.

Run: ./venv/bin/python _mc3_mov_sweep.py [build|score] [W ...]   (W given in tenths, e.g. 15)
"""
import gc
import os
import sys

import numpy as np
import pandas as pd

import _mc2_surface_sr_sweep as SW
from _mc2_shrink_sweep import live_blend
from tennis_mc3 import MC3_KS

SRC = "_mc2_stage1b_serve_return.py"
WS = [0, 5, 10, 15, 20, 30, 40]   # tenths of MOV_W; 30/40 added to BRACKET the
                                  # optimum -- shipping a value at the edge of a
                                  # swept range is how an artifact gets shipped
FEAT = "data_cache/_mc2_features_mov%d.parquet"
KS = int(MC3_KS)
MOV_REF = 0.25

HELPER = '''def _mov_mult(score, mov_w, ref=%r):
    """K multiplier from the games margin. 1.0 when there is no usable margin."""
    if mov_w <= 0 or not isinstance(score, str) or not score.strip():
        return 1.0
    gw = gl = 0
    nsets = 0
    for tok in score.split():
        t = tok.split("(")[0]
        if "-" not in t:
            continue
        x, _, y = t.partition("-")
        try:
            x, y = int(x), int(y)
        except ValueError:
            continue
        gw += x
        gl += y
        nsets += 1
    tot = gw + gl
    if tot < 6 or nsets < 2:
        # an abandoned match or a fragment: no meaningful margin, so do not invent one
        return 1.0
    mov = abs(gw - gl) / float(tot)
    m = 1.0 + mov_w * (mov - ref)
    return min(max(m, 0.5), 2.0)


''' % MOV_REF


def build(w10):
    mov_w = w10 / 10.0
    src = open(SRC, encoding="utf-8").read()

    # the helper, placed just before the chronological loop
    anchor = "AF = 0.12"
    assert src.count(anchor) == 1
    src = src.replace(anchor, HELPER + anchor)

    # compute the multiplier once per match, before any Elo update
    anchor = "    # ---- updates ----"
    assert src.count(anchor) == 1, src.count(anchor)
    src = src.replace(anchor, anchor + ("\n    _mv = _mov_mult(t.score, %r)" % mov_w))

    # scale every Elo K by it -- overall and surface, both players
    pairs = [
        ('    K = 250.0 / (5 + a["n"]) + 5.0',
         '    K = (250.0 / (5 + a["n"]) + 5.0) * _mv'),
        ('    K2 = 250.0 / (5 + b["n"]) + 5.0',
         '    K2 = (250.0 / (5 + b["n"]) + 5.0) * _mv'),
        ('    a["elo_s"][s] += (250.0 / (5 + a["ns"][s]) + 5.0) * (won - pse)',
         '    a["elo_s"][s] += (250.0 / (5 + a["ns"][s]) + 5.0) * _mv * (won - pse)'),
        ('    b["elo_s"][s] += (250.0 / (5 + b["ns"][s]) + 5.0) * ((1 - won) - (1 - pse))',
         '    b["elo_s"][s] += (250.0 / (5 + b["ns"][s]) + 5.0) * _mv * ((1 - won) - (1 - pse))'),
    ]
    for old, new in pairs:
        assert src.count(old) == 1, (old, src.count(old))
        src = src.replace(old, new)

    # and keep MC3's per-surface serve/return, by reusing the validated transform
    src = SW.apply_surface_transform(src, KS)
    src = src.replace('"data_cache/_mc2_features.parquet"', '"%s"' % (FEAT % w10))
    src = src.replace('"data_cache/_mc2_state.pkl"',
                      '"data_cache/_mc2_state_mov%d.pkl"' % w10)
    for bad in ('to_parquet("data_cache/_mc2_features.parquet")',
                'open("data_cache/_mc2_state.pkl"'):
        assert bad not in src, "would overwrite production: %s" % bad
    print("=" * 78)
    print("BUILD MOV_W=%.1f%s  ->  %s"
          % (mov_w, "  (CONTROL: must reproduce shipped MC3)" if w10 == 0 else "",
             FEAT % w10))
    print("=" * 78)
    sys.stdout.flush()
    g = {"__name__": "__mov_sweep__", "__file__": SRC}
    exec(compile(src, SRC + "(mov=%.1f)" % mov_w, "exec"), g)      # noqa: S102
    del g
    gc.collect()


def score():
    from sklearn.metrics import roc_auc_score
    out = {}
    for w10 in WS:
        p = FEAT % w10
        if not os.path.exists(p):
            print("   (missing %s)" % p)
            continue
        F = pd.read_parquet(p, columns=["year", "p_elo", "pa_pt", "pb_pt", "nS_a", "nS_b",
                                        "imp", "won", "surf"])
        F = F[F["imp"].notna() & F["won"].notna() & F["pa_pt"].notna()
              & F["pb_pt"].notna() & F["p_elo"].notna()]
        F = F[(F["nS_a"] >= 4) & (F["nS_b"] >= 4)].copy()
        F["mc3"], _ = live_blend(F)
        out[w10] = F
        print("   MOV_W=%.1f scored %d" % (w10 / 10.0, len(F)))
        gc.collect()
    if not out:
        return
    BAR = "=" * 96

    def lab(w10):
        return "binary (CONTROL)" if w10 == 0 else "MOV_W=%.1f" % (w10 / 10.0)

    print("\n" + BAR)
    print("MARGIN-AWARE ELO -- MC3's blend, by year")
    print(BAR)
    print("   %-20s" % "variant" + "".join("%26s" % y for y in (2024, 2025, 2026)))
    for w10, F in out.items():
        line = "   %-20s" % lab(w10)
        for y in (2024, 2025, 2026):
            g = F[F["year"] == y]
            if len(g) < 300:
                line += "%26s" % "--"
                continue
            line += "%26s" % ("AUC %.4f  Brier %.4f"
                              % (roc_auc_score(g["won"], g["mc3"]),
                                 float(((g["mc3"] - g["won"]) ** 2).mean())))
        print(line)
    F0 = out[WS[0]]
    line = "   %-20s" % "market"
    for y in (2024, 2025, 2026):
        g = F0[F0["year"] == y]
        line += "%26s" % ("AUC %.4f  Brier %.4f"
                          % (roc_auc_score(g["won"], g["imp"]),
                             float(((g["imp"] - g["won"]) ** 2).mean())))
    print(line)

    print("\n" + BAR)
    print("OVERALL, and the market gap -- a win must hold on ALL THREE measures")
    print(BAR)
    for w10, F in out.items():
        p = F["mc3"].to_numpy()
        w = F["won"].to_numpy(dtype=float)
        m = F["imp"].to_numpy(dtype=float)
        print("   %-20s AUC %.4f  Brier %.4f  |model-mkt| %5.2fpt"
              % (lab(w10), roc_auc_score(w, p), float(((p - w) ** 2).mean()),
                 100 * float(np.abs(p - m).mean())))


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "score"
    ws = [int(x) for x in sys.argv[2:]] or WS
    if what == "build":
        for w in ws:
            build(w)
    else:
        score()
