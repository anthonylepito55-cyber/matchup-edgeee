"""LAST-10-ON-SURFACE STATS UNDER THE 52-WEEK LINE (2026-10-11, user: "Below the hard 52 w
stats can u give hard l10 game stats too").

The TR CONTEXT block shows each player's stats over the 52-week window ON THIS SURFACE
(falling back to L20 then All-surfaces when thin). This adds the same stat set computed over
the LAST 10 MATCHES on that same surface, on its own line underneath, so recent form on the
court being played is readable next to the season-long baseline.

Same stats, same surface, same pre-match as-of cut -- only the window differs:
    1stSv / 2ndSv / SGW / Ret1 / Ret2 / RGW / win%
SGW and RGW are recomputed from the game SUMS over the 10 matches rather than averaged, which
is how the 52w figures are built, so the two lines are directly comparable.

Also carries a delta on win% so the line answers "is this player above or below their own
52-week norm on this court" without arithmetic.
"""
import io


def rep(path, a, b):
    s = io.open(path, encoding="utf-8").read()
    assert s.count(a) == 1, (path, s.count(a), a[:90])
    io.open(path, "w", encoding="utf-8", newline="\n").write(s.replace(a, b))


# ---- backend: add a last-10-on-surface block beside surface_stats ----------------------
rep("backend/tennis_context.py",
    '''    recent = g.tail(25)''',
    '''    # LAST 10 ON THIS SURFACE (2026-10-11, user ask: "below the hard 52w stats can u give
    # hard l10 game stats too"). Same stat set and the same pre-match cut as the 52w block
    # above -- only the window differs -- and SGW/RGW are rebuilt from the game sums rather
    # than averaged so the two lines are directly comparable. `sub` is already filtered to
    # the chosen surface; if the 52w fallback widened to All, this follows it.
    l10 = sub.tail(10)
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
        }
    recent = g.tail(25)''')

rep("backend/tennis_context.py",
    '''    return {"slug": cur["slug"], "tour": cur.get("tour"), "surface_used": surf, "surface_stats": stats,''',
    '''    return {"slug": cur["slug"], "tour": cur.get("tour"), "surface_used": surf, "surface_stats": stats,
            "surface_l10": stats_l10,''')

# ---- frontend: a second line under the 52w one -----------------------------------------
rep("frontend/src/TennisSection.jsx",
    """      {ctx.avg_opp_rank != null ? ` · avg opp #${ctx.avg_opp_rank}` : ''}
    </div>
  )
}""",
    """      {ctx.avg_opp_rank != null ? ` · avg opp #${ctx.avg_opp_rank}` : ''}
      {/* LAST 10 ON THIS SURFACE (2026-10-11, user ask) -- same stats, same court, shorter
          window, with the win% delta against the 52w line directly above so recent form is
          readable without arithmetic. Indented and dimmer so the 52w line stays primary. */}
      {ctx.surface_l10 ? (() => {
        const q = ctx.surface_l10
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
      })() : null}
    </div>
  )
}""")

# the tooltip should say what the second line is
rep("frontend/src/TennisSection.jsx",
    '''title="TennisRatio profile context, real stat names on the site's 52-week surface window (falls back to last-20 when thin): 1stSv/2ndSv = 1st/2nd-serve points won, SGW/RGW = service/return games won (p## = percentile within OUR ingested pool for that tour), plus last-25 record vs top-200-ranked opponents, pressure-point conversion, and median recent opponent rank.''',
    '''title="TennisRatio profile context, real stat names on the site's 52-week surface window (falls back to last-20 when thin): 1stSv/2ndSv = 1st/2nd-serve points won, SGW/RGW = service/return games won (p## = percentile within OUR ingested pool for that tour), plus last-25 record vs top-200-ranked opponents, pressure-point conversion, and median recent opponent rank. The indented second line per player (2026-10-11 user ask) is the SAME stat set over that player's LAST 10 MATCHES ON THIS SAME SURFACE, with the win-rate delta against the 52-week line above it in green/red — recent form on the court actually being played, next to the longer baseline.''')
print("hard L10 line added: backend block + card line + tooltip")
