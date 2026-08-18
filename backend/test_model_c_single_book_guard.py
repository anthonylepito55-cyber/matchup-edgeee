"""
test_model_c_single_book_guard.py

Regression check for the exact bug found in Model B (get_market_snapshot): consensus_prob/
book_median_prob/book_favor_diff only required ONE book to be present, so a "consensus" could
silently be just whichever single book happened to be synced, mislabeled as a broad-market read.
Model B is left as-is per explicit instruction, but Model C (get_model_c_snapshot) was built with
a >=2-book minimum on these same three fields from day one -- this proves it actually holds by
simulating the exact failure mode (only FanDuel synced, all other books stale/missing) and
asserting the result is None (no signal), not FanDuel's price passed off as consensus.

Run directly: python test_model_c_single_book_guard.py
"""
import sys
import tempfile
from unittest.mock import patch

import odds_fetcher as of

FAKE_FIXTURE = {
    "id": "test123", "start_date": "2026-08-19T22:00:00Z",
    "home_competitors": [{"abbreviation": "NYY"}], "away_competitors": [{"abbreviation": "BOS"}],
    "home_team_display": "New York Yankees", "away_team_display": "Boston Red Sox",
}


def _fake_panel(fixture_id, sportsbooks):
    # Only FanDuel ever has a synced price -- every other MODEL_C_MONEYLINE_BOOKS/
    # MODEL_C_PREDICTION_BOOKS member is stale/missing, the exact scenario that leaked through
    # Model B's un-guarded consensus_prob.
    if "FanDuel" in sportsbooks:
        return {"FanDuel": {"home": -180, "away": 150, "home_open": -170, "away_open": 140}}
    return {}


def main():
    with patch.object(of, "OPTICODDS_API_KEY", "test"), \
         patch.object(of, "_fetch_fixture_map", return_value={}), \
         patch("requests.get") as mock_get, \
         patch.object(of, "_fetch_panel_odds", side_effect=_fake_panel), \
         patch.object(of, "_fetch_totals_panel", return_value={}), \
         patch("time.sleep", return_value=None), \
         tempfile.TemporaryDirectory() as tmp, \
         patch.object(of, "CACHE_DIR", tmp):
        mock_get.return_value.raise_for_status = lambda: None
        mock_get.return_value.json = lambda: {"data": [FAKE_FIXTURE]}
        snapshot = of.get_model_c_snapshot("2026-08-19", force_refresh=True)

    key = ("2026-08-19T22:00:00Z", "Boston Red Sox", "New York Yankees")
    v = snapshot.get(key, {})

    assert v.get("n_books") == 1, f"expected exactly 1 book present, got {v.get('n_books')}"
    assert v.get("consensus_prob") is None, "FAIL: single book leaked into consensus_prob"
    assert v.get("book_median_prob") is None, "FAIL: single book leaked into book_median_prob"
    assert v.get("book_favor_diff") is None, "FAIL: single book leaked into book_favor_diff"
    print("PASS: single-book data correctly produces no signal (None), not a false consensus.")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"FAIL: {e}")
        sys.exit(1)
