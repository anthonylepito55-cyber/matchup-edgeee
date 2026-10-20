# DQU daily runbook — manual capture and supervised settlement

Every command below was run in the environment it is listed for. Nothing here is scheduled:
these run when a person runs them.

**Timing.** Capture *after* the authorized nightly ingest (`tennis-site-ingest.timer`,
**06:04 UTC**). Capturing before it gets a byte-identical file, which is recorded as a
duplicate — harmless, but it adds no new as-of date. Settlement is worth running more than
once a day, since matches finish through the evening.

---

## A. Windows PowerShell (this workstation)

Paths use `\`, the venv is invoked with `&`, and `$env:TEMP` replaces `/tmp`.

**1 — pull the production archive**

```powershell
$d = (Get-Date).ToUniversalTime().ToString("yyyyMMdd")
$dst = "$env:TEMP\prod_$d.parquet"
scp -i "$env:USERPROFILE\Downloads\AnthonyBB.pem" -o StrictHostKeyChecking=no ec2-user@3.22.236.36:~/mlb-predictor/backend/data_cache/tennisratio/all_match_logs.parquet $dst
(Get-FileHash $dst -Algorithm SHA256).Hash
```

**2 — capture, checkpoint, verify**

```powershell
Set-Location "C:\Users\actsl.DESKTOP-5CTNC21\OneDrive\Documents\Desktop\mlb-predictor\backend\research\tennis_next"
& "..\..\venv\Scripts\python.exe" dqu_capture.py capture --source $dst --from "scp ec2 production all_match_logs.parquet"
& "..\..\venv\Scripts\python.exe" dqu_capture.py checkpoint
& "..\..\venv\Scripts\python.exe" dqu_capture.py verify
```

**3 — settlement, dry run first, always**

```powershell
& "..\..\venv\Scripts\python.exe" tsm_beta_settle.py --dry-run
& "..\..\venv\Scripts\python.exe" tsm_beta_settle.py --settle
```

**4 — gate status (never prints an outcome statistic before the threshold)**

```powershell
& "..\..\venv\Scripts\python.exe" dqu_prospective.py --status
```

**Tests**

```powershell
& "..\..\venv\Scripts\python.exe" dqu_capture_tests.py
& "..\..\venv\Scripts\python.exe" dqu_eligibility_tests.py
```

---

## B. EC2 / Linux (on the host itself)

On EC2 the archive is already local, so there is no transfer and no `scp`. Note the repo
there is on a different lineage — `git pull` is a no-op — so these modules must be scp'd in
before first use.

```bash
cd ~/mlb-predictor/backend/research/tennis_next
python3 dqu_capture.py capture --source ~/mlb-predictor/backend/data_cache/tennisratio/all_match_logs.parquet --from "local production archive on 3.22.236.36"
python3 dqu_capture.py checkpoint
python3 dqu_capture.py verify
```

```bash
cd ~/mlb-predictor/backend/research/tennis_next && python3 tsm_beta_settle.py --dry-run
```

```bash
cd ~/mlb-predictor/backend/research/tennis_next && python3 tsm_beta_settle.py --settle
```

Check when the nightly ingest last ran, and when it next will:

```bash
systemctl list-timers tennis-site-ingest.timer --no-pager
```

---

## C. Git Bash on Windows (if you prefer it to PowerShell)

```bash
cd /c/Users/actsl.DESKTOP-5CTNC21/OneDrive/Documents/Desktop/mlb-predictor/backend/research/tennis_next && ../../venv/Scripts/python.exe dqu_capture.py verify
```

---

## D. What to do when something fails

Report it, do not repair it. The system is built so a failure is visible rather than
smoothed over, and a silently repaired capture is worth less than no capture.

| symptom | meaning | action |
|---|---|---|
| `REFUSED: N players (< 1000)` | the source is the degraded 157-player subset | pull again from EC2; do not force it |
| `REFUSED: ... already exists` | a stored filename collision | stop and report; never delete the existing file |
| `INTEGRITY CHECK FAILED` | stored bytes differ from the source | the failure is already recorded as `failed_capture`; report it |
| `verify` reports a changed or missing file | a capture was edited or deleted after the fact | report; the manifest's hash is the record of what it was |
| `verify` reports a checkpoint mismatch | manifest entries were removed or replaced | report immediately — this is the tail-deletion signal |
| settlement shows `unverifiable_winner_mapping` | the result source's winner matches neither player, or both | expected and safe: nothing is recorded; report if it is frequent |
| the same fixture appears twice under SETTLE | a withdrawn phantom record and its clean replacement, both matching one real match | expected; the withdrawn one is excluded at analysis time |

---

## E. Standing constraints

No scheduling, no retraining, no probability changes, no production warning changes, no
bets. The frozen D_rest model, the prediction ledger, the pre-registration
(sha256 `25b36a94573718385890a35673177ced…`) and the official 16-week trial are not to be
touched. The prospective gate stays at **≥300 eligible settled and ≥60 flagged**, and no
outcome-dependent DQU statistic is displayed before it opens.
