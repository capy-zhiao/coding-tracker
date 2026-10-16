// Light / dark theme. Dark until the user picks one explicitly, then remembers the
// choice. index.html applies the same rule before React loads, so the page never flashes
// the wrong colours.
import { useSyncExternalStore } from 'react'

export type Theme = 'light' | 'dark'
const KEY = 'theme'
const DEFAULT: Theme = 'dark'

function stored(): Theme | null {
  try {
    const t = localStorage.getItem(KEY)
    return t === 'light' || t === 'dark' ? t : null
  } catch { return null }        // storage can be blocked; fall back to the default
}

let current: Theme = stored() ?? DEFAULT
const listeners = new Set<() => void>()

function apply(t: Theme) {
  current = t
  document.documentElement.classList.toggle('dark', t === 'dark')
  listeners.forEach((l) => l())
}

export function setTheme(t: Theme) {
  try { localStorage.setItem(KEY, t) } catch { /* still applies for this session */ }
  apply(t)
}

/** The current theme, re-rendering when the user toggles it. */
export function useTheme(): Theme {
  return useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => listeners.delete(cb) },
    () => current,
  )
}
