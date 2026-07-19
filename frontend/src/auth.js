// Shared password gate for the deployed dashboard (backend only enforces this when
// DASHBOARD_PASSWORD is set — see main.py — so local dev is unaffected). Patches the global
// fetch once so every /api/* call in the app picks up the stored password automatically,
// without touching each component's own fetch() call individually.
const STORAGE_KEY = 'matchup_edge_pw'

export function getPassword() {
  return localStorage.getItem(STORAGE_KEY) || ''
}

export function setPassword(pw) {
  localStorage.setItem(STORAGE_KEY, pw)
}

const nativeFetch = window.fetch.bind(window)
window.fetch = (input, init = {}) => {
  const url = typeof input === 'string' ? input : input.url
  if (url.startsWith('/api/')) {
    init = { ...init, headers: { ...(init.headers || {}), 'X-Dashboard-Password': getPassword() } }
  }
  return nativeFetch(input, init)
}
