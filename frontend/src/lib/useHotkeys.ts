// Keyboard shortcuts.
//
// The one rule that makes this safe: a shortcut never fires while the caret is in an
// editable field, so pressing space inside the code editor types a space instead of
// toggling the timer. Keys listed in `alsoWhileTyping` opt out of that rule — Cmd+Enter
// has to work from inside the editor, that is the whole point of it.
import { useEffect, useRef } from 'react'

export type HotkeyMap = Record<string, (e: KeyboardEvent) => void>

/** Canonical name for a key event: "mod+enter", "space", "j", "?" */
export function keyOf(e: KeyboardEvent): string {
  const parts: string[] = []
  if (e.metaKey || e.ctrlKey) parts.push('mod')
  if (e.altKey) parts.push('alt')
  // For printable characters the shift is already reflected in e.key ("?" not "shift+/"),
  // so only named keys need an explicit shift prefix.
  if (e.shiftKey && e.key.length > 1) parts.push('shift')
  parts.push(e.key === ' ' ? 'space' : e.key.toLowerCase())
  return parts.join('+')
}

function isEditable(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el || !el.tagName) return false
  if (el.isContentEditable) return true
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)) return true
  // Monaco 0.56+ takes keyboard input through the EditContext API, so the focused node is
  // a plain <div class="native-edit-context"> — none of the checks above catch it. Testing
  // for the editor container covers that and the older hidden-textarea implementation,
  // and keeps working if Monaco changes its internals again.
  return Boolean(el.closest?.('.monaco-editor'))
}

interface Options {
  enabled?: boolean
  /** Shortcuts that still fire when the caret is in an editor or input. */
  alsoWhileTyping?: string[]
}

export function useHotkeys(map: HotkeyMap, opts: Options = {}) {
  const { enabled = true, alsoWhileTyping = ['mod+enter', 'escape'] } = opts

  // Keep the latest handlers in a ref so the listener is attached once, not on every
  // render — otherwise every keystroke that re-renders would swap the listener.
  const mapRef = useRef(map)
  mapRef.current = map
  const allowRef = useRef(alsoWhileTyping)
  allowRef.current = alsoWhileTyping

  useEffect(() => {
    if (!enabled) return
    const onKeyDown = (e: KeyboardEvent) => {
      const key = keyOf(e)
      const handler = mapRef.current[key]
      if (!handler) return
      if (isEditable(e.target) && !allowRef.current.includes(key)) return
      e.preventDefault()
      handler(e)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [enabled])
}

/** Rendered in the help overlay and as inline hints next to buttons. */
export const SHORTCUTS: { keys: string; label: string; where: string }[] = [
  { keys: 'Space',  label: 'Start / stop the timer',        where: 'Solve' },
  { keys: '1 – 4',  label: 'Pick a grade (again → easy)',   where: 'Solve' },
  { keys: '⌘ ↵',    label: 'Submit (works inside the editor)', where: 'Solve, Drill' },
  { keys: 'C',      label: 'Check the blind-write',         where: 'Drill' },
  { keys: 'J / K',  label: 'Move down / up the queue',      where: 'Today' },
  { keys: '↵',      label: 'Open the highlighted problem',  where: 'Today' },
  { keys: 'R',      label: 'Random batch of reviews',       where: 'Today' },
  { keys: 'G',      label: 'Jump to Today',                 where: 'Anywhere' },
  { keys: '?',      label: 'Show this list',                where: 'Anywhere' },
  { keys: 'Esc',    label: 'Close',                         where: 'Anywhere' },
]
