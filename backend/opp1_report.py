"""OPP1 v3.5 — report assembly, non-gating analysis wrappers, and the N1 post-thinning guard.

Everything here consumes PASSED-IN data only; no store/log/live access exists in this module.
Registered obligations implemented:
- N5: per-tier coverage/missingness with NUMERATOR AND DENOMINATOR on every percentage, and
  quote-age median/p90 per venue per tier.
- Per-label exclusion counts (naive-interpreted timestamps, validation pending/resolved,
  taxonomy labels, ambiguous linkage, metadata-incomplete, ...), reported separately.
- Final post-thinning per-key shares (the cap bounds the PRE-thinning contribution only).
- A-O2 frozen-MC2 reconstructed-row counts.
- Kalshi-only and E3-ablation readouts — REGISTERED NON-GATING, and marked so.
- Accrual / results report structures (coverage before any metric).
"""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

import opp1_eval as EV
import opp1_sample as SA

# every label gets its own line even at zero, so reports never silently drop a category
CANONICAL_LABELS = (
    "ts_naive_interpreted", "ts_missing", "ts_malformed", "ts_date_only_not_eligibility",
    "validation_pending", "validation_resolved", "analyst_exposure_excluded",
    "before_dev_cutoff", "postponed", "void", "status_contradictory", "rescheduled_gt6h",
    "reschedule_unverifiable", "retirement_unresolved", "ambiguous_linkage", "no_candidate",
    "metadata_incomplete",
)


def exclusion_report(label_lists) -> dict:
    """Counts per label over an iterable of per-row label lists; zero rows included."""
    c = Counter(l for labels in label_lists for l in labels)
    out = {lab: int(c.get(lab, 0)) for lab in CANONICAL_LABELS}
    for lab in c:                           # never drop an unexpected label silently
        out.setdefault(lab, int(c[lab]))
    return out


def coverage_staleness_report(feat_df: pd.DataFrame, tier_col: str = "league") -> dict:
    """N5: per tier, per feature: missing numerator / eligible denominator / pct, plus
    quote-age median and p90 per venue."""
    out = {}
    ind_cols = [c for c in feat_df.columns if c.endswith("_ind")]
    for tier, g in feat_df.groupby(tier_col):
        den = int(len(g))
        feats = {}
        for c in ind_cols:
            num = int(g[c].fillna(1).astype(int).sum())
            feats[c[:-4]] = {"missing_n": num, "den": den,
                             "missing_pct": round(100.0 * num / den, 2) if den else None}
        ages = {}
        for v in ("K", "PM"):
            col = "age_%s_s" % v
            a = g[col].dropna() if col in g else pd.Series(dtype=float)
            ages[v] = {"n": int(len(a)),
                       "median_s": float(a.median()) if len(a) else None,
                       "p90_s": float(a.quantile(0.9)) if len(a) else None}
        out[str(tier)] = {"eligible_denominator": den, "features": feats, "quote_age": ages}
    return out


def mc2_recon_report(feat_df: pd.DataFrame) -> dict:
    """A-O2: count of rows forced onto the missing-value path by mc2_recon."""
    n = int(feat_df.get("mc2_recon_affected", pd.Series(dtype=int)).fillna(0).sum())
    return {"mc2_recon_affected_n": n, "den": int(len(feat_df))}


def per_key_share_table(df: pd.DataFrame) -> dict:
    """Final post-thinning per-key shares, numerators and denominator explicit. The registered
    cap bounds the PRE-thinning contribution and does NOT guarantee these stay <= 10%."""
    n = int(len(df))
    counts = df["K"].value_counts()
    return {"den": n, "keys": {str(k): {"n": int(v), "share_pct": round(100.0 * v / n, 2)}
                               for k, v in counts.items()}}


def assert_post_thinning(df: pd.DataFrame, thin_info: dict) -> None:
    """N1 guard: the accrual minimum counters must receive the FINAL POST-THINNING EVALUATED
    population (v3.5 D4). Raises otherwise."""
    if "evaluated" in df.columns and not bool(df["evaluated"].all()):
        raise AssertionError("counter input contains non-evaluated rows (D4 violation)")
    expect = thin_info["n_pre"] - thin_info["thinned"]
    if len(df) != expect:
        raise AssertionError("counter input is not the post-thinning set: %d rows, expected %d"
                             % (len(df), expect))
    cap = thin_info["cap_size"]
    if cap > 0 and int(df["K"].value_counts().max()) > cap:
        raise AssertionError("a key exceeds cap_size=%d — input was not thinned" % cap)


def accrual_report(evaluated_df: pd.DataFrame, thin_info: dict, label_lists,
                   feat_df: pd.DataFrame | None = None) -> dict:
    """The registered accrual report: guard first, pure counts only (no outcome analysis)."""
    assert_post_thinning(evaluated_df, thin_info)
    rep = {"counts": SA.dev_counts(evaluated_df),
           "tier_counts": SA.tier_counts(evaluated_df),
           "thinning": {k: thin_info[k] for k in ("n_pre", "cap_size", "thinned",
                                                  "boundary_fail_cap0")},
           "per_key_shares": per_key_share_table(evaluated_df),
           "exclusions": exclusion_report(label_lists)}
    if feat_df is not None:
        rep["coverage"] = coverage_staleness_report(feat_df)
        rep["mc2"] = mc2_recon_report(feat_df)
    return rep


# ---------------------------------------------------------------- non-gating readout wrappers
def kalshi_only_cols(e_cols) -> list:
    """The Kalshi-only feature subset (v3.5 §3 robustness readout): the per-venue _K columns
    and their indicators. E3 is venue-pooled, not Kalshi-only, so it is NOT in this subset —
    an implementation reading, disclosed; the readout is non-gating either way."""
    return [c for c in e_cols if "_K" in c]


def _readout(df, e_cols, seed_boot):
    scored, _ = EV.walk_forward(df, e_cols)
    if not len(scored):
        return {"non_gating": True, "note": "no scored rows"}
    con = EV.contrasts(scored)
    out = {"non_gating": True}
    for h in ("H1", "H2"):
        s = EV.cluster_bootstrap(con[h], scored["K"].values, seed=seed_boot)
        out[h] = {"mean": s["mean"], "t": s["t"], "ci95": s["ci95"], "n": s["n"]}
    return out


def kalshi_only_readout(df, e_cols, seed_boot) -> dict:
    """Registered NON-GATING robustness readout: H1/H2 re-estimated on the Kalshi-only subset.
    Never gates any decision in this or any future version."""
    return _readout(df, kalshi_only_cols(e_cols), seed_boot)


def e3_ablation_readout(df, e_cols, seed_boot) -> dict:
    """Registered NON-GATING readout: M2/M3 re-estimated without E3/E3_ind, published with the
    primary result. Never gates any decision."""
    kept = [c for c in e_cols if c not in ("E3", "E3_ind")]
    return _readout(df, kept, seed_boot)


def results_report(coverage: dict, exclusions: dict, per_key: dict, mc2: dict,
                   stats: dict, readouts: dict) -> dict:
    """Registered results structure: coverage tables come BEFORE any metric (v3.5 §3)."""
    return {"1_coverage": coverage, "2_exclusions": exclusions, "3_per_key_shares": per_key,
            "4_mc2_recon": mc2, "5_primary_stats": stats,
            "6_non_gating_readouts": {k: dict(v, non_gating=True)
                                      for k, v in readouts.items()}}
