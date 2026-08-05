"""
Monte Carlo win-probability simulation.

Instead of a single classifier outputting P(home win) straight from a feature-diff vector, this
draws thousands of plausible final scores and reports how often each side wins. It's built
entirely on top of models this app already has (the IP/ER point projections, team bullpen FIP,
park factor) rather than adding new raw features — the earlier ablation testing tonight
(bullpen_availability_diff, team_hook_tendency, tto_penalty, spin/movement trend) showed the
win-prob classifier already squeezes out what marginal signal those features have; the lever left
is not "one more column" but modeling the actual *uncertainty* around the point projections
instead of collapsing everything to a single diff.

How a team's runs-allowed-tonight are modeled: two phases, both drawn from a Negative Binomial
(real single-game earned-runs-allowed is meaningfully overdispersed relative to Poisson — see
_ER_OVERDISPERSION_RATIO's calibration note below).
  1. Starter phase: mean = the ER model's own point projection for that start.
  2. Bullpen phase: mean = team bullpen_fip/9 * (9 - starter's projected IP), i.e. the team's
     bullpen quality rate applied to however many innings the starter isn't expected to cover.
A team's final runs allowed = starter phase + bullpen phase. The OTHER team's runs scored is
exactly that (pitching is symmetric: what the home starter+pen allow IS what the away team
scores). Park factor scales both means multiplicatively (same run environment, both directions).

This does NOT simulate innings, base-out states, or individual plate appearances — see this
repo's plan file /Phase note on why a full plate-appearance sim was scoped out tonight as a
much larger, separate undertaking. This is explicitly the "score-distribution" tier: real
uncertainty modeling, reusing existing point projections, without a full game-state engine.
"""
import numpy as np

# Calibrated 2026-08-05 from the 3-season (2024-2026) pitcher-outing dataset
# (strikeout_training_dataset.parquet): within narrow season-FIP quality bins, earned-runs-allowed
# variance/mean ratio is consistently ~1.6-1.7 (population-level ratio: 1.64), confirming this
# isn't just heterogeneity across pitcher quality — a single start's ER really is overdispersed
# relative to a Poisson process. Used for both the starter and bullpen phase (no direct per-game
# bullpen-earned-runs data is cached to calibrate that phase separately; treated as the same
# underlying "earned runs allowed over N innings" process).
_ER_OVERDISPERSION_RATIO = 1.6

# A team's own average runs scored is fairly stable game to game (~4.3-4.7 in modern MLB) --
# extra-inning games are the tail of that distribution, not a separate process, so a coin flip
# weighted only slightly toward whichever side has the (very marginally) better bullpen rate is a
# reasonable simplification rather than modeling extra frames explicitly.
_REGULATION_INNINGS = 9.0


def _nb_params(mean: float, ratio: float = _ER_OVERDISPERSION_RATIO):
    """Negative-binomial (n, p) for numpy's random.negative_binomial matching a target mean with
    variance = mean * ratio (ratio > 1 required; ratio == 1 degenerates toward Poisson)."""
    mean = max(float(mean), 1e-6)
    ratio = max(ratio, 1.0 + 1e-6)
    variance = mean * ratio
    p = mean / variance
    n = mean * p / (1 - p)
    return max(n, 1e-6), min(max(p, 1e-6), 1 - 1e-6)


def simulate_team_runs_allowed(
    starter_ip: float, starter_er_mean: float, bullpen_fip: float,
    n_sims: int, park_factor: float = 1.0, rng: np.random.Generator = None,
) -> np.ndarray:
    """Draws n_sims plausible final runs-allowed totals for one team's pitching staff tonight
    (starter + whatever's left for the bullpen). starter_er_mean should be the ER model's own
    point projection for that starter; bullpen_fip the team's season bullpen FIP (raw, not a
    diff). Returns an (n_sims,) int array."""
    rng = rng or np.random.default_rng()
    starter_ip = max(float(starter_ip), 0.0) if starter_ip is not None else 5.0
    bullpen_innings = max(_REGULATION_INNINGS - starter_ip, 0.0)

    starter_mean = max(float(starter_er_mean), 0.0) * park_factor if starter_er_mean is not None else 2.5 * park_factor
    bullpen_rate = float(bullpen_fip) / 9.0 if bullpen_fip is not None and np.isfinite(bullpen_fip) else 4.3 / 9.0
    bullpen_mean = max(bullpen_rate, 0.0) * bullpen_innings * park_factor

    n_s, p_s = _nb_params(starter_mean)
    n_b, p_b = _nb_params(bullpen_mean)
    starter_draws = rng.negative_binomial(n_s, p_s, size=n_sims)
    bullpen_draws = rng.negative_binomial(n_b, p_b, size=n_sims)
    return starter_draws + bullpen_draws


def simulate_game(
    home_starter_ip: float, home_starter_er: float, home_bullpen_fip: float,
    away_starter_ip: float, away_starter_er: float, away_bullpen_fip: float,
    park_factor: float = 1.0, n_sims: int = 100_000, seed: int = None,
) -> dict:
    """Simulates one game n_sims times. Returns win_prob_home plus the underlying run
    distributions, so callers can also surface a projected total/spread from the same draws
    instead of running a separate calculation for those.

    Note the directionality: the HOME starter/bullpen's runs-allowed IS the AWAY team's runs
    scored, and vice versa — pitching and opposing offense are the same coin.
    """
    rng = np.random.default_rng(seed)
    away_team_runs = simulate_team_runs_allowed(
        home_starter_ip, home_starter_er, home_bullpen_fip, n_sims, park_factor, rng
    )
    home_team_runs = simulate_team_runs_allowed(
        away_starter_ip, away_starter_er, away_bullpen_fip, n_sims, park_factor, rng
    )

    home_wins = home_team_runs > away_team_runs
    ties = home_team_runs == away_team_runs
    # Tied regulation totals go to extra innings — a near-coin-flip, nudged by whichever side
    # has the better bullpen rate (the only signal left once the starters are already spent).
    tie_home_edge = 0.5
    if home_bullpen_fip is not None and away_bullpen_fip is not None and np.isfinite(home_bullpen_fip) and np.isfinite(away_bullpen_fip):
        gap = float(away_bullpen_fip) - float(home_bullpen_fip)  # positive favors home (lower FIP)
        tie_home_edge = float(np.clip(0.5 + gap * 0.02, 0.35, 0.65))

    win_prob_home = float(home_wins.mean() + tie_home_edge * ties.mean())
    run_diff = home_team_runs.astype(int) - away_team_runs.astype(int)
    total_runs = home_team_runs.astype(int) + away_team_runs.astype(int)

    return {
        "win_prob_home": win_prob_home,
        "home_runs_mean": float(home_team_runs.mean()),
        "away_runs_mean": float(away_team_runs.mean()),
        "projected_total": float(total_runs.mean()),
        "projected_spread": float(run_diff.mean()),  # positive = home favored by this many runs
        "run_diff_p10": float(np.percentile(run_diff, 10)),
        "run_diff_p90": float(np.percentile(run_diff, 90)),
        "n_sims": n_sims,
    }
