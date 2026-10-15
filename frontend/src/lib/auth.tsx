// Who is signed in, for the whole app. In local mode /auth/me always answers with the one
// local user, so nothing below ever shows a login page there.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, ApiError } from './api'
import type { Me } from './types'

type Status = 'loading' | 'signed-in' | 'signed-out' | 'unreachable'

interface Auth {
  me: Me | null
  status: Status
  signOut: () => Promise<void>
}

const AuthContext = createContext<Auth>({
  me: null, status: 'loading', signOut: async () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [status, setStatus] = useState<Status>('loading')

  useEffect(() => {
    api.me()
      .then((m) => { setMe(m); setStatus('signed-in') })
      .catch((e) => {
        // 401 = github mode and no session. Anything else (backend down) is left to the
        // pages, which already say "Is the backend running?".
        setStatus(e instanceof ApiError && e.status === 401 ? 'signed-out' : 'unreachable')
      })
    const expired = () => { setMe(null); setStatus('signed-out') }
    window.addEventListener('auth:expired', expired)
    return () => window.removeEventListener('auth:expired', expired)
  }, [])

  const signOut = useCallback(async () => {
    await api.logout().catch(() => {})
    setMe(null)
    setStatus('signed-out')
  }, [])

  return <AuthContext.Provider value={{ me, status, signOut }}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
