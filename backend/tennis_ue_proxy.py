"""ESTIMATED UNFORCED ERRORS for every match (2026-10-09, user: "anyway to get an unforced
errors number for every single game?").

Real unforced errors exist only for matches somebody charted by hand (Tennis Abstract's Match
Charting Project): both players are charted on 42.9% of our settled ATP games, 20.6% of WTA,
0.5% of challengers and essentially no ITF futures -- and futures are 348k of the archive's
615k player-matches. So a real UE number for every game is not available at any price.

This module provides the alternative: UE/set LEARNED from the stat line every match does have
(serve/return splits, aces, double faults, break points, the pressure-point grid, games, sets,
surface, level, gender), fit on the charted matches where the true count is known.

Shared feature code, used by _ue_proxy_build.py (accuracy) and _ue_proxy_backtest.py (does it
carry the betting edge). Keep the two in lockstep by importing from here, never copying.
"""
import re

import numpy as np
import pandas as pd

import tennis_ue as U

FEATS = ["first_serve_accuracy", "first_serve_points", "second_serve_points",
         "return_1st_serve_points", "return_2nd_serve_points",
         "ace_pg", "df_pg", "sg_rate", "rg_rate", "bp_sav", "bp_con",
         "spress_rate", "rpress_rate", "spress_pg", "rpress_pg",
         "n_sets", "n_games", "tb_rate", "games_per_set", "hold_break_gap",
         "is_clay", "is_grass", "is_itf", "is_chall", "is_tour", "is_w"]


def frac(s):
    """'13/15' -> (won, played) arrays."""
    out = np.full((len(s), 2), np.nan)
    for i, v in enumerate(s.astype(str).values):
        m = re.match(r"^(\d+)/(\d+)$", v)
        if m:
            out[i] = (int(m.group(1)), int(m.group(2)))
    return out[:, 0], out[:, 1]


def score_parts(s):
    """sets played, total games, tiebreaks, retired flag from a score string."""
    sets_, games_, tb_, ret_ = [], [], [], []
    for v in s.astype(str).values:
        v = v.strip()
        ret_.append(1.0 if re.search(r"ret|w/o|def", v, re.I) else 0.0)
        pairs = re.findall(r"(\d+)-(\d+)", v)
        sets_.append(float(len(pairs)))
        games_.append(float(sum(int(a) + int(b) for a, b in pairs)))
        tb_.append(float(len(re.findall(r"\(", v))))
    return np.array(sets_), np.array(games_), np.array(tb_), np.array(ret_)


def prep(A):
    """Derive the shared columns the features need from a raw archive frame."""
    A = A.copy()
    A["d"] = pd.to_datetime(A["date"]).dt.normalize()
    A["key"] = A["player_slug"].astype(str).map(U.norm)
    A["okey"] = A["rival_slugname"].astype(str).map(U.norm)
    sgw, sgn = frac(A["service_games_won"])
    rgw, rgn = frac(A["return_games_won"])
    ns, ng, ntb, nret = score_parts(A["score"])
    A["sg_won"], A["sg_all"], A["rg_won"], A["rg_all"] = sgw, sgn, rgw, rgn
    A["n_sets"], A["n_games"], A["n_tb"], A["retired"] = ns, ng, ntb, nret
    A["lvl"] = A["tournament_level"].astype(str).str.lower()
    A["surf"] = A["surface"].astype(str).str.title().replace({"Carpet": "Hard"})
    return A


def build_feats(D, is_w=None):
    """The model matrix. `is_w` = 1.0 for women, 0.0 for men (array or scalar)."""
    X = pd.DataFrame(index=D.index)
    for c in ("first_serve_accuracy", "first_serve_points", "second_serve_points",
              "return_1st_serve_points", "return_2nd_serve_points"):
        X[c] = pd.to_numeric(D[c], errors="coerce")
    sg = D["sg_all"].replace(0, np.nan)
    rg = D["rg_all"].replace(0, np.nan)
    X["ace_pg"] = pd.to_numeric(D["aces"], errors="coerce") / sg
    X["df_pg"] = pd.to_numeric(D["double_faults"], errors="coerce") / sg
    X["sg_rate"] = D["sg_won"] / sg
    X["rg_rate"] = D["rg_won"] / rg
    X["bp_sav"] = pd.to_numeric(D["breakpoints_saved_count"], errors="coerce") / sg
    X["bp_con"] = pd.to_numeric(D["breakpoints_converted_count"], errors="coerce") / rg
    sp = pd.to_numeric(D["serve_pressure_all"], errors="coerce")
    rp = pd.to_numeric(D["return_pressure_all"], errors="coerce")
    X["spress_rate"] = pd.to_numeric(D["serve_pressure_won"], errors="coerce") / sp.replace(0, np.nan)
    X["rpress_rate"] = pd.to_numeric(D["return_pressure_won"], errors="coerce") / rp.replace(0, np.nan)
    X["spress_pg"] = sp / sg
    X["rpress_pg"] = rp / rg
    X["n_sets"] = D["n_sets"]
    X["n_games"] = D["n_games"]
    X["tb_rate"] = D["n_tb"] / D["n_sets"].replace(0, np.nan)
    X["games_per_set"] = D["n_games"] / D["n_sets"].replace(0, np.nan)
    X["hold_break_gap"] = X["sg_rate"] - X["rg_rate"]
    X["is_clay"] = (D["surf"] == "Clay").astype(float)
    X["is_grass"] = (D["surf"] == "Grass").astype(float)
    X["is_itf"] = D["lvl"].str.contains("future").astype(float)
    X["is_chall"] = D["lvl"].str.contains("challenger").astype(float)
    X["is_tour"] = D["lvl"].isin(["atp", "wta", "grand slams"]).astype(float)
    X["is_w"] = is_w if is_w is not None else np.nan
    return X[FEATS]


def charted_truth(A):
    """Archive rows that also have a hand-charted true UE count, with UE/set attached."""
    C = U.load().copy()
    C["d"] = C["date"].dt.normalize()
    J = C[["d", "key", "okey", "unforced", "pts", "G"]].merge(
        A, on=["d", "key", "okey"], how="inner", suffixes=("_c", ""))
    J = J[(J["n_sets"] > 0) & J["unforced"].notna() & (J["n_games"] > 0) & (J["retired"] == 0)].copy()
    J["ue_set"] = J["unforced"] / J["n_sets"]
    J["ue_100"] = 100 * J["unforced"] / J["pts"]
    J["is_w"] = (J["G_c"] == "W").astype(float)
    return J
