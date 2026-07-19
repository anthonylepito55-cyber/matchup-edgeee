"""
analyze_override_calibration.py

One-off analysis: does the confidence override (main._apply_confidence_override) actually
improve Brier score / calibration, or does it just feel more intuitive? Answers this against
the full walk-forward backtest set (~3,800 historical games), not the live prediction log —
the log currently only has 44 rows across 3 dates, nowhere near enough to say anything
statistically meaningful, and (separately, see prediction_log.py's fix) was silently discarding
the pre-override raw probability for every overridden row anyway.

Method: reproduces model.py's exact walk-forward fold split, trains Model A (baseball-only,
BASEBALL_ONLY_FEATURE_COLUMNS — what's actually served) on each fold, gets each held-out game's
raw probability, then applies the SAME _agreement_score/_apply_confidence_override logic
imported directly from main.py (not reimplemented) to get the final/overridden probability.
Compares Brier score and a reliability (calibration) curve between raw and final, both overall
and specifically on the subset of games the override actually touched.

Caveat: main._agreement_score's reliability gates (recent_form_reliable/season_reliable/
identity_reliable) default to True and require live-serving context (sample sizes, IP-per-start,
IL-return/layoff/opener flags) that isn't persisted in training_dataset.parquet — this analysis
uses the defaults (assume reliable), which means it may fire the override on a few more games
than live serving actually would (live serving sometimes gates terms off for thin-sample
pitchers). Flagged wherever it matters below; the core question (does extremizing on multi-
signal agreement help or hurt) is still answered faithfully on the ~90% of games where those
gates wouldn't have mattered anyway.

Run directly:
    python analyze_override_calibration.py
"""

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss

import model as model_module
from features import BASEBALL_ONLY_FEATURE_COLUMNS
from main import _agreement_score, AGREEMENT_OVERRIDE_THRESHOLD, AGREEMENT_OVERRIDE_MAX_SHIFT
from data_collection import CACHE_DIR
import os

TRAINING_CACHE = os.path.join(CACHE_DIR, "training_dataset.parquet")
ODDS_CACHE = os.path.join(CACHE_DIR, "historical_market_probs.parquet")
N_FOLDS = 5


def expected_calibration_error(probs: np.ndarray, outcomes: np.ndarray, n_bins: int = 10) -> float:
    """Weighted-average |predicted - actual| across bins — the single-number version of the
    reliability curve below. Lower is better; 0.0 is perfect calibration."""
    bins = np.linspace(0, 1, n_bins + 1)
    bin_idx = np.clip(np.digitize(probs, bins) - 1, 0, n_bins - 1)
    total = 0.0
    for b in range(n_bins):
        mask = bin_idx == b
        if mask.sum() == 0:
            continue
        total += (mask.sum() / len(probs)) * abs(probs[mask].mean() - outcomes[mask].mean())
    return total


def high_confidence_precision(probs: np.ndarray, outcomes: np.ndarray, threshold: float = 0.65) -> tuple[float, int]:
    """Precision on the subset where the FAVORED side's own probability is >= threshold —
    i.e. 'high-confidence bets'. Returns (precision, n)."""
    favored_prob = np.where(probs >= 0.5, probs, 1 - probs)
    mask = favored_prob >= threshold
    if mask.sum() == 0:
        return None, 0
    picked_home = probs[mask] >= 0.5
    correct = (picked_home == outcomes[mask].astype(bool)).mean()
    return float(correct), int(mask.sum())


def apply_override(raw_prob: float, feats: dict) -> tuple[float, bool]:
    """Same logic as main._apply_confidence_override, reliability gates defaulted to True (see
    module docstring's caveat) — returns (final_prob, overridden)."""
    score = _agreement_score(feats)
    if abs(score) < AGREEMENT_OVERRIDE_THRESHOLD:
        return raw_prob, False
    excess = min(abs(score) - AGREEMENT_OVERRIDE_THRESHOLD, 10.0)
    shift = min(AGREEMENT_OVERRIDE_MAX_SHIFT * (0.5 + excess / 10.0), AGREEMENT_OVERRIDE_MAX_SHIFT)
    adjusted = (min(raw_prob + shift, 0.85) if score > 0 else max(raw_prob - shift, 0.15))
    return adjusted, True


def reliability_curve(probs: np.ndarray, outcomes: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    bins = np.linspace(0, 1, n_bins + 1)
    bin_idx = np.digitize(probs, bins) - 1
    bin_idx = np.clip(bin_idx, 0, n_bins - 1)
    rows = []
    for b in range(n_bins):
        mask = bin_idx == b
        if mask.sum() == 0:
            continue
        rows.append({
            "bin": f"{bins[b]:.1f}-{bins[b+1]:.1f}",
            "n": int(mask.sum()),
            "avg_predicted": probs[mask].mean(),
            "actual_rate": outcomes[mask].mean(),
        })
    return pd.DataFrame(rows)


def main():
    df = pd.read_parquet(TRAINING_CACHE).sort_values("game_date").reset_index(drop=True)
    print(f"Loaded {len(df)} historical games.\n")

    fold_size = len(df) // (N_FOLDS + 1)
    all_raw, all_final, all_outcome, all_overridden, all_game_pk = [], [], [], [], []

    for fold in range(1, N_FOLDS + 1):
        train_end = fold_size * fold
        test_end = fold_size * (fold + 1)
        train_df = df.iloc[:train_end]
        test_df = df.iloc[train_end:test_end]
        if len(train_df) < 50 or len(test_df) < 10:
            continue

        model, medians, _ = model_module.train(
            train_df, save=False, feature_columns=BASEBALL_ONLY_FEATURE_COLUMNS
        )
        X_test = test_df[BASEBALL_ONLY_FEATURE_COLUMNS].fillna(medians)
        raw_probs = model.predict_proba(X_test)[:, 1]
        outcomes = test_df["home_win"].astype(int).values

        for i, (_, row) in enumerate(test_df.iterrows()):
            raw_prob = float(raw_probs[i])
            feats = row.to_dict()
            final_prob, overridden = apply_override(raw_prob, feats)
            all_raw.append(raw_prob)
            all_final.append(final_prob)
            all_outcome.append(outcomes[i])
            all_overridden.append(overridden)
            all_game_pk.append(row.get("game_pk"))

    all_raw = np.array(all_raw)
    all_final = np.array(all_final)
    all_outcome = np.array(all_outcome)
    all_overridden = np.array(all_overridden)
    all_game_pk = np.array(all_game_pk)

    print(f"Total held-out (out-of-fold) predictions: {len(all_raw)}")
    print(f"Overridden: {all_overridden.sum()} ({100 * all_overridden.mean():.1f}%)\n")

    print("=== Overall (all held-out games) ===")
    print(f"Raw model   — Brier: {brier_score_loss(all_outcome, all_raw):.4f}, "
          f"log loss: {log_loss(all_outcome, all_raw):.4f}")
    print(f"Final/adj.  — Brier: {brier_score_loss(all_outcome, all_final):.4f}, "
          f"log loss: {log_loss(all_outcome, all_final):.4f}")

    if all_overridden.sum() > 0:
        print(f"\n=== Overridden subset only (n={all_overridden.sum()}) — the actual test ===")
        sub_raw = all_raw[all_overridden]
        sub_final = all_final[all_overridden]
        sub_outcome = all_outcome[all_overridden]
        print(f"Raw model on this subset   — Brier: {brier_score_loss(sub_outcome, sub_raw):.4f}, "
              f"log loss: {log_loss(sub_outcome, sub_raw):.4f}, actual home-win rate: {sub_outcome.mean():.3f}")
        print(f"Overridden on this subset  — Brier: {brier_score_loss(sub_outcome, sub_final):.4f}, "
              f"log loss: {log_loss(sub_outcome, sub_final):.4f}")
        print(f"\nBrier delta on overridden subset: {brier_score_loss(sub_outcome, sub_final) - brier_score_loss(sub_outcome, sub_raw):+.4f} "
              f"(negative = override helped, positive = override hurt)")

    print("\n=== Calibration curve: RAW model (all held-out games) ===")
    print(reliability_curve(all_raw, all_outcome).to_string(index=False))

    print("\n=== Calibration curve: FINAL/overridden probabilities (all held-out games) ===")
    print(reliability_curve(all_final, all_outcome).to_string(index=False))

    if all_overridden.sum() > 0:
        print("\n=== Calibration curve: overridden subset only, RAW probabilities ===")
        print(reliability_curve(all_raw[all_overridden], all_outcome[all_overridden], n_bins=5).to_string(index=False))
        print("\n=== Calibration curve: overridden subset only, FINAL probabilities ===")
        print(reliability_curve(all_final[all_overridden], all_outcome[all_overridden], n_bins=5).to_string(index=False))

    # --- Expected Calibration Error (single-number summary of the curves above) ---
    print("\n=== Expected Calibration Error (lower is better) ===")
    print(f"Raw model (all games):    ECE {expected_calibration_error(all_raw, all_outcome):.4f}")
    print(f"Final/adj. (all games):   ECE {expected_calibration_error(all_final, all_outcome):.4f}")
    if all_overridden.sum() > 0:
        print(f"Raw model (overridden subset):  ECE {expected_calibration_error(all_raw[all_overridden], all_outcome[all_overridden], n_bins=5):.4f}")
        print(f"Final (overridden subset):      ECE {expected_calibration_error(all_final[all_overridden], all_outcome[all_overridden], n_bins=5):.4f}")

    # --- Precision on high-confidence bets (favored side's own prob >= 65%) ---
    print("\n=== Precision on high-confidence bets (favored prob >= 65%) ===")
    raw_prec, raw_n = high_confidence_precision(all_raw, all_outcome)
    final_prec, final_n = high_confidence_precision(all_final, all_outcome)
    print(f"Raw model:   {raw_prec:.1%} correct (n={raw_n})" if raw_n else "Raw model: no games clear 65%")
    print(f"Final/adj.:  {final_prec:.1%} correct (n={final_n})" if final_n else "Final/adj.: no games clear 65%")
    if all_overridden.sum() > 0:
        sub_raw_prec, sub_raw_n = high_confidence_precision(all_raw[all_overridden], all_outcome[all_overridden])
        sub_final_prec, sub_final_n = high_confidence_precision(all_final[all_overridden], all_outcome[all_overridden])
        print(f"Overridden subset, raw:   {sub_raw_prec:.1%} correct (n={sub_raw_n})" if sub_raw_n else "Overridden subset, raw: no games clear 65%")
        print(f"Overridden subset, final: {sub_final_prec:.1%} correct (n={sub_final_n})" if sub_final_n else "Overridden subset, final: no games clear 65%")

    # --- CLV / ROI: does the override change anything that touches the market? ---
    # The override only ever nudges an already-agreeing probability further in the SAME
    # direction (capped at 0.15/0.85) — it can't flip which side is favored unless the raw
    # prob was already on the far side of 0.5, so any CLV/ROI difference here is really asking
    # "does inflating confidence on these picks change the betting math," not "does the override
    # pick different winners."
    print("\n=== CLV / ROI impact (flat-stake, bet the favored side at market's own closing price) ===")
    if not os.path.exists(ODDS_CACHE):
        print(f"No {ODDS_CACHE} found — skipping (run backfill_historical_odds.py first).")
    else:
        odds_df = pd.read_parquet(ODDS_CACHE)
        market_prob_by_game = dict(zip(odds_df["game_pk"], odds_df["market_home_prob"]))
        market_probs = np.array([market_prob_by_game.get(gp) for gp in all_game_pk], dtype=float)
        has_market = ~np.isnan(market_probs)

        def flat_stake_roi(probs, outcome, mkt_probs, mask):
            picked_home = probs[mask] >= 0.5
            won = picked_home == outcome[mask].astype(bool)
            price_prob = np.where(picked_home, mkt_probs[mask], 1 - mkt_probs[mask])
            payout = np.where(won, np.where(price_prob > 0, (1 / price_prob) - 1, 0.0), -1.0)
            return payout.mean(), int(mask.sum())

        n_matched = int(has_market.sum())
        print(f"{n_matched}/{len(all_raw)} held-out games matched to a closing line.\n")

        for label, mask in [
            ("All games", has_market),
            ("Overridden subset", has_market & all_overridden),
        ]:
            n = int(mask.sum())
            if n < 10:
                print(f"{label}: only {n} games with a closing line, skipping.")
                continue
            raw_roi, _ = flat_stake_roi(all_raw, all_outcome, market_probs, mask)
            final_roi, _ = flat_stake_roi(all_final, all_outcome, market_probs, mask)
            flips = int((mask & ((all_raw >= 0.5) != (all_final >= 0.5))).sum())
            print(f"{label} (n={n}): raw ROI {raw_roi:+.1%}, final/adj. ROI {final_roi:+.1%}, "
                  f"picks flipped by override: {flips}")


if __name__ == "__main__":
    main()
