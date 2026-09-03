"""
build_and_train_model_e.py -- trains Model E (see model_e.py) and, more importantly, decides
its calibration layer with a leakage-free walk-forward test, then reports raw-vs-calibrated
on both calibration metrics AND betting outcomes. Writes:

    model_artifacts/model_e.joblib             5-seed ensemble, Model B's recipe on MODEL_E_FEATURE_COLUMNS
    model_artifacts/model_e_calibrator.joblib  chosen Calibrator (identity / platt / isotonic)
    model_artifacts/model_e_validation.json    everything printed below, for the UI/API

Method:
  * 5 chronological folds, 5 seeds each (same split as model.backtest_ensemble) -> out-of-fold
    RAW ensemble probs for every game outside fold-1's training block.
  * Calibrator selection is NESTED: for each fold k >= 3, fit each candidate calibrator on the
    OOF probs of folds < k only, apply to fold k. So every calibrated probability scored here
    was produced by a calibrator that never saw that game -- no "fit on the set you score" bias.
  * Candidates: identity (== Model B), Platt (2-param logistic on the logit), isotonic.
    Chosen by mean nested-OOF Brier; ties -> simpler. The winner is refit on ALL OOF probs and
    saved. If identity wins, Model E's probabilities are Model B's -- reported as such.
  * Betting outcomes: the exact model_e.compute_bet selection (underdog/favorite, 0.02) on the
    market-covered games, hit rate vs market-implied and ROI at FAIR (de-vigged) odds, for raw
    vs calibrated. Real ROI will be lower by the vig (~2% Pinnacle / 4-5% soft books) -- this is
    the edge before price, apples-to-apples with revalidate_value_bet_types.py.

Run: python build_and_train_model_e.py
"""
import json
import time

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

import model as model_module
import model_e
from build_training_data import TRAINING_CACHE

N_FOLDS = 5
SEEDS = model_module.ENSEMBLE_SEEDS
CANDIDATES = ["identity", "platt", "isotonic"]
MIN_CAL_FOLD = 3  # first fold evaluated with a calibrator fitted on earlier folds' OOF


def score(p, y):
    return {"brier": float(brier_score_loss(y, p)), "logloss": float(log_loss(y, p)),
            "auc": float(roc_auc_score(y, p)), "ece": model_e.expected_calibration_error(p, y), "n": int(len(y))}


def betting_outcomes(p_home, mkt_home, y):
    """Apply model_e's side selection at FAIR odds (no book prices historically) per type."""
    out = {}
    rows = []
    for p, m, yy in zip(p_home, mkt_home, y):
        if np.isnan(m):
            continue
        bet = model_e.compute_bet(float(p), float(m), "H", "A", book_prices=None, live_odds=None)
        if not bet:
            continue
        won = bool(yy) if bet["side_is_home"] else not bool(yy)
        fair_dec = 1.0 / bet["market_prob"]  # pay-out if you got the de-vigged market price
        rows.append((bet["type"], won, bet["market_prob"], bet["model_prob"], fair_dec))
    df = pd.DataFrame(rows, columns=["type", "won", "mkt", "model", "dec"])
    for t, sub in df.groupby("type"):
        profit = (sub["won"] * (sub["dec"] - 1) - (~sub["won"]) * 1.0).sum()
        out[t] = {"n": int(len(sub)), "hit_rate": round(sub["won"].mean(), 4),
                  "market_implied": round(sub["mkt"].mean(), 4), "model_avg": round(sub["model"].mean(), 4),
                  "edge_pts": round(sub["won"].mean() - sub["mkt"].mean(), 4),
                  "roi_fair_odds_pct": round(100 * profit / len(sub), 2)}
    if len(df):
        profit = (df["won"] * (df["dec"] - 1) - (~df["won"]) * 1.0).sum()
        out["all"] = {"n": int(len(df)), "hit_rate": round(df["won"].mean(), 4),
                      "roi_fair_odds_pct": round(100 * profit / len(df), 2)}
    return out


def main():
    df = pd.read_parquet(TRAINING_CACHE).sort_values("game_date").reset_index(drop=True)
    df = df[df["home_win"].notna()].reset_index(drop=True)
    print(f"{len(df)} games {df['game_date'].min()} -> {df['game_date'].max()}; {N_FOLDS} folds x {len(SEEDS)} seeds", flush=True)

    fold_size = len(df) // (N_FOLDS + 1)
    raw_oof = np.full(len(df), np.nan)
    fold_id = np.full(len(df), -1)
    t0 = time.time()
    for fold in range(1, N_FOLDS + 1):
        tr_end, te_end = fold_size * fold, fold_size * (fold + 1)
        train_df, test_idx = df.iloc[:tr_end], np.arange(tr_end, te_end)
        test_df = df.iloc[test_idx]
        fold_id[test_idx] = fold
        seed_probs = []
        for seed in SEEDS:
            m, med, _ = model_module.train(train_df, "home_win", save=False, feature_columns=model_e.MODEL_E_FEATURE_COLUMNS, random_state=seed)
            seed_probs.append(m.predict_proba(test_df[model_e.MODEL_E_FEATURE_COLUMNS].fillna(med))[:, 1])
        raw_oof[test_idx] = np.mean(seed_probs, axis=0)
        print(f"  fold {fold} OOF done ({time.time()-t0:.0f}s)", flush=True)

    y_all = df["home_win"].astype(int).values
    mkt_all = (0.5 + df["consensus_prob_diff"]).values

    # ---- nested calibrator selection ------------------------------------------------------
    print("\n=== Nested walk-forward calibration test (calibrator fit on earlier folds' OOF only) ===")
    nested = {c: {"p": [], "y": [], "m": []} for c in CANDIDATES}
    for k in range(MIN_CAL_FOLD, N_FOLDS + 1):
        fit_mask, eval_mask = (fold_id > 0) & (fold_id < k), fold_id == k
        for c in CANDIDATES:
            cal = model_e.Calibrator(c).fit(raw_oof[fit_mask], y_all[fit_mask])
            nested[c]["p"].append(cal.transform(raw_oof[eval_mask]))
            nested[c]["y"].append(y_all[eval_mask])
            nested[c]["m"].append(mkt_all[eval_mask])
    report = {"n_games": int(len(df)), "folds_evaluated": list(range(MIN_CAL_FOLD, N_FOLDS + 1)), "candidates": {}}
    for c in CANDIDATES:
        p = np.concatenate(nested[c]["p"]); y = np.concatenate(nested[c]["y"]); m = np.concatenate(nested[c]["m"])
        s = score(p, y)
        b = betting_outcomes(p, m, y)
        report["candidates"][c] = {"calibration": s, "betting_fair_odds": b}
        print(f"\n[{c}]  brier {s['brier']:.5f}  logloss {s['logloss']:.5f}  auc {s['auc']:.4f}  ece {s['ece']:.4f}  (n={s['n']})")
        for t, v in b.items():
            extra = f"  market-implied {v['market_implied']:.3f}  edge {v['edge_pts']:+.3f}" if "market_implied" in v else ""
            print(f"    {t:9s} n={v['n']:4d}  hit {v['hit_rate']:.3f}{extra}  ROI@fair {v['roi_fair_odds_pct']:+.2f}%")

    briers = {c: report["candidates"][c]["calibration"]["brier"] for c in CANDIDATES}
    # simplest candidate within 0.0001 Brier of the best wins -- isotonic's extra wiggle has to pay for itself
    best = min(briers.values())
    chosen = next(c for c in CANDIDATES if briers[c] <= best + 1e-4)
    report["chosen"] = chosen
    report["brier_gain_vs_identity"] = round(briers["identity"] - briers[chosen], 6)
    print(f"\nCHOSEN calibrator: {chosen}  (Brier gain vs identity {report['brier_gain_vs_identity']:+.6f})")

    # ---- final fit: ensemble on all data, calibrator on ALL OOF ------------------------------
    print("\n--- Training final Model E ensemble (Model B recipe, 5 seeds) ---", flush=True)
    _, _, metrics = model_module.train_ensemble(df, feature_columns=model_e.MODEL_E_FEATURE_COLUMNS, model_path=model_e.MODEL_E_PATH)
    print(f"Validation Brier {metrics['brier_score']:.4f}  AUC {metrics['auc']:.4f}  -> {model_e.MODEL_E_PATH}")
    oof_mask = fold_id > 0
    cal = model_e.Calibrator(chosen).fit(raw_oof[oof_mask], y_all[oof_mask])
    model_e.save_calibrator(cal)
    print(f"Calibrator '{chosen}' fit on {cal.n_fit} OOF games -> {model_e.MODEL_E_CALIBRATOR_PATH}")

    # ---- baseball-only leg: same 13 factors, no market; OOF vs Model A on identical folds -------
    print("\n--- Baseball-only leg (MODEL_E_BASEBALL_COLUMNS, no market) vs Model A, same folds ---", flush=True)
    from features import BASEBALL_ONLY_FEATURE_COLUMNS
    leg_oof, a_oof = np.full(len(df), np.nan), np.full(len(df), np.nan)
    for fold in range(1, N_FOLDS + 1):
        tr_end, te_end = fold_size * fold, fold_size * (fold + 1)
        train_df, test_df = df.iloc[:tr_end], df.iloc[tr_end:te_end]
        for cols, arr in ((model_e.MODEL_E_BASEBALL_COLUMNS, leg_oof), (BASEBALL_ONLY_FEATURE_COLUMNS, a_oof)):
            ps = []
            for seed in SEEDS:
                m, med, _ = model_module.train(train_df, "home_win", save=False, feature_columns=cols, random_state=seed)
                ps.append(m.predict_proba(test_df[cols].fillna(med))[:, 1])
            arr[tr_end:te_end] = np.mean(ps, axis=0)
    leg = {"baseball_leg": score(leg_oof[oof_mask], y_all[oof_mask]), "model_a_same_folds": score(a_oof[oof_mask], y_all[oof_mask])}
    print(f"  E-baseball AUC {leg['baseball_leg']['auc']:.4f} Brier {leg['baseball_leg']['brier']:.4f} | Model A AUC {leg['model_a_same_folds']['auc']:.4f} Brier {leg['model_a_same_folds']['brier']:.4f}")
    _, _, leg_metrics = model_module.train_ensemble(df, feature_columns=model_e.MODEL_E_BASEBALL_COLUMNS, model_path=model_e.MODEL_E_BASEBALL_PATH)
    print(f"  saved baseball leg -> {model_e.MODEL_E_BASEBALL_PATH} (val AUC {leg_metrics['auc']:.4f})")
    report["baseball_leg"] = leg

    report["ensemble_val_metrics"] = metrics
    report["trained_at"] = pd.Timestamp.utcnow().isoformat()
    with open(model_e.MODEL_E_VALIDATION_PATH, "w") as f:
        json.dump(report, f, indent=1, default=float)
    print(f"Wrote {model_e.MODEL_E_VALIDATION_PATH}")


if __name__ == "__main__":
    main()
