"""
build_and_train_model_f5.py -- trains the F5 model (model_f5.py) and validates it the only way
that matters for betting: walk-forward, against the F5 market's own prices.

Reports (and writes to model_artifacts/model_f5_validation.json):
  * OOF AUC / Brier / log-loss on decided-after-5 games, 5 folds x 5 seeds
  * on the subset with an F5 market close: model vs MARKET Brier/AUC apples-to-apples
  * betting sim via model_e.compute_bet at the F5 market (fair odds): underdog/favorite n,
    hit rate vs implied, ROI, per-fold stability, threshold sensitivity
Then trains the final 5-seed ensemble on all decided games -> model_artifacts/model_f5.joblib.

Run after build_f5_labels.py (required) and backfill_f5_odds.py (market comparison is only as
complete as that backfill is -- re-run this once it finishes):
    python build_and_train_model_f5.py
"""
import json
import time

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

import model as model_module
import model_e
import model_f5
from build_training_data import TRAINING_CACHE
from features import FEATURE_COLUMNS

N_FOLDS = 5
SEEDS = model_module.ENSEMBLE_SEEDS


def score(p, y):
    return {"brier": float(brier_score_loss(y, p)), "logloss": float(log_loss(y, p)),
            "auc": float(roc_auc_score(y, p)), "n": int(len(y))}


def main():
    df = model_f5.training_frame(pd.read_parquet(TRAINING_CACHE))
    y = df[model_f5.LABEL_COL].values
    print(f"{len(df)} decided-after-5 games {df['game_date'].min()} -> {df['game_date'].max()}; "
          f"home F5 win rate {y.mean():.3f}; F5 market close on {int(df['f5_market_home_prob'].notna().sum())}", flush=True)

    fold_size = len(df) // (N_FOLDS + 1)
    oof = np.full(len(df), np.nan)
    fold_id = np.full(len(df), -1)
    t0 = time.time()
    for fold in range(1, N_FOLDS + 1):
        tr_end, te_end = fold_size * fold, fold_size * (fold + 1)
        train_df, test_idx = df.iloc[:tr_end], np.arange(tr_end, te_end)
        test_df = df.iloc[test_idx]
        fold_id[test_idx] = fold
        ps = []
        for seed in SEEDS:
            m, med, _ = model_module.train(train_df, model_f5.LABEL_COL, save=False, feature_columns=FEATURE_COLUMNS, random_state=seed)
            ps.append(m.predict_proba(test_df[FEATURE_COLUMNS].fillna(med))[:, 1])
        oof[test_idx] = np.mean(ps, axis=0)
        print(f"  fold {fold} ({time.time()-t0:.0f}s)", flush=True)

    scored = fold_id > 0
    rep = {"n_games": int(len(df)), "all": score(oof[scored], y[scored])}
    print(f"\nOOF all decided games: AUC {rep['all']['auc']:.4f}  Brier {rep['all']['brier']:.4f}  (n={rep['all']['n']})")

    mkt = df["f5_market_home_prob"].values
    has = scored & ~np.isnan(mkt)
    if has.sum() >= 50:
        rep["market_subset"] = {"model": score(oof[has], y[has]), "market": score(mkt[has], y[has])}
        print(f"F5-market subset (n={int(has.sum())}): model AUC {rep['market_subset']['model']['auc']:.4f} Brier {rep['market_subset']['model']['brier']:.4f}"
              f" | MARKET AUC {rep['market_subset']['market']['auc']:.4f} Brier {rep['market_subset']['market']['brier']:.4f}")

        def sim(thr):
            rows = []
            model_e.UNDERDOG_THRESHOLD = model_e.FAVORITE_THRESHOLD = thr
            for i in np.where(has)[0]:
                bet = model_e.compute_bet(float(oof[i]), float(mkt[i]), "H", "A")
                if not bet:
                    continue
                won = bool(y[i]) if bet["side_is_home"] else not bool(y[i])
                rows.append((fold_id[i], bet["type"], won, bet["market_prob"], (1 / bet["market_prob"] - 1) if won else -1.0))
            model_e.UNDERDOG_THRESHOLD = model_e.FAVORITE_THRESHOLD = 0.02
            return pd.DataFrame(rows, columns=["fold", "type", "won", "mkt", "pnl"])

        d = sim(0.02)
        bet_rep = {}
        print("\nBetting vs F5 market @0.02, fair odds:")
        for t, sub in list(d.groupby("type")) + [("all", d)]:
            bet_rep[t] = {"n": int(len(sub)), "hit_rate": round(sub["won"].mean(), 4), "market_implied": round(sub["mkt"].mean(), 4),
                          "roi_fair_odds_pct": round(100 * sub["pnl"].mean(), 2)}
            print(f"  {t:9s} n={len(sub):4d} hit {sub['won'].mean():.3f} implied {sub['mkt'].mean():.3f} ROI {100*sub['pnl'].mean():+.2f}%")
        pf = d.groupby("fold")["pnl"].agg(["size", "mean"])
        print("  per-fold ROI:", "  ".join(f"f{int(k)} {100*v['mean']:+.1f}% (n={int(v['size'])})" for k, v in pf.iterrows()))
        sens = {}
        for thr in (0.02, 0.04, 0.06, 0.08):
            dd = sim(thr)
            sens[str(thr)] = {"n": int(len(dd)), "roi": round(100 * dd["pnl"].mean(), 2) if len(dd) else None}
        print("  threshold sensitivity:", "  ".join(f"{k}: {v['roi']:+.1f}% n={v['n']}" if v['roi'] is not None else f"{k}: —" for k, v in sens.items()))
        rep["betting_fair_odds"] = bet_rep
        rep["per_fold_roi"] = {int(k): {"n": int(v["size"]), "roi": round(100 * v["mean"], 2)} for k, v in pf.iterrows()}
        rep["threshold_sensitivity"] = sens
    else:
        print("F5 market backfill not far enough along for a market comparison yet -- re-run after backfill_f5_odds.py")

    print("\n--- Training final F5 ensemble (5 seeds) ---", flush=True)
    _, _, metrics = model_module.train_ensemble(df, label_col=model_f5.LABEL_COL, feature_columns=FEATURE_COLUMNS, model_path=model_f5.MODEL_F5_PATH)
    print(f"Validation AUC {metrics['auc']:.4f} Brier {metrics['brier_score']:.4f} -> {model_f5.MODEL_F5_PATH}")
    rep["ensemble_val_metrics"] = metrics
    rep["trained_at"] = pd.Timestamp.utcnow().isoformat()
    with open(model_f5.MODEL_F5_VALIDATION_PATH, "w") as f:
        json.dump(rep, f, indent=1, default=float)
    print(f"Wrote {model_f5.MODEL_F5_VALIDATION_PATH}")


if __name__ == "__main__":
    main()
