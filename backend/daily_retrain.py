"""
daily_retrain.py

Meant to run once a day (see the scheduled job that calls this). Pulls whatever new completed
games happened since the last run (incremental — see build_training_data.fetch_season_schedule_
with_pitchers), retrains every model on the updated dataset, and only deploys (commits + pushes
model_artifacts/) if the retrained "Model A" candidates — the PRIMARY served predictions for both
win-prob and strikeout-props, see main.py — don't backtest worse than whatever's currently live.
A regression just gets logged and skipped; nothing about production changes on a bad day.

Run manually:
    python daily_retrain.py
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from data_collection import CACHE_DIR
import build_training_data
import train as train_module

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METRICS_PATH = train_module.METRICS_PATH
LOG_PATH = os.path.join(CACHE_DIR, "daily_retrain_log.jsonl")
SEASONS = [2024, 2025, 2026]

# How much a fresh candidate is allowed to be worse than the currently-deployed model before
# daily_retrain.py refuses to deploy it. Not zero: adding one day's handful of new games to a
# ~4,000-game walk-forward backtest naturally jitters the average slightly even when nothing is
# actually wrong (random_state is fixed — see model.py — so this isn't retrain-to-retrain
# seed noise, just the honest effect of a slightly different game mix). Wide enough to not block
# harmless day-to-day movement, tight enough to catch a real regression (for scale, a genuinely
# unhelpful feature added earlier this session moved AUC by 0.0004 on a full ablation — these
# tolerances are ~5x that).
AUC_TOLERANCE = 0.002
BRIER_TOLERANCE = 0.001
MAE_TOLERANCE = 0.01
# IP/ER MAE tolerances start smaller than strikeouts' since both targets have a smaller natural
# scale (typical IP MAE ~1-1.5 innings, ER MAE ~1.2-1.5 runs, vs ~1.8 strikeouts) — recalibrate
# once the first real backtest shows actual fold-to-fold variance for these two, same as
# MAE_TOLERANCE above was sized off strikeouts' own observed noise floor, not guessed blind.
IP_MAE_TOLERANCE = 0.05
ER_MAE_TOLERANCE = 0.05


def _git(*args, check=True):
    return subprocess.run(["git", *args], cwd=REPO_ROOT, check=check, capture_output=True, text=True)


def _load_old_metrics() -> dict:
    if not os.path.exists(METRICS_PATH):
        return {}
    try:
        with open(METRICS_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _passes_gate(old: dict, new: dict) -> tuple[bool, list[str]]:
    """Returns (ok_to_deploy, reasons) — reasons explains any regression found, empty if clean.
    An empty `old` (first-ever run, no prior deployed metrics to compare against) always passes."""
    if not old:
        return True, []

    reasons = []
    old_wp, new_wp = old.get("win_prob_a"), new.get("win_prob_a")
    if old_wp and new_wp:
        if new_wp["auc"] < old_wp["auc"] - AUC_TOLERANCE:
            reasons.append(f"win-prob AUC regressed: {old_wp['auc']:.4f} -> {new_wp['auc']:.4f}")
        if new_wp["brier"] > old_wp["brier"] + BRIER_TOLERANCE:
            reasons.append(f"win-prob Brier regressed: {old_wp['brier']:.4f} -> {new_wp['brier']:.4f}")

    old_k, new_k = old.get("strikeout_a"), new.get("strikeout_a")
    if old_k and new_k:
        if new_k["mae"] > old_k["mae"] + MAE_TOLERANCE:
            reasons.append(f"strikeout MAE regressed: {old_k['mae']:.3f} -> {new_k['mae']:.3f}")

    old_ip, new_ip = old.get("ip_a"), new.get("ip_a")
    if old_ip and new_ip:
        if new_ip["mae"] > old_ip["mae"] + IP_MAE_TOLERANCE:
            reasons.append(f"IP MAE regressed: {old_ip['mae']:.3f} -> {new_ip['mae']:.3f}")

    old_er, new_er = old.get("er_a"), new.get("er_a")
    if old_er and new_er:
        if new_er["mae"] > old_er["mae"] + ER_MAE_TOLERANCE:
            reasons.append(f"ER MAE regressed: {old_er['mae']:.3f} -> {new_er['mae']:.3f}")

    return len(reasons) == 0, reasons


def main():
    run_started = datetime.now(timezone.utc).isoformat()
    old_metrics = _load_old_metrics()

    # data_cache/*.parquet isn't git-tracked, so a rejected candidate below can't be rolled back
    # the way model_artifacts/ is (git checkout). Without this, a regressed rebuild (e.g. a
    # season's data source going temporarily thin) leaves the WORSE dataset sitting on disk even
    # though the gate correctly refused to deploy the model trained on it — silently degrading the
    # next day's starting point. Snapshot both caches first and restore them on rejection.
    win_prob_cache = os.path.join(CACHE_DIR, "training_dataset.parquet")
    strikeout_cache = os.path.join(CACHE_DIR, "strikeout_training_dataset.parquet")
    win_prob_backup = win_prob_cache + ".pre_retrain_backup"
    strikeout_backup = strikeout_cache + ".pre_retrain_backup"
    if os.path.exists(win_prob_cache):
        shutil.copy2(win_prob_cache, win_prob_backup)
    if os.path.exists(strikeout_cache):
        shutil.copy2(strikeout_cache, strikeout_backup)

    print("=== Step 1: incremental game-log refresh + rebuild training data ===")
    build_training_data.build_full_training_set(SEASONS)
    build_training_data.build_strikeout_training_set(SEASONS)

    print("\n=== Step 2: retrain all model variants ===")
    new_metrics = train_module.main()

    print("\n=== Step 3: compare candidate against currently-deployed metrics ===")
    ok, reasons = _passes_gate(old_metrics, new_metrics)

    log_entry = {
        "run_started": run_started,
        "old_metrics": old_metrics,
        "new_metrics": new_metrics,
        "deployed": ok,
        "skip_reasons": reasons,
    }

    if ok:
        print("Candidate is not worse than the live model (or no prior deployment to compare "
              "against) — deploying.")
        status = _git("status", "--porcelain", "backend/model_artifacts/")
        if not status.stdout.strip():
            print("No changes to model_artifacts/ (new games didn't move anything) — nothing to deploy.")
            log_entry["deployed"] = False
            log_entry["skip_reasons"] = ["no file changes"]
        else:
            _git("add", "backend/model_artifacts/")
            summary_bits = []
            if "win_prob_a" in new_metrics:
                summary_bits.append(f"win-prob AUC {new_metrics['win_prob_a']['auc']:.4f}")
            if "strikeout_a" in new_metrics:
                summary_bits.append(f"strikeout MAE {new_metrics['strikeout_a']['mae']:.3f}")
            if "ip_a" in new_metrics:
                summary_bits.append(f"IP MAE {new_metrics['ip_a']['mae']:.3f}")
            if "er_a" in new_metrics:
                summary_bits.append(f"ER MAE {new_metrics['er_a']['mae']:.3f}")
            message = (
                f"Daily retrain: {', '.join(summary_bits)} "
                f"({new_metrics.get('win_prob_games', '?')} games)\n\n"
                f"Automated daily retrain — see backend/daily_retrain.py.\n\n"
                f"Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
            )
            _git("commit", "-m", message)
            _git("push", "origin", "main")
            print("Pushed — Railway will redeploy automatically.")
    else:
        print("Candidate regressed beyond tolerance — NOT deploying:")
        for r in reasons:
            print(f"  - {r}")
        # Revert model_artifacts/ so the working tree matches whatever's actually still live,
        # not the (unused) candidate this run just trained.
        _git("checkout", "--", "backend/model_artifacts/")
        print("Reverted local model_artifacts/ to the last-deployed state.")
        # data_cache/*.parquet isn't git-tracked, so it doesn't get restored by the checkout above
        # — put back the pre-rebuild snapshot so a rejected run doesn't leave a worse dataset sitting
        # on disk than what actually produced the currently-deployed model (see snapshot comment above).
        if os.path.exists(win_prob_backup):
            shutil.move(win_prob_backup, win_prob_cache)
        if os.path.exists(strikeout_backup):
            shutil.move(strikeout_backup, strikeout_cache)
        print("Restored data_cache/ training sets to their pre-rebuild state.")

    for backup in (win_prob_backup, strikeout_backup):
        if os.path.exists(backup):
            os.remove(backup)

    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    print(f"\nLogged this run to {LOG_PATH}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"daily_retrain.py FAILED: {e}", file=sys.stderr)
        raise
