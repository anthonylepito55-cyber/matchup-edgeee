"""
analyze_xfip_seasonal_drift.py

One-off validation, follow-up to analyze_xfip_siera_fix.py: does xfip_diff/siera_diff actually
get MORE useful as the season progresses, the way you'd expect if the fix is doing what it's
supposed to (each walk-forward estimate is backed by more accumulated batted balls later in the
season than in April)? If true, that's independent evidence the fix is working as designed, not
just a backtest number that happened to move.

Pools both seasons (2025 full, 2026 through mid-July) by CALENDAR month — 2026 alone has no
August/September yet, so "September" here means "every September game in the dataset," not one
specific season. Restricted to April-September per the request; March (spring training / opening
week, ~140 games total, distinct sample-size regime) is excluded.

Four angles, all against Model A (baseball-only, what's actually served):
  1. Feature distribution: xfip_diff/siera_diff/xera_diff coverage, mean, std per month — raw
     input distribution, independent of any model.
  2. Feature importance: XGBoost gain-based importance, per WALK-FORWARD FOLD (not per calendar
     month — a fold trained through August has seen more mature walk-forward estimates in its
     training data than one trained only through May, so this is "importance as more of the
     season has been observed," a related but distinct axis from #3/#4 below).
  3. SHAP: mean |SHAP value| for held-out predictions, bucketed by the PREDICTED GAME's calendar
     month (not the fold) — "how much did xfip_diff actually move this specific prediction,"
     averaged within each month.
  4. Permutation importance: within each month's held-out subset, shuffle xfip_diff and measure
     the Brier-score degradation using that row's own fold model — "how much would performance
     specifically on May games suffer if xfip_diff were useless," month by month.

Run directly:
    python analyze_xfip_seasonal_drift.py
"""

import numpy as np
import pandas as pd
import shap

import model as model_module
from features import BASEBALL_ONLY_FEATURE_COLUMNS
from build_training_data import TRAINING_CACHE
from sklearn.metrics import brier_score_loss

N_FOLDS = 5
MONTHS = [4, 5, 6, 7, 8, 9]
MONTH_NAMES = {4: "April", 5: "May", 6: "June", 7: "July", 8: "August", 9: "September"}
FOCUS_FEATURES = ["xfip_diff", "siera_diff", "xera_diff"]
PERM_SHUFFLES = 30
RNG = np.random.default_rng(42)


def main():
    df = pd.read_parquet(TRAINING_CACHE).sort_values("game_date").reset_index(drop=True)
    df["month"] = pd.to_datetime(df["game_date"]).dt.month
    print(f"Loaded {len(df)} historical games (pooling 2025 + 2026 by calendar month).\n")

    # --- 1. Feature distribution by month (full dataset, not just held-out) ---
    print("=== 1. Feature distribution by month (all games, both seasons pooled) ===")
    dist_rows = []
    for m in MONTHS:
        sub = df[df["month"] == m]
        row = {"month": MONTH_NAMES[m], "n_games": len(sub)}
        for feat in FOCUS_FEATURES:
            row[f"{feat}_coverage"] = f"{sub[feat].notna().mean():.1%}"
            row[f"{feat}_std"] = round(sub[feat].std(skipna=True), 3)
        dist_rows.append(row)
    print(pd.DataFrame(dist_rows).to_string(index=False))

    # --- Walk-forward folds: collect fold models + held-out predictions with SHAP ---
    fold_size = len(df) // (N_FOLDS + 1)
    fold_importances = []
    shap_rows = []  # per held-out row: month, feature -> |shap value|
    perm_pool = {}  # month -> list of (fold_idx, row_index_in_test, y_true)
    fold_models = {}
    fold_test_X = {}
    fold_medians = {}

    for fold in range(1, N_FOLDS + 1):
        train_end = fold_size * fold
        test_end = fold_size * (fold + 1)
        train_df = df.iloc[:train_end]
        test_df = df.iloc[train_end:test_end]
        if len(train_df) < 50 or len(test_df) < 10:
            continue

        model_obj, medians, _ = model_module.train(train_df, save=False, feature_columns=BASEBALL_ONLY_FEATURE_COLUMNS)
        X_test = test_df[BASEBALL_ONLY_FEATURE_COLUMNS].fillna(medians)
        fold_models[fold] = model_obj
        fold_test_X[fold] = (X_test, test_df)
        fold_medians[fold] = medians

        # 2. Gain-based importance for THIS fold's trained model (avg across the internal
        # CalibratedClassifierCV estimators, same way predict_proba averages their outputs).
        boosters = [cc.estimator for cc in model_obj.calibrated_classifiers_]
        gain_matrix = np.array([b.feature_importances_ for b in boosters])
        avg_gain = gain_matrix.mean(axis=0)
        fold_importances.append({
            "fold": fold, "train_through": train_df["game_date"].max(),
            **{feat: avg_gain[BASEBALL_ONLY_FEATURE_COLUMNS.index(feat)] for feat in FOCUS_FEATURES},
        })

        # 3. SHAP — average across the same internal boosters, TreeExplainer on raw margin output.
        shap_values_per_booster = []
        for b in boosters:
            explainer = shap.TreeExplainer(b)
            shap_values_per_booster.append(explainer.shap_values(X_test))
        avg_shap = np.mean(shap_values_per_booster, axis=0)  # (n_rows, n_features)
        for i, (_, row) in enumerate(test_df.iterrows()):
            entry = {"month": row["month"]}
            for feat in FOCUS_FEATURES:
                entry[feat] = avg_shap[i, BASEBALL_ONLY_FEATURE_COLUMNS.index(feat)]
            shap_rows.append(entry)

        for i, (_, row) in enumerate(test_df.iterrows()):
            perm_pool.setdefault(row["month"], []).append((fold, i))

        print(f"Fold {fold}: trained through {train_df['game_date'].max()}, "
              f"{len(test_df)} held-out games ({test_df['month'].min()}-{test_df['month'].max()} range)")

    print("\n=== 2. Gain-based feature importance, by walk-forward fold (chronological progression) ===")
    print(pd.DataFrame(fold_importances).to_string(index=False))

    print("\n=== 3. SHAP: mean |SHAP value| on held-out predictions, by the predicted game's month ===")
    shap_df = pd.DataFrame(shap_rows)
    shap_summary = []
    for m in MONTHS:
        sub = shap_df[shap_df["month"] == m]
        if sub.empty:
            continue
        row = {"month": MONTH_NAMES[m], "n": len(sub)}
        for feat in FOCUS_FEATURES:
            row[feat] = round(sub[feat].abs().mean(), 4)
        shap_summary.append(row)
    print(pd.DataFrame(shap_summary).to_string(index=False))

    # --- 4. Permutation importance by month ---
    print(f"\n=== 4. Permutation importance by month ({PERM_SHUFFLES} shuffles/month, Brier-score degradation) ===")
    perm_summary = []
    for m in MONTHS:
        entries = perm_pool.get(m, [])
        if len(entries) < 10:
            continue
        row = {"month": MONTH_NAMES[m], "n": len(entries)}
        for feat in FOCUS_FEATURES:
            feat_idx = BASEBALL_ONLY_FEATURE_COLUMNS.index(feat)
            degradations = []
            for _ in range(PERM_SHUFFLES):
                baseline_probs, perm_probs, y_true = [], [], []
                # Group by fold so each row uses its OWN fold's model, but shuffle feat values
                # only within this month's pooled subset (across folds) for a stable permutation.
                by_fold = {}
                for fold_idx, row_i in entries:
                    by_fold.setdefault(fold_idx, []).append(row_i)
                all_feat_vals = []
                for fold_idx, row_idxs in by_fold.items():
                    X_test, test_df = fold_test_X[fold_idx]
                    all_feat_vals.extend(X_test.iloc[row_idxs][feat].tolist())
                shuffled_vals = RNG.permutation(all_feat_vals)
                cursor = 0
                for fold_idx, row_idxs in by_fold.items():
                    X_test, test_df = fold_test_X[fold_idx]
                    model_obj = fold_models[fold_idx]
                    base_probs = model_obj.predict_proba(X_test.iloc[row_idxs])[:, 1]
                    X_perm = X_test.iloc[row_idxs].copy()
                    n = len(row_idxs)
                    X_perm[feat] = shuffled_vals[cursor:cursor + n]
                    cursor += n
                    perturbed_probs = model_obj.predict_proba(X_perm)[:, 1]
                    y = test_df.iloc[row_idxs]["home_win"].astype(int).values
                    baseline_probs.extend(base_probs)
                    perm_probs.extend(perturbed_probs)
                    y_true.extend(y)
                base_brier = brier_score_loss(y_true, baseline_probs)
                perm_brier = brier_score_loss(y_true, perm_probs)
                degradations.append(perm_brier - base_brier)
            row[feat] = round(float(np.mean(degradations)), 5)
        perm_summary.append(row)
    print(pd.DataFrame(perm_summary).to_string(index=False))

    print("\n=== Hypothesis check: does xfip_diff's SHAP/permutation-importance rise April -> September? ===")
    shap_series = pd.DataFrame(shap_summary).set_index("month")["xfip_diff"] if shap_summary else None
    perm_series = pd.DataFrame(perm_summary).set_index("month")["xfip_diff"] if perm_summary else None
    if shap_series is not None:
        print("SHAP |value| by month:", dict(shap_series))
    if perm_series is not None:
        print("Permutation importance (Brier degradation) by month:", dict(perm_series))


if __name__ == "__main__":
    main()
