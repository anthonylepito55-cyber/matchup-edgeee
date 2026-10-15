"""AS-OF BACKFILL OF MC6 ONTO PAST GAMES (2026-10-15).

User: "can u make mc6 show up on previous day tabs". Wiring the display was not enough -- mc6_p1
only started being written today, so every earlier day showed no chip. This fills them.

WHAT IS COMPUTED, and why it is leak-free:

    MC6 = sigmoid( logit(MC5) + 0.25*h2h + 0.50*sform )

  MC5          taken from the ledger's own frozen mc5_p1. Not recomputed -- recomputing it from
               today's ratings is exactly the stale-state contamination that forced the recon
               rebuild on 2026-10-14, and the frozen column is already the right number.
  h2h          recency-weighted head-to-head over meetings STRICTLY BEFORE that match's date,
               weighted from that date, not from today. A meeting two days before the match must
               count as two days old, not as however old it is now.
  sform        EWMA of (result - what Elo expected) on that surface over that player's matches
               STRICTLY BEFORE the match.

Both terms are rebuilt per row with a date cutoff, which is the same shape as the MC3 as-of fill
of 2026-10-13. Nothing can see its own result or any later one.

EVERY FILLED ROW IS STAMPED mc6_recon = True. It is a replay, not a pick that was ever shown, so
it must stay out of the forward lanes and must render dimmed with a leading "~". Rows that already
carry a genuine forward mc6_p1 are left alone.

A row whose mc5_p1 is itself a recon produces an MC6 that inherits that -- which is correct and is
why the stamp matters more than the number.

Written through a temp copy and validated before replacing the log, with a .bak.

Run: ./venv/bin/python _mc6_history_backfill.py [--dry]
"""
import bisect
import math
import os
import re
import shutil
import sys

import numpy as np
import pandas as pd

import tennis_log
from tennis_mc6 import MC6_HL_DAYS, MC6_MARG_W, MC6_SFORM_CAP, MC6_WH, MC6_WS

DRY = "--dry" in sys.argv
DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- the archive, indexed as-of
F = pd.read_parquet(os.path.join(DIR, "data_cache", "_mc2_features.parquet"),
                    columns=["date", "a", "b", "surf", "won", "p_elo", "score"])
F["date"] = pd.to_datetime(F["date"], errors="coerce")
F = F[F["date"].notna() & F["a"].notna() & F["b"].notna() & F["won"].notna() & F["p_elo"].notna()]
F = F.sort_values("date", kind="stable").reset_index(drop=True)
print("archive rows: %d  (%s .. %s)" % (len(F), F.date.min().date(), F.date.max().date()),
      flush=True)


def _margin(s):
    if not isinstance(s, str) or not s:
        return 0.0
    d = n = 0
    for x, y in re.findall(r"(\d+)\s*[-:]\s*(\d+)", s):
        x, y = int(x), int(y)
        if x > 30 or y > 30:
            continue
        d += x - y
        n += 1
    return float(d) if n else 0.0


A = F["a"].astype(str).to_numpy()
B = F["b"].astype(str).to_numpy()
SU = F["surf"].astype(str).to_numpy()
WON = F["won"].astype(bool).to_numpy()
PE = F["p_elo"].to_numpy(float)
DAY = F["date"].astype("int64").to_numpy() / 86_400_000_000_000.0
MG = F["score"].map(_margin).to_numpy(float)

# pair -> sorted [(day, won_by_first, margin_for_first)]
H2H = {}
for i in range(len(F)):
    fa = A[i] < B[i]
    key = (A[i], B[i]) if fa else (B[i], A[i])
    H2H.setdefault(key, []).append((DAY[i], bool(WON[i]) if fa else (not bool(WON[i])),
                                    MG[i] if fa else -MG[i]))
for k in H2H:
    H2H[k].sort(key=lambda x: x[0])
# (player, surface) -> sorted days + residuals, for the as-of EWMA
SF = {}
for i in range(len(F)):
    SF.setdefault((A[i], SU[i]), []).append((DAY[i], float(WON[i]) - PE[i]))
    SF.setdefault((B[i], SU[i]), []).append((DAY[i], (0.0 if WON[i] else 1.0) - (1.0 - PE[i])))
for k in SF:
    SF[k].sort(key=lambda x: x[0])
SF_KEYS = {k: [d for d, _ in v] for k, v in SF.items()}
print("pairs %d   (player,surface) cells %d" % (len(H2H), len(SF)), flush=True)

HL_MATCH = 5.0


def h2h_asof(s1, s2, day):
    fa = s1 < s2
    mts = H2H.get((s1, s2) if fa else (s2, s1))
    if not mts:
        return 0.0
    wsum = shr = mrg = 0.0
    for d, wf, mf in mts:
        if d >= day:            # STRICTLY prior
            break
        w = 0.5 ** ((day - d) / MC6_HL_DAYS)
        wsum += w
        shr += w * (1.0 if wf else 0.0)
        mrg += w * mf
    if wsum <= 0:
        return 0.0
    share = shr / wsum - 0.5
    marg = max(min((mrg / wsum) / 6.0, 1.5), -1.5)
    raw = (1.0 - MC6_MARG_W) * (2.0 * share) + MC6_MARG_W * marg
    return (1.0 if fa else -1.0) * raw * (wsum / (wsum + 1.0))


def sform_asof(slug, surf, day):
    key = (slug, surf)
    arr = SF.get(key)
    if not arr:
        return None
    j = bisect.bisect_left(SF_KEYS[key], day)      # strictly prior
    if j <= 0:
        return None
    num = den = 0.0
    for d, r in arr[max(0, j - 60):j][::-1]:
        pass
    # exponential by MATCH count, most recent first, matching the live state's ewm(halflife=5)
    k = 0
    for d, r in arr[:j][::-1]:
        w = 0.5 ** (k / HL_MATCH)
        num += w * r
        den += w
        k += 1
        if k >= 80:
            break
    return (num / den) if den > 0 else None


# ---------------------------------------------------------------- the log
log = pd.read_parquet(tennis_log.LOG_PATH)
for c in ("mc6_p1", "mc6_recon"):
    if c not in log.columns:
        log[c] = np.nan
need = log["mc5_p1"].notna() & log["mc6_p1"].isna()
print("log rows %d   with mc5_p1 %d   to fill %d"
      % (len(log), int(log["mc5_p1"].notna().sum()), int(need.sum())), flush=True)

try:
    from tennis_mc2 import _slug, _surf
except Exception as e:  # noqa: BLE001
    raise SystemExit("cannot import slug resolver: %s" % e)

lg = lambda p: math.log(max(min(float(p), 1 - 1e-6), 1e-6)
                        / (1 - max(min(float(p), 1 - 1e-6), 1e-6)))
filled = skipped = noslug = 0
idx = log.index[need]
for i in idx:
    r = log.loc[i]
    try:
        d = pd.to_datetime(r.get("date"), errors="coerce")
        if pd.isna(d):
            skipped += 1
            continue
        day = d.value / 86_400_000_000_000.0
        surface = r.get("surface")
        s1, s2 = _slug(r.get("player_1"), surface), _slug(r.get("player_2"), surface)
        if not s1 or not s2:
            noslug += 1
            continue
        su = _surf(surface)
        h = h2h_asof(s1, s2, day)
        a = sform_asof(s1, su, day)
        b = sform_asof(s2, su, day)
        sf = 0.0 if (a is None and b is None) else max(
            min((a or 0.0) - (b or 0.0), MC6_SFORM_CAP), -MC6_SFORM_CAP)
        z = lg(r["mc5_p1"]) + MC6_WH * h + MC6_WS * sf
        log.at[i, "mc6_p1"] = round(1.0 / (1.0 + math.exp(-z)), 4)
        log.at[i, "mc6_recon"] = True
        filled += 1
    except Exception:  # noqa: BLE001
        skipped += 1

print("filled %d   no-slug %d   skipped %d" % (filled, noslug, skipped))
if filled:
    f = log.loc[log["mc6_recon"] == True, ["mc5_p1", "mc6_p1"]].dropna()  # noqa: E712
    dd = (f["mc6_p1"] - f["mc5_p1"]).abs()
    print("mean |MC6-MC5| on filled rows %.4f   max %.4f   moved >2pt: %d (%.0f%%)"
          % (dd.mean(), dd.max(), int((dd > 0.02).sum()), 100 * (dd > 0.02).mean()))

if DRY:
    print("dry run -- nothing written")
    raise SystemExit(0)
if not filled:
    print("nothing to write")
    raise SystemExit(0)

tmp = tennis_log.LOG_PATH + ".tmp"
log.to_parquet(tmp, index=False)
chk = pd.read_parquet(tmp)
assert len(chk) == len(log), "row count changed"
assert int(chk["mc6_p1"].notna().sum()) >= filled, "mc6_p1 did not persist"
shutil.copy2(tennis_log.LOG_PATH, tennis_log.LOG_PATH + ".bak")
os.replace(tmp, tennis_log.LOG_PATH)
print("wrote log; mc6_p1 now on %d rows (%d forward, %d recon)"
      % (int(chk["mc6_p1"].notna().sum()),
         int((chk["mc6_p1"].notna() & (chk["mc6_recon"] != True)).sum()),   # noqa: E712
         int((chk["mc6_recon"] == True).sum())))                            # noqa: E712
print("RESULT: OK")
