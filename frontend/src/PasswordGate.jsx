import { useState, useEffect } from 'react'
import { getPassword, setPassword } from './auth'

// Blocks rendering the dashboard until /api/model/status succeeds. When the backend has no
// DASHBOARD_PASSWORD set (local dev), that call succeeds with no header needed and this never
// shows a prompt. When it's set (deployed), a 401 shows the password form instead.
export default function PasswordGate({ children }) {
  const [status, setStatus] = useState('checking') // checking | ok | needed
  const [input, setInput] = useState('')
  const [errorMsg, setErrorMsg] = useState('')

  async function check() {
    try {
      const res = await fetch('/api/model/status')
      setStatus(res.status === 401 ? 'needed' : 'ok')
    } catch {
      setStatus('ok') // backend unreachable — let the app's own error handling surface that
    }
  }

  useEffect(() => { check() }, [])

  async function submit(e) {
    e.preventDefault()
    setPassword(input)
    setErrorMsg('')
    setStatus('checking')
    const res = await fetch('/api/model/status')
    if (res.status === 401) {
      setErrorMsg('Wrong password')
      setStatus('needed')
    } else {
      setStatus('ok')
    }
  }

  if (status === 'checking') return null
  if (status === 'needed') {
    return (
      <div style={{
        minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: '#0b0e14',
      }}>
        <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 12, width: 260 }}>
          <div style={{ color: '#fff', fontFamily: 'monospace', fontSize: 14, letterSpacing: 1 }}>
            MATCHUP <span style={{ color: '#f5a623' }}>EDGE</span>
          </div>
          <input
            type="password"
            autoFocus
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Password"
            style={{
              padding: 10, borderRadius: 6, border: '1px solid #2a2f3a',
              background: '#11151c', color: '#fff', fontFamily: 'monospace',
            }}
          />
          <button type="submit" style={{
            padding: 10, borderRadius: 6, border: 'none',
            background: '#f5a623', color: '#000', fontWeight: 600, cursor: 'pointer',
          }}>
            Enter
          </button>
          {errorMsg && <div style={{ color: '#e5484d', fontSize: 12, fontFamily: 'monospace' }}>{errorMsg}</div>}
        </form>
      </div>
    )
  }
  return children
}
