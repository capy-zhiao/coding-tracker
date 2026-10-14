// Home screen: what to work on today. This replaces the hand-maintained markdown plan.
// J / K walk the queue, Enter opens the highlighted item — no mouse needed.
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import LoadChart, { type ForecastRow } from '../components/LoadChart'
import ProblemRow, { rowHref } from '../components/ProblemRow'
import { api } from '../lib/api'
import { useHotkeys } from '../lib/useHotkeys'
import type { DailyQueue, QueueItem } from '../lib/types'

// "Next batch" picks reviews at random. The seed and the batch it replaced are kept for
// the rest of the day, so opening a problem and coming back shows the same batch.
const BATCH_KEY = 'today-review-batch'
type Batch = { date: string; seed: number; skip: number[] }

function loadBatch(): Batch | null {
  try { return JSON.parse(localStorage.getItem(BATCH_KEY) ?? 'null') } catch { return null }
}

function saveBatch(b: Batch) {
  try { localStorage.setItem(BATCH_KEY, JSON.stringify(b)) } catch { /* not kept, still works */ }
}

export default function Today() {
  // data / loading / error — the standard trio for any page that fetches
  const [queue, setQueue] = useState<DailyQueue | null>(null)
  const [forecast, setForecast] = useState<ForecastRow[]>([])
  const [error, setError] = useState('')
  const [cursor, setCursor] = useState(-1)      // -1 = nothing highlighted yet
  const [shuffled, setShuffled] = useState(false)
  const [swapping, setSwapping] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    const saved = loadBatch()
    api.today(saved ? { shuffle: saved.seed, skip: saved.skip } : {})
      .then(async (q) => {
        // A batch from an earlier day doesn't carry over: a new day starts by priority
        if (saved && saved.date !== q.date) q = await api.today()
        else if (saved) setShuffled(true)
        setQueue(q)
      })
      .catch((e) => setError(e.message))
    api.forecast(14).then(setForecast).catch(() => {})
  }, [])

  // A random batch from everything due today, avoiding the one on screen
  const nextBatch = async () => {
    if (!queue || swapping || queue.deferred === 0) return
    setSwapping(true)
    try {
      const batch = {
        date: queue.date,
        seed: Math.floor(Math.random() * 2 ** 31),
        skip: queue.reviews.map((i) => i.problem.id),
      }
      const q = await api.today({ shuffle: batch.seed, skip: batch.skip })
      saveBatch({ ...batch, date: q.date })
      setShuffled(true)
      setQueue(q)
      setCursor(-1)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSwapping(false)
    }
  }

  // One flat list across all three sections, so J/K walk the whole day in order.
  // useMemo keeps the array identity stable between renders.
  const flat = useMemo<QueueItem[]>(
    () => (queue ? [...queue.reviews, ...queue.new_problems, ...queue.templates] : []),
    [queue],
  )

  const move = (delta: number) => {
    if (!flat.length) return
    setCursor((c) => {
      const next = Math.min(flat.length - 1, Math.max(0, c + delta))
      document.getElementById(`row-${flat[next].problem.number}`)
        ?.scrollIntoView({ block: 'nearest' })
      return next
    })
  }

  useHotkeys({
    j: () => move(1),
    k: () => move(-1),
    arrowdown: () => move(1),
    arrowup: () => move(-1),
    r: () => { void nextBatch() },
    enter: () => {
      const item = flat[cursor]
      if (item) navigate(rowHref(item.problem.number, item.problem.kind))
    },
  })

  if (error) return (
    <p className="card text-red-600">
      {error}<br />
      <span className="text-slate-500 text-sm">
        Is the backend running? <code>uvicorn app.main:app --reload</code>
      </span>
    </p>
  )
  if (!queue) return <p className="text-slate-400">Loading…</p>

  const selected = flat[cursor]?.problem.number

  return (
    <div className="space-y-5">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">{queue.date}</h1>
        <p className="text-sm text-slate-500">
          <b>{queue.total_due}</b> due today
          {queue.deferred > 0 && <> · ranked by priority, <b>{queue.deferred}</b> deferred</>}
          <span className="ml-2 text-xs text-slate-400">
            <kbd className="border border-slate-200 rounded px-1">J</kbd>
            <kbd className="border border-slate-200 rounded px-1 ml-0.5">K</kbd> to navigate
          </span>
        </p>
      </div>

      <Section title="🔁 Review"
               hint={`${shuffled ? 'random pick' : 'ranked by priority'} · at most 2 per chapter or pattern, so the day stays mixed`}
               items={queue.reviews} selected={selected}
               action={queue.deferred > 0 && (
                 <button className="btn text-xs py-1" onClick={nextBatch} disabled={swapping}
                         title="Swap in a random batch of today's reviews (R)">
                   ↻ Next batch
                 </button>
               )} />
      <Section title="🆕 New" hint="NeetCode 150, then Top Interview 150, then LeetCode 75 · Bit & Math and Hards wait"
               items={queue.new_problems} selected={selected} />
      <Section title="🔧 Template drill" hint="five minutes of blind writing before you start"
               items={queue.templates} selected={selected} />

      <LoadChart rows={forecast} reviewCap={queue.review_cap} />
    </div>
  )
}

function Section({
  title, hint, items, selected, action,
}: { title: string; hint: string; items: QueueItem[]; selected?: number; action?: ReactNode }) {
  return (
    <section className="card">
      <div className="flex items-baseline gap-2 mb-2">
        <h2 className="font-medium">{title}</h2>
        <span className="text-xs text-slate-400">{hint}</span>
        <div className="ml-auto flex items-center gap-3">
          {action}
          <span className="text-sm text-slate-400">{items.length}</span>
        </div>
      </div>
      {items.length === 0
        ? <p className="text-sm text-slate-400 px-3 py-2">Nothing here today 🎉</p>
        : (
          <div className="-mx-1">
            {items.map((i) => (
              <div key={i.problem.id} id={`row-${i.problem.number}`}>
                <ProblemRow item={i} selected={i.problem.number === selected} />
              </div>
            ))}
          </div>
        )}
    </section>
  )
}
