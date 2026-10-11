"""ADD A LAST-5-ON-SURFACE LINE TOO (2026-10-11, user: "And l5 stats").

Same treatment as the L10 line shipped minutes ago: identical stat set, identical surface, the
window is just shorter, SGW/RGW rebuilt from game sums so all three lines are comparable, and
the win-rate delta is measured against the 52-week line at the top.

Rendering is refactored from the duplicated L10 block into a loop over the available windows,
so L10 and L5 share one code path and a future L20 would be a one-line addition rather than a
third copy.

Both context paths again:
  * `_load()` profile builder  -> p["surfaces"][surf]["l5"]   (live board)
  * `context_asof()`           -> "surface_l5" at the top level (as-of replay)
The frontend accepts either shape, as it already does for L10.
"""
import io


def rep(path, a, b):
    s = io.open(path, encoding="utf-8").read()
    assert s.count(a) == 1, (path, s.count(a), a[:90])
    io.open(path, "w", encoding="utf-8", newline="\n").write(s.replace(a, b))


BE = "backend/tennis_context.py"
FE = "frontend/src/TennisSection.jsx"

# ---- 1. live profile builder: factor the window stat-block out, then emit L10 AND L5 ----
rep(BE,
    '''            # LAST 10 ON THIS SURFACE (2026-10-11, user: "below the hard 52w stats can u give
            # hard l10 game stats too"). Same stat set as the 52w block above, same surface,
            # only the window differs; SGW/RGW are rebuilt from the game SUMS rather than
            # averaged, exactly as the 52w figures are, so the two lines are comparable.
            l10 = sub.tail(10)
            if len(l10) >= 3:
                sga10, rga10 = l10["sg_all"].sum(), l10["rg_all"].sum()
                p["surfaces"][surf]["l10"] = {
                    "n": int(len(l10)),
                    "sv1": _fin(l10["first_serve_points"].mean()),
                    "sv2": _fin(l10["second_serve_points"].mean()),
                    "sgw": _fin(100 * l10["sg_won"].sum() / sga10) if sga10 else None,
                    "r1": _fin(l10["return_1st_serve_points"].mean()),
                    "r2": _fin(l10["return_2nd_serve_points"].mean()),
                    "rgw": _fin(100 * l10["rg_won"].sum() / rga10) if rga10 else None,
                    "win": round(float(l10["won"].mean()), 3),
                    "from": str(l10["date"].min().date()),
                }''',
    '''            # SHORT WINDOWS ON THIS SURFACE (L10 2026-10-11, L5 same day on "And l5 stats").
            # Same stat set as the 52w block above and the same surface -- only the window
            # length differs. SGW/RGW are rebuilt from the game SUMS rather than averaged,
            # exactly as the 52w figures are, so every line is directly comparable.
            for _tag, _k in (("l10", 10), ("l5", 5)):
                _w = sub.tail(_k)
                if len(_w) < 3:
                    continue
                _sga, _rga = _w["sg_all"].sum(), _w["rg_all"].sum()
                p["surfaces"][surf][_tag] = {
                    "n": int(len(_w)),
                    "sv1": _fin(_w["first_serve_points"].mean()),
                    "sv2": _fin(_w["second_serve_points"].mean()),
                    "sgw": _fin(100 * _w["sg_won"].sum() / _sga) if _sga else None,
                    "r1": _fin(_w["return_1st_serve_points"].mean()),
                    "r2": _fin(_w["return_2nd_serve_points"].mean()),
                    "rgw": _fin(100 * _w["rg_won"].sum() / _rga) if _rga else None,
                    "win": round(float(_w["won"].mean()), 3),
                    "from": str(_w["date"].min().date()),
                }''')

# ---- 2. the as-of replay path, same refactor ------------------------------------------
rep(BE,
    '''    l10 = sub.tail(10)
    sga10, rga10 = l10["sg_all"].sum(), l10["rg_all"].sum()
    stats_l10 = None
    if len(l10) >= 3:
        stats_l10 = {
            "n": int(len(l10)),
            "sv1": _fin(l10["first_serve_points"].mean()),
            "sv2": _fin(l10["second_serve_points"].mean()),
            "sgw": _fin(100 * l10["sg_won"].sum() / sga10) if sga10 else None,
            "r1": _fin(l10["return_1st_serve_points"].mean()),
            "r2": _fin(l10["return_2nd_serve_points"].mean()),
            "rgw": _fin(100 * l10["rg_won"].sum() / rga10) if rga10 else None,
            "win": round(float(l10["won"].mean()), 3),
            "from": str(l10["date"].min().date()),
        }''',
    '''    short = {}
    for _tag, _k in (("l10", 10), ("l5", 5)):
        _w = sub.tail(_k)
        if len(_w) < 3:
            continue
        _sga, _rga = _w["sg_all"].sum(), _w["rg_all"].sum()
        short[_tag] = {
            "n": int(len(_w)),
            "sv1": _fin(_w["first_serve_points"].mean()),
            "sv2": _fin(_w["second_serve_points"].mean()),
            "sgw": _fin(100 * _w["sg_won"].sum() / _sga) if _sga else None,
            "r1": _fin(_w["return_1st_serve_points"].mean()),
            "r2": _fin(_w["return_2nd_serve_points"].mean()),
            "rgw": _fin(100 * _w["rg_won"].sum() / _rga) if _rga else None,
            "win": round(float(_w["won"].mean()), 3),
            "from": str(_w["date"].min().date()),
        }
    stats_l10, stats_l5 = short.get("l10"), short.get("l5")''')

rep(BE,
    '''            "surface_l10": stats_l10,''',
    '''            "surface_l10": stats_l10, "surface_l5": stats_l5,''')

# ---- 3. frontend: one loop instead of a per-window block ------------------------------
old_fe = """      {(s.l10 || ctx.surface_l10) ? (() => {
        const q = s.l10 || ctx.surface_l10
        const d = (a, b) => (a == null || b == null) ? null : Math.round((a - b) * 10) / 10
        const dw = d(q.win * 100, s.win * 100)
        const sgn = v => `${v > 0 ? '+' : ''}${v}`
        return (
          <div style={{ paddingLeft: 12, opacity: 0.78 }}>
            {`└ ${ctx.surface_used.toLowerCase()} L${q.n}:`}
            {q.sv1 != null ? ` 1stSv ${q.sv1}%` : ''}
            {q.sv2 != null ? ` · 2ndSv ${q.sv2}%` : ''}
            {q.sgw != null ? ` · SGW ${q.sgw}%` : ''}
            {q.r1 != null ? ` · Ret1 ${q.r1}%` : ''}
            {q.r2 != null ? ` · Ret2 ${q.r2}%` : ''}
            {q.rgw != null ? ` · RGW ${q.rgw}%` : ''}
            {` · win ${(q.win * 100).toFixed(0)}%`}
            {dw != null ? (
              <span style={{ color: dw > 0 ? '#3fb950' : dw < 0 ? '#f85149' : 'var(--text-tertiary)' }}>
                {` (${sgn(dw)}pt vs ${s.window || '52w'})`}
              </span>
            ) : null}
            {q.from ? ` · since ${q.from}` : ''}
          </div>
        )
      })() : null}"""
new_fe = """      {/* SHORT WINDOWS ON THIS SURFACE (L10 then L5, 2026-10-11 user asks). One loop so the
          windows share a code path; each shows the same stat set as the 52w line above with
          its win-rate delta against that line, and fades slightly as the window shortens. */}
      {[['l10', s.l10 || ctx.surface_l10], ['l5', s.l5 || ctx.surface_l5]]
        .filter(([, q]) => q)
        .map(([tag, q], i) => {
          const dw = (q.win == null || s.win == null) ? null
            : Math.round((q.win * 100 - s.win * 100) * 10) / 10
          return (
            <div key={tag} style={{ paddingLeft: 12, opacity: i === 0 ? 0.78 : 0.68 }}>
              {`└ ${ctx.surface_used.toLowerCase()} L${q.n}:`}
              {q.sv1 != null ? ` 1stSv ${q.sv1}%` : ''}
              {q.sv2 != null ? ` · 2ndSv ${q.sv2}%` : ''}
              {q.sgw != null ? ` · SGW ${q.sgw}%` : ''}
              {q.r1 != null ? ` · Ret1 ${q.r1}%` : ''}
              {q.r2 != null ? ` · Ret2 ${q.r2}%` : ''}
              {q.rgw != null ? ` · RGW ${q.rgw}%` : ''}
              {` · win ${(q.win * 100).toFixed(0)}%`}
              {dw != null ? (
                <span style={{ color: dw > 0 ? '#3fb950' : dw < 0 ? '#f85149' : 'var(--text-tertiary)' }}>
                  {` (${dw > 0 ? '+' : ''}${dw}pt vs ${s.window || '52w'})`}
                </span>
              ) : null}
              {q.from ? ` · since ${q.from}` : ''}
            </div>
          )
        })}"""
rep(FE, old_fe, new_fe)

rep(FE,
    '''The indented second line per player (2026-10-11 user ask) is the SAME stat set over that player's LAST 10 MATCHES ON THIS SAME SURFACE, with the win-rate delta against the 52-week line above it in green/red — recent form on the court actually being played, next to the longer baseline.''',
    '''The indented lines per player (2026-10-11 user asks) are the SAME stat set over that player's LAST 10 and LAST 5 MATCHES ON THIS SAME SURFACE, each with its win-rate delta against the 52-week line above it in green/red — recent form on the court actually being played, at two depths, next to the longer baseline. Both need 3+ matches on the surface, and SGW/RGW are rebuilt from game sums exactly as the 52-week figures are, so every line is directly comparable.''')
print("L5 added alongside L10, both paths, rendering refactored to one loop")
