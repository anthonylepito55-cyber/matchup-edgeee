"""ROOT-CAUSE FIX for the winner-biased archive lag (2026-10-10, user "Yes").

discover_active_slugs() walks TODAY's/upcoming matches only. A winner advances, appears on
tomorrow's slate and gets refreshed, so their row lands. A loser is out of the draw, never
reappears, and their loss row never lands until they enter a new tournament a week or two
later. That is why one-sided rows aged 0-7 days are 96.8% wins.

Fix: after the slate walk, add the players whose recent rows are demonstrably MISSING --
tennis_archive.stale_slugs() finds them exactly (a one-sided row in the window whose opponent
is tracked means that opponent played and their own row was never fetched). Capped and
failure-tolerant so the nightly can never be broken by it.
"""
import io

P = 'backend/tennisratio_ingest.py'


def rep(a, b, path=P):
    s = io.open(path, encoding='utf-8').read()
    assert s.count(a) == 1, (path, s.count(a), a[:90])
    io.open(path, 'w', encoding='utf-8', newline='\n').write(s.replace(a, b))


rep('''def discover_active_slugs(tours=("atp", "wta")):
    """Players in today's/upcoming matches — the ones that matter for betting. Rankings-based
    top-200 enumeration is a separate step (no clean rankings API found yet)."""
    slugs = {}
    for t in tours:
        for mt in fetch_today_matches(t):
            for k in ("player1_slug", "player2_slug"):
                s = mt.get(k)
                if s:
                    slugs[s] = {"tour": t.upper(),
                                "name": mt.get(k.replace("_slug", "_name")),
                                "rank": mt.get(k.replace("_slug", "_rank"))}
    return slugs''',
    '''#: how far back to chase players whose recent rows never landed, and how many per run
STALE_DAYS = 21
STALE_LIMIT = 350


def discover_active_slugs(tours=("atp", "wta"), include_stale=True):
    """Players in today's/upcoming matches — the ones that matter for betting. Rankings-based
    top-200 enumeration is a separate step (no clean rankings API found yet).

    PLUS (2026-10-10) the players whose RECENT ROWS ARE MISSING. Walking only today's slate is
    winner-biased: a winner advances, is on tomorrow's slate and gets refreshed, so their row
    lands; a loser is out of the draw, never reappears here, and their loss row never lands
    until they enter a new tournament. Measured before this fix, one-sided archive rows aged
    0-7 days were 96.8% wins (78.7% of the priced rows that young had no mirror at all), which
    overstated recent win rates by +0.064 on average for 45% of active players -- straight into
    l10, form_win, sn_win and d_m_won on the live board.

    tennis_archive.stale_slugs() names them exactly: a one-sided row in the window whose
    opponent is TRACKED means that opponent played the match and their own row was never
    fetched. Capped at STALE_LIMIT per run, most recent first, and failure-tolerant -- the
    nightly must never die because this extra pass could not run."""
    slugs = {}
    for t in tours:
        for mt in fetch_today_matches(t):
            for k in ("player1_slug", "player2_slug"):
                s = mt.get(k)
                if s:
                    slugs[s] = {"tour": t.upper(),
                                "name": mt.get(k.replace("_slug", "_name")),
                                "rank": mt.get(k.replace("_slug", "_rank"))}
    if not include_stale:
        return slugs
    try:
        import tennis_archive
        stale = tennis_archive.stale_slugs(days=STALE_DAYS, limit=STALE_LIMIT)
        added = 0
        for s in stale:
            if s and s not in slugs:
                slugs[s] = {"tour": None, "name": None, "rank": None}
                added += 1
        print(f"  [stale] +{added} players whose last {STALE_DAYS}d rows never landed "
              f"(of {len(stale)} found; cap {STALE_LIMIT})")
    except Exception as e:  # noqa: BLE001 -- never let this break the nightly refresh
        print(f"  [stale] skipped: {e}")
    return slugs''')
print('ingest now chases the losers whose rows never landed')
