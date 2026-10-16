// One blind-write drill.
//
// This replaces the manual loop from the markdown notes: write the template into a blank
// area, scroll to the bottom of the file, compare by eye. Comparing by eye is where it
// broke down — "I basically had it" is not a verdict. Here the reference stays hidden
// until you submit, and the checkpoints are the ones that actually cause bugs.
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { CircleCheck, CircleX, TriangleAlert } from 'lucide-react'
import CodeEditor from '../components/CodeEditor'
import Timer, { useTimer } from '../components/Timer'
import { api } from '../lib/api'
import { useHotkeys } from '../lib/useHotkeys'
import type { BlindWriteResult, Grade, TemplateSummary } from '../lib/types'

export default function Drill() {
  const { number } = useParams()
  const num = Number(number)

  const [meta, setMeta] = useState<TemplateSummary | null>(null)
  const [code, setCode] = useState('')
  const [checked, setChecked] = useState<BlindWriteResult | null>(null)
  const [saved, setSaved] = useState<{ days: number } | null>(null)
  const [gaveUp, setGaveUp] = useState(false)
  const [busy, setBusy] = useState(false)
  const timer = useTimer()

  useEffect(() => {
    api.templates()
      .then((all) => setMeta(all.find((t) => t.number === num) ?? null))
      .catch(() => {})
    timer.start()
    // Intentionally runs once per template: the timer starts when the drill opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [num])

  const check = async () => {
    if (!code.trim() || busy) return
    setBusy(true)
    timer.pause()
    try {
      setChecked(await api.checkBlindWrite(num, code))
    } catch (e) { alert((e as Error).message) } finally { setBusy(false) }
  }

  const giveUp = async () => {
    setGaveUp(true)
    timer.pause()
    setChecked(await api.checkBlindWrite(num, code))
  }

  const record = async (grade: Grade) => {
    if (busy || saved) return
    setBusy(true)
    try {
      const r = await api.submitAttempt(num, {
        grade, seconds: timer.seconds, looked_at_solution: gaveUp,
        had_bugs: false, code, note: '', mode: 'drill',
        time_complexity: '', space_complexity: '',
        blindwrite_score: checked
          ? checked.checks.filter((c) => c.passed).length / checked.checks.length
          : null,
      })
      setSaved({ days: r.next_due_in_days })
    } finally { setBusy(false) }
  }

  useHotkeys({
    c: () => check(),
    'mod+enter': () => (checked ? record(checked.suggested_grade) : check()),
  })

  if (!meta) return <p className="text-slate-400">Loading…</p>

  return (
    <div className="space-y-4">
      <div className="card flex items-start gap-3">
        <div className="flex-1">
          <p className="text-xs text-slate-400">Template drill</p>
          <h1 className="text-lg font-semibold">{meta.title}</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {meta.chapter} · {meta.check_count} checkpoints ·{' '}
            {meta.state?.lapses ? <span className="text-orange-600">failed {meta.state.lapses}x</span>
                                : 'write it from memory'}
          </p>
        </div>
        <Timer running={timer.running} seconds={timer.seconds} onTick={timer.onTick} />
      </div>

      <div className="card">
        <div className="flex items-center mb-2">
          <h2 className="font-medium">Blind write</h2>
          <span className="text-xs text-slate-400 ml-2">no peeking — the reference is hidden</span>
          <div className="ml-auto flex gap-2">
            {!checked && (
              <button className="btn text-xs" onClick={giveUp}>Give up, show me</button>
            )}
            <button className="btn btn-primary text-xs" onClick={check} disabled={busy || !code.trim()}>
              Check <kbd className="ml-1 text-[10px] opacity-60">C</kbd>
            </button>
          </div>
        </div>
        <CodeEditor
          value={code} onChange={setCode} onSubmit={check} height={300}
          placeholder="Type the template from memory…"
        />
      </div>

      {checked && <Verdict r={checked} gaveUp={gaveUp} />}

      {checked && (
        saved ? (
          <div className="card bg-emerald-50 border-emerald-200 text-sm text-emerald-800 pop">
            <CircleCheck size={15} className="inline -mt-0.5 mr-1.5 text-emerald-500" />Recorded — this drill comes back in <b>{saved.days}</b> day
            {saved.days === 1 ? '' : 's'}.
            <Link to="/drill" className="underline ml-2">Back to drills</Link>
          </div>
        ) : (
          <div className="card space-y-2">
            <p className="text-sm font-medium">Record this attempt</p>
            <div className="grid grid-cols-4 gap-2">
              {(['again', 'hard', 'good', 'easy'] as Grade[]).map((g) => (
                <button
                  key={g}
                  onClick={() => record(g)}
                  disabled={busy}
                  className={`btn text-sm capitalize ${
                    g === checked.suggested_grade ? 'btn-primary' : ''
                  }`}
                >
                  {g}
                  {g === checked.suggested_grade && (
                    <span className="ml-1 text-[10px] opacity-70">suggested</span>
                  )}
                </button>
              ))}
            </div>
          </div>
        )
      )}
    </div>
  )
}

function Verdict({ r, gaveUp }: { r: BlindWriteResult; gaveUp: boolean }) {
  const hit = r.checks.filter((c) => c.passed).length
  return (
    <div className="space-y-4">
      <div className={`card ${r.passed ? 'bg-emerald-50 border-emerald-200'
                                       : 'bg-amber-50 border-amber-200'}`}>
        <div className="flex items-baseline gap-3">
          <span className="self-center pop">{r.passed ? <CircleCheck size={20} className="text-emerald-500" />
                                                  : <TriangleAlert size={20} className="text-amber-500" />}</span>
          <p className="font-medium flex-1">{gaveUp ? 'Reference revealed.' : r.verdict}</p>
          <span className="text-sm text-slate-500">
            {hit}/{r.checks.length} checkpoints · {Math.round(r.similarity * 100)}% shape match
          </span>
        </div>
      </div>

      <div className="card">
        <h2 className="font-medium mb-2">Checkpoints</h2>
        <div className="space-y-1.5 stagger">
          {r.checks.map((c) => (
            <div key={c.id} className="flex gap-2 text-sm">
              <span className="mt-0.5 shrink-0">{c.passed ? <CircleCheck size={15} className="text-emerald-500" />
                                                     : <CircleX size={15} className="text-red-500" />}</span>
              <div>
                <p className={c.passed ? 'text-slate-600' : 'font-medium text-slate-900'}>
                  {c.label}
                </p>
                {!c.passed && <p className="text-xs text-slate-500 mt-0.5">{c.why}</p>}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="card">
          <h2 className="font-medium mb-2">Reference</h2>
          <pre className="text-xs bg-slate-50 rounded-lg p-3 overflow-x-auto">{r.reference}</pre>
        </div>
        <div className="card">
          <h2 className="font-medium mb-2">
            Diff <span className="text-xs font-normal text-slate-400">
              (comments and blank lines ignored)
            </span>
          </h2>
          {r.diff.length === 0
            ? <p className="text-sm text-slate-400">Identical.</p>
            : (
              <pre className="text-xs bg-slate-50 rounded-lg p-3 overflow-x-auto leading-relaxed">
                {r.diff.map((line, i) => (
                  <div key={i} className={
                    line.startsWith('+') ? 'text-emerald-700'
                    : line.startsWith('-') ? 'text-red-700'
                    : line.startsWith('@') ? 'text-slate-400' : 'text-slate-600'
                  }>{line}</div>
                ))}
              </pre>
            )}
        </div>
      </div>
    </div>
  )
}
