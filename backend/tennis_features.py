"""
tennis_features.py

Feature engineering for the tennis moneyline model — built entirely from
the free Kaggle historical dataset (see tennis_data.py). Deliberately
scoped: covers surface form, opponent-quality-adjusted strength, Elo
(overall + surface), head-to-head, and rest days/fatigue. Serve & return
stats (aces, DFs, hold%, break%, first-serve%) and injury/home-country
signals are NOT included — no free data source for them was found; a paid
API (e.g. Matchstat via RapidAPI) would be needed to add them later. This
mirrors roughly 6 of the 8 factors in the methodology this was built from,
missing the "serve & return stats" (20% weight) and "injuries/motivation/
home country" (5% weight) categories entirely.

Everything here is computed in ONE chronological walk-forward pass over
the full match history (compute_walk_forward_state) — same no-leakage
discipline as the MLB side's build_training_data.py: a feature used to
predict match N is built only from state as of strictly before match N.
The same pass produces both (a) a per-historical-match feature table for
training and (b) a running "current state" snapshot (final Elo ratings,
recent-form windows, etc. as of the most recent match in the dataset) that
live serving reads directly for today's matchups — no separate live
computation path to keep in sync with the training one.
"""

import time
from collections import deque
import numpy as np
import pandas as pd

DEFAULT_ELO = 1500.0
SURFACE_FORM_WINDOW = 10   # "last 10 matches on that surface" per the methodology this is built from
OVERALL_FORM_WINDOW = 20
OPPONENT_QUALITY_WINDOW = 10
MAX_REST_DAYS = 14         # beyond this, extra rest stops mattering (long enough any injury/layoff concern would show elsewhere)
MIN_RELIABLE_H2H = 3       # fewer meetings than this and head-to-head is mostly noise, not signal

# A player's own independent surface-Elo ladder is noisy for anyone with few
# matches on that specific surface (a hard-court specialist's first few clay
# matches shouldn't swing their "clay rating" by the full Elo K-factor on
# pure vibes) — blended toward their overall Elo until they've built up real
# surface-specific sample size. At SURFACE_BLEND_HALFLIFE_MATCHES surface
# matches played, the blend is 50/50 surface/overall; it asymptotically
# approaches pure surface-Elo as that count grows.
SURFACE_BLEND_HALFLIFE_MATCHES = 10

FEATURE_COLUMNS = [
    "elo_diff",              # overall Elo, player_1 - player_2 (positive favors player_1)
    "surface_elo_diff",      # surface-specific Elo, same convention
    "surface_form_diff",     # win% over last SURFACE_FORM_WINDOW matches on this surface
    "overall_form_diff",     # win% over last OVERALL_FORM_WINDOW matches, any surface
    "opponent_quality_diff", # avg opponent Elo faced over last OPPONENT_QUALITY_WINDOW matches
    "h2h_diff",               # shrunk head-to-head win-rate diff
    "rest_days_diff",        # days since each player's last match
    "best_of_5",             # 1 if this is a best-of-5 match (men's Slams), else 0 — same for both players
]


def _k_factor(matches_played: int) -> float:
    """Ratings move fast for a player with little history, then stabilize —
    same idea as chess/Elo systems generally, tuned simply (not claiming to
    replicate any specific published tennis-Elo K-schedule)."""
    if matches_played < 30:
        return 32.0
    if matches_played < 100:
        return 24.0
    return 16.0


def _expected_win_prob(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


def _win_rate(outcomes: deque) -> float:
    return float(np.mean(outcomes)) if outcomes else np.nan


def _rest_days_feature(days) -> float:
    """Mirrors the MLB side's _rest_effect: more rest is fine up to a point, capped
    rather than let a rare multi-month layoff (injury return) dominate the diff."""
    if days is None or pd.isna(days):
        return np.nan
    return float(min(days, MAX_REST_DAYS))


def _blended_surface_elo(overall_elo: float, surface_elo: float, surface_matches: int) -> float:
    """weight ramps 0 -> 1 as surface_matches grows, 0.5 at SURFACE_BLEND_HALFLIFE_MATCHES."""
    weight = surface_matches / (surface_matches + SURFACE_BLEND_HALFLIFE_MATCHES)
    return surface_elo * weight + overall_elo * (1 - weight)


class _PlayerState:
    __slots__ = ("elo", "surface_elo", "surface_matches", "surface_form", "overall_form",
                 "opponent_quality", "last_match_date", "matches_played")

    def __init__(self):
        self.elo = DEFAULT_ELO
        self.surface_elo = {}  # surface -> elo
        self.surface_matches = {}  # surface -> count (uncapped, unlike surface_form's windowed deque — feeds the blend weight)
        self.surface_form = {}  # surface -> deque(maxlen=SURFACE_FORM_WINDOW) of 1/0
        self.overall_form = deque(maxlen=OVERALL_FORM_WINDOW)
        self.opponent_quality = deque(maxlen=OPPONENT_QUALITY_WINDOW)  # opponent's pre-match elo, each match played
        self.last_match_date = None
        self.matches_played = 0


def compute_walk_forward_state(history: pd.DataFrame):
    """
    Single chronological pass building every feature above for every
    historical match (leakage-free — each row's features use only state
    from strictly earlier matches), plus the final per-player state dicts
    usable directly for live "as of today" predictions.

    Returns (history_with_features: pd.DataFrame, player_states: dict[name -> _PlayerState], h2h: dict).
    """
    if history.empty:
        return history, {}, {}

    players: dict[str, _PlayerState] = {}
    h2h: dict[frozenset, dict[str, int]] = {}  # frozenset({p1,p2}) -> {p1: wins, p2: wins}

    feature_rows = []

    for row in history.itertuples(index=False):
        p1, p2, surface, winner = row.Player_1, row.Player_2, row.Surface, row.Winner

        s1 = players.setdefault(p1, _PlayerState())
        s2 = players.setdefault(p2, _PlayerState())

        # --- pre-match feature snapshot (nothing below this point has seen this match's outcome yet) ---
        elo1, elo2 = s1.elo, s2.elo
        selo1_raw = s1.surface_elo.get(surface, DEFAULT_ELO)
        selo2_raw = s2.surface_elo.get(surface, DEFAULT_ELO)
        selo1 = _blended_surface_elo(elo1, selo1_raw, s1.surface_matches.get(surface, 0))
        selo2 = _blended_surface_elo(elo2, selo2_raw, s2.surface_matches.get(surface, 0))
        sform1 = _win_rate(s1.surface_form.get(surface, deque()))
        sform2 = _win_rate(s2.surface_form.get(surface, deque()))
        oform1 = _win_rate(s1.overall_form)
        oform2 = _win_rate(s2.overall_form)
        oppq1 = float(np.mean(s1.opponent_quality)) if s1.opponent_quality else np.nan
        oppq2 = float(np.mean(s2.opponent_quality)) if s2.opponent_quality else np.nan

        key = frozenset((p1, p2))
        record = h2h.get(key, {})
        w1, w2 = record.get(p1, 0), record.get(p2, 0)
        total_h2h = w1 + w2
        h2h_diff = ((w1 - w2) / total_h2h) if total_h2h >= MIN_RELIABLE_H2H else 0.0

        rest1 = (row.Date - s1.last_match_date).days if s1.last_match_date is not None else None
        rest2 = (row.Date - s2.last_match_date).days if s2.last_match_date is not None else None

        feature_rows.append({
            "elo_diff": elo1 - elo2,
            "surface_elo_diff": selo1 - selo2,
            "surface_form_diff": (sform1 - sform2) if pd.notna(sform1) and pd.notna(sform2) else np.nan,
            "overall_form_diff": (oform1 - oform2) if pd.notna(oform1) and pd.notna(oform2) else np.nan,
            "opponent_quality_diff": (oppq1 - oppq2) if pd.notna(oppq1) and pd.notna(oppq2) else np.nan,
            "h2h_diff": h2h_diff,
            "rest_days_diff": (
                (_rest_days_feature(rest1) - _rest_days_feature(rest2))
                if rest1 is not None and rest2 is not None else np.nan
            ),
            "best_of_5": 1 if getattr(row, "Best_of", 3) == 5 else 0,
            "player_1_won": 1 if winner == p1 else 0,
        })

        # --- update state AFTER recording features (this is what makes it walk-forward) ---
        actual1 = 1.0 if winner == p1 else 0.0
        actual2 = 1.0 - actual1
        k1, k2 = _k_factor(s1.matches_played), _k_factor(s2.matches_played)

        exp1 = _expected_win_prob(elo1, elo2)
        s1.elo = elo1 + k1 * (actual1 - exp1)
        s2.elo = elo2 + k2 * (actual2 - (1.0 - exp1))

        # The raw per-surface ladder updates against its OWN (unblended) expectation —
        # mixing in the blended value here would let the blend's overall-Elo component
        # leak into and corrupt the surface-specific ladder itself. Blending is a
        # read-time concern (feature output above, and build_live_matchup_features),
        # not a storage concern.
        sexp1_raw = _expected_win_prob(selo1_raw, selo2_raw)
        s1.surface_elo[surface] = selo1_raw + k1 * (actual1 - sexp1_raw)
        s2.surface_elo[surface] = selo2_raw + k2 * (actual2 - (1.0 - sexp1_raw))
        s1.surface_matches[surface] = s1.surface_matches.get(surface, 0) + 1
        s2.surface_matches[surface] = s2.surface_matches.get(surface, 0) + 1

        s1.surface_form.setdefault(surface, deque(maxlen=SURFACE_FORM_WINDOW)).append(actual1)
        s2.surface_form.setdefault(surface, deque(maxlen=SURFACE_FORM_WINDOW)).append(actual2)
        s1.overall_form.append(actual1)
        s2.overall_form.append(actual2)
        s1.opponent_quality.append(elo2)
        s2.opponent_quality.append(elo1)
        s1.last_match_date = row.Date
        s2.last_match_date = row.Date
        s1.matches_played += 1
        s2.matches_played += 1

        h2h[key] = {p1: w1 + (1 if winner == p1 else 0), p2: w2 + (1 if winner == p2 else 0)}

    feat_df = pd.DataFrame(feature_rows)
    result = pd.concat([history.reset_index(drop=True), feat_df], axis=1)
    return result, players, h2h


_STATE_CACHE = {}  # (league, as_of_date) -> (computed_at, feat_df, player_states, h2h)
_STATE_CACHE_MAX_AGE_SECONDS = 3600  # the underlying history itself only refreshes ~daily; no need to recompute more often


def get_or_compute_state(league: str, history_fn, as_of_date: pd.Timestamp = None, force_refresh: bool = False):
    """In-process cache around compute_walk_forward_state — it's fast (a couple
    seconds even over 68k+ rows) but there's no reason to redo it on every single
    request when the underlying history data only changes about once a day.

    `as_of_date`, if given, strictly excludes matches on or after that date before
    computing state — the live-serving equivalent of the MLB side's "pre-game
    only" freeze discipline. The free Kaggle dataset currently lags ~1-2 weeks
    behind today, so today's own matches are never actually present in `history`
    yet in practice — but that's an accident of the current data source's update
    cadence, not something the code enforces. Without this filter, a future
    same-day (or even same-week) data refresh would silently start leaking a
    match's own result into the player state used to predict that very match —
    the exact bug already caught and fixed on the MLB side (see
    prediction_log.py), just not yet triggered here because the data happens to
    already lag enough to mask it.
    """
    cache_key = (league, str(as_of_date.date()) if as_of_date is not None else None)
    cached = _STATE_CACHE.get(cache_key)
    if not force_refresh and cached is not None and (time.time() - cached[0]) < _STATE_CACHE_MAX_AGE_SECONDS:
        return cached[1], cached[2], cached[3]
    history = history_fn()
    if as_of_date is not None and not history.empty:
        history = history[pd.to_datetime(history["Date"]) < as_of_date]
    feat_df, player_states, h2h = compute_walk_forward_state(history)
    _STATE_CACHE[cache_key] = (time.time(), feat_df, player_states, h2h)
    return feat_df, player_states, h2h


def build_live_matchup_features(
    player_1: str, player_2: str, surface: str, best_of_5: bool,
    player_states: dict, h2h: dict, as_of_date: pd.Timestamp,
) -> dict:
    """Same feature shape as the training rows, but reading the FINAL state after
    the full historical walk-forward — i.e. 'as of today'. Unknown players
    (no tour-level history in the free dataset — a qualifier, wildcard, or
    player who hasn't played a tracked match) fall back to DEFAULT_ELO and
    NaN for everything else, same as a brand-new player would mid-history."""
    s1 = player_states.get(player_1, _PlayerState())
    s2 = player_states.get(player_2, _PlayerState())

    blended_selo1 = _blended_surface_elo(s1.elo, s1.surface_elo.get(surface, DEFAULT_ELO), s1.surface_matches.get(surface, 0))
    blended_selo2 = _blended_surface_elo(s2.elo, s2.surface_elo.get(surface, DEFAULT_ELO), s2.surface_matches.get(surface, 0))

    sform1 = _win_rate(s1.surface_form.get(surface, deque()))
    sform2 = _win_rate(s2.surface_form.get(surface, deque()))
    oppq1 = float(np.mean(s1.opponent_quality)) if s1.opponent_quality else np.nan
    oppq2 = float(np.mean(s2.opponent_quality)) if s2.opponent_quality else np.nan

    key = frozenset((player_1, player_2))
    record = h2h.get(key, {})
    w1, w2 = record.get(player_1, 0), record.get(player_2, 0)
    total_h2h = w1 + w2
    h2h_diff = ((w1 - w2) / total_h2h) if total_h2h >= MIN_RELIABLE_H2H else 0.0

    rest1 = (as_of_date - s1.last_match_date).days if s1.last_match_date is not None else None
    rest2 = (as_of_date - s2.last_match_date).days if s2.last_match_date is not None else None

    return {
        "elo_diff": s1.elo - s2.elo,
        "surface_elo_diff": blended_selo1 - blended_selo2,
        "surface_form_diff": (sform1 - sform2) if pd.notna(sform1) and pd.notna(sform2) else np.nan,
        "overall_form_diff": (
            (_win_rate(s1.overall_form) - _win_rate(s2.overall_form))
            if s1.overall_form and s2.overall_form else np.nan
        ),
        "opponent_quality_diff": (oppq1 - oppq2) if pd.notna(oppq1) and pd.notna(oppq2) else np.nan,
        "h2h_diff": h2h_diff,
        "rest_days_diff": (
            (_rest_days_feature(rest1) - _rest_days_feature(rest2))
            if rest1 is not None and rest2 is not None else np.nan
        ),
        "best_of_5": 1 if best_of_5 else 0,
    }


def features_to_row(features: dict) -> pd.DataFrame:
    row = {col: features.get(col, np.nan) for col in FEATURE_COLUMNS}
    return pd.DataFrame([row])
