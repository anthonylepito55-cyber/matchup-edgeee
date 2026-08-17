"""
test_market_snapshot_key_collision.py

Regression check for the 2026-08-17 bug: get_market_snapshot's fetch window spans date..date+2,
so the same two teams playing on consecutive days (any 2+ game series) used to collide on a
(away_team, home_team)-only dict key -- a later day's not-yet-lined fixture (all fields None)
silently overwrote an earlier day's real market data. Fixed by keying on (start_date, away, home)
instead. This reproduces that exact shape with two synthetic fixtures and asserts both survive
distinctly, so a future "simplification" back to a team-only key breaks loudly here instead of
silently degrading live predictions again.

No pytest dependency, matching this project's existing standalone-script convention.
Run directly: python test_market_snapshot_key_collision.py
"""
import sys
import tempfile
from unittest.mock import patch, MagicMock

import odds_fetcher as of


def _fixture(start_date, away, home, away_abbr, home_abbr):
    return {
        "id": f"fx-{start_date}-{away_abbr}-{home_abbr}",
        "start_date": start_date,
        "away_team_display": away,
        "home_team_display": home,
        "away_competitors": [{"abbreviation": away_abbr}],
        "home_competitors": [{"abbreviation": home_abbr}],
    }


def main():
    day1 = _fixture("2026-08-17T22:40:00Z", "Miami Marlins", "Philadelphia Phillies", "MIA", "PHI")
    day2 = _fixture("2026-08-18T22:40:00Z", "Miami Marlins", "Philadelphia Phillies", "MIA", "PHI")

    fixtures_resp = MagicMock()
    fixtures_resp.json.return_value = {"data": [day1, day2]}
    fixtures_resp.raise_for_status = lambda: None

    with tempfile.TemporaryDirectory() as tmp, \
         patch.object(of, "CACHE_DIR", tmp), \
         patch.object(of, "OPTICODDS_API_KEY", "test-key"), \
         patch.object(of, "_fetch_fixture_map", return_value={}), \
         patch("requests.get", return_value=fixtures_resp), \
         patch.object(of, "_fetch_panel_odds", return_value={"Pinnacle": {"home": -150, "away": 130}}), \
         patch.object(of, "_fetch_totals_panel", return_value={}), \
         patch("time.sleep", return_value=None):
        snapshot = of.get_market_snapshot("2026-08-17", force_refresh=True)

    key1 = ("2026-08-17T22:40:00Z", "Miami Marlins", "Philadelphia Phillies")
    key2 = ("2026-08-18T22:40:00Z", "Miami Marlins", "Philadelphia Phillies")

    assert key1 in snapshot, f"day-1 fixture missing from snapshot entirely: {list(snapshot.keys())}"
    assert key2 in snapshot, f"day-2 fixture missing from snapshot entirely: {list(snapshot.keys())}"
    assert snapshot[key1].get("consensus_prob") is not None, (
        "day-1 fixture's real data was lost -- this is the exact regression: a team-only key "
        "would let day-2 overwrite day-1 in the dict"
    )
    print("PASS: same-teams-different-day fixtures both retained distinctly, day-1 data intact.")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"FAIL: {e}")
        sys.exit(1)
