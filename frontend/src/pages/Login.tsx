// Sign-in page, shown only when the server runs in github mode and nobody is signed in.
// Local mode never gets here: /auth/me always answers with the local user.
import { useEffect, useState } from 'react'
import { api } from '../lib/api'

export default function Login() {
  const failed = new URLSearchParams(window.location.search).get('signin') === 'failed'
  const [demo, setDemo] = useState(false)
  const [entering, setEntering] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { api.health().then((h) => setDemo(h.demo)).catch(() => {}) }, [])

  const tryDemo = async () => {
    setEntering(true)
    try {
      await api.demo()
      window.location.assign('/')         // the session cookie is set; start the app fresh
    } catch (e) {
      setError((e as Error).message)
      setEntering(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="card w-full max-w-sm text-center space-y-4 py-8">
        <div className="text-3xl">🧠</div>
        <h1 className="text-xl font-semibold">LeetCode Tracker</h1>
        <p className="text-sm text-slate-500">
          Spaced repetition for NeetCode 150, Top Interview 150 and LeetCode 75: what to
          practise each day, when to review it, and whether your big-O was right.
        </p>
        {failed && (
          <p className="text-sm text-red-600">Sign-in didn't complete. Please try again.</p>
        )}
        {/* A plain link, not fetch: the browser has to leave for GitHub and come back */}
        <a href="/api/auth/login/github"
           className="btn btn-primary w-full inline-flex items-center justify-center gap-2">
          <GitHubMark />
          Sign in with GitHub
        </a>
        {demo && (
          <button onClick={tryDemo} disabled={entering} className="btn w-full">
            {entering ? 'Opening the demo…' : 'Try the demo, no account needed'}
          </button>
        )}
        {error && <p className="text-sm text-red-600">{error}</p>}
        <p className="text-xs text-slate-400">
          Only your public GitHub profile is read: username, name and avatar.
        </p>
      </div>
    </div>
  )
}

function GitHubMark() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}
