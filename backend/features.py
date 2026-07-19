"""
features.py

Builds the feature vector for a single game (home pitcher vs away pitcher)
that gets fed into the gradient-boosted model.

Feature groups:
  1. Season-level pitcher quality (FIP, K-BB%), season-to-date — walk-
     forward in training (built from the pitcher's own prior starts, same
     as group 2), not a full-season snapshot applied to every game. A
     flat, ALREADY-COMPLETE season line was fed to every training row
     early on; that's real look-ahead leakage (an April game seeing the
     pitcher's whole-season FIP, including starts that hadn't happened
     yet) and was fixed by aggregating the same season-to-date numbers a
     live prediction would actually have. Recency-weighted (EWMA by start
     number) was also tried and rejected via backtest — underperformed a
     plain cumulative season average, likely because "recent form" is
     already captured explicitly by group 2 below.
  2. Recent form: FIP, K/9, BB/9 over each pitcher's last 5 starts (official
     MLB box-score numbers, not an approximation). FIP drives this rather
     than ERA — ERA is skewed by defense and sequencing luck over a short
     5-start window, while FIP isolates what the pitcher actually
     controlled (K, BB, HR), so it's a truer read on recent form.
  3. Opponent lineup quality (team wOBA, derived from Baseball-Reference)
  4. Opponent platoon matchup: each lineup's wOBA specifically against the
     hand (L/R) of the pitcher they're actually facing — distinct from
     group 3's season-long overall wOBA, which doesn't know or care who's
     on the mound. Uses the team-wide vs-LHP/vs-RHP split (MLB Stats API)
     by default, upgraded to the REAL confirmed starting lineup (each
     actual batter's own season wOBA + a literature-average platoon
     adjustment for their handedness) once one's posted, typically 1-3
     hours before first pitch — this is live-serving-only (no walk-forward
     historical lineup data was built for training; the feature's scale
     and meaning don't change, so the already-trained model doesn't need
     retraining to benefit from a more precise number at inference time).
  5. Bullpen strength: two separate signals, not one blended number —
     full-pen season-long FIP/ERA (every reliever a team has used, mop-up
     arms included), and closer/setup-only FIP (top ~3 relievers by
     saves-then-innings). Who actually pitches the 7th-9th of a close
     game matters more there than how deep the bullpen's 8th man is.
  6. Bullpen fatigue: innings each team's pen has actually thrown in the
     last 3 days — distinct from group 5's season-long quality average. A
     good bullpen that just covered extra innings or a bullpen game is
     worse tonight than its season ERA says, independent of how good it
     normally is.
  7. Team defense: BABIP allowed, aggregated across a team's whole
     pitching staff for the season — independent of any one pitcher's own
     skill/luck (a single pitcher's BABIP is mostly noise; a full team's
     season-long BABIP allowed is a real signal of how many balls in play
     that defense turns into outs behind whoever's pitching).
  8. Statcast pitch quality: whiff% (swings-and-misses per swing), chase%
     (swings induced outside the zone), hard-hit% allowed (batted balls
     95+ mph) — season-to-date, walk-forward (computed ourselves from raw
     pitch-level Statcast data by game date, see data_collection.
     get_pitcher_statcast_daily / statcast_cumulative_as_of). This is
     process signal, not outcome signal: FIP/K-BB% describe what already
     happened (strikeouts, walks, homers recorded), while whiff%/chase%
     describe how well the pitcher's actual stuff is missing bats and
     avoiding hard contact — a pitcher can have a mediocre K rate with an
     elite whiff rate that hasn't caught up yet, or the reverse.
  9. Park factor
  10. Home field flag
  11. Rest days since each pitcher's last start
"""

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "home_field",
    "park_factor_home",
    "game_temp_f",   # game-day high temp, raw (not sign-based) — see weather.py
    # game_wind_mph (raw mean wind speed) REMOVED from the win-prob model as of 2026-07-15 —
    # analyze_feature_stability.py, 10 seeds x 5 folds: mean rank 42/56 (never top-half),
    # permutation importance ~0 and negative in 54% of runs, and a same-seed/same-fold paired
    # with-vs-without comparison showed no measurable Brier/log-loss/ECE/ROI difference (AUC
    # trended very slightly BETTER without it). Not evidence "wind doesn't matter" — a raw scalar
    # speed with no direction is likely the wrong representation; wind-out-to-center/wind-in/
    # crosswind relative to park orientation, or wind x fly-ball-tendency / x handedness / x roof
    # state, could easily carry real signal this one doesn't. Blocked on park-orientation data
    # (see weather.py — confirmed unavailable for all 30 parks as of this session). Still present
    # in STRIKEOUT_FEATURE_COLUMNS (game_wind_mph) — untested by this study, not touched.
    "fip_diff",
    "k_bb_pct_diff",
    # xera_diff: Statcast contact-quality-based expected ERA, away - home flipped (positive favors home).
    # Unlike xfip_diff/siera_diff below, this ALWAYS reflects the pitcher's PRIOR season, never blended
    # with anything from the current season — xERA needs Savant's own (non-public) contact-quality model
    # per batted ball, which can't be reproduced walk-forward from box-score/pitch-level data the way
    # xFIP/SIERA can (see data_collection.compute_xfip_siera). blend_with_prior_season still runs, but
    # current-season xera is never populated, so it always falls through to prior's value.
    "xera_diff",
    # xfip_diff/siera_diff: FIP-with-league-HR/FB-substituted and the approximated published SIERA
    # formula, away - home flipped (positive favors home) — genuinely walk-forward during training as of
    # this session (blend_with_prior_season's current-season component now comes from
    # data_collection.compute_xfip_siera, fed by statcast_cumulative_as_of's gb_pct/fb_pct/pu_pct; before
    # that these two silently always used the PRIOR season's value only, identical to xera_diff's
    # still-current limitation above).
    "xfip_diff",
    "siera_diff",
    "prior_season_fip_diff",      # LAST season's full FIP: away - home — a genuinely independent signal from this
    "prior_season_k_bb_pct_diff", # season's blended stats, not folded into fip_diff/k_bb_pct_diff above (see build_matchup_features)
    "season_ip_per_start_diff",   # season innings-per-start: home - away (deeper outings = less bullpen exposure, positive favors home)
    "pitches_per_start_diff",  # season pitches thrown per start: home - away — a workload/efficiency signal distinct from IP-per-start (an efficient pitcher throws fewer pitches per inning)
    "h2h_fip_diff",            # this pitcher's own FIP specifically against tonight's opponent, reliability-weighted by sample size: away - home (positive favors home)
    "hr9_diff",                # season home runs allowed per 9: away - home (lower is better, positive favors home)
    "h9_diff",                 # season hits allowed per 9: away - home (lower is better, NOT captured by FIP, positive favors home)
    "recent_fip_diff",        # last-5-starts FIP: away - home (lower FIP is better, so positive favors home)
    "recent_k9_diff",         # last-5-starts K/9: home - away (higher K/9 is better, so positive favors home)
    "recent_bb9_diff",        # last-5-starts BB/9: away - home (lower BB/9 is better, so positive favors home)
    "recent_hr9_diff",         # last-5-starts home runs allowed per 9: away - home (positive favors home)
    "recent_h9_diff",          # last-5-starts hits allowed per 9: away - home (positive favors home)
    "recent_ip_per_start_diff",  # last-5-starts innings-per-start: home - away (positive favors home)
    "bullpen_fip_diff",       # away bullpen fip - home bullpen fip (positive favors home)
    # 2026-07-18: tried scaling this AND high_leverage_bullpen_fip_diff by starter closeness too
    # (removing this column as a then-duplicate) — backtested worse (see build_matchup_features'
    # closeness comment for the numbers). Reverted; kept as its own flat-vs-scaled pair.
    "bullpen_edge_when_close_diff",  # bullpen_fip_diff scaled down as the starters' own FIP gap widens — see build_matchup_features
    "arsenal_matchup_woba_diff",  # each lineup's expected wOBA against the SPECIFIC pitch mix they're facing tonight, weighted by that pitcher's own arsenal — see build_matchup_features
    "opp_lineup_woba_diff",   # away lineup woba - home lineup woba (positive favors home pitcher)
    "opp_power_diff",         # opposing lineup's own raw power (ISO), away - home — pairs with hr9_diff so the model sees both a pitcher's own homer-proneness and the specific opponent's power
    "recent_team_batting_diff",  # each team's own batting avg over its last ~7 games (positive favors home)
    # recent_team_batting_30d_diff (the same signal over ~30 days) REMOVED from the model as of
    # 2026-07-18 — real coverage (99.6%) and real variance (std 0.028), so not a data bug, but
    # zero gain importance in the trained model: verified via user-flagged-game review (see
    # 2026-07-17 slate) that recent-form/team-batting signals looked underweighted relative to a
    # single bullpen feature's individual rank and season fip_diff — that specific "bullpen_fip_diff
    # is the #1 feature" read didn't survive a proper category-level re-check (see below), but this
    # 30-day column's own zero-importance finding held up independently either way: it contributes
    # literally nothing (0.0 gain across all boosters), while the 7-day version above ranks a
    # modest #42/55. With max_depth=1 (decision
    # stumps — see DEFAULT_XGB_PARAMS), the two compete for the same splits every round since
    # they're correlated (r=0.58) but not redundant, and the 7-day version wins every time,
    # leaving this one pure dead weight. Still computed in build_matchup_features below (harmless,
    # available for display/future use), just no longer fed to the model.
    "lineup_xwoba_diff",       # each lineup's own average expected wOBA (contact-quality-based), home - away
    "lineup_xba_diff",         # same, expected batting average
    "lineup_xslg_diff",        # same, expected slugging
    "lineup_hard_hit_diff",    # each lineup's own hard-hit% (95+ mph batted balls), home - away
    "lineup_barrel_diff",      # each lineup's own barrel%, home - away
    "lineup_sweet_spot_diff",  # each lineup's own sweet-spot% (launch angle 8-32deg), home - away
    "lineup_chase_percentile_diff",   # league percentile rank of chase rate, away - home (lower chase is better)
    "lineup_contact_percentile_diff", # league percentile rank of contact rate (already flipped so higher=better), home - away
    "lineup_pull_pct_diff",    # each lineup's own pull rate, home - away (treated as a mild positive, see build_matchup_features)
    "lineup_gb_pct_diff",      # each lineup's own ground-ball rate, away - home (higher GB% is generally worse for offense)
    "travel_fatigue_diff",    # away team's travel distance since their last game minus home's, in thousands of miles (positive favors home, see weather.team_travel_miles)
    "line_movement_diff",     # how far the moneyline has moved toward home since opening (positive favors home) — see odds_fetcher.get_line_movement
    "market_divergence_diff",  # Pinnacle's movement since open minus DraftKings' — sharp-vs-retail reverse-line-movement proxy, positive favors home — see odds_fetcher.get_market_divergence
    "prediction_market_diff",  # Kalshi/Polymarket (USA) current price vs. Pinnacle's current price — positive favors home — see odds_fetcher.get_prediction_market_signal
    "consensus_prob_diff",    # average devigged home win prob across CONSENSUS_BOOKS minus 0.5 — the market's own current read on the game (a level, not a movement), positive favors home — see odds_fetcher.get_consensus_odds
    "book_disagreement",      # max-min spread of devigged home prob across CONSENSUS_BOOKS — a volatility/uncertainty proxy, not sign-based (always >= 0) — see odds_fetcher.get_consensus_odds
    "book_movement_agreement",  # signed fraction of CONSENSUS_BOOKS moving the same direction since open (+1 = all toward home, -1 = all toward away) — how many sportsbooks are moving together, positive favors home — see odds_fetcher.get_consensus_odds
    "consensus_median_diff",  # median (not mean) devigged home win prob across CONSENSUS_BOOKS minus 0.5 — robust to one outlier book skewing the average, positive favors home — see odds_fetcher.get_consensus_odds
    "book_prob_std",          # population std of devigged home win prob across CONSENSUS_BOOKS — a more holistic disagreement measure than book_disagreement's max-min range, not sign-based (always >= 0) — see odds_fetcher.get_consensus_odds
    "book_favor_diff",        # signed fraction of CONSENSUS_BOOKS currently favoring home vs away (>50%/<50%) — distinct from consensus_median_diff's probability LEVEL, positive favors home — see odds_fetcher.get_consensus_odds
    "market_outs_line_diff",         # home pitcher's posted outs-recorded line minus away's — who the market expects to go deeper tonight, positive favors home — see odds_fetcher.get_pitcher_market_lines
    "market_er_line_diff",           # away pitcher's posted earned-runs line minus home's — fewer expected ER favors home, positive favors home
    "market_hits_allowed_line_diff",  # away pitcher's posted hits-allowed line minus home's — fewer expected hits allowed favors home, positive favors home
    "team_total_diff",        # home team's posted Team Total runs line minus away's, averaged across CONSENSUS_BOOKS — the market's own projected score differential, positive favors home — see odds_fetcher.get_market_snapshot
    "market_total_runs",      # game Total Runs line, averaged across CONSENSUS_BOOKS — the market's expected scoring environment tonight, NOT sign-based (no home/away meaning on its own) — see odds_fetcher.get_market_snapshot
    "opp_platoon_woba_diff",  # opponent lineups' wOBA specifically vs each starter's own throwing hand (positive favors home pitcher)
    "bullpen_fatigue_diff",   # away bullpen's innings thrown in the last 3 days minus home's (positive = away more tired, favors home)
    "high_leverage_bullpen_fip_diff",  # away closer/setup FIP - home closer/setup FIP (positive favors home)
    "defense_oaa_diff",       # home team OAA - away team OAA (positive favors home's defense; higher OAA = better D)
    "whiff_pct_diff",         # home whiff% - away whiff% (higher is better stuff, positive favors home)
    "chase_pct_diff",         # home chase% induced - away chase% induced (positive favors home)
    "hard_hit_pct_diff",      # away hard-hit% allowed - home hard-hit% allowed (lower is better, positive favors home)
    "gb_pct_diff",            # home ground-ball% - away ground-ball% (higher is generally better, positive favors home)
    "barrel_pct_diff",        # away barrel% allowed - home barrel% allowed (lower is better, positive favors home)
    "zone_pct_diff",          # home zone% - away zone% (more strikes in zone, a command signal, positive favors home)
    "contact_pct_diff",       # away contact% allowed - home contact% allowed (lower is better, positive favors home)
    "first_pitch_strike_pct_diff",  # home first-pitch-strike% - away (ahead in counts, positive favors home)
    "csw_pct_diff",            # home CSW% (called strikes + whiffs, per pitch) - away (a blended command/stuff signal not decomposable from whiff%/chase%/zone% alone, positive favors home)
    "velo_trend_diff",         # each pitcher's own recent-minus-season fastball velocity: home - away (positive means away pitcher fading more, or home trending up more, favors home)
    "fip_trend_diff",          # each pitcher's own recent-minus-season FIP (positive = trending worse than their own season line): away - home so positive favors home, same convention as fip_diff
    "pitch_diversity_diff",    # each pitcher's own arsenal balance (1 - max pitch-type share): home - away (harder to sit on one pitch, positive favors home)
    "rest_days_diff",
]

# Market-derived features, called out separately so Model A (baseball-only) can be defined as
# "everything except these" without ever manually re-syncing two lists — see train.py. Every
# entry here must also appear in FEATURE_COLUMNS above.
MARKET_FEATURE_COLUMNS = [
    "line_movement_diff", "market_divergence_diff", "prediction_market_diff",
    "consensus_prob_diff", "book_disagreement", "book_movement_agreement",
    "consensus_median_diff", "book_prob_std", "book_favor_diff",
    "market_outs_line_diff", "market_er_line_diff", "market_hits_allowed_line_diff",
    "team_total_diff", "market_total_runs",
]

BASEBALL_ONLY_FEATURE_COLUMNS = [c for c in FEATURE_COLUMNS if c not in MARKET_FEATURE_COLUMNS]

MAX_REST_DAYS = 10  # beyond this, extra rest stops being a freshness bonus — see _rest_effect

MIN_RELIABLE_STARTS = 3        # fewer starts than this and a "last N starts" stat is mostly noise, not signal
FULL_RELIABILITY_STARTS = 5    # sample size at which recent-form is treated as fully reliable
MIN_RELIABLE_SEASON_IP = 30.0  # season IP below which "season" and "recent form" are basically the same small sample
LONG_LAYOFF_DAYS = 12          # normal rotations skip a turn at most ~10-11 days; beyond this, recent-form predates the absence
MIN_RELIABLE_IP_PER_START = 3.0  # short-leash/bulk-relief stints below this depth aren't a real "start" sample, whatever the count says
CLOSE_MATCHUP_FIP_SCALE = 0.75  # combined season+recent starter FIP gap beyond which bullpen_edge_when_close_diff fades to 0 — see build_matchup_features


def _safe_get(df: pd.DataFrame, team: str, col: str, default=np.nan):
    row = df[df["Team"] == team]
    if row.empty or col not in row.columns:
        return default
    return row.iloc[0][col]


# Generic (literature-average, not fit from this app's own data — there's no
# reliable way to derive per-batter platoon splits from what's available here)
# platoon wOBA adjustments. Left-handed batters show a consistently larger
# platoon split than right-handed batters in published research, so they get
# a bigger swing both directions; switch hitters always take the favorable
# (opposite-hand) side.
_PLATOON_ADJUSTMENT = {"R": {"same": -0.010, "opp": 0.010}, "L": {"same": -0.020, "opp": 0.020}}


def _batter_platoon_woba(base_woba: float, batter_hand: str, pitcher_hand: str) -> float:
    if pd.isna(base_woba):
        return np.nan
    if batter_hand == "S":
        return base_woba + 0.015  # switch hitter: always bats the favorable side
    adj = _PLATOON_ADJUSTMENT.get(batter_hand, _PLATOON_ADJUSTMENT["R"])
    return base_woba + (adj["same"] if batter_hand == pitcher_hand else adj["opp"])


def _lineup_platoon_woba(batter_ids: list, pitcher_hand: str, player_batting: pd.DataFrame, batter_hands: dict) -> float:
    """
    Real confirmed lineup's wOBA against a specific pitcher's throwing
    hand, weighted by each actual batter's own season wOBA plus a generic
    platoon adjustment for their own handedness — a genuine upgrade over
    the team-wide average when a lineup has posted (excludes injured/
    rested regulars, includes the real bench replacement), NaN if no
    lineup or batting data is available so the caller can fall back to
    the team-average version.
    """
    if not batter_ids or player_batting is None or player_batting.empty:
        return np.nan
    values = []
    for bid in batter_ids:
        row = player_batting[player_batting["mlbID"] == bid]
        if row.empty:
            continue
        base_woba = row.iloc[0]["player_wOBA"]
        hand = batter_hands.get(bid, "R")
        adjusted = _batter_platoon_woba(base_woba, hand, pitcher_hand)
        if pd.notna(adjusted):
            values.append(adjusted)
    return float(np.mean(values)) if values else np.nan


def _lineup_woba(batter_ids: list, player_batting: pd.DataFrame) -> float:
    """
    Real confirmed lineup's own overall wOBA, averaged across the actual
    batters starting tonight (no platoon adjustment — see
    _lineup_platoon_woba for that) — a genuine upgrade over the team-wide
    season wOBA for the main offense-quality feature: a team's whole-
    season average is blind to who's ACTUALLY in the lineup tonight, so a
    missing star hitter (injured, resting, whatever the reason) silently
    keeps inflating the team's offense number long after they're gone.
    Once a real lineup is out, this reflects that absence directly — no
    separate injury-tracking needed, since the missing player simply isn't
    in batter_ids. NaN if no lineup or batting data is available yet, so
    the caller falls back to the team-wide season average.
    """
    if not batter_ids or player_batting is None or player_batting.empty:
        return np.nan
    values = []
    for bid in batter_ids:
        row = player_batting[player_batting["mlbID"] == bid]
        if row.empty:
            continue
        woba = row.iloc[0]["player_wOBA"]
        if pd.notna(woba):
            values.append(woba)
    return float(np.mean(values)) if values else np.nan


def _lineup_k_pct(batter_ids: list, player_batting: pd.DataFrame) -> float:
    """
    Real confirmed lineup's own strikeout rate, averaged across the actual
    batters starting tonight — a genuine upgrade over the team-wide season
    K% for strikeout props, same reasoning as _lineup_platoon_woba above:
    a team's whole-roster average includes bench bats and rested regulars
    who aren't the ones actually facing this pitcher. NaN if no lineup or
    batting data is available so the caller can fall back to the team
    average.
    """
    if not batter_ids or player_batting is None or player_batting.empty:
        return np.nan
    values = []
    for bid in batter_ids:
        row = player_batting[player_batting["mlbID"] == bid]
        if row.empty:
            continue
        k_pct = row.iloc[0]["player_k_pct"]
        if pd.notna(k_pct):
            values.append(k_pct)
    return float(np.mean(values)) if values else np.nan


def _team_batter_arsenal(batter_ids: list, batter_arsenal: pd.DataFrame, team_abbr: str, metric_col: str) -> dict:
    """
    {pitch_type: average metric_col value} across a set of batters — "this lineup's whiff rate
    against sliders specifically," not their overall whiff rate. Prefers the real confirmed/
    predicted lineup (batter_ids) when given; falls back to every batter on team_abbr's roster
    (via batter_arsenal's own team_name_alt column) when no lineup id list is available — same
    upgrade-when-posted pattern as _lineup_woba, just per pitch type instead of one blended number.
    """
    if batter_arsenal is None or batter_arsenal.empty:
        return {}
    if batter_ids:
        subset = batter_arsenal[batter_arsenal["mlbID"].isin(batter_ids)]
    else:
        subset = batter_arsenal[batter_arsenal["team_name_alt"] == team_abbr]
    if subset.empty:
        return {}
    return subset.groupby("pitch_type")[metric_col].mean().to_dict()


def _lineup_metric_avg(batter_ids: list, df: pd.DataFrame, col: str, team_abbr: str = None,
                        team_map: dict = None) -> float:
    """
    Generic version of _lineup_woba/_lineup_k_pct for any single per-batter metric column — real
    confirmed/predicted lineup average when batter_ids is given, team-wide fallback via team_map
    (mlbID -> team_abbr, see data_collection.get_batter_team_map) otherwise. Built for the batch
    of expected-stats/exit-velo/batted-ball/percentile-rank batter tables added alongside this —
    none of those carry their own team column the way get_batter_pitch_arsenal's team_name_alt
    does, so the fallback needs an external team map instead of filtering the table directly.
    """
    if df is None or df.empty or col not in df.columns:
        return np.nan
    if batter_ids:
        subset = df[df["mlbID"].isin(batter_ids)]
    elif team_abbr and team_map:
        team_batter_ids = [bid for bid, team in team_map.items() if team == team_abbr]
        subset = df[df["mlbID"].isin(team_batter_ids)]
    else:
        return np.nan
    vals = subset[col].dropna()
    return float(vals.mean()) if len(vals) > 0 else np.nan


def _arsenal_matchup_score(pitcher_mix: dict, opp_arsenal: dict) -> float:
    """
    Weighted average of the opponent's per-pitch-type value (whiff% or wOBA, see callers),
    weighted by how often TONIGHT's specific pitcher actually throws each pitch type — a lineup
    that crushes fastballs but chases sliders matters very differently against a pitcher who
    throws 70% fastballs than one who throws 50% sliders, which a single season-wide whiff%/wOBA
    number can't see. Pitch types missing from either side are skipped and the remaining weights
    renormalized (dividing by total_weight below), rather than silently treating a missing type
    as 0. NaN if there's no overlap at all.
    """
    if not pitcher_mix or not opp_arsenal:
        return np.nan
    weighted_sum, total_weight = 0.0, 0.0
    for pt, share in pitcher_mix.items():
        val = opp_arsenal.get(pt)
        if val is None or pd.isna(val):
            continue
        weighted_sum += share * val
        total_weight += share
    return (weighted_sum / total_weight) if total_weight > 0 else np.nan


NORMAL_IP_PER_START = 5.0  # a normal, healthy MLB start goes at least this deep


def _recent_form_weight(recent: dict) -> float:
    """
    0..1 confidence weight for how much to trust a pitcher's last-N-starts
    FIP/K9/BB9 — ramps up with sample size (a single-start sample is
    almost pure noise, five is the full window this stat is built from),
    and appearances-fallback outings (relief work standing in for a
    starter with too few real starts) count for half as much since they
    tend to run a bit better than the same pitcher's own start numbers.

    Also dampened by how deep those starts actually went. Sample size alone
    treats three 2-inning stints as equally reliable as three full 6-inning
    starts — but FIP over a 2-inning outing is a handful of batters faced,
    barely more informative than the single-start case this function
    already treats as almost pure noise. A pitcher getting pulled early
    (short leash after struggling, or a bulk-relief role) isn't
    demonstrating the same thing a real start does, regardless of how many
    of them there've been. Caught directly: a pitcher with 3 "starts"
    averaging 2.4 IP each got 60% reliability weight on a small-sample FIP
    that then got cited as "better recent form" in a losing pick.
    """
    sample_size = recent.get("sample_size") or 0
    sample_type = recent.get("sample_type", "starts")
    effective = sample_size if sample_type == "starts" else sample_size * 0.5
    weight = max(0.0, min(1.0, effective / FULL_RELIABILITY_STARTS))

    ip_per_start = recent.get("ip_per_start")
    if ip_per_start is not None and pd.notna(ip_per_start) and ip_per_start > 0:
        depth_factor = max(0.0, min(1.0, ip_per_start / NORMAL_IP_PER_START))
        weight *= depth_factor
    return weight


def _layoff_weight(days) -> float:
    """
    1.0 for a normal rest gap. Beyond LONG_LAYOFF_DAYS, ramps down toward
    0 as the gap stretches further — the pitcher's recent-form numbers
    all predate the absence, so the longer it's been, the less they say
    about how they'll look tonight.
    """
    if days is None or pd.isna(days):
        return 1.0
    if days <= LONG_LAYOFF_DAYS:
        return 1.0
    return max(0.0, 1.0 - (days - LONG_LAYOFF_DAYS) / LONG_LAYOFF_DAYS)


IL_RETURN_WINDOW_DAYS = 30  # must match data_collection.IL_RETURN_WINDOW_DAYS — kept separate since features.py has no data-fetching dependency
IL_RETURN_FLOOR_WEIGHT = 0.3  # reliability weight right at activation; ramps linearly up to 1.0 by IL_RETURN_WINDOW_DAYS


def _il_return_weight(days_since_return) -> float:
    """
    1.0 when there's no recent IL activation on record. Otherwise ramps from
    IL_RETURN_FLOOR_WEIGHT right at activation up to 1.0 by IL_RETURN_WINDOW_DAYS
    — a pitcher can rack up several starts post-return without tripping the
    generic long-layoff heuristic (_layoff_weight only looks at days since their
    LAST start, not days since they came off the IL), so a real, sustained hot or
    cold stretch during that window could still out-weigh a much larger, more
    reliable season sample in the raw model's own inputs. Caught directly: Casey
    Mize's last-5-starts FIP (2.96) was fully trusted despite a confirmed IL
    activation 24 days earlier, flipping a matchup where his season line (3.32
    FIP, 149 IP) was clearly worse than the opponent's (2.58 FIP, 227 IP). This
    discounts the recent-form feature diffs themselves, not just the display-
    layer confidence override, which only gated amplification, not the base
    model's own prediction.
    """
    if days_since_return is None or pd.isna(days_since_return):
        return 1.0
    return IL_RETURN_FLOOR_WEIGHT + (1.0 - IL_RETURN_FLOOR_WEIGHT) * min(1.0, days_since_return / IL_RETURN_WINDOW_DAYS)


NOT_MOSTLY_STARTER_DISCOUNT = 0.35  # extra multiplier when ip_per_start is null — see _season_ip_weight


def _season_ip_weight(ip, ip_per_start=None) -> float:
    """
    0..1 confidence weight for a pitcher's season FIP/K-BB%. Below
    MIN_RELIABLE_SEASON_IP, a pitcher's "season" line is really just his
    recent-form window in different clothing (the same handful of
    starts), not an independently larger sample confirming it.

    ip_per_start, when given, applies the same kind of depth discount
    _recent_form_weight's ip_per_start check already does on the recent-form
    side: get_season_pitching_stats leaves ip_per_start (IP_per_GS) null
    whenever a pitcher isn't "mostly a starter" this season (GS/G < 0.5 or
    fewer than 3 starts) — a good-looking small IP total built mostly from
    short relief/opener stints isn't the same thing as the same innings as a
    real starter, and the plain ip/MIN_RELIABLE_SEASON_IP ramp alone can't
    tell the difference. Caught directly (user-flagged, 2026-07-17 slate):
    Gabriel Hughes, 9 season IP (2 appearances, only 1 real start) with a
    lucky small-sample 2.32 FIP, got a bare 30% weight (9/30) on the raw IP
    ramp alone — enough to help swing a game to a ~60% favorite that then
    lost by 5.
    """
    if ip is None or pd.isna(ip):
        return 0.0
    weight = max(0.0, min(1.0, ip / MIN_RELIABLE_SEASON_IP))
    if ip_per_start is None or pd.isna(ip_per_start):
        weight *= NOT_MOSTLY_STARTER_DISCOUNT
    return weight


H2H_FULL_RELIABILITY_STARTS = 6  # must match data_collection.H2H_FULL_RELIABILITY_STARTS — kept
# separate since features.py has no data-fetching dependency, same pattern as IL_RETURN_WINDOW_DAYS above


def _h2h_weight(starts) -> float:
    """
    0..1 confidence weight for a pitcher's own head-to-head history against
    tonight's specific opponent. These samples are inherently tiny — most
    pitcher/opponent pairs see 0-4 starts across two seasons, occasionally
    more against a divisional rival — so even "starts" at the low end of
    what a recent-form window would already treat as thin gets shrunk
    further here rather than trusted as a meaningful head-to-head trend.
    """
    if starts is None or pd.isna(starts) or starts <= 0:
        return 0.0
    return max(0.0, min(1.0, starts / H2H_FULL_RELIABILITY_STARTS))


# A full season a year ago is real signal about who a pitcher actually is —
# discounted below 1.0 since it's a year stale (age, stuff changes, injuries
# recover or recur), but not thrown away the way a pitcher with a thin
# current-season sample otherwise would be (season_weight -> ~0, "fip_diff"
# effectively vanishes regardless of how good or bad the small sample looked).
# Caught directly: a pitcher back from a long injury absence with one bad
# start (ERA 21+ in 3 IP) got a near-toss-up prediction instead of correctly
# leaning on his real track record (2025: 3.09 ERA, 3.57 FIP) — the model had
# no way to see that a mediocre 2026 fip_diff-toward-zero was hiding a
# genuinely above-average pitcher, because low-current-IP just meant "ignore
# season stats," not "fall back to what we actually know about this guy."
PRIOR_SEASON_DISCOUNT = 0.5


def blend_with_prior_season(current: dict, prior: dict) -> dict:
    """
    Blends a pitcher's current-season stat line ({"era","ip","fip","k_bb_pct","k9"})
    with their prior-season line, weighted by innings (prior innings
    discounted by PRIOR_SEASON_DISCOUNT — a year-old full season is real
    signal but less current than this year's own innings). Current season
    fully dominates once it reaches MIN_RELIABLE_SEASON_IP on its own; below
    that, prior-season performance fills in rather than the pitcher being
    treated as a blank slate.

    Falls back gracefully: no prior-season data (rookie's first year) ->
    current only, unchanged from before this existed. No current-season
    starts yet (hasn't debuted this year) -> prior only, but the season's
    own current_ip (0 or NaN) is preserved in the output for genuine "hasn't
    played" cases to still read correctly elsewhere (e.g. pitcher_warnings).
    """
    current = current or {}
    prior = prior or {}
    cur_ip = current.get("ip") or 0.0
    prior_ip_raw = prior.get("ip") or 0.0
    prior_ip = prior_ip_raw * PRIOR_SEASON_DISCOUNT

    if prior_ip <= 0:
        return current
    if cur_ip <= 0:
        return {**prior, "ip": current.get("ip", 0.0)}

    total = cur_ip + prior_ip
    w_cur = cur_ip / total
    blended = {"ip": cur_ip + prior_ip}  # effective combined reliability, feeds _season_ip_weight
    for key in (
        "era", "fip", "k_bb_pct", "k9", "hr9", "h9", "whip", "k_pct", "bb_pct", "ip_per_start",
        "xera", "xfip", "siera",
    ):
        cv, pv = current.get(key), prior.get(key)
        if cv is None or pd.isna(cv):
            blended[key] = pv
        elif pv is None or pd.isna(pv):
            blended[key] = cv
        else:
            blended[key] = cv * w_cur + pv * (1 - w_cur)
    return blended


def _rest_effect(days):
    """
    Transforms raw days-since-last-start into a rest signal that's
    positive for normal-to-extended rest and NEGATIVE for a genuinely
    long layoff — not just capped/neutral. Checked against the actual
    training data: same-season starts following an 11-20 day gap ran a
    meaningfully worse FIP than a normal 4-6 day gap (4.49 vs 4.17,
    weighted by innings) and covered noticeably fewer innings (4.46 vs
    5.35 IP/start) — consistent with a rehab/return outing, not a fresh
    arm. A 21+ day gap was worse still on both counts. So beyond
    MAX_REST_DAYS, each additional day is treated as rust risk (declining
    signal) rather than more freshness, floored so an extreme outlier
    (100+ days) doesn't dominate more than a clearly-rusty medium one.
    """
    if pd.isna(days):
        return np.nan
    if days <= MAX_REST_DAYS:
        return days
    penalty_days = min(days - MAX_REST_DAYS, 20)
    return MAX_REST_DAYS - penalty_days


def _pitcher_market_line_diff(home_lines: dict, away_lines: dict, key: str, higher_favors_home: bool) -> float:
    """home_lines[key] - away_lines[key] if higher_favors_home, else the reverse — the shared
    sign-flip logic behind market_outs_line_diff/market_er_line_diff/market_hits_allowed_line_diff
    in build_matchup_features, so "positive always favors home" stays true regardless of whether
    a higher number is good (outs) or bad (earned runs, hits allowed) for that stat."""
    home_val = (home_lines or {}).get(key)
    away_val = (away_lines or {}).get(key)
    if home_val is None or away_val is None or pd.isna(home_val) or pd.isna(away_val):
        return np.nan
    return (home_val - away_val) if higher_favors_home else (away_val - home_val)


def build_matchup_features(
    home_pitcher_id: int,
    away_pitcher_id: int,
    home_team_abbr: str,
    away_team_abbr: str,
    season_stats: dict,                 # {pitcher_id: {"fip":.., "k_bb_pct":.., "ip":..}} — season-to-date
    team_batting: pd.DataFrame,
    bullpen_stats: pd.DataFrame,
    park_factor_lookup,
    recent_stats: dict = None,          # {pitcher_id: {"era":.., "fip":.., "k9":.., "bb9":..}}
    rest_days: dict = None,             # {pitcher_id: days_rest}
    pitcher_hands: dict = None,         # {pitcher_id: "L"/"R"}
    team_batting_vs_hand: dict = None,  # {"L": df vs LHP, "R": df vs RHP}, each with Team/wOBA_vs_hand
    bullpen_fatigue: dict = None,       # {team_abbr: bullpen IP thrown in the last 3 days}
    high_leverage_bullpen_stats: pd.DataFrame = None,  # Team/high_leverage_fip — closer + top setup arms only
    team_defense: pd.DataFrame = None,  # Team/team_oaa — Statcast Outs Above Average, whole roster
    lineups: dict = None,               # {"home": [batter_id,...], "away": [batter_id,...]} — confirmed, may be empty
    player_batting: pd.DataFrame = None,  # mlbID/player_wOBA — needed to weight a real lineup
    batter_hands: dict = None,          # {batter_id: "L"/"R"/"S"}
    statcast: dict = None,              # {pitcher_id: {"whiff_pct":.., "chase_pct":.., "hard_hit_pct":..}} — season-to-date
    velocity_trend: dict = None,        # {pitcher_id: {"season_avg_velo":.., "recent_avg_velo":.., "velo_trend":..}}
    pitch_diversity: dict = None,       # {pitcher_id: {"pitch_diversity":..}} — season-to-date
    game_weather: dict = None,          # {"temp_max_f":.., "wind_mean_mph":..} — game-day, not pitcher-specific; see weather.py
    il_return_days: dict = None,        # {pitcher_id: days_since_il_return or None} — see data_collection.days_since_il_return
    prior_season_stats: dict = None,    # {pitcher_id: {"fip":.., "k_bb_pct":.., "ip":..}} — RAW last season, NOT blended into season_stats
    h2h_stats: dict = None,             # {pitcher_id: {"fip":.., "k9":.., "starts":.., "ip":..}} — THIS pitcher's own
                                         # career vs THEIR specific opponent tonight, see data_collection.get_pitcher_vs_team_history
    recent_team_batting: dict = None,   # {team_abbr: {"avg":.., "games":..}} — team's own batting average over its
                                         # last ~7 games, see data_collection.get_team_recent_batting_form
    recent_team_batting_30d: dict = None,  # same shape, over the last ~30 days (data_collection.RECENT_TEAM_BATTING_GAMES_30D)
    team_travel: dict = None,           # {team_abbr: miles_since_last_game} — see weather.team_travel_miles
    line_movement: float = None,        # devigged current-minus-opening home win prob, if available — see odds_fetcher.get_line_movement
    market_divergence: float = None,    # Pinnacle movement minus DraftKings movement — see odds_fetcher.get_market_divergence
    prediction_market_signal: float = None,  # Kalshi/Polymarket (USA) current prob minus Pinnacle's — see odds_fetcher.get_prediction_market_signal
    consensus_prob: float = None,       # average devigged home win prob across CONSENSUS_BOOKS, raw 0-1 — see odds_fetcher.get_consensus_odds
    book_disagreement: float = None,    # max-min spread of devigged home prob across CONSENSUS_BOOKS — see odds_fetcher.get_consensus_odds
    book_movement_agreement: float = None,  # signed fraction of CONSENSUS_BOOKS moving the same direction since open — see odds_fetcher.get_consensus_odds
    consensus_median_prob: float = None,  # median devigged home win prob across CONSENSUS_BOOKS, raw 0-1 — see odds_fetcher.get_consensus_odds
    book_prob_std: float = None,          # population std of devigged home win prob across CONSENSUS_BOOKS — see odds_fetcher.get_consensus_odds
    book_favor_diff: float = None,        # signed fraction of CONSENSUS_BOOKS currently favoring home vs away — see odds_fetcher.get_consensus_odds
    home_pitcher_market_lines: dict = None,  # {"outs_line":.., "er_line":.., "hits_allowed_line":..} for the HOME starter — see odds_fetcher.get_pitcher_market_lines
    away_pitcher_market_lines: dict = None,  # same shape, AWAY starter
    team_total_diff: float = None,      # home Team Total runs line minus away's, averaged across CONSENSUS_BOOKS — see odds_fetcher.get_market_snapshot
    market_total_runs: float = None,    # game Total Runs line, averaged across CONSENSUS_BOOKS — see odds_fetcher.get_market_snapshot
    batter_expected: pd.DataFrame = None,  # mlbID/xba/xslg/xwoba — data_collection.get_batter_expected_stats
    batter_exitvelo: pd.DataFrame = None,  # mlbID/hard_hit_pct/barrel_pct/sweet_spot_pct — data_collection.get_batter_exitvelo_barrels
    batter_percentile: pd.DataFrame = None,  # mlbID/chase_percentile/contact_percentile — data_collection.get_batter_percentile_ranks
    batter_batted_ball: pd.DataFrame = None,  # mlbID/gb_pct/fb_pct/pu_pct/pull_pct — data_collection.get_batted_ball_profile(type="batter")
    batter_team_map: dict = None,       # {mlbID: team_abbr} — data_collection.get_batter_team_map, fallback when no lineup posted
    pitch_mix: dict = None,             # {pitcher_id: {pitch_type: share}} — see data_collection.statcast_pitch_mix_as_of
    batter_arsenal: pd.DataFrame = None,  # mlbID/team_name_alt/pitch_type/whiff_percent/woba — see data_collection.get_batter_pitch_arsenal
) -> dict:
    """Returns a flat dict of features for one game, ready for the model."""
    recent_stats = recent_stats or {}
    il_return_days = il_return_days or {}
    game_weather = game_weather or {}
    prior_season_stats = prior_season_stats or {}
    h2h_stats = h2h_stats or {}
    recent_team_batting = recent_team_batting or {}
    recent_team_batting_30d = recent_team_batting_30d or {}
    team_travel = team_travel or {}
    batter_team_map = batter_team_map or {}
    rest_days = rest_days or {}
    season_stats = season_stats or {}
    pitcher_hands = pitcher_hands or {}
    team_batting_vs_hand = team_batting_vs_hand or {}
    bullpen_fatigue = bullpen_fatigue or {}
    high_leverage_bullpen_stats = high_leverage_bullpen_stats if high_leverage_bullpen_stats is not None else pd.DataFrame()
    team_defense = team_defense if team_defense is not None else pd.DataFrame()
    lineups = lineups or {}
    batter_hands = batter_hands or {}
    statcast = statcast or {}
    velocity_trend = velocity_trend or {}
    pitch_diversity = pitch_diversity or {}
    pitch_mix = pitch_mix or {}
    batter_arsenal = batter_arsenal if batter_arsenal is not None else pd.DataFrame()

    season_home = season_stats.get(home_pitcher_id, {})
    season_away = season_stats.get(away_pitcher_id, {})
    fip_home, fip_away = season_home.get("fip", np.nan), season_away.get("fip", np.nan)
    kbb_home, kbb_away = season_home.get("k_bb_pct", np.nan), season_away.get("k_bb_pct", np.nan)
    hr9_home, hr9_away = season_home.get("hr9", np.nan), season_away.get("hr9", np.nan)
    h9_home, h9_away = season_home.get("h9", np.nan), season_away.get("h9", np.nan)
    whip_home, whip_away = season_home.get("whip", np.nan), season_away.get("whip", np.nan)
    kpct_home, kpct_away = season_home.get("k_pct", np.nan), season_away.get("k_pct", np.nan)
    bbpct_home, bbpct_away = season_home.get("bb_pct", np.nan), season_away.get("bb_pct", np.nan)
    season_ip_per_start_home = season_home.get("ip_per_start", np.nan)
    season_ip_per_start_away = season_away.get("ip_per_start", np.nan)
    ip_home, ip_away = season_home.get("ip", np.nan), season_away.get("ip", np.nan)
    xera_home, xera_away = season_home.get("xera", np.nan), season_away.get("xera", np.nan)
    xfip_home, xfip_away = season_home.get("xfip", np.nan), season_away.get("xfip", np.nan)
    siera_home, siera_away = season_home.get("siera", np.nan), season_away.get("siera", np.nan)
    # A pitcher's season FIP/K-BB% only means as much as the innings behind
    # it — below MIN_RELIABLE_SEASON_IP it's really the same small sample
    # as "recent form" in different clothing, so shrink the diff toward 0
    # rather than let a noisy small-sample season line drive the model as
    # hard as an established one would. Statcast pitch-quality stats are
    # season-to-date too, so the same shrinkage applies to them.
    season_weight = min(
        _season_ip_weight(ip_home, season_ip_per_start_home), _season_ip_weight(ip_away, season_ip_per_start_away)
    )

    # Prior-season (e.g. 2025) form as its OWN signal — distinct from season_stats above, which
    # already blends in prior-season data but only to fill in a thin current-season sample, and
    # even then it's invisible to the model as a separate number (folded into one blended FIP).
    # This is the raw prior-season line, always available when it exists, weighted by ITS OWN
    # innings — so the model can lean on "how did they pitch all of last year" as an independent
    # confirmation even when a pitcher has a full current-season sample, which the blend alone
    # never surfaces once current-season IP clears MIN_RELIABLE_SEASON_IP.
    prior_home = prior_season_stats.get(home_pitcher_id, {})
    prior_away = prior_season_stats.get(away_pitcher_id, {})
    prior_fip_home, prior_fip_away = prior_home.get("fip", np.nan), prior_away.get("fip", np.nan)
    prior_kbb_home, prior_kbb_away = prior_home.get("k_bb_pct", np.nan), prior_away.get("k_bb_pct", np.nan)
    prior_ip_home, prior_ip_away = prior_home.get("ip", np.nan), prior_away.get("ip", np.nan)
    prior_season_weight = min(_season_ip_weight(prior_ip_home), _season_ip_weight(prior_ip_away))

    # Head-to-head: each pitcher's OWN track record against the specific opponent they're
    # facing tonight (not a team-wide platoon split) — how has THIS starter actually done
    # against THIS lineup historically, across this season and last. Samples here are
    # almost always tiny (0-4 starts is typical), so weighted by _h2h_weight rather than
    # trusted the way the much larger season/recent-form samples are.
    h2h_home = h2h_stats.get(home_pitcher_id, {})
    h2h_away = h2h_stats.get(away_pitcher_id, {})
    h2h_fip_home, h2h_fip_away = h2h_home.get("fip", np.nan), h2h_away.get("fip", np.nan)
    h2h_starts_home, h2h_starts_away = h2h_home.get("starts", 0), h2h_away.get("starts", 0)
    h2h_weight = min(_h2h_weight(h2h_starts_home), _h2h_weight(h2h_starts_away))

    statcast_home = statcast.get(home_pitcher_id, {})
    statcast_away = statcast.get(away_pitcher_id, {})
    whiff_home, whiff_away = statcast_home.get("whiff_pct", np.nan), statcast_away.get("whiff_pct", np.nan)
    chase_home, chase_away = statcast_home.get("chase_pct", np.nan), statcast_away.get("chase_pct", np.nan)
    hard_hit_home, hard_hit_away = statcast_home.get("hard_hit_pct", np.nan), statcast_away.get("hard_hit_pct", np.nan)
    csw_home, csw_away = statcast_home.get("csw_pct", np.nan), statcast_away.get("csw_pct", np.nan)
    pps_home, pps_away = statcast_home.get("pitches_per_start", np.nan), statcast_away.get("pitches_per_start", np.nan)
    gb_home, gb_away = statcast_home.get("gb_pct", np.nan), statcast_away.get("gb_pct", np.nan)
    barrel_home, barrel_away = statcast_home.get("barrel_pct", np.nan), statcast_away.get("barrel_pct", np.nan)
    zone_home, zone_away = statcast_home.get("zone_pct", np.nan), statcast_away.get("zone_pct", np.nan)
    contact_home, contact_away = statcast_home.get("contact_pct", np.nan), statcast_away.get("contact_pct", np.nan)
    fps_home, fps_away = statcast_home.get("first_pitch_strike_pct", np.nan), statcast_away.get("first_pitch_strike_pct", np.nan)

    velo_home = velocity_trend.get(home_pitcher_id, {})
    velo_away = velocity_trend.get(away_pitcher_id, {})
    velo_trend_home, velo_trend_away = velo_home.get("velo_trend", np.nan), velo_away.get("velo_trend", np.nan)

    diversity_home = pitch_diversity.get(home_pitcher_id, {}).get("pitch_diversity", np.nan)
    diversity_away = pitch_diversity.get(away_pitcher_id, {}).get("pitch_diversity", np.nan)

    bullpen_home = _safe_get(bullpen_stats, home_team_abbr, "bullpen_fip")
    bullpen_away = _safe_get(bullpen_stats, away_team_abbr, "bullpen_fip")

    # Closer/setup-only FIP: who actually pitches the 7th-9th of a close
    # game matters more there than the average across a team's whole
    # bullpen depth chart, mop-up arms included.
    hl_bullpen_home = _safe_get(high_leverage_bullpen_stats, home_team_abbr, "high_leverage_fip")
    hl_bullpen_away = _safe_get(high_leverage_bullpen_stats, away_team_abbr, "high_leverage_fip")

    defense_home = _safe_get(team_defense, home_team_abbr, "team_oaa")
    defense_away = _safe_get(team_defense, away_team_abbr, "team_oaa")

    # Team's own batting average over its last ~7 games — a team-wide season wOBA says
    # nothing about a lineup that's genuinely hot or cold right now.
    recent_avg_home = recent_team_batting.get(home_team_abbr, {}).get("avg", np.nan)
    recent_avg_away = recent_team_batting.get(away_team_abbr, {}).get("avg", np.nan)
    # Same idea, over ~30 days instead — long enough to smooth out a bad week's small-sample
    # noise while still catching a genuine month-long slump/hot streak a season-long average
    # is too slow to reflect.
    recent_avg_30d_home = recent_team_batting_30d.get(home_team_abbr, {}).get("avg", np.nan)
    recent_avg_30d_away = recent_team_batting_30d.get(away_team_abbr, {}).get("avg", np.nan)

    # Distance each team traveled to get here since their last game — a team that just flew
    # cross-country is plausibly more gassed than one on a homestand, independent of any
    # pitcher's own rest days. NaN (season opener, no prior game found) treated as "no signal."
    travel_home = team_travel.get(home_team_abbr, np.nan)
    travel_away = team_travel.get(away_team_abbr, np.nan)

    lineup_home = _safe_get(team_batting, home_team_abbr, "wOBA")
    lineup_away = _safe_get(team_batting, away_team_abbr, "wOBA")
    # Upgrade to the real confirmed lineup when one's posted — see _lineup_woba. Independently
    # per side, same fallback pattern as the platoon upgrade below: only overrides when a real
    # lineup is actually out, otherwise keeps the team-season average.
    real_lineup_woba_home = _lineup_woba(lineups.get("home"), player_batting)
    real_lineup_woba_away = _lineup_woba(lineups.get("away"), player_batting)
    if pd.notna(real_lineup_woba_home):
        lineup_home = real_lineup_woba_home
    if pd.notna(real_lineup_woba_away):
        lineup_away = real_lineup_woba_away
    # Raw power, distinct from wOBA — a lineup can have an ordinary wOBA while still being
    # unusually home-run-heavy (or the reverse). The opposing lineup's ISO is what the pitcher
    # allowing home runs is actually facing, so this pairs directly with hr9_diff above.
    power_home = _safe_get(team_batting, home_team_abbr, "ISO")
    power_away = _safe_get(team_batting, away_team_abbr, "ISO")

    # Platoon matchup: each lineup's wOBA specifically against the hand of
    # the pitcher they're actually facing tonight, not their overall wOBA —
    # a lefty-heavy lineup facing a lefty starter is a real disadvantage
    # the plain season-long team wOBA above doesn't see.
    home_hand = pitcher_hands.get(home_pitcher_id, "R")
    away_hand = pitcher_hands.get(away_pitcher_id, "R")
    platoon_vs_home_pitcher = _safe_get(team_batting_vs_hand.get(home_hand, pd.DataFrame()), away_team_abbr, "wOBA_vs_hand")
    platoon_vs_away_pitcher = _safe_get(team_batting_vs_hand.get(away_hand, pd.DataFrame()), home_team_abbr, "wOBA_vs_hand")

    # Upgrade to the real confirmed lineup when one's posted — excludes a
    # rested/injured regular and includes the actual bench replacement,
    # which a team-wide average can't see. Falls back to the team-average
    # value above (independently per side) when a lineup isn't out yet.
    real_platoon_vs_home = _lineup_platoon_woba(lineups.get("away"), home_hand, player_batting, batter_hands)
    real_platoon_vs_away = _lineup_platoon_woba(lineups.get("home"), away_hand, player_batting, batter_hands)
    if pd.notna(real_platoon_vs_home):
        platoon_vs_home_pitcher = real_platoon_vs_home
    if pd.notna(real_platoon_vs_away):
        platoon_vs_away_pitcher = real_platoon_vs_away

    park_home = park_factor_lookup(home_team_abbr)

    recent_home = recent_stats.get(home_pitcher_id, {})
    recent_away = recent_stats.get(away_pitcher_id, {})
    rfip_home, rfip_away = recent_home.get("fip", np.nan), recent_away.get("fip", np.nan)
    k9_home, k9_away = recent_home.get("k9", np.nan), recent_away.get("k9", np.nan)
    bb9_home, bb9_away = recent_home.get("bb9", np.nan), recent_away.get("bb9", np.nan)
    recent_hr9_home, recent_hr9_away = recent_home.get("hr9", np.nan), recent_away.get("hr9", np.nan)
    recent_h9_home, recent_h9_away = recent_home.get("h9", np.nan), recent_away.get("h9", np.nan)
    recent_ip_per_start_home = recent_home.get("ip_per_start", np.nan)
    recent_ip_per_start_away = recent_away.get("ip_per_start", np.nan)
    # Same shrinkage idea for recent-form: too small a sample, a sample that
    # predates an active long layoff (stale — no read on how it'll look
    # tonight), or a sample sitting inside a post-IL-return window (still a
    # return trajectory, not a settled read — see _il_return_weight) all get
    # discounted toward 0 rather than trusted at full strength.
    recent_weight = min(
        _recent_form_weight(recent_home), _recent_form_weight(recent_away),
        _layoff_weight(rest_days.get(home_pitcher_id)), _layoff_weight(rest_days.get(away_pitcher_id)),
        _il_return_weight(il_return_days.get(home_pitcher_id)), _il_return_weight(il_return_days.get(away_pitcher_id)),
    )

    # Recent FIP minus season FIP, per pitcher — same "recent minus season" idea as
    # velo_trend_diff, but for the core run-prevention stat rather than raw velocity. A pitcher
    # whose season line looks great on a small/hot sample but whose last-N-starts FIP is trending
    # WORSE than that (positive trend) is a real risk fip_diff alone can't see: fip_diff only
    # compares the two pitchers' absolute levels, blind to which one is actively getting better or
    # worse right now. Caught directly (user-flagged, 2026-07-17 slate): Spencer Miles had an
    # excellent 60-IP season FIP (3.02) built before a 7.2-ERA/3-start slide that his recent FIP
    # (4.30) already reflected almost as poorly as his opponent's FIP (4.23) — fip_diff alone
    # still favored Miles on the strength of the stale season number. Gated by both season_weight
    # AND recent_weight (min of the two) since the trend is only as trustworthy as its shakier
    # input.
    trend_home = (rfip_home - fip_home) if pd.notna(rfip_home) and pd.notna(fip_home) else np.nan
    trend_away = (rfip_away - fip_away) if pd.notna(rfip_away) and pd.notna(fip_away) else np.nan
    trend_weight = min(season_weight, recent_weight)

    rest_home = _rest_effect(rest_days.get(home_pitcher_id, np.nan))
    rest_away = _rest_effect(rest_days.get(away_pitcher_id, np.nan))

    # How far apart the starters' own quality actually is (season + recent FIP, weighted the
    # same way fip_diff/recent_fip_diff already are) — used below to scale bullpen_fip_diff's
    # effective weight. bullpen_fip_diff already exists as its own flat-weight feature above;
    # this is a genuinely different signal: the bullpen should matter MOST when the starting
    # matchup is a wash (whoever's pen is better plausibly decides a close game) and matter
    # LESS when one starter clearly outclasses the other (that game's mostly decided by him
    # regardless of who's behind him). max_depth=1 trees (see model.py) can't discover this
    # interaction on their own — each stump splits on one raw feature at a time — so it has to
    # be handed to the model as its own precomputed column, not left for training to find.
    #
    # 2026-07-18: tried extending this same closeness scaling to the plain bullpen_fip_diff AND
    # high_leverage_bullpen_fip_diff too (removing this dedicated column as a then-duplicate) —
    # a well-reasoned, user-flagged hypothesis (MIA@MIL: a moderate bullpen gap helped flip a game
    # where the starters weren't actually close). Backtested WORSE on the full walk-forward set:
    # Model A Brier 0.2459->0.2469, AUC 0.5685->0.5616, validation AUC 0.586->0.563 — a real
    # regression, not noise. Reverted. The lesson generalizes past this specific idea: a plausible
    # story about ONE game is not evidence a structural change helps across ~3,800 of them: this
    # is the same discipline that killed the confidence override and the game_wind_mph feature
    # earlier this session, just this time the idea failed at the backtest stage instead of
    # passing it.
    _starter_fip_gap, _has_starter_gap = 0.0, False
    if pd.notna(fip_home) and pd.notna(fip_away):
        _starter_fip_gap += abs(fip_away - fip_home) * season_weight
        _has_starter_gap = True
    if pd.notna(rfip_home) and pd.notna(rfip_away):
        _starter_fip_gap += abs(rfip_away - rfip_home) * recent_weight
        _has_starter_gap = True
    # Combined season+recent FIP gap beyond which the starters no longer count as "close" and
    # the bullpen-when-close term fades to 0 — roughly a full run of combined FIP separation.
    closeness = max(0.0, 1.0 - _starter_fip_gap / CLOSE_MATCHUP_FIP_SCALE) if _has_starter_gap else 1.0

    # "This lineup crushes fastballs but chases sliders" + "tonight's pitcher throws 50% sliders" —
    # each side's expected wOBA allowed against the SPECIFIC arsenal they're actually facing
    # tonight, not a single season-wide number blind to pitch mix. Real lineup when posted
    # (upgrades independently per side, same pattern as _lineup_woba), team-wide roster average
    # otherwise. Lower expected wOBA is better for the pitcher's own team, same "away - home"
    # convention as fip_diff, flipped so positive favors home.
    home_pitcher_mix = pitch_mix.get(home_pitcher_id, {})
    away_pitcher_mix = pitch_mix.get(away_pitcher_id, {})
    # away_lineup_arsenal_woba: the AWAY team's own batters — the lineup HOME's pitcher faces.
    # home_lineup_arsenal_woba: the HOME team's own batters — the lineup AWAY's pitcher faces.
    away_lineup_arsenal_woba = _team_batter_arsenal(lineups.get("away"), batter_arsenal, away_team_abbr, "woba")
    home_lineup_arsenal_woba = _team_batter_arsenal(lineups.get("home"), batter_arsenal, home_team_abbr, "woba")
    # Expected wOBA the AWAY lineup produces against HOME's specific arsenal — low is good for home.
    home_pitcher_arsenal_edge = _arsenal_matchup_score(home_pitcher_mix, away_lineup_arsenal_woba)
    # Expected wOBA the HOME lineup produces against AWAY's specific arsenal — high is good for home.
    away_pitcher_arsenal_edge = _arsenal_matchup_score(away_pitcher_mix, home_lineup_arsenal_woba)

    # Batter-level expected-stats/exit-velo/percentile-rank/batted-ball lineup averages — each
    # team's OWN lineup quality (not who's facing whom, same framing as opp_lineup_woba_diff/
    # recent_team_batting_diff above), real/predicted lineup when posted, team-wide fallback via
    # batter_team_map otherwise (see _lineup_metric_avg).
    def _side_avg(col, df):
        return (
            _lineup_metric_avg(lineups.get("home"), df, col, home_team_abbr, batter_team_map),
            _lineup_metric_avg(lineups.get("away"), df, col, away_team_abbr, batter_team_map),
        )
    xwoba_home, xwoba_away = _side_avg("xwoba", batter_expected)
    xba_home, xba_away = _side_avg("xba", batter_expected)
    xslg_home, xslg_away = _side_avg("xslg", batter_expected)
    hard_hit_bat_home, hard_hit_bat_away = _side_avg("hard_hit_pct", batter_exitvelo)
    barrel_bat_home, barrel_bat_away = _side_avg("barrel_pct", batter_exitvelo)
    sweet_spot_home, sweet_spot_away = _side_avg("sweet_spot_pct", batter_exitvelo)
    chase_pctl_home, chase_pctl_away = _side_avg("chase_percentile", batter_percentile)
    contact_pctl_home, contact_pctl_away = _side_avg("contact_percentile", batter_percentile)
    pull_home, pull_away = _side_avg("pull_pct", batter_batted_ball)
    gb_bat_home, gb_bat_away = _side_avg("gb_pct", batter_batted_ball)

    features = {
        "home_field": 1,
        "park_factor_home": park_home,
        "game_temp_f": game_weather.get("temp_max_f", np.nan),
        "game_wind_mph": game_weather.get("wind_mean_mph", np.nan),
        # FIP: LOWER is better, so flip sign so positive = home advantage
        "fip_diff": ((fip_away - fip_home) * season_weight) if pd.notna(fip_home) and pd.notna(fip_away) else np.nan,
        "k_bb_pct_diff": ((kbb_home - kbb_away) * season_weight) if pd.notna(kbb_home) and pd.notna(kbb_away) else np.nan,
        # xERA/xFIP/SIERA: all LOWER-is-better, same sign flip as fip_diff. See
        # data_collection.get_season_pitching_stats for how each is derived/approximated.
        "xera_diff": ((xera_away - xera_home) * season_weight) if pd.notna(xera_home) and pd.notna(xera_away) else np.nan,
        "xfip_diff": ((xfip_away - xfip_home) * season_weight) if pd.notna(xfip_home) and pd.notna(xfip_away) else np.nan,
        "siera_diff": (
            ((siera_away - siera_home) * season_weight) if pd.notna(siera_home) and pd.notna(siera_away) else np.nan
        ),
        # prior (e.g. 2025) season FIP/K-BB%: same sign convention as the current-season versions above
        "prior_season_fip_diff": (
            ((prior_fip_away - prior_fip_home) * prior_season_weight)
            if pd.notna(prior_fip_home) and pd.notna(prior_fip_away) else np.nan
        ),
        "prior_season_k_bb_pct_diff": (
            ((prior_kbb_home - prior_kbb_away) * prior_season_weight)
            if pd.notna(prior_kbb_home) and pd.notna(prior_kbb_away) else np.nan
        ),
        # each pitcher's own FIP specifically against tonight's opponent: lower is better,
        # away - home so positive favors home, same convention as fip_diff
        "h2h_fip_diff": (
            ((h2h_fip_away - h2h_fip_home) * h2h_weight)
            if pd.notna(h2h_fip_home) and pd.notna(h2h_fip_away) else np.nan
        ),
        # HR/9 allowed: lower is better, away - home so positive favors home
        "hr9_diff": ((hr9_away - hr9_home) * season_weight) if pd.notna(hr9_home) and pd.notna(hr9_away) else np.nan,
        # Hits allowed per 9, season-to-date — NOT captured by FIP (which deliberately excludes
        # hits on balls in play), so this is a genuinely independent signal from fip_diff/hr9_diff
        # above. Lower is better, away - home so positive favors home.
        "h9_diff": ((h9_away - h9_home) * season_weight) if pd.notna(h9_home) and pd.notna(h9_away) else np.nan,
        # WHIP: lower is better, away - home so positive favors home
        "whip_diff": ((whip_away - whip_home) * season_weight) if pd.notna(whip_home) and pd.notna(whip_away) else np.nan,
        # K%/BB%: higher K% and lower BB% are better, same sign convention as k_bb_pct_diff/fip_diff
        "k_pct_diff": ((kpct_home - kpct_away) * season_weight) if pd.notna(kpct_home) and pd.notna(kpct_away) else np.nan,
        "bb_pct_diff": ((bbpct_away - bbpct_home) * season_weight) if pd.notna(bbpct_home) and pd.notna(bbpct_away) else np.nan,
        # how deep each starter typically goes, season-to-date — going deeper means less
        # exposure to bullpen variance, home - away so positive favors home. Independent of
        # FIP/quality: a great pitcher who's usually pulled after 4 still hands the game to
        # the bullpen for 5 innings.
        "season_ip_per_start_diff": (
            ((season_ip_per_start_home - season_ip_per_start_away) * season_weight)
            if pd.notna(season_ip_per_start_home) and pd.notna(season_ip_per_start_away) else np.nan
        ),
        # pitches thrown per start, season-to-date — a workload/efficiency signal (going deeper on
        # the same pitch budget), home - away so positive favors home
        "pitches_per_start_diff": (
            ((pps_home - pps_away) * season_weight) if pd.notna(pps_home) and pd.notna(pps_away) else np.nan
        ),
        # opposing lineup's raw power (ISO) — same "away minus home" convention as opp_lineup_woba_diff
        # above, pairs with hr9_diff so the model can see both a pitcher's own homer-proneness and
        # the specific opponent's power together (a fly-ball-prone pitcher facing a power-heavy lineup
        # is a real, elevated risk neither signal alone fully captures).
        "opp_power_diff": (power_away - power_home) if pd.notna(power_home) and pd.notna(power_away) else np.nan,
        # recent FIP/BB9: lower is better, so away - home = positive favors home
        "recent_fip_diff": ((rfip_away - rfip_home) * recent_weight) if pd.notna(rfip_home) and pd.notna(rfip_away) else np.nan,
        "recent_k9_diff": ((k9_home - k9_away) * recent_weight) if pd.notna(k9_home) and pd.notna(k9_away) else np.nan,
        "recent_bb9_diff": ((bb9_away - bb9_home) * recent_weight) if pd.notna(bb9_home) and pd.notna(bb9_away) else np.nan,
        # same HR9/H9 signals as the season versions above, but last-5-starts — catches a
        # pitcher who's recently been getting hit harder (or better) than his season norm
        "recent_hr9_diff": (
            ((recent_hr9_away - recent_hr9_home) * recent_weight)
            if pd.notna(recent_hr9_home) and pd.notna(recent_hr9_away) else np.nan
        ),
        "recent_h9_diff": (
            ((recent_h9_away - recent_h9_home) * recent_weight)
            if pd.notna(recent_h9_home) and pd.notna(recent_h9_away) else np.nan
        ),
        # same depth-of-outing signal as season_ip_per_start_diff above, but last-5-starts —
        # catches a pitcher who's recently been getting pulled earlier (or later) than their
        # season norm, home - away so positive favors home
        "recent_ip_per_start_diff": (
            ((recent_ip_per_start_home - recent_ip_per_start_away) * recent_weight)
            if pd.notna(recent_ip_per_start_home) and pd.notna(recent_ip_per_start_away) else np.nan
        ),
        # bullpen FIP: lower is better, away - home so positive favors home
        "bullpen_fip_diff": (bullpen_away - bullpen_home) if pd.notna(bullpen_home) and pd.notna(bullpen_away) else np.nan,
        # away_pitcher_arsenal_edge high (home lineup hits well vs away's specific pitches) and
        # home_pitcher_arsenal_edge low (away lineup hits poorly vs home's specific pitches) both
        # favor home, so positive = favors home, same convention as every other diff here.
        "arsenal_matchup_woba_diff": (
            (away_pitcher_arsenal_edge - home_pitcher_arsenal_edge)
            if pd.notna(home_pitcher_arsenal_edge) and pd.notna(away_pitcher_arsenal_edge) else np.nan
        ),
        # bullpen_fip_diff again, but scaled down toward 0 the more the starters themselves
        # differ — see the closeness computation above. Same sign convention: positive favors home.
        "bullpen_edge_when_close_diff": (
            (bullpen_away - bullpen_home) * closeness
        ) if pd.notna(bullpen_home) and pd.notna(bullpen_away) else np.nan,
        "high_leverage_bullpen_fip_diff": (
            (hl_bullpen_away - hl_bullpen_home) if pd.notna(hl_bullpen_home) and pd.notna(hl_bullpen_away) else np.nan
        ),
        # OAA: higher is better defense, home - away so positive favors home's defense
        "defense_oaa_diff": (
            (defense_home - defense_away) if pd.notna(defense_home) and pd.notna(defense_away) else np.nan
        ),
        # higher whiff/chase is better stuff, home - away so positive favors home
        "whiff_pct_diff": (
            ((whiff_home - whiff_away) * season_weight) if pd.notna(whiff_home) and pd.notna(whiff_away) else np.nan
        ),
        "chase_pct_diff": (
            ((chase_home - chase_away) * season_weight) if pd.notna(chase_home) and pd.notna(chase_away) else np.nan
        ),
        # lower hard-hit% allowed is better, away - home so positive favors home
        "hard_hit_pct_diff": (
            ((hard_hit_away - hard_hit_home) * season_weight) if pd.notna(hard_hit_home) and pd.notna(hard_hit_away) else np.nan
        ),
        # higher ground-ball% is generally better (fewer home runs, more double-play chances),
        # home - away so positive favors home
        "gb_pct_diff": (
            ((gb_home - gb_away) * season_weight) if pd.notna(gb_home) and pd.notna(gb_away) else np.nan
        ),
        # lower barrel% allowed (best-quality contact) is better, away - home so positive favors home
        "barrel_pct_diff": (
            ((barrel_away - barrel_home) * season_weight) if pd.notna(barrel_home) and pd.notna(barrel_away) else np.nan
        ),
        # higher zone% (more strikes in the zone, a command signal) is better, home - away so positive favors home
        "zone_pct_diff": (
            ((zone_home - zone_away) * season_weight) if pd.notna(zone_home) and pd.notna(zone_away) else np.nan
        ),
        # lower contact% allowed (more empty swings) is better, away - home so positive favors home
        "contact_pct_diff": (
            ((contact_away - contact_home) * season_weight) if pd.notna(contact_home) and pd.notna(contact_away) else np.nan
        ),
        # higher first-pitch-strike% (ahead in counts) is better, home - away so positive favors home
        "first_pitch_strike_pct_diff": (
            ((fps_home - fps_away) * season_weight) if pd.notna(fps_home) and pd.notna(fps_away) else np.nan
        ),
        # higher CSW% is better command, home - away so positive favors home
        "csw_pct_diff": (
            ((csw_home - csw_away) * season_weight) if pd.notna(csw_home) and pd.notna(csw_away) else np.nan
        ),
        # velo_trend is recent-minus-season for each pitcher already; home - away so positive
        # favors home (away pitcher fading more than home, or home trending up more)
        "velo_trend_diff": (
            ((velo_trend_home - velo_trend_away) * recent_weight)
            if pd.notna(velo_trend_home) and pd.notna(velo_trend_away) else np.nan
        ),
        # fip_trend = recent FIP - season FIP per pitcher (positive = trending worse than their
        # own season line, negative = trending better) — away minus home so positive favors home,
        # same convention as fip_diff itself. See trend_home/trend_away above.
        "fip_trend_diff": (
            ((trend_away - trend_home) * trend_weight)
            if pd.notna(trend_home) and pd.notna(trend_away) else np.nan
        ),
        # higher diversity (harder to sit on one pitch) is better, home - away so positive favors home
        "pitch_diversity_diff": (
            ((diversity_home - diversity_away) * season_weight)
            if pd.notna(diversity_home) and pd.notna(diversity_away) else np.nan
        ),
        "opp_lineup_woba_diff": (lineup_away - lineup_home) if pd.notna(lineup_home) and pd.notna(lineup_away) else np.nan,
        # each team's OWN batting average over its last ~7 games — home minus away, positive
        # means home's lineup is hitting better right now, so positive favors home
        "recent_team_batting_diff": (
            (recent_avg_home - recent_avg_away) if pd.notna(recent_avg_home) and pd.notna(recent_avg_away) else np.nan
        ),
        # same as recent_team_batting_diff but over ~30 days — see recent_avg_30d_home/away above
        "recent_team_batting_30d_diff": (
            (recent_avg_30d_home - recent_avg_30d_away)
            if pd.notna(recent_avg_30d_home) and pd.notna(recent_avg_30d_away) else np.nan
        ),
        # Batter-level expected-stats/exit-velo/percentile/batted-ball lineup diffs — each team's
        # OWN lineup average, home minus away unless noted, positive favors home.
        "lineup_xwoba_diff": (xwoba_home - xwoba_away) if pd.notna(xwoba_home) and pd.notna(xwoba_away) else np.nan,
        "lineup_xba_diff": (xba_home - xba_away) if pd.notna(xba_home) and pd.notna(xba_away) else np.nan,
        "lineup_xslg_diff": (xslg_home - xslg_away) if pd.notna(xslg_home) and pd.notna(xslg_away) else np.nan,
        "lineup_hard_hit_diff": (
            (hard_hit_bat_home - hard_hit_bat_away) if pd.notna(hard_hit_bat_home) and pd.notna(hard_hit_bat_away) else np.nan
        ),
        "lineup_barrel_diff": (
            (barrel_bat_home - barrel_bat_away) if pd.notna(barrel_bat_home) and pd.notna(barrel_bat_away) else np.nan
        ),
        "lineup_sweet_spot_diff": (
            (sweet_spot_home - sweet_spot_away) if pd.notna(sweet_spot_home) and pd.notna(sweet_spot_away) else np.nan
        ),
        # chase_percentile is "how much this lineup chases relative to league" — HIGHER means
        # worse plate discipline, so away - home (positive favors home when away chases more)
        "lineup_chase_percentile_diff": (
            (chase_pctl_away - chase_pctl_home) if pd.notna(chase_pctl_home) and pd.notna(chase_pctl_away) else np.nan
        ),
        # contact_percentile is already flipped in the data layer so higher = better contact
        "lineup_contact_percentile_diff": (
            (contact_pctl_home - contact_pctl_away) if pd.notna(contact_pctl_home) and pd.notna(contact_pctl_away) else np.nan
        ),
        # Pull% treated as a mild positive (pulled fly balls are the highest-value batted-ball
        # type in modern sabermetrics) — a tendency more than a pure quality signal like the rest
        # of this batch, worth treating with extra skepticism if it doesn't backtest well.
        "lineup_pull_pct_diff": (pull_home - pull_away) if pd.notna(pull_home) and pd.notna(pull_away) else np.nan,
        # higher ground-ball% is generally worse for offensive production (fewer extra-base
        # hits), away - home so positive favors home
        "lineup_gb_pct_diff": (
            (gb_bat_away - gb_bat_home) if pd.notna(gb_bat_home) and pd.notna(gb_bat_away) else np.nan
        ),
        # away travel miles minus home's, in thousands — positive means away traveled further
        # (more fatigued), which favors home, same sign convention as everything else here
        "travel_fatigue_diff": (
            (travel_away - travel_home) / 1000.0 if pd.notna(travel_home) and pd.notna(travel_away) else np.nan
        ),
        # already home-perspective (current minus opening devigged home win prob) — positive
        # means the market has moved toward home since the line opened, so positive favors home,
        # same convention as everything else here, no further sign flip needed.
        "line_movement_diff": line_movement if line_movement is not None and pd.notna(line_movement) else np.nan,
        # already home-perspective (Pinnacle movement minus DraftKings movement) — positive
        # means the sharp book moved toward home MORE than the retail book did, same
        # sign convention as line_movement_diff — see odds_fetcher.get_market_divergence
        "market_divergence_diff": (
            market_divergence if market_divergence is not None and pd.notna(market_divergence) else np.nan
        ),
        # already home-perspective (prediction-market current prob minus Pinnacle's current
        # prob) — positive means Kalshi/Polymarket price home HIGHER than the sharp sportsbook
        # right now — see odds_fetcher.get_prediction_market_signal
        "prediction_market_diff": (
            prediction_market_signal if prediction_market_signal is not None and pd.notna(prediction_market_signal)
            else np.nan
        ),
        # centered at 0 (raw consensus_prob minus 0.5) so it's on the same scale/sign convention
        # as every other _diff feature here — positive means the book panel favors home overall
        "consensus_prob_diff": (
            (consensus_prob - 0.5) if consensus_prob is not None and pd.notna(consensus_prob) else np.nan
        ),
        # NOT sign-based (always >= 0) — how much the books in CONSENSUS_BOOKS disagree with
        # each other right now, a market-uncertainty proxy
        "book_disagreement": (
            book_disagreement if book_disagreement is not None and pd.notna(book_disagreement) else np.nan
        ),
        # signed: +1 all CONSENSUS_BOOKS moved toward home since open, -1 all toward away —
        # positive favors home, already on that convention with no sign flip needed
        "book_movement_agreement": (
            book_movement_agreement if book_movement_agreement is not None and pd.notna(book_movement_agreement)
            else np.nan
        ),
        # median rather than mean — robust to one outlier book skewing consensus_prob_diff
        "consensus_median_diff": (
            (consensus_median_prob - 0.5) if consensus_median_prob is not None and pd.notna(consensus_median_prob)
            else np.nan
        ),
        # NOT sign-based (always >= 0) — population std across CONSENSUS_BOOKS, a more holistic
        # disagreement measure than book_disagreement's max-min range
        "book_prob_std": (
            book_prob_std if book_prob_std is not None and pd.notna(book_prob_std) else np.nan
        ),
        # signed: +1 every CONSENSUS_BOOKS member currently favors home (>50%), -1 every book
        # favors away — a different axis from consensus_median_diff's probability LEVEL
        "book_favor_diff": (
            book_favor_diff if book_favor_diff is not None and pd.notna(book_favor_diff) else np.nan
        ),
        # home pitcher's posted outs line minus away's — who the market expects to go deeper
        # tonight, positive favors home — see odds_fetcher.get_pitcher_market_lines
        "market_outs_line_diff": _pitcher_market_line_diff(
            home_pitcher_market_lines, away_pitcher_market_lines, "outs_line", higher_favors_home=True
        ),
        # away pitcher's posted earned-runs line minus home's — fewer expected ER favors home
        "market_er_line_diff": _pitcher_market_line_diff(
            home_pitcher_market_lines, away_pitcher_market_lines, "er_line", higher_favors_home=False
        ),
        # away pitcher's posted hits-allowed line minus home's — fewer expected hits favors home
        "market_hits_allowed_line_diff": _pitcher_market_line_diff(
            home_pitcher_market_lines, away_pitcher_market_lines, "hits_allowed_line", higher_favors_home=False
        ),
        # home Team Total minus away's, averaged across CONSENSUS_BOOKS — the market's own
        # projected score differential, already home-perspective, positive favors home
        "team_total_diff": (
            team_total_diff if team_total_diff is not None and pd.notna(team_total_diff) else np.nan
        ),
        # game Total Runs line — NOT sign-based, no home/away meaning on its own (a scoring-
        # environment/context feature, not a "who wins" signal by itself)
        "market_total_runs": (
            market_total_runs if market_total_runs is not None and pd.notna(market_total_runs) else np.nan
        ),
        # positive favors home: home's own lineup hits well against the away pitcher's hand,
        # and/or the away lineup does NOT hit well against the home pitcher's hand
        "opp_platoon_woba_diff": (
            (platoon_vs_away_pitcher - platoon_vs_home_pitcher)
            if pd.notna(platoon_vs_home_pitcher) and pd.notna(platoon_vs_away_pitcher) else np.nan
        ),
        # more recent bullpen innings = more fatigued = worse tonight; positive favors home
        # when the AWAY pen has thrown more in the last 3 days than the home pen has
        "bullpen_fatigue_diff": bullpen_fatigue.get(away_team_abbr, 0.0) - bullpen_fatigue.get(home_team_abbr, 0.0),
        "rest_days_diff": (rest_home - rest_away) if pd.notna(rest_home) and pd.notna(rest_away) else 0,
    }

    return features


def features_to_row(features: dict) -> pd.DataFrame:
    """Turns a single feature dict into a 1-row DataFrame in the right column order,
    filling missing values with 0 (neutral) after z-scoring is handled by the model pipeline."""
    row = {col: features.get(col, np.nan) for col in FEATURE_COLUMNS}
    return pd.DataFrame([row])


# --- Strikeout-prop features -------------------------------------------
#
# Unlike FEATURE_COLUMNS above (a home-vs-away diff for one game), this is
# a per-pitcher-outing feature row: each start a pitcher makes is its own
# prediction target (their own strikeout count), not a comparison between
# the two starters. So a single game contributes two rows to this model's
# training set — the home starter's outing and the away starter's outing.

STRIKEOUT_FEATURE_COLUMNS = [
    "home_field",
    "season_k9",           # this pitcher's own season K/9
    "recent_k9",            # this pitcher's own last-5-starts K/9
    "recent_ip_per_start",  # how deep they've been going lately (K total scales with innings, not just rate)
    "h2h_k9",                # this pitcher's own K/9 specifically against tonight's opponent, when they've faced them before
    "opp_k_pct",             # opposing team's season strikeout rate — a lineup that whiffs more boosts every pitcher's K total against them
    "opp_k_pct_vs_hand",     # opposing team's strikeout rate specifically against THIS pitcher's throwing hand — a platoon-specific refinement of opp_k_pct
    "season_whiff_pct",      # this pitcher's own season-to-date whiff% (swings-and-misses per swing) — process signal behind K9
    "season_chase_pct",      # this pitcher's own season-to-date chase% (swings induced outside the zone)
    "recent_whiff_pct",      # same whiff%, but only the pitcher's last few starts — catches stuff trending up/down that the season average smooths over
    "recent_chase_pct",      # same, for chase%
    "season_pitches_per_start",  # this pitcher's own season pitches thrown per start — more pitches = more batters faced = more K opportunity, independent of IP alone
    "recent_pitches_per_start",  # same, but only the pitcher's last few starts
    "season_csw_pct",        # this pitcher's own season-to-date CSW% (called strikes + whiffs per pitch) — a blended command/stuff signal distinct from whiff%/chase% alone
    "velo_trend",             # this pitcher's own recent-minus-season fastball velocity — a declining trend caps K upside even before results-level stats catch up
    "pitch_diversity",        # this pitcher's own arsenal balance (1 - max pitch-type share) — harder to sit on one pitch
    "game_temp_f",            # game-day high temp, raw (not sign-based) — see weather.py
    "game_wind_mph",          # game-day mean wind speed, raw (not sign-based) — see weather.py
    "rest_days_effect",      # this pitcher's own rest state (short rest / normal / rusty long layoff) — see features._rest_effect
    # Market-implied win probability for THIS pitcher's own team (de-vigged moneyline) —
    # a proxy for game-script/blowout risk. A lopsided moneyline (in either direction) means
    # a manager is more likely to pull the starter early once the outcome looks decided,
    # capping strikeout upside regardless of how well they're pitching. Not captured by any
    # other feature here, all of which describe the pitcher/opponent in isolation, not how
    # likely tonight's specific game is to stay competitive deep into it.
    "team_market_win_prob",
    # This pitcher's own arsenal mix, weighted against the opposing lineup's whiff rate against
    # EACH of those specific pitch types — a lineup that whiffs a ton against sliders matters far
    # more against a pitcher who throws 50% sliders than one who's mostly fastballs. See
    # features._arsenal_matchup_score / data_collection.get_batter_pitch_arsenal.
    "arsenal_matchup_whiff",
    # This pitcher's own posted lines tonight (see odds_fetcher.get_pitcher_market_lines /
    # PLAYER_PROP_MARKETS) — the market's specialized per-pitcher-per-night forecast, distinct
    # from team_market_win_prob (game-level) and from season/recent-form averages (this is
    # TONIGHT-specific, factoring in whatever the book knows about matchup/workload/weather).
    "market_strikeout_line",     # posted strikeout O/U line — a genuinely independent K forecast
    "market_outs_line",          # posted outs-recorded O/U line — market's depth expectation tonight
    "market_er_line",            # posted earned-runs O/U line — market's run-prevention expectation
    "market_hits_allowed_line",  # posted hits-allowed O/U line — market's contact-quality-allowed expectation
]

# Market-derived features, called out separately so a baseball-only strikeout model variant can
# be defined as "everything except these," same pattern as features.MARKET_FEATURE_COLUMNS for
# the win-prob model. Every entry here must also appear in STRIKEOUT_FEATURE_COLUMNS above.
STRIKEOUT_MARKET_FEATURE_COLUMNS = [
    "team_market_win_prob", "market_strikeout_line", "market_outs_line",
    "market_er_line", "market_hits_allowed_line",
]

STRIKEOUT_BASEBALL_ONLY_FEATURE_COLUMNS = [
    c for c in STRIKEOUT_FEATURE_COLUMNS if c not in STRIKEOUT_MARKET_FEATURE_COLUMNS
]


def build_strikeout_features(
    pitcher_id: int,
    opp_team_abbr: str,
    is_home: bool,
    season_k9: float,
    team_batting: pd.DataFrame,
    recent_stats: dict = None,       # {pitcher_id: {"k9":.., "ip_per_start":..}}
    statcast: dict = None,           # {pitcher_id: {"whiff_pct":.., "chase_pct":.., "hard_hit_pct":..}}
    opp_lineup: list = None,         # confirmed opposing batter ids, may be empty/unposted
    player_batting: pd.DataFrame = None,  # mlbID/player_k_pct — needed to weight a real lineup
    recent_statcast: dict = None,    # {pitcher_id: {"whiff_pct":.., "chase_pct":..}} — last-few-starts window, see data_collection.statcast_recent_as_of
    rest_days: float = None,         # this pitcher's own days since last start
    velocity_trend: dict = None,     # {pitcher_id: {"velo_trend":..}}
    pitch_diversity: dict = None,    # {pitcher_id: {"pitch_diversity":..}}
    game_weather: dict = None,       # {"temp_max_f":.., "wind_mean_mph":..} — game-day, see weather.py
    pitcher_hand: str = None,        # "L"/"R" — this pitcher's own throwing hand, to pick the right platoon split
    team_batting_vs_hand: dict = None,  # {"L": df vs LHP, "R": df vs RHP}, each with Team/K_pct_vs_hand — same dict build_matchup_features uses
    h2h_stats: dict = None,          # {pitcher_id: {"k9":.., "starts":.., "ip":..}} — this pitcher's own history vs opp_team_abbr
    team_market_prob: float = None,  # de-vigged moneyline win prob for THIS pitcher's own team, if odds are available
    pitch_mix: dict = None,          # {pitcher_id: {pitch_type: share}} — see data_collection.statcast_pitch_mix_as_of
    batter_arsenal: pd.DataFrame = None,  # mlbID/team_name_alt/pitch_type/whiff_percent/woba — see data_collection.get_batter_pitch_arsenal
    pitcher_market_lines: dict = None,  # {"strikeout_line":.., "outs_line":.., "er_line":.., "hits_allowed_line":..} for
                                         # THIS pitcher, already resolved by the caller — see odds_fetcher.get_pitcher_market_lines
) -> dict:
    """Feature row for predicting one pitcher's strikeout total in one start."""
    pitcher_market_lines = pitcher_market_lines or {}
    recent_stats = recent_stats or {}
    statcast = statcast or {}
    recent_statcast = recent_statcast or {}
    velocity_trend = velocity_trend or {}
    pitch_diversity = pitch_diversity or {}
    game_weather = game_weather or {}
    team_batting_vs_hand = team_batting_vs_hand or {}
    h2h_stats = h2h_stats or {}
    pitch_mix = pitch_mix or {}
    batter_arsenal = batter_arsenal if batter_arsenal is not None else pd.DataFrame()
    recent = recent_stats.get(pitcher_id, {})
    pitcher_statcast = statcast.get(pitcher_id, {})
    pitcher_recent_statcast = recent_statcast.get(pitcher_id, {})

    # This pitcher's own arsenal mix, weighted against the opposing lineup's whiff rate
    # specifically against each of those pitch types — see _arsenal_matchup_score.
    this_pitcher_mix = pitch_mix.get(pitcher_id, {})
    opp_lineup_arsenal_whiff = _team_batter_arsenal(opp_lineup, batter_arsenal, opp_team_abbr, "whiff_percent")
    arsenal_matchup_whiff = _arsenal_matchup_score(this_pitcher_mix, opp_lineup_arsenal_whiff)

    real_lineup_k_pct = _lineup_k_pct(opp_lineup, player_batting)
    opp_k_pct = real_lineup_k_pct if pd.notna(real_lineup_k_pct) else _safe_get(team_batting, opp_team_abbr, "K_pct")
    opp_k_pct_vs_hand = _safe_get(
        team_batting_vs_hand.get(pitcher_hand or "R", pd.DataFrame()), opp_team_abbr, "K_pct_vs_hand"
    )
    h2h = h2h_stats.get(pitcher_id, {})
    h2h_starts = h2h.get("starts", 0)
    # No reliability shrinkage applied here (unlike build_matchup_features' h2h_fip_diff) — the
    # strikeout model has no existing recent-form reliability weighting at all (see
    # build_training_data.build_strikeout_training_set's comment on the same gap for IL-return),
    # so this stays raw, NaN when there's no head-to-head sample, consistent with that choice.
    h2h_k9 = h2h.get("k9", np.nan) if h2h_starts > 0 else np.nan

    return {
        "home_field": 1 if is_home else 0,
        "season_k9": season_k9,
        "recent_k9": recent.get("k9", np.nan),
        "recent_ip_per_start": recent.get("ip_per_start", np.nan),
        "h2h_k9": h2h_k9,
        "opp_k_pct": opp_k_pct,
        "opp_k_pct_vs_hand": opp_k_pct_vs_hand,
        "season_whiff_pct": pitcher_statcast.get("whiff_pct", np.nan),
        "season_chase_pct": pitcher_statcast.get("chase_pct", np.nan),
        "recent_whiff_pct": pitcher_recent_statcast.get("whiff_pct", np.nan),
        "recent_chase_pct": pitcher_recent_statcast.get("chase_pct", np.nan),
        "season_pitches_per_start": pitcher_statcast.get("pitches_per_start", np.nan),
        "recent_pitches_per_start": pitcher_recent_statcast.get("pitches_per_start", np.nan),
        "season_csw_pct": pitcher_statcast.get("csw_pct", np.nan),
        "velo_trend": velocity_trend.get(pitcher_id, {}).get("velo_trend", np.nan),
        "pitch_diversity": pitch_diversity.get(pitcher_id, {}).get("pitch_diversity", np.nan),
        "game_temp_f": game_weather.get("temp_max_f", np.nan),
        "game_wind_mph": game_weather.get("wind_mean_mph", np.nan),
        "rest_days_effect": _rest_effect(rest_days) if rest_days is not None else np.nan,
        "team_market_win_prob": team_market_prob if team_market_prob is not None else np.nan,
        "arsenal_matchup_whiff": arsenal_matchup_whiff,
        "market_strikeout_line": pitcher_market_lines.get("strikeout_line", np.nan),
        "market_outs_line": pitcher_market_lines.get("outs_line", np.nan),
        "market_er_line": pitcher_market_lines.get("er_line", np.nan),
        "market_hits_allowed_line": pitcher_market_lines.get("hits_allowed_line", np.nan),
    }


def strikeout_features_to_row(features: dict) -> pd.DataFrame:
    row = {col: features.get(col, np.nan) for col in STRIKEOUT_FEATURE_COLUMNS}
    return pd.DataFrame([row])
