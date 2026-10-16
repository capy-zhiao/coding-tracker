// One problem in a library list: difficulty, number, title, and where it stands in review.
import { Link } from 'react-router-dom'
import type { Problem } from '../lib/types'

const DIFF_COLOR: Record<string, string> = {
  Easy: 'bg-emerald-100 text-emerald-700',
  Medium: 'bg-amber-100 text-amber-700',
  Hard: 'bg-rose-100 text-rose-700',
}

export default function ProblemListRow({ p, showChapter = false }: { p: Problem; showChapter?: boolean }) {
  const mastered = (p.state?.interval_days ?? 0) >= 21
  return (
    <Link to={`/solve/${p.number}`}
          className="row flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-slate-100/60 transition text-sm">
      <span className={`chip ${DIFF_COLOR[p.difficulty]}`}>{p.difficulty[0]}</span>
      <span className="font-mono text-xs text-slate-400 w-12 text-right">{p.number}</span>
      <span className="flex-1 truncate">{p.title}</span>
      {showChapter && <span className="text-xs text-slate-400 truncate max-w-32">{p.chapter}</span>}
      <ListTags p={p} />
      {p.state?.due
        ? <span className={`w-28 shrink-0 text-right text-xs ${mastered ? 'text-emerald-600' : 'text-slate-400'}`}>
            {mastered ? 'mastered' : `${p.state.interval_days}d interval`}
            {p.state.lapses > 0 && ` · ✗${p.state.lapses}`}
          </span>
        : <span className="w-28 shrink-0 text-right text-xs text-slate-300">not started</span>}
    </Link>
  )
}

// Which lists a problem belongs to. One fixed column per list, so the tags line up down
// the page and a gap means "not in this list".
const LISTS: { key: 'in_neetcode150' | 'in_top150' | 'in_lc75'; label: string; title: string; tone: string }[] = [
  { key: 'in_neetcode150', label: 'NC 150', title: 'NeetCode 150', tone: 'bg-indigo-50 text-indigo-700' },
  { key: 'in_top150', label: 'LC 150', title: 'LeetCode Top Interview 150', tone: 'bg-purple-50 text-purple-700' },
  { key: 'in_lc75', label: 'LC 75', title: 'LeetCode 75', tone: 'bg-sky-50 text-sky-700' },
]

function ListTags({ p }: { p: Problem }) {
  return (
    <span className="flex shrink-0 gap-1">
      {LISTS.map((l) => (
        <span key={l.key} className="w-16 flex justify-center">
          {p[l.key] && <span className={`chip ${l.tone}`} title={l.title}>{l.label}</span>}
        </span>
      ))}
    </span>
  )
}
