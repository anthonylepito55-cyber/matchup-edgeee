#!/usr/bin/env bash
# Auto-commit + push every 2h (cron). Commits only when dirty; pushes to the local
# bare origin AND the offsite "backup" remote (added once Jacob supplies the repo URL).
set -u
cd /home/ec2-user/mlb-predictor || exit 1
LOG=/home/ec2-user/auto-push.log
{
  echo "[$(date -Is)] run"
  if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git commit -m "auto-backup: $(date -u +%Y-%m-%dT%H:%MZ)" >/dev/null && echo "  committed $(git rev-parse --short HEAD)"
  else
    echo "  clean — nothing to commit"
  fi
  git push origin HEAD >/dev/null 2>&1 && echo "  pushed local origin" || echo "  local origin push failed"
  if git remote get-url backup >/dev/null 2>&1; then
    git push backup HEAD:main >/dev/null 2>&1 && echo "  pushed offsite backup" || echo "  OFFSITE PUSH FAILED"
  else
    echo "  offsite backup remote not configured yet"
  fi
} >> "$LOG" 2>&1
tail -c 200000 "$LOG" > "$LOG.t" && mv "$LOG.t" "$LOG"
