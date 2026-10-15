// Shared shell for every page: top navigation plus the content area.
// Also owns the global shortcuts (? for help, G for today) so every page inherits them.
import { useState, type ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import ShortcutHelp from './ShortcutHelp'
import { useAuth } from '../lib/auth'
import { setTheme, useTheme } from '../lib/theme'
import { useHotkeys } from '../lib/useHotkeys'

const links = [
  { to: '/', label: 'Today' },
  { to: '/drill', label: 'Drills' },
  { to: '/patterns', label: 'Patterns' },
  { to: '/mock', label: 'Mock Interview' },
  { to: '/stats', label: 'Stats' },
]

export default function Layout({ children }: { children: ReactNode }) {
  const [helpOpen, setHelpOpen] = useState(false)
  const navigate = useNavigate()
  const theme = useTheme()
  const { me, signOut } = useAuth()
  const next = theme === 'dark' ? 'light' : 'dark'

  useHotkeys({
    '?': () => setHelpOpen(true),
    escape: () => setHelpOpen(false),
    g: () => navigate('/'),
  })

  return (
    <div className="min-h-screen">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <nav className="max-w-4xl mx-auto px-4 h-14 flex items-center gap-1">
          <span className="font-semibold mr-4">🧠 Coding Tracker</span>
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              // `end` stops "/" from matching every route
              end={l.to === '/'}
              // NavLink works out whether its route is the current one and hands you isActive
              className={({ isActive }) =>
                `px-2.5 py-1.5 rounded-lg text-sm transition ${
                  isActive ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
                }`
              }
            >
              {l.label}
            </NavLink>
          ))}
          <NavLink to="/settings" title="Settings" aria-label="Settings"
                   className="ml-auto text-lg px-2 rounded-lg hover:bg-slate-100">
            ⚙️
          </NavLink>
          <button
            onClick={() => setTheme(next)}
            title={`Switch to ${next} mode`}
            aria-label={`Switch to ${next} mode`}
            className="text-lg px-2 rounded-lg hover:bg-slate-100"
          >
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>
          <button
            onClick={() => setHelpOpen(true)}
            title="Keyboard shortcuts"
            className="text-slate-400 hover:text-slate-700 text-sm px-2"
          >
            ⌘ <kbd className="border border-slate-200 rounded px-1 text-xs">?</kbd>
          </button>
          {/* Signed-in accounts only; the local user has nothing to sign out of */}
          {me && me.provider !== 'local' && (
            <div className="flex items-center gap-2 pl-2 border-l border-slate-200">
              {me.avatar_url && <img src={me.avatar_url} alt="" className="w-6 h-6 rounded-full" />}
              <span className="hidden sm:inline text-sm text-slate-600">{me.login}</span>
              <button onClick={signOut} className="text-sm text-slate-500 hover:text-slate-800 px-1">
                Sign out
              </button>
            </div>
          )}
        </nav>
      </header>
      {me?.is_demo && (
        <div className="bg-amber-50 border-b border-amber-200 text-amber-900 text-sm">
          <p className="max-w-4xl mx-auto px-4 py-2">
            You're in the shared demo account: other visitors see the same data, and it's
            rebuilt every day. Sign in with GitHub to keep your own.
          </p>
        </div>
      )}
      <main className="max-w-4xl mx-auto px-4 py-6">{children}</main>
      {helpOpen && <ShortcutHelp onClose={() => setHelpOpen(false)} />}
    </div>
  )
}
