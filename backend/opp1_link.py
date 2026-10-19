"""OPP1 v3.5 — fixture-to-outcome linkage, A-O3 ambiguity rule, tournament normalization.

PURE FUNCTIONS over passed-in frames; no store/log access exists in this module.
Linkage tiers: (1) fixture_id equality; (2) unique both-player name match on the same UTC day.
A-O3: zero candidates -> unlinked(no_candidate); more than one -> unlinked(ambiguous), excluded
from the evaluated set and reported separately from metadata-incomplete.
"""
from __future__ import annotations

import re

MISSING_TOURNAMENT = {"", "none", "nan"}


def norm_tournament(value):
    """v3.5 V1/V3: cast to string -> whitespace-trim -> lowercase; '' / 'none' / 'nan' are
    metadata-incomplete. Returns (tournament_norm | None, is_missing)."""
    s = str(value).strip().lower() if value is not None else ""
    if s in MISSING_TOURNAMENT:
        return None, True
    return s, False


def name_keys(full: str) -> set:
    """Order-insensitive (surname, initial) keys for one player name. Both token orders are
    generated so 'Novak Djokovic' matches 'Djokovic N.'. Tokens shorter than 2 chars are
    treated as initials only."""
    toks = re.findall(r"[a-z]+", str(full).lower())
    toks = [t for t in toks if t]
    keys = set()
    for sur in toks:
        if len(sur) < 2:
            continue
        for other in toks:
            if other is not sur and other:
                keys.add((sur, other[0]))
    if len(toks) == 1 and toks[0]:
        keys.add((toks[0], ""))
    return keys


def _players_match(a1, a2, b1, b2) -> bool:
    k_a1, k_a2, k_b1, k_b2 = (name_keys(a1), name_keys(a2), name_keys(b1), name_keys(b2))
    straight = (k_a1 & k_b1) and (k_a2 & k_b2)
    flipped = (k_a1 & k_b2) and (k_a2 & k_b1)
    return bool(straight or flipped)


def link_fixture(fx: dict, outcomes) -> dict:
    """Link one store fixture to its outcome record.
    fx: dict(fixture_id, p1, p2, day) with day = 'YYYY-MM-DD' UTC of the scheduled start.
    outcomes: DataFrame with columns fixture_id, p1, p2, day, tournament.
    Returns dict(status, record|None, tournament_norm, labels)."""
    labels = []
    # tier 1: direct fixture_id equality
    hit = outcomes[outcomes["fixture_id"].astype(str) == str(fx["fixture_id"])]
    if len(hit) == 1:
        rec = hit.iloc[0]
    elif len(hit) > 1:
        return {"status": "unlinked_ambiguous", "record": None, "tournament_norm": None,
                "labels": ["ambiguous_linkage"]}
    else:
        # tier 2: same UTC day + both-player name match, exactly one candidate (A-O3)
        day = outcomes[outcomes["day"].astype(str) == str(fx["day"])]
        cands = [r for _, r in day.iterrows()
                 if _players_match(fx["p1"], fx["p2"], r["p1"], r["p2"])]
        if len(cands) == 0:
            return {"status": "unlinked_no_candidate", "record": None,
                    "tournament_norm": None, "labels": ["no_candidate"]}
        if len(cands) > 1:
            return {"status": "unlinked_ambiguous", "record": None, "tournament_norm": None,
                    "labels": ["ambiguous_linkage"]}
        rec = cands[0]
    t_norm, missing = norm_tournament(rec.get("tournament"))
    if missing:
        labels.append("metadata_incomplete")
        return {"status": "linked_metadata_incomplete", "record": rec,
                "tournament_norm": None, "labels": labels}
    return {"status": "linked", "record": rec, "tournament_norm": t_norm, "labels": labels}
