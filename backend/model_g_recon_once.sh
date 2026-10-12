#!/bin/bash
# MODEL G RECON, nightly (2026-10-12). Backfills model_g onto settled log rows the model did
# not price live.
#
# WHY THIS HAS TO REPEAT rather than run once: the recon needs the match in the TennisRatio
# archive with both players' 52-week windows and both-side odds, and that archive ingests a day
# over the following day or two -- 2026-10-11 held 122 rows while 10-08 already held 277. A
# single pass therefore leaves the NEWEST day almost empty, which is exactly the day you look
# at first. Re-running nightly fills each day in as the archive catches up, and the --apply
# path never overwrites a genuine frozen value, so repeats are safe.
set -u
cd /home/ec2-user/mlb-predictor/backend || exit 1
exec ./venv/bin/python -W ignore _model_g_recon.py data_cache/tennis_prediction_log.parquet --apply
