#!/bin/bash
# One poll + scan + flag-log pass. Driven by the oo-poll systemd timer.
cd /home/ec2-user/mlb-predictor/backend || exit 1
exec venv/bin/python -W ignore oo_scan.py once >> /home/ec2-user/mlb-predictor/backend/logs/oo_poll.log 2>&1
