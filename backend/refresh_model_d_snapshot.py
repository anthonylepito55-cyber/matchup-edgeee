"""
refresh_model_d_snapshot.py

"Model D" isn't a distinct trained model or feature set -- it's the ENTIRE OLD APP (main.py,
features.py, odds_fetcher.py, etc. exactly as they existed at commit 76330f5, 2026-08-16 03:35,
"before all the changes") actually executing its own real API calls against TODAY's real games.
Deliberately NOT "Model B's old trained weights fed by today's current/fixed feature-computation
code" -- that hybrid was tried first and rejected as insufficient, since it doesn't reproduce
bugs/behavior that lived in the old data-fetching code itself (e.g. the stale-opening-line
fallback fixed 2026-08-18, still present in the old worktree). This runs the genuine old
pipeline, bugs and all.

Running the full old pipeline on every live request would mean permanently duplicating
OpticOdds/MLB-API traffic forever just for a comparison feature, so this is a SNAPSHOT instead:
run this script periodically (manually, or on a schedule you set up) to refresh
data_cache/model_d_snapshot.json. main.py reads from that file cheaply on every request -- no
live computation, no worktree dependency at serving time. The snapshot goes stale between
refreshes (lineups/odds move); that's an accepted tradeoff for not running two live pipelines
forever.

Requires the sibling worktree this script created via:
    git worktree add ../mlb-predictor-model-d-worktree 76330f5
(run once from the repo root) to still exist, checked out at that commit. If that worktree is
ever removed, this script will fail loudly rather than silently produce nothing.

IMPORTANT: must be run as its own fresh `python refresh_model_d_snapshot.py` process, never
imported into an already-running process that has already imported this repo's own main.py --
Python caches modules by name in sys.modules, so an already-loaded "main"/"features"/etc. from
THIS repo would shadow the worktree's versions instead of actually running the old code.

Run directly: python refresh_model_d_snapshot.py
"""
import datetime
import json
import os
import sys

WORKTREE_BACKEND = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "mlb-predictor-model-d-worktree", "backend")
)
SNAPSHOT_PATH = os.path.join(os.path.dirname(__file__), "data_cache", "model_d_snapshot.json")


def main():
    if not os.path.isdir(WORKTREE_BACKEND):
        print(f"ERROR: worktree not found at {WORKTREE_BACKEND} -- see this file's docstring "
              f"for the `git worktree add` command that creates it.")
        raise SystemExit(1)

    sys.path.insert(0, WORKTREE_BACKEND)
    cwd_before = os.getcwd()
    os.chdir(WORKTREE_BACKEND)
    try:
        import main as old_main
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        print(f"Running the OLD (2026-08-16, pre-changes) codebase's today() for {today_str}...")
        resp = old_main.today(today_str)
    finally:
        os.chdir(cwd_before)

    games = {}
    for g in resp.get("games", []):
        key = f"{g.get('away_team_abbr')}|||{g.get('home_team_abbr')}"
        games[key] = {
            "model_b_old": g.get("market_model_prob"),
            "model_a_old": (g.get("prediction") or {}).get("home_win_prob"),
        }

    os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)
    with open(SNAPSHOT_PATH, "w") as f:
        json.dump({
            "date": today_str,
            "refreshed_at": datetime.datetime.utcnow().isoformat() + "Z",
            "games": games,
        }, f, indent=2)
    print(f"Saved {len(games)} games to {SNAPSHOT_PATH}")


if __name__ == "__main__":
    main()
