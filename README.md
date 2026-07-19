# Matchup Edge — MLB Pitcher Prediction Dashboard

Predicts win probability for MLB games based on the starting pitcher matchup,
using a gradient-boosted (XGBoost) model trained on historical starts —
season and recent-form FIP/K-BB%, bullpen quality, opponent lineup strength,
park factor, and rest days. Ships with a dashboard that shows today's games,
your model's probability, and (if you enter sportsbook odds) your edge vs the market.

## Quickest path: one-click scripts

**Mac/Linux:** double-click `setup.sh` (or run `bash setup.sh` in Terminal) once.
Then double-click `start.sh` (or `bash start.sh`) any time you want to launch it.

**Windows:** double-click `setup.bat` once. Then double-click `start.bat` any
time you want to launch it.

`setup` installs everything and trains the model — it's slow (20-40 min) but
you only do it once (or occasionally, to retrain on fresh data). `start` just
boots the API + dashboard and opens your browser; takes a few seconds.

If double-clicking `.sh` files on Mac doesn't run them (some Mac security
settings block this), right-click → Open With → Terminal, or run `bash setup.sh`
from a Terminal window opened in that folder.

Everything below is the manual/step-by-step version of what those scripts do,
useful if something goes wrong and you want to see what's happening.

## What's actually in here

```
backend/
  data_collection.py     data pulls from pybaseball + MLB Stats API (free, no key)
  features.py             feature engineering (FIP/K-BB%, recent form, bullpen, park, opponent)
  model.py                XGBoost model, calibration, backtesting
  build_training_data.py  builds historical training set from past seasons
  train.py                trains the model + prints backtest results
  main.py                 FastAPI server, serves the dashboard's data
frontend/
  src/App.jsx              dashboard UI
  src/ProbabilityBar.jsx   the win-probability visualization
  ...
```

## 1. Backend setup

Requires Python 3.10+.

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Build historical training data (one-time, takes a while)

This walks the MLB Stats API across past seasons pulling boxscores for every
game, so it's slow the first time (expect 10-20 min for 2 seasons — it's
making a few thousand HTTP requests). It caches to `backend/data_cache/` so
you only pay this cost once; delete that folder to force a refresh.

Defaults to the current and prior season (2025-2026) rather than going back
further — recent pitcher/roster performance is what actually matters for
predicting today's games, and older seasons mostly just dilute that signal.

```bash
python build_training_data.py --seasons 2025 2026
```

### Train the model

```bash
python train.py
```

This prints a **walk-forward backtest** — pay attention to this before you
trust any prediction. Realistic expectations for pitcher-matchup-only models:

- Brier score around 0.23–0.24 (0.25 = coin flip, lower is better)
- AUC around 0.55–0.58
- If your numbers look dramatically better than that, something's leaking
  (e.g. using data that wouldn't have been available before the game).

### Run the API

```bash
uvicorn main:app --reload --port 8000
```

Visit `http://localhost:8000/docs` to see/test the endpoints directly.

## 2. Frontend setup

Requires Node 18+.

```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173`. It proxies `/api` calls to the backend on
port 8000, so keep both running.

## 3. Keeping it current

- **Daily**: probable pitchers and today's predictions refresh automatically
  when you load the dashboard (it hits the MLB Stats API live).
- **Retrain periodically**: pitcher form changes over a season. Re-run
  `python build_training_data.py --seasons 2025 2026` and `python train.py`
  every couple of weeks, or hit `POST /api/retrain` on the running API.
- **Season rollover**: add the new season to the `--seasons` list each year.

## 4. Adding real sportsbook odds (optional)

The dashboard lets you manually type in American odds (e.g. `-130`, `+110`)
per game to see your edge. To automate that pull:

1. Sign up for a free key at [the-odds-api.com](https://the-odds-api.com)
   (500 free requests/month).
2. I didn't wire this in yet since it needs your key — happy to add an
   `odds_fetcher.py` module and a live-odds column in the dashboard once
   you have a key. Just paste it in and ask.

## 5. Honest limitations, read this before betting real money

- **Backtest on YOUR data before trusting it.** The metrics above are typical
  ranges, not a promise. Check `train.py`'s output every time you retrain.
- **Sportsbook lines already price starter quality efficiently.** Research
  on baseball market efficiency consistently finds most exploitable edge
  isn't in "who's the better starter" (the market knows that) but in
  things this model doesn't capture well: late lineup scratches, bullpen
  fatigue from the last 2-3 days, weather shifts close to first pitch, and
  umpire assignments. Treat this model's edge estimates as one input, not
  a green light.
- **Sample size matters.** A "12% edge" on one game means much less than a
  12% edge that holds up across 200 backtested games. Don't bet-size based
  on a single prediction's confidence.
- **This is not financial advice** and I'm not a licensed advisor — this
  tool gives you information to make your own decisions, nothing more.

## Troubleshooting

- **`pybaseball` pulls are slow/rate-limited**: this is normal, FanGraphs
  and Baseball-Reference throttle scrapers. The caching layer means you
  only pay this cost once per day (season stats) or per pitcher (Statcast).
- **Boxscore pulls in `build_training_data.py` fail intermittently**: the
  MLB Stats API occasionally 500s on specific gamePks; the script just skips
  those rows and keeps going, which is fine at this data volume.
- **CORS errors in the browser**: make sure the backend is running on port
  8000 before starting the frontend dev server.
