// Proficiency by algorithm pattern rather than by roadmap chapter.
//
// Chapters are a teaching order; patterns are how an interviewer thinks. 239 sits in the
// Sliding Window chapter but is really a monotonic deque, and 787 sits in Advanced Graphs
// but is really Bellman-Ford. Sorted weakest first, so the top of this page is the
// revision list.
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Wrench } from 'lucide-react'
import { api } from '../lib/api'
import { formatTime } from '../components/Timer'
import type { PatternStat, Problem } from '../lib/types'

export default function Patterns() {
  const [rows, setRows] = useState<PatternStat[]>([])
  const [open, setOpen] = useState<string | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.patterns().then((r) => {
      setRows(r)
      // Deep link from a pattern chip: /patterns#monotonic-stack
      const hash = window.location.hash.slice(1)
      if (hash && r.some((p) => p.id === hash)) setOpen(hash)
    }).catch((e) => setError(e.message))
  }, [])

  if (error) return <p className="card text-red-600">{error}</p>
  if (!rows.length) return <p className="text-slate-400">Loading…</p>

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Proficiency by pattern</h1>
        <p className="text-sm text-slate-500 mt-1">
          Weakest first. Weakness combines how much of the pattern you have mastered, how
          often attempts collapse into "again", and how many times those problems have
          failed before.
        </p>
      </div>

      <div className="card divide-y divide-slate-100 stagger">
        {rows.map((p) => (
          <PatternRow
            key={p.id} p={p}
            open={open === p.id}
            onToggle={() => setOpen(open === p.id ? null : p.id)}
          />
        ))}
      </div>
    </div>
  )
}

function PatternRow({ p, open, onToggle }: { p: PatternStat; open: boolean; onToggle: () => void }) {
  const [problems, setProblems] = useState<Problem[] | null>(null)

  useEffect(() => {
    if (open && !problems) api.problems({ pattern: p.id }).then(setProblems).catch(() => {})
  }, [open, problems, p.id])

  const pct = p.total ? (p.mastered / p.total) * 100 : 0
  // Red above 0.6, amber in the middle, green below 0.3
  const tone = p.weakness > 0.6 ? 'bg-red-500'
             : p.weakness > 0.3 ? 'bg-amber-500' : 'bg-emerald-500'

  return (
    <div id={p.id} className="py-2.5 scroll-mt-20">
      <button onClick={onToggle} className="w-full flex items-center gap-3 text-left">
        <span className={`w-1.5 h-8 rounded-full ${tone}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="font-medium">{p.label}</span>
            <span className="text-xs text-slate-400 truncate">{p.description}</span>
          </div>
          <div className="mt-1 h-1.5 bg-slate-100 rounded-full overflow-hidden max-w-xs">
            <div className="h-full bar-fill bar-mastered rounded-full" style={{ width: `${pct}%` }} />
          </div>
        </div>
        <div className="text-right text-xs text-slate-500 w-32 shrink-0">
          <div>{p.mastered}/{p.total} mastered</div>
          {p.attempts > 0 && (
            <div className="text-slate-400">
              {p.attempts} attempts · {formatTime(p.avg_seconds)} avg
            </div>
          )}
        </div>
        <span className="text-slate-300 text-xs w-4">{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <div className="pl-6 pr-2 pt-2 pb-1 space-y-2">
          <div className="flex gap-3 text-xs text-slate-500">
            <span>started {p.started}/{p.total}</span>
            {p.attempts > 0 && <span>again rate {Math.round(p.again_rate * 100)}%</span>}
            {p.template_number && (
              <Link to={`/drill/${p.template_number}`}
                    className="inline-flex items-center gap-1 text-sky-600 hover:underline">
                <Wrench size={12} /> drill this template
              </Link>
            )}
          </div>
          {problems === null
            ? <p className="text-xs text-slate-400">Loading…</p>
            : (
              <div className="flex flex-wrap gap-1">
                {problems.map((pr) => {
                  const mastered = (pr.state?.interval_days ?? 0) >= 21
                  const started = Boolean(pr.state?.due)
                  return (
                    <Link
                      key={pr.id} to={`/solve/${pr.number}`}
                      title={pr.title}
                      className={`chip ${
                        mastered ? 'bg-emerald-100 text-emerald-700'
                        : started ? 'bg-amber-100 text-amber-700'
                        : 'bg-slate-100 text-slate-500'
                      }`}
                    >
                      {pr.number}
                    </Link>
                  )
                })}
              </div>
            )}
        </div>
      )}
    </div>
  )
}
