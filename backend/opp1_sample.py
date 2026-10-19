"""OPP1 v3.5 — key K, deduplication, deterministic one-pass thinning, registered-blob seed,
and the (inactive) accrual-counter logic.

Seed: int(sha256(registered_file_bytes).hexdigest()[:16], 16) over the EXACT registered
git-blob bytes of OPP1_SPEC_V3_5_PROPOSAL.md at commit b0f59fb — never a working copy, whose
line endings may differ. registered_seed() verifies the blob's sha256 against the registered
value and refuses to return a seed otherwise.

PURE FUNCTIONS over passed-in frames; the only I/O is the local `git show` of the frozen blob.
The accrual counter here is logic only — nothing in this module reads live data, and nothing
schedules or activates anything.
"""
from __future__ import annotations

import hashlib
import math
import subprocess

import numpy as np
import pandas as pd

REG_COMMIT = "b0f59fb"
REG_BLOB_PATH = "OPP1_SPEC_V3_5_PROPOSAL.md"
REG_SHA256 = "7539adbbafc84d2257dfafd52982f3f756e52cfb83aa974db3366243c90ba56e"

# ---- registered minimums (v3.5 §4) ---------------------------------------------------------
DE_PLAN = 1.5
DEV_RAW_MIN = 12000          # 8,000 effective x DE_plan
DEV_ISO_MONTHS_MIN = 9
DEV_TIERS_MIN = 3
TIER_RAW_MIN = 2250          # 1,500 effective x DE_plan
TIER_ISO_WEEKS_MIN = 12
CAP_FRAC = 0.10


def seed_from_bytes(blob: bytes) -> int:
    """int(sha256(registered_file_bytes).hexdigest()[:16], 16); refuses non-registered bytes."""
    h = hashlib.sha256(blob).hexdigest()
    if h != REG_SHA256:
        raise ValueError("bytes do not hash to the registered sha256 (%s... != %s...)"
                         % (h[:12], REG_SHA256[:12]))
    return int(h[:16], 16)


def registered_seed(repo_root: str) -> int:
    """Read the frozen blob via `git show b0f59fb:OPP1_SPEC_V3_5_PROPOSAL.md` (local git only)."""
    blob = subprocess.run(["git", "show", "%s:%s" % (REG_COMMIT, REG_BLOB_PATH)],
                          cwd=repo_root, capture_output=True, check=True).stdout
    return seed_from_bytes(blob)


# ---- owner-approved domain-separated RNG policy (adopted 2026-10-19) -----------------------
SEED_LABELS = ("boot:dev", "boot:tier1", "boot:tier2", "perm:dev", "perm:tier1", "perm:tier2")


def derive_seed(label: str) -> int:
    """Deterministic analysis-stage RNG seeds (owner-approved implementation rule):
        seed(L) = int(sha256((REG + "|" + L).encode("utf-8")).hexdigest()[:16], 16)
    where REG is the registered spec sha256 as the 64-char lowercase hex STRING and the first
    16 hex digest characters are read as a big-endian unsigned 64-bit integer.
    Label map: boot:dev / boot:tier1 / boot:tier2 seed that stage's cluster bootstrap;
    perm:dev / perm:tier1 / perm:tier2 seed that stage's permutation integrity check. Each
    stage initializes its numpy RNG once from its assigned seed. These streams are
    DOMAIN-SEPARATED AND REPRODUCIBLE — not claimed mathematically collision-proof.
    The registered THINNING seed (registered_seed/seed_from_bytes above) is a separate,
    registered rule and is unchanged by this policy."""
    if label not in SEED_LABELS:
        raise ValueError("unknown RNG label %r; approved labels: %s" % (label, (SEED_LABELS,)))
    return int(hashlib.sha256((REG_SHA256 + "|" + label).encode("utf-8")).hexdigest()[:16], 16)


def iso_week(ts: pd.Timestamp) -> str:
    """ISO-8601 year-week of the scheduled start_date, UTC, formatted %G-W%V (v3.5 V1)."""
    t = ts if ts.tzinfo else ts.tz_localize("UTC")
    return t.tz_convert("UTC").strftime("%G-W%V")


def key_k(tournament_norm: str, start_ts: pd.Timestamp) -> tuple:
    """The shared key K = (tournament_norm, ISO year-week). One definition for the 10% cap AND
    the cluster bootstrap."""
    return (tournament_norm, iso_week(start_ts))


def dedup(df: pd.DataFrame) -> pd.DataFrame:
    """One row per unique match: deterministic keep-first on ascending fixture_id."""
    return (df.sort_values("fixture_id", kind="mergesort")
              .drop_duplicates("fixture_id", keep="first").reset_index(drop=True))


def thin(df: pd.DataFrame, seed: int):
    """Deterministic ONE-PASS thinning (v3.5 §4 Q1/B3).
    df: evaluated-candidate rows with columns fixture_id and K (tuple).
    cap_size = floor(0.10 x N_pre) against the FIXED pre-thinning denominator; caps are never
    recomputed after thinning; keys processed in ascending tuple order; within a key rows sorted
    by ascending fixture_id; one rng; drawn indices are the rows KEPT.
    Returns (kept_df, info)."""
    n_pre = int(len(df))
    cap = math.floor(CAP_FRAC * n_pre)
    info = {"n_pre": n_pre, "cap_size": cap, "thinned": 0, "keys_capped": [],
            "boundary_fail_cap0": cap == 0}
    if cap == 0:
        return df.copy().reset_index(drop=True), info   # no thinning; boundary check fails
    rng = np.random.default_rng(seed)
    kept_parts = []
    for k in sorted(df["K"].unique()):                   # tuple ordering, no serialization
        g = df[df["K"] == k].sort_values("fixture_id", kind="mergesort")
        if len(g) <= cap:
            kept_parts.append(g)
            continue
        idx = rng.choice(len(g), size=cap, replace=False)  # drawn indices are KEPT
        kept_parts.append(g.iloc[np.sort(idx)])
        info["thinned"] += int(len(g) - cap)
        info["keys_capped"].append(k)
    out = (pd.concat(kept_parts, ignore_index=True)
             .sort_values("fixture_id", kind="mergesort").reset_index(drop=True))
    return out, info


def per_key_shares(df: pd.DataFrame) -> pd.Series:
    """Final post-thinning per-key shares — mandated in every results report; the cap bounds
    the PRE-thinning contribution and does NOT guarantee these stay <= 10%."""
    return df["K"].value_counts() / max(len(df), 1)


def dev_counts(df: pd.DataFrame) -> dict:
    """Outcome-free accrual counter on the FINAL POST-THINNING evaluated set (v3.5 D4).
    df: columns start (tz-aware), league, K."""
    months = df["start"].dt.tz_convert("UTC").dt.strftime("%Y-%m").nunique()
    tiers = df["league"].nunique()
    n = int(len(df))
    return {"n_raw": n, "iso_months": int(months), "tiers": int(tiers),
            "meets_dev_minimums": (n >= DEV_RAW_MIN and months >= DEV_ISO_MONTHS_MIN
                                   and tiers >= DEV_TIERS_MIN)}


def tier_counts(df: pd.DataFrame) -> dict:
    weeks = df["start"].dt.tz_convert("UTC").dt.strftime("%G-W%V").nunique()
    n = int(len(df))
    return {"n_raw": n, "iso_weeks": int(weeks),
            "meets_tier_minimums": (n >= TIER_RAW_MIN and weeks >= TIER_ISO_WEEKS_MIN)}
