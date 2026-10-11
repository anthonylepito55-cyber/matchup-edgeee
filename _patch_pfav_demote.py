"""DEMOTE Ⓟ FAV TO WATCH-ONLY (2026-10-10, user "Demote P fav").

Same treatment CE5 got on 10-08: the mark keeps showing what it WOULD have picked and keeps
scoring itself in the p_fav lane, but it stops instructing a bet and can no longer colour a
card. The backend lane is untouched so the record keeps building.

Evidence:
  * live p_fav lane 7-8, -18.5% (n=15) -- men 0-4 (-100%), women 7-4 (+11.2%), and the
    Brengle -141 loss on 10-10 takes women to 7-5 / +1.9%
  * the whole favourite side in P's universe, frozen log 09-28..10-10: men -12.4% (n=241),
    women -11.3% (n=124) across 365 settles
  * the g_C gate that was supposed to rescue it is refuted -- in the walk-forward the extreme
    cases are the BEST cell (M +19.3%, W +36.4%), so there is nothing to filter on, and the
    live log says the reverse with matching g_C distributions
  * a career-peak feature (328k player-days of ranking history) carries ~zero weight
Fifth instance of the backtest-favourite / live-fail pattern.
"""
import io

P = 'frontend/src/TennisSection.jsx'


def rep(a, b, path=P):
    s = io.open(path, encoding='utf-8').read()
    assert s.count(a) == 1, (path, s.count(a), a[:90])
    io.open(path, 'w', encoding='utf-8', newline='\n').write(s.replace(a, b))


# ---- 1. it can no longer colour a card --------------------------------------------------
rep("""  const hlP = (!!(pModel && pModel.bet) && hlOK('p_dog', gHL)) || (!!(pModel && pModel.close) && hlOK(`p_close_t${pModel.close_tier || 1}`, gHL))
    || (!!(pModel && pModel.fav_bet && !pModel.close) && hlOK('p_fav', gHL))""",
    """  // Ⓟ FAV was removed from this chain on 2026-10-10 (user "Demote P fav"): a favourite-side
  // P edge no longer colours a card at all. Only the dog side and Ⓟ CLOSE can.
  const hlP = (!!(pModel && pModel.bet) && hlOK('p_dog', gHL)) || (!!(pModel && pModel.close) && hlOK(`p_close_t${pModel.close_tier || 1}`, gHL))""")

# ---- 2. the auto highlight gate must refuse it even if the lane turns positive ----------
rep("""    p_dog: { m: true, w: true }, p_fav: { m: true, w: true }, p_close: { m: true, w: true },""",
    """    p_dog: { m: true, w: true }, p_close: { m: true, w: true },
    // Ⓟ FAV DEMOTED TO WATCH 2026-10-10 (user "Demote P fav"). Backtest-positive both
    // genders (M +8.6% n=1,752, W +17.1% n=1,476) but live -18.5% (n=15), and the whole
    // favourite side of P's universe is -12.4% / -11.3% over 365 live settles. It comes
    // back only on an explicit sign-off, not on a lane turning green.
    p_fav: { m: false, w: false },""")

# ---- 3. the card line: WATCH, not TAKE --------------------------------------------------
rep("""        const st = (((laneRec && laneRec.study) || {}).p_fav) || {}
        const c = st[gHL] || {}
        const live = c.n ? `LIVE ${c.roi_pct > 0 ? '+' : ''}${Math.round(c.roi_pct * 10) / 10}% (${c.wins}-${c.n - c.wins})` : 'LIVE tracking from today'
        const ok = hlOK('p_fav', gHL)
        return (
          <div className="mono"
            title={`Ⓟ MODEL P — FAVOURITE side: P rates the dog below its price, so the -100..-200 favourite is underpriced: P ${Math.round(pModel.p_fav * 1000) / 10}% → EV +${Math.round(pModel.fav_ev * 1000) / 10}%. Backtest out-of-sample 2024-26 (fav EV ≥ 3%): men +8.6% (n=1,752), women +17.1% (n=1,476). ⚠ The live check before shipping was NEGATIVE (men −12.7% n=37, women −6.8% n=14) — favourite edges have failed live four times. Built at the user's request; lane p_fav decides.`}
            style={{ fontSize: 9, fontWeight: 800, marginBottom: 6, letterSpacing: '0.03em', color: '#e3b341', opacity: ok ? 1 : 0.8 }}>
            {ok ? null : noHL(hlWhy('p_fav', gHL))}
            Ⓟ MODEL P FAV ⚠ → <span style={{ fontSize: 12, fontWeight: 900, color: '#fff1c9' }}>TAKE {fname}{fodd != null && !isNaN(fodd) ? ` ${fodd}` : ''}</span>
            <span style={{ fontWeight: 400 }}> · P {Math.round(pModel.p_fav * 1000) / 10}% · EV +{Math.round(pModel.fav_ev * 1000) / 10}% · bt {gHL === 'w' ? 'W +17.1% (n=1,476)' : 'M +8.6% (n=1,752)'} · live check {gHL === 'w' ? '−6.8% (14)' : '−12.7% (37)'} · {live}</span>
          </div>
        )""",
    """        const st = (((laneRec && laneRec.study) || {}).p_fav) || {}
        const c = st[gHL] || {}
        const live = c.n ? `LANE ${c.roi_pct > 0 ? '+' : ''}${Math.round(c.roi_pct * 10) / 10}% (${c.wins}-${c.n - c.wins})` : 'LANE tracking from today'
        return (
          <div className="mono"
            title={`Ⓟ MODEL P — FAVOURITE side. DEMOTED TO WATCH-ONLY 2026-10-10 (user "Demote P fav"): this line NO LONGER INSTRUCTS A BET. It shows what P would have picked and keeps scoring itself in the p_fav lane. P rates the dog below its price, so it reads the −100..−200 favourite as underpriced: P ${Math.round(pModel.p_fav * 1000) / 10}% → EV +${Math.round(pModel.fav_ev * 1000) / 10}%. The backtest likes it — out-of-sample 2024-26 at fav EV ≥ 3%, men +8.6% (n=1,752), women +17.1% (n=1,476), positive every year — but LIVE it is 7-8, −18.5% (n=15), and the broader favourite side of P's own universe ran −12.4% (men, n=241) and −11.3% (women, n=124) over 365 frozen-log settles since 09-28. Two attempted rescues both failed on 10-10: gating on g_C is refuted (in the walk-forward the extreme-C favourites are the BEST cell, M +19.3% / W +36.4%, so there is nothing to filter — and the live log says the reverse with a matching g_C distribution), and a career-peak-rank feature built from 328,168 player-days carries ~zero weight. This is the fifth favourite edge to pass the backtest and fail live. It earns a colour back only on an explicit sign-off. The LANE number is the live frozen-log record for this match's gender.`}
            style={{ fontSize: 9, fontWeight: 700, marginBottom: 6, letterSpacing: '0.03em', color: 'var(--text-secondary)', opacity: 0.85 }}>
            Ⓟ MODEL P FAV <span style={{ color: '#e3b341' }}>⚠ WATCH ONLY</span> → <span style={{ fontSize: 11, fontWeight: 800, color: 'var(--text-primary)' }}>would have taken {fname}{fodd != null && !isNaN(fodd) ? ` ${fodd}` : ''}</span>
            <span style={{ fontWeight: 400 }}> · NO BET — demoted 10-10, favourite edges have failed live 5x · P {Math.round(pModel.p_fav * 1000) / 10}% · EV +{Math.round(pModel.fav_ev * 1000) / 10}% · bt {gHL === 'w' ? 'W +17.1% (n=1,476)' : 'M +8.6% (n=1,752)'} · live all favs {gHL === 'w' ? '−11.3% (124)' : '−12.4% (241)'} · {live}</span>
          </div>
        )""")

# ---- 4. Ⓟ MODEL P TODAY panel: the fav chips are watch, not bets ------------------------
rep("""    else if (p.fav_bet) rows.push({ side: 'fav', who: p.fav === 1 ? m.player_1 : m.player_2, opp: p.fav === 1 ? m.player_2 : m.player_1,
      od: p.fav === 1 ? lo.player_1 : lo.player_2, pr: p.p_fav, ev: p.fav_ev, t: m.start_time_utc, st: m.status, lg: m.league })""",
    """    // side 'fav' is WATCH-ONLY from 2026-10-10 (user "Demote P fav") -- kept visible so the
    // cell keeps being scored, rendered muted and never counted as a bet.
    else if (p.fav_bet) rows.push({ side: 'fav', watch: true, who: p.fav === 1 ? m.player_1 : m.player_2, opp: p.fav === 1 ? m.player_2 : m.player_1,
      od: p.fav === 1 ? lo.player_1 : lo.player_2, pr: p.p_fav, ev: p.fav_ev, t: m.start_time_utc, st: m.status, lg: m.league })""")

rep("""              border: `1px solid ${r.side === 'dog' ? 'rgba(45,212,191,0.7)' : r.side === 'close' ? 'rgba(94,234,212,0.9)' : 'rgba(227,179,65,0.7)'}`, color: r.side === 'dog' ? '#2dd4bf' : r.side === 'close' ? '#5eead4' : '#e3b341' }}
              title={`${r.who} vs ${r.opp} · ${String(r.lg || '').toUpperCase()} · P ${Math.round(r.pr * 1000) / 10}%`}>
              {String(r.lg || '').startsWith('itf') ? <span style={{ fontSize: 8, opacity: 0.75 }}>ITF </span> : null}{r.side === 'dog' ? 'Ⓟ' : r.side === 'close' ? `Ⓟ CLOSE T${r.tier}` : 'Ⓟ FAV⚠'} <b style={{ color: 'var(--text-primary)' }}>{(r.who || '').split(' ').slice(-1)[0]}</b>""",
    """              border: `1px solid ${r.side === 'dog' ? 'rgba(45,212,191,0.7)' : r.side === 'close' ? 'rgba(94,234,212,0.9)' : 'var(--border)'}`, color: r.side === 'dog' ? '#2dd4bf' : r.side === 'close' ? '#5eead4' : 'var(--text-secondary)', opacity: r.watch ? 0.8 : 1 }}
              title={`${r.who} vs ${r.opp} · ${String(r.lg || '').toUpperCase()} · P ${Math.round(r.pr * 1000) / 10}%${r.watch ? ' · WATCH ONLY, demoted 2026-10-10: the favourite side is NOT a bet. Live p_fav 7-8 -18.5% (n=15) and the whole favourite side of P\\u0027s universe is -12.4% / -11.3% over 365 live settles.' : ''}`}>
              {String(r.lg || '').startsWith('itf') ? <span style={{ fontSize: 8, opacity: 0.75 }}>ITF </span> : null}{r.side === 'dog' ? 'Ⓟ' : r.side === 'close' ? `Ⓟ CLOSE T${r.tier}` : 'Ⓟ FAV ⚠ watch'} <b style={{ color: 'var(--text-primary)' }}>{(r.who || '').split(' ').slice(-1)[0]}</b>""")

rep("""        Ⓟ MODEL P TODAY · {rows.filter(r => r.side === 'dog').length} dog · {rows.filter(r => r.side === 'close').length} close · {rows.filter(r => r.side === 'fav').length} fav
        <span style={{ fontWeight: 400, color: 'var(--text-tertiary)' }}> · dogs M +100..+200 / W +100..+250 · dog bt M +14.2% / W +23.9% · fav bt M +8.6% / W +17.1% (⚠ live check negative) · record on the Ⓟ Model P tab</span>""",
    """        Ⓟ MODEL P TODAY · {rows.filter(r => r.side === 'dog').length} dog · {rows.filter(r => r.side === 'close').length} close · <span style={{ color: 'var(--text-tertiary)' }}>{rows.filter(r => r.side === 'fav').length} fav (watch)</span>
        <span style={{ fontWeight: 400, color: 'var(--text-tertiary)' }}> · dogs M +100..+200 / W +100..+250 · dog bt M +14.2% / W +23.9% · <b>FAV SIDE DEMOTED TO WATCH 10-10 — not a bet</b> (live −18.5% n=15; all favs in universe −12.4% / −11.3% over 365) · record on the Ⓟ Model P tab</span>""")

# ---- 5. the Model P tab lane label ------------------------------------------------------
rep("""        {lane(L.p_fav, 'Ⓟ FAV bets (EV ≥ 3%) ⚠', 'favourite side')}""",
    """        {lane(L.p_fav, 'Ⓟ FAV (EV ≥ 3%) ⚠ WATCH ONLY', 'favourite side — DEMOTED 2026-10-10, no longer a bet; still scored')}""")

# ---- 6. the per-match Model P detail line -----------------------------------------------
rep("""            <span style={{ fontWeight: 700, color: mp.bet ? '#2dd4bf' : mp.fav_bet ? '#e3b341' : 'var(--text-tertiary)' }}> · {mp.bet ? `BET ${dogN.split(' ').slice(-1)[0]}` : mp.fav_bet ? `FAV BET ${favN.split(' ').slice(-1)[0]} ⚠` : 'no bet'}</span>""",
    """            <span style={{ fontWeight: 700, color: mp.bet ? '#2dd4bf' : 'var(--text-tertiary)' }}> · {mp.bet ? `BET ${dogN.split(' ').slice(-1)[0]}` : mp.fav_bet ? `FAV ${favN.split(' ').slice(-1)[0]} ⚠ watch only (demoted 10-10)` : 'no bet'}</span>""")

# ---- 7. the Model P header tooltip ------------------------------------------------------
rep("""        title="Model P = the profit model: an offset model on the market (it starts from the price and only learns where the price is wrong). DOG bets: +100..+200 dogs with P EV ≥ 5% — backtest 2024-26 men +14.2% (n=3,235), women +21.4% (n=2,442). FAV bets: −100..−200 favourites with P EV ≥ 3% — backtest men +8.6%, women +17.1%, but the live check before shipping was negative. Full record on the Ⓟ Model P tab.">""",
    """        title="Model P = the profit model: an offset model on the market (it starts from the price and only learns where the price is wrong). DOG bets: +100..+200 dogs with P EV ≥ 5% — backtest 2024-26 men +14.2% (n=3,235), women +21.4% (n=2,442). FAV side: −100..−200 favourites with P EV ≥ 3% — DEMOTED TO WATCH-ONLY on 2026-10-10 and no longer a bet. The backtest liked it (men +8.6%, women +17.1%) but live it went 7-8, −18.5% (n=15), and the whole favourite side of P's universe ran −12.4% (men) / −11.3% (women) over 365 frozen-log settles. Gating it on g_C was refuted and a career-peak feature carried no weight. Full record on the Ⓟ Model P tab.">""")

print('Ⓟ FAV demoted to watch-only: 7 edits applied')
