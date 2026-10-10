#!/usr/bin/env bash
# Prompt for the RapidAPI key and store it where _ue_api_probe.py looks for it.
# (2026-10-10) The key is read with `read -s`, so it is not echoed to the screen and
# never reaches your shell history or any command line. The file is chmod 600 and is
# gitignored. Nothing else is written, and the value is never printed back.
set -euo pipefail
DEST="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.rapidapi_key"
printf 'Paste your RapidAPI key (it will not be shown), then press Enter: '
read -rs KEY
printf '\n'
if [ -z "${KEY}" ]; then
  echo "nothing entered -- no file written" >&2
  exit 1
fi
printf '%s' "${KEY}" > "${DEST}"
chmod 600 "${DEST}"
unset KEY
echo "stored ${#DEST} -> $(ls -l "${DEST}" | awk '{print $1, $3, $NF}')"
echo "done. tell Claude it is set and the probe can run."
