// Stats dashboard: headline numbers, daily activity and progress by chapter.
// It also holds the problem library: each chapter row expands into its problem list, and
// the search box finds any problem by number or title.
import { useEffect, useState } from 'react'
import { Bot, Flame, Library } from 'lucide-react'
import ActivityHeatmap from '../components/ActivityHeatmap'
import ProblemListRow from '../components/ProblemListRow'
import SectionTitle from '../components/SectionTitle'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useCountUp } from '../lib/motion'
import type { ChapterStat, Credit, Problem, Stats as StatsT } from '../lib/types'

export default function Stats() {
  const [s, setS] = useState<StatsT | null>(null)
  useEffect(() => { api.stats().then(setS).catch(() => {}) }, [])
  if (!s) return <p className="text-slate-400">Loading…</p>

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Metric label="Started" n={s.started} suffix={` / ${s.total_problems}`} />
        <Metric label="Mastered" n={s.mastered} hint="interval ≥ 21 days" />
        <Metric label="Streak" n={s.streak_days} suffix={s.streak_days === 1 ? ' day' : ' days'}
                hot={s.streak_days > 0} />
        <Metric label="Average time" n={s.avg_seconds ? Math.round(s.avg_seconds / 60) : null}
                suffix=" min" />
      </div>

      <ActivityHeatmap />

      <CreditCard />

      <ChapterLibrary chapters={s.by_chapter} />

      <p className="text-sm text-slate-400">
        <span className="font-mono">{s.attempts_7d}</span> attempts in the last 7 days ·{' '}
        <span className="font-mono">{s.attempts_total}</span> all time ·{' '}
        <span className="font-mono">{s.due_today}</span> due today
      </p>
    </div>
  )
}

function Metric({ label, n, suffix = '', hint, hot = false }: {
  label: string; n: number | null; suffix?: string; hint?: string; hot?: boolean
}) {
  const shown = useCountUp(n ?? 0)
  return (
    <div className="card card-glow">
      <p className="text-xs text-slate-500 flex items-center gap-1">
        {label}
        {hot && <Flame size={13} className="text-orange-500 flicker" />}
      </p>
      <p className="text-2xl font-semibold mt-1 font-mono tracking-tight">
        {n === null ? <span className="text-slate-400">—</span> : (
          <>
            <span className="text-gradient">{Math.round(shown)}</span>
            <span className="text-base font-normal text-slate-400">{suffix}</span>
          </>
        )}
      </p>
      {hint && <p className="text-[10px] text-slate-400">{hint}</p>}
    </div>
  )
}

/** Progress per chapter; a row expands into that chapter's problems. Search spans them all. */
function ChapterLibrary({ chapters }: { chapters: ChapterStat[] }) {
  const [open, setOpen] = useState<Set<number>>(new Set())
  const [lists, setLists] = useState<Record<number, Problem[]>>({})
  const [q, setQ] = useState('')
  const [results, setResults] = useState<Problem[] | null>(null)

  // Search replaces the accordion while there is a query
  useEffect(() => {
    if (!q.trim()) { setResults(null); return }
    api.problems({ q: q.trim() }).then(setResults).catch(() => setResults([]))
  }, [q])

  const toggle = (ch: number) => {
    const next = new Set(open)
    if (next.has(ch)) next.delete(ch)
    else {
      next.add(ch)
      if (!lists[ch]) {
        api.problems({ chapter: ch }).then((items) => setLists((m) => ({ ...m, [ch]: items })))
      }
    }
    setOpen(next)
  }

  return (
    <section className="card">
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <SectionTitle icon={Library} tone="emerald">Progress by chapter</SectionTitle>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Find a problem by number or title…"
          className="sm:ml-auto w-full sm:w-64 text-sm p-1.5 px-2.5 rounded-lg border border-slate-200"
        />
      </div>

      {results !== null ? (
        results.length === 0
          ? <p className="text-sm text-slate-400 px-1 py-2">No problem matches “{q}”.</p>
          : <div className="-mx-1">{results.map((p) => <ProblemListRow key={p.id} p={p} showChapter />)}</div>
      ) : (
        <div className="space-y-0.5">
          {chapters.map((c, i) => {
            const isOpen = open.has(c.chapter_num)
            return (
              <div key={c.chapter_num}>
                <button
                  onClick={() => toggle(c.chapter_num)}
                  aria-expanded={isOpen}
                  className="w-full flex items-center gap-3 text-sm rounded-lg px-1 py-1 hover:bg-slate-50"
                >
                  <span className="w-3 text-xs text-slate-300">{isOpen ? '▾' : '▸'}</span>
                  <span className="w-6 text-xs font-mono text-slate-400 text-right">{c.chapter_num}</span>
                  <span className="w-28 sm:w-40 truncate text-left">{c.chapter}</span>
                  <div className="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden flex">
                    <div className="h-full bar-fill bar-mastered"
                         style={{ width: `${(c.mastered / c.total) * 100}%`, animationDelay: `${i * 35}ms` }}
                         title={`${c.mastered} mastered`} />
                    <div className="h-full bar-fill bar-review"
                         style={{ width: `${((c.started - c.mastered) / c.total) * 100}%`, animationDelay: `${i * 35}ms` }}
                         title={`${c.started - c.mastered} in review`} />
                  </div>
                  <span className="text-xs font-mono text-slate-500 w-14 text-right">{c.started}/{c.total}</span>
                </button>
                {isOpen && (
                  <div className="ml-6 mb-2 border-l border-slate-100 pl-1">
                    {lists[c.chapter_num]
                      ? lists[c.chapter_num].map((p) => <ProblemListRow key={p.id} p={p} />)
                      : <p className="text-xs text-slate-400 px-3 py-2">Loading…</p>}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      <p className="text-xs text-slate-400 mt-3">
        <span className="inline-block w-3 h-3 bar-mastered rounded-sm align-middle" /> mastered
        <span className="inline-block w-3 h-3 bar-review rounded-sm align-middle ml-3" /> in review
        <span className="ml-3">· click a chapter to see its problems</span>
      </p>
    </section>
  )
}

/** Remaining credit on the server's AI account. Only its owner sees it, and only when the
 *  server has a key. */
function CreditCard() {
  const { me } = useAuth()
  const enabled = Boolean(me?.is_owner && me.ai_enabled)
  const [c, setC] = useState<Credit | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const load = (refresh = false) => {
    setLoading(true)
    api.credit(refresh)
      .then((r) => { setC(r); setError('') })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (enabled) load()
  }, [enabled])

  if (!enabled) return null
  const sym = c?.currency === 'CNY' ? '¥' : '$'
  const money = (x: number | null | undefined) => (x == null ? '—' : `${sym}${x.toFixed(2)}`)
  const left = c && c.granted ? c.available / c.granted : null
  // Colour tracks how much is left; the text always states it too
  const tone = left === null ? 'bg-indigo-400'
    : left < 0.1 ? 'bg-rose-400' : left < 0.25 ? 'bg-amber-400' : 'bg-emerald-400'

  return (
    <section className="card">
      <div className="flex items-baseline gap-2">
        <SectionTitle icon={Bot} tone="indigo">AI credit</SectionTitle>
        {c && (
          <span className="text-xs text-slate-400">
            {c.expires_at === 0 ? 'never expires'
              : `expires ${new Date(c.expires_at * 1000).toLocaleDateString()}`}
          </span>
        )}
        <button className="btn text-xs py-1 px-2 ml-auto" onClick={() => load(true)} disabled={loading}>
          {loading ? 'Checking…' : 'Refresh'}
        </button>
      </div>

      {error && !c && <p className="text-sm text-slate-500 mt-2">Couldn't read the balance: {error}</p>}

      {c && (
        <div className="mt-2 space-y-1.5">
          <p className="text-sm">
            <span className="text-2xl font-semibold">{c.unlimited ? 'Unlimited' : money(c.available)}</span>
            {!c.unlimited && c.granted !== null && (
              <span className="text-slate-500"> left of {money(c.granted)}</span>
            )}
          </p>
          {left !== null && !c.unlimited && (
            <div className="h-2 bg-slate-100 rounded-full overflow-hidden"
                 role="progressbar" aria-valuenow={Math.round(left * 100)} aria-valuemin={0} aria-valuemax={100}
                 aria-label="Credit remaining">
              <div className={`h-full rounded-full bar-fill ${tone}`} style={{ width: `${Math.max(left * 100, 1)}%` }} />
            </div>
          )}
          {c.used !== null && (
            <p className="text-xs text-slate-400">
              {money(c.used)} used · complexity checks run on the cheap model, interview grading on the strong one
            </p>
          )}
        </div>
      )}
    </section>
  )
}
