import React, { useEffect, useState } from 'react'

export default function PropsSection() {
  const [props, setProps] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [marketFilter, setMarketFilter] = useState('all')

  useEffect(() => { fetchProps() }, [])

  async function fetchProps() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/props')
      if (!res.ok) throw new Error(`API returned ${res.status}`)
      const json = await res.json()
      setProps(json.props || [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const markets = ['all', ...Array.from(new Set(props.map(p => p.market))).sort()]
  const shown = marketFilter === 'all' ? props : props.filter(p => p.market === marketFilter)

  return (
    <div>
      <div style={{
        marginTop: 20, padding: '10px 16px', borderRadius: 6,
        background: 'rgba(140,140,150,0.06)', border: '1px solid var(--line)',
        fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.5,
      }}>
        Every player prop where PrizePicks has posted a line, compared against every sportsbook
        that has the SAME line — each book's over/under price is de-vigged into a fair
        probability, then averaged across books into one consensus number. PrizePicks' own price
        is shown for reference only (it's a pick'em price, not devigged — there's no real
        two-sided market to remove juice from). Sorted highest consensus probability first.
        Display-only — doesn't feed either prediction model.
      </div>

      {markets.length > 2 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
          <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            market:
          </span>
          {markets.map(m => (
            <button key={m} onClick={() => setMarketFilter(m)} className={marketFilter === m ? '' : 'btn-ghost'} style={{
              background: marketFilter === m ? 'var(--panel-raised)' : 'transparent',
              border: `1px solid ${marketFilter === m ? 'var(--amber)' : 'var(--line)'}`,
              borderRadius: 5, color: marketFilter === m ? 'var(--amber)' : 'var(--text-secondary)',
              fontSize: 11, padding: '4px 10px', fontFamily: 'var(--font-mono)', textTransform: 'capitalize',
            }}>
              {m === 'all' ? `all (${props.length})` : m}
            </button>
          ))}
        </div>
      )}

      {error && (
        <div style={{
          background: 'rgba(255,92,92,0.08)', border: '1px solid var(--edge-neg)',
          borderRadius: 8, padding: '14px 18px', margin: '20px 0', color: 'var(--edge-neg)',
          fontSize: 14, fontFamily: 'var(--font-mono)',
        }}>
          Couldn't reach the props API ({error})
        </div>
      )}

      {loading && (
        <div style={{ color: 'var(--text-tertiary)', padding: '40px 0', textAlign: 'center', fontSize: 13 }}>
          loading…
        </div>
      )}

      {!loading && !error && props.length === 0 && (
        <div style={{ color: 'var(--text-secondary)', padding: '60px 0', textAlign: 'center' }}>
          No props with a matching PrizePicks + sportsbook line right now — check back closer to game time.
        </div>
      )}

      {!loading && !error && shown.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 14 }}>
          {shown.map((p, i) => <PropRow key={`${p.player_name}-${p.market}-${i}`} prop={p} />)}
        </div>
      )}
    </div>
  )
}

function PropRow({ prop: p }) {
  const pct = (p.consensus_prob * 100).toFixed(1)
  const strong = p.consensus_prob >= 0.6
  const priceStr = (price) => price == null ? '—' : (price > 0 ? `+${price}` : `${price}`)

  return (
    <div style={{
      background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 8,
      padding: '10px 16px', borderLeft: `3px solid ${strong ? 'var(--edge-pos)' : 'var(--line)'}`,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap',
    }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
          {p.player_name}
          <span className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 400, marginLeft: 8 }}>
            {p.market}
          </span>
        </div>
        <div className="mono" style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 2 }}>
          {p.matchup} · line {p.line} · PrizePicks {priceStr(p.prizepicks_over_price)}/{priceStr(p.prizepicks_under_price)}
          · {p.num_books} book{p.num_books === 1 ? '' : 's'} ({p.books_used.join(', ')})
        </div>
      </div>
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        <div className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>
          {p.side}
        </div>
        <div className="mono" style={{ fontSize: 18, fontWeight: 700, color: strong ? 'var(--edge-pos)' : 'var(--text-primary)' }}>
          {pct}%
        </div>
      </div>
    </div>
  )
}
