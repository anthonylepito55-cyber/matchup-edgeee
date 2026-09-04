"""Flapping root-cause probe: every 2 minutes, force-refresh the market snapshot and record,
per pass: how many fixtures came back, how many games have consensus, and per-game which fields
are missing. Writes JSONL to data_cache/flap_probe.jsonl. Run for a few hours, then diff passes
where a game flips ok->missing to see WHICH stage lost it (fixture absent vs panel empty)."""
import json, time, datetime
import odds_fetcher as of
from data_collection import todays_date_et, get_probable_pitchers
while True:
    t0=time.time()
    d = todays_date_et()
    rec = {'ts': datetime.datetime.utcnow().isoformat(), 'date': d}
    try:
        fx = of._fetch_fixtures_full(d, (datetime.datetime.strptime(d,'%Y-%m-%d')+datetime.timedelta(days=2)).strftime('%Y-%m-%d'), statuses=('unplayed','live'))
        rec['n_fixtures'] = len(fx)
        rec['fixture_ids'] = sorted(f.get('id') for f in fx)
        snap = of.get_market_snapshot(d, force_refresh=True)
        games = get_probable_pitchers(d)
        per = {}
        for g in games:
            key=(g.get('game_time_utc'), g.get('away_team'), g.get('home_team'))
            v = snap.get(key) or {}
            per[f"{g.get('away_team_abbr','?')}@{g.get('home_team_abbr','?')}"] = {
                'consensus': v.get('consensus_prob') is not None,
                'books': len(v.get('book_probs') or {}),
                'line_movement': v.get('line_movement') is not None,
                'in_snapshot': key in snap,
            }
        rec['games'] = per
        rec['n_ok'] = sum(1 for x in per.values() if x['consensus'])
    except Exception as e:
        rec['error'] = repr(e)
    with open('data_cache/flap_probe.jsonl','a') as f:
        f.write(json.dumps(rec)+'\n')
    time.sleep(max(0, 120 - (time.time()-t0)))
