"""THREE COMPARABLE LANES FOR THE C VARIANTS (2026-10-10, user "Yes").

Each lane scores the same rule -- "this flavour of Model C picks the market DOG" -- so the
three records are directly comparable on identical games:

    c_ship_dog   the shipped 35-feature C            (the control)
    c_nohb_dog   31 feats, no pressure / hold / break (backtest dog ROI +15.5% vs +14.2%)
    c_api_dog    27 feats, everything the fast feed can supply

c_ship_dog is the point: without a control on the SAME games over the SAME window, a variant
lane's number means nothing. Backtest 2024-26 for reference -- ship +14.2%, nohb +15.5%,
api +14.6% -- and the live lanes are what actually decide, per the forward-tests-only rule.
"""
import io

P = "backend/tennis_log.py"


def rep(a, b):
    s = io.open(P, encoding="utf-8").read()
    assert s.count(a) == 1, (s.count(a), a[:90])
    io.open(P, "w", encoding="utf-8", newline="\n").write(s.replace(a, b))


# register the lanes so the study initialises them
rep('''              "coinflip_c_dog", "mchall_dog_marks",''',
    '''              "coinflip_c_dog", "mchall_dog_marks",
              # tracked Model C variants (2026-10-10): same rule, three feature sets, so the
              # control c_ship_dog is what makes the other two readable
              "c_ship_dog", "c_nohb_dog", "c_api_dog",''')

# and score them, right after the existing C-vs-gray fight block
rep('''            if c1 != g1:                       # C vs gray FIGHT (2026 bt: C-side -1.5%)
                bet("cvg_c", c1)''',
    '''            # TRACKED C VARIANTS (2026-10-10, user "Yes" to forward-tracking rather than
            # shipping on a backtest). Identical rule per lane -- back the market dog when
            # that flavour of C prefers it -- so the three lanes are comparable game by game.
            # Backtest 2024-26 dog ROI: ship +14.2%, nohb +15.5%, api +14.6%. WATCH ONLY:
            # none of these colours a card or changes a pick.
            for _vtag, _vcol in (("c_ship_dog", "model_c_p1"),
                                 ("c_nohb_dog", "model_cnohb_p1"),
                                 ("c_api_dog", "model_capi_p1")):
                _vp = r.get(_vcol)
                if _vp is None or pd.isna(_vp):
                    continue
                _vside = float(_vp) >= 0.5          # which player this C flavour prefers
                if _vside == dog1:                  # it prefers the market dog
                    bet(_vtag, _vside)

            if c1 != g1:                       # C vs gray FIGHT (2026 bt: C-side -1.5%)
                bet("cvg_c", c1)''')
print("lanes added: c_ship_dog / c_nohb_dog / c_api_dog")
