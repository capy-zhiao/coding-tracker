// Template drill index: the 15 algorithm skeletons, with their SRS state.
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Wrench } from 'lucide-react'
import SectionTitle from '../components/SectionTitle'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import type { TemplateSummary } from '../lib/types'

export default function Drills() {
  const [rows, setRows] = useState<TemplateSummary[]>([])
  const [error, setError] = useState('')
  const { me } = useAuth()

  useEffect(() => { api.templates().then(setRows).catch((e) => setError(e.message)) }, [])

  if (error) return <p className="card text-red-600">{error}</p>

  // Your study day from the server, in your time zone. The browser's toISOString() is the
  // UTC date, which is already tomorrow on an evening west of Greenwich.
  const today = me?.today ?? new Date().toLocaleDateString('en-CA')
  const due = rows.filter((r) => r.state?.due && r.state.due <= today)

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Template drills</h1>
        <p className="text-sm text-slate-500 mt-1">
          Write the skeleton from memory, then have it checked against the reference.
          Grading is by checkpoint, not by text match — renaming every variable is fine,
          dropping the <code className="text-xs">while</code> in Union-Find is not.
        </p>
      </div>

      <div className="card">
        <div className="flex items-baseline gap-2 mb-2">
          <SectionTitle icon={Wrench} tone="amber">Due today</SectionTitle>
          <span className="ml-auto text-sm font-mono text-slate-400">{due.length} / {rows.length}</span>
        </div>
        {rows.length === 0
          ? <p className="text-sm text-slate-400 px-1 py-2">Loading…</p>
          : <div className="-mx-1 stagger">{rows.map((t) => <Row key={t.number} t={t} today={today} />)}</div>}
      </div>
    </div>
  )
}

function Row({ t, today }: { t: TemplateSummary; today: string }) {
  const isDue = Boolean(t.state?.due && t.state.due <= today)
  const interval = t.state?.interval_days ?? 0
  // 21 days is the same "mastered" threshold the stats page uses
  const mastered = interval >= 21

  return (
    <Link
      to={`/drill/${t.number}`}
      className="row flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-slate-100/60 transition"
    >
      <span className={`w-1.5 h-1.5 rounded-full ${
        mastered ? 'bg-emerald-500 shadow-[0_0_8px] shadow-emerald-400'
          : isDue ? 'bg-amber-500 shadow-[0_0_8px] shadow-amber-400 animate-pulse' : 'bg-slate-300'
      }`} />
      <span className="flex-1 font-medium">{t.title}</span>
      <span className="text-xs text-slate-400">{t.check_count} checkpoints</span>
      <span className="text-xs text-slate-400 w-28 truncate text-right">{t.chapter}</span>
      <span className="text-xs font-mono w-20 text-right">
        {isDue ? <span className="text-amber-600">due</span>
               : <span className="text-slate-400">{interval}d</span>}
      </span>
    </Link>
  )
}
