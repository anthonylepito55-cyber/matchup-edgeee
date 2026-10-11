"""FORWARD-TRACK THE MODEL C VARIANTS (2026-10-10, user "Yes").

The ablation said Model C loses nothing without the game-count features, and dropping pressure
+ hold/break lifted the backtest dog ROI from +14.2% to +15.5%. That is inside backtest noise
and the standing rule is that the frozen live log decides, so the variants get LOGGED and
SCORED, not shipped. The board is unchanged: no mark, no colour, no pick moves.

  C-NOHB  31 feats, drops pressure + hold%/break%
  C-API   27 feats, also drops the per-service-game rates = everything the fast RapidAPI feed
          can actually supply, so its lane doubles as the evidence for whether that feed could
          price the board

Three lanes so the comparison is apples-to-apples on identical games:
  c_ship_dog / c_nohb_dog / c_api_dog -- each scores "this variant of C picks the market dog".
"""
import io


def rep(path, a, b):
    s = io.open(path, encoding="utf-8").read()
    assert s.count(a) == 1, (path, s.count(a), a[:90])
    io.open(path, "w", encoding="utf-8", newline="\n").write(s.replace(a, b))


# ---- 1. tennis_model_a: load the variant artifacts and let predict_c use one ------------
rep("backend/tennis_model_a.py",
    'ARTIFACT_D = os.path.join(_here, "model_artifacts", "tennis_model_d.joblib")',
    '''ARTIFACT_D = os.path.join(_here, "model_artifacts", "tennis_model_d.joblib")
# MODEL C TRACKING VARIANTS (2026-10-10): strict subsets of C's feature list, scored through
# predict_c's existing path because it builds every feature and then selects mdl["features"].
# Cached separately from _load() so the main artifact's invalidation logic is untouched.
ARTIFACT_C_VAR = {
    "nohb": os.path.join(_here, "model_artifacts", "tennis_model_c_nohb.joblib"),
    "api": os.path.join(_here, "model_artifacts", "tennis_model_c_api.joblib"),
}
_c_var_cache = {}


def c_variant(tag):
    """The variant artifact, reloaded when the file changes. None if it is not built."""
    p = ARTIFACT_C_VAR.get(tag)
    if not p or not os.path.exists(p):
        return None
    mt = os.path.getmtime(p)
    if _c_var_cache.get(tag, (None, None))[0] != mt:
        _c_var_cache[tag] = (mt, joblib.load(p))
    return _c_var_cache[tag][1]''')

rep("backend/tennis_model_a.py",
    'def predict_c(name1, name2, surface, market_p1=None):',
    'def predict_c(name1, name2, surface, market_p1=None, variant=None):')

rep("backend/tennis_model_a.py",
    '''    mdl = c["model_c"]
    X = np.array([[f.get(k, 0.0) for k in mdl["features"]]])''',
    '''    # `variant` picks a tracked subset-of-features artifact instead of the shipped one
    # (2026-10-10). Everything downstream is identical, so the variants are directly
    # comparable to C on the same game.
    mdl = c_variant(variant) if variant else c["model_c"]
    if mdl is None:
        return None
    X = np.array([[f.get(k, 0.0) for k in mdl["features"]]])''')

# ---- 2. main.py: compute the variants on the card ---------------------------------------
rep("backend/main.py",
    '''            mc = _tma.predict_c(r["player_1"], r["player_2"], r.get("surface"), market_p1=_mk1)
            if mc and _mk1 is not None:''',
    '''            mc = _tma.predict_c(r["player_1"], r["player_2"], r.get("surface"), market_p1=_mk1)
            # TRACKED C VARIANTS (2026-10-10): logged and scored, never shown as a mark. The
            # ablation found C loses nothing without the game-count features; the live lanes
            # c_nohb_dog / c_api_dog decide whether that holds outside the backtest.
            for _vt in ("nohb", "api"):
                try:
                    _vc = _tma.predict_c(r["player_1"], r["player_2"], r.get("surface"),
                                         market_p1=_mk1, variant=_vt)
                except Exception:  # noqa: BLE001
                    _vc = None
                if _vc is not None and mc is not None:
                    mc[f"p1_prob_{_vt}"] = _vc.get("p1_prob")
            if mc and _mk1 is not None:''')

# ---- 3. tennis_log: persist them and score three comparable lanes ----------------------
rep("backend/tennis_log.py",
    '''           "model_p_dog", "model_p_prob", "model_p_ev", "model_p_fev", "ac_v",''',
    '''           "model_cnohb_p1", "model_capi_p1",
           "model_p_dog", "model_p_prob", "model_p_ev", "model_p_fev", "ac_v",''')

rep("backend/tennis_log.py",
    '''            "model_p_fev": (m.get("model_p") or {}).get("fav_ev"),''',
    '''            "model_p_fev": (m.get("model_p") or {}).get("fav_ev"),
            # tracked C variants (2026-10-10), frozen like every other model output
            "model_cnohb_p1": (m.get("model_c") or {}).get("p1_prob_nohb"),
            "model_capi_p1": (m.get("model_c") or {}).get("p1_prob_api"),''')

print("backend wired: variants load, compute on the card, and persist to the log")
