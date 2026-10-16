// Shared shell for every page: top navigation plus the content area.
// Also owns the global shortcuts (? for help, G for today) so every page inherits them.
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { Braces, Keyboard, LogOut, Moon, Settings, Sun } from 'lucide-react'
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

const iconBtn = 'grid place-items-center w-8 h-8 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition'

export default function Layout({ children }: { children: ReactNode }) {
  const [helpOpen, setHelpOpen] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const theme = useTheme()
  const { me, signOut } = useAuth()
  const next = theme === 'dark' ? 'light' : 'dark'

  useHotkeys({
    '?': () => setHelpOpen(true),
    escape: () => setHelpOpen(false),
    g: () => navigate('/'),
  })

  // The gradient pill slides to whichever link is active. Measured rather than styled per
  // link, so it can travel between them; re-measured once the web fonts change the widths.
  const linksRef = useRef<HTMLDivElement>(null)
  const [pill, setPill] = useState<{ x: number; w: number } | null>(null)
  useLayoutEffect(() => {
    const measure = () => {
      const a = linksRef.current?.querySelector<HTMLElement>('a[aria-current="page"]')
      setPill(a ? { x: a.offsetLeft, w: a.offsetWidth } : null)
    }
    measure()
    document.fonts?.ready.then(measure)
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [location.pathname])

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-slate-200/70 bg-white/70 backdrop-blur-md">
        <nav className="max-w-4xl mx-auto px-4 h-14 flex items-center gap-2">
          <NavLink to="/" aria-label="Coding Tracker" className="flex items-center gap-2 mr-1 shrink-0">
            <span className="logo-mark"><Braces size={16} strokeWidth={2.5} /></span>
            <span className="hidden md:inline font-semibold tracking-tight text-gradient">Coding Tracker</span>
          </NavLink>

          <div ref={linksRef} className="relative flex items-center gap-0.5 min-w-0 overflow-x-auto no-scrollbar">
            {pill && (
              <span aria-hidden className="nav-pill" style={{ transform: `translateX(${pill.x}px)`, width: pill.w }} />
            )}
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                // `end` stops "/" from matching every route
                end={l.to === '/'}
                className={({ isActive }) =>
                  `relative z-10 px-2.5 py-1.5 rounded-lg text-sm whitespace-nowrap transition-colors duration-300 ${
                    isActive ? 'text-[color:var(--on-accent)] font-medium' : 'text-slate-500 hover:text-slate-800'
                  }`
                }
              >
                {l.label}
              </NavLink>
            ))}
          </div>

          <div className="ml-auto flex items-center gap-0.5 shrink-0">
            <NavLink to="/settings" title="Settings" aria-label="Settings" className={iconBtn}>
              <Settings size={17} />
            </NavLink>
            <button onClick={() => setTheme(next)} title={`Switch to ${next} mode`}
                    aria-label={`Switch to ${next} mode`} className={iconBtn}>
              {/* keyed, so the new icon spins in each time the theme flips */}
              <span key={theme} className="spin-in">
                {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
              </span>
            </button>
            <button onClick={() => setHelpOpen(true)} title="Keyboard shortcuts (?)"
                    aria-label="Keyboard shortcuts" className={`${iconBtn} hidden md:grid`}>
              <Keyboard size={17} />
            </button>
            {/* Signed-in accounts only; the local user has nothing to sign out of */}
            {me && me.provider !== 'local' && (
              <div className="flex items-center gap-1.5 pl-2 ml-1 border-l border-slate-200">
                {me.avatar_url && (
                  <img src={me.avatar_url} alt="" className="w-6 h-6 rounded-full ring-2 ring-slate-200" />
                )}
                <span className="hidden sm:inline text-sm text-slate-600">{me.login}</span>
                <button onClick={signOut} title="Sign out" aria-label="Sign out" className={iconBtn}>
                  <LogOut size={16} />
                </button>
              </div>
            )}
          </div>
        </nav>
      </header>
      {me?.is_demo && (
        <div className="bg-amber-50 border-b border-amber-200 text-amber-800 text-sm">
          <p className="max-w-4xl mx-auto px-4 py-2">
            You're in the shared demo account: other visitors see the same data, and it's
            rebuilt every day. Sign in with GitHub to keep your own.
          </p>
        </div>
      )}
      <main className="max-w-4xl mx-auto px-4 py-6">
        {/* keyed by route, so each page plays its entrance */}
        <div key={location.pathname} className="page-in">{children}</div>
      </main>
      {helpOpen && <ShortcutHelp onClose={() => setHelpOpen(false)} />}
    </div>
  )
}
