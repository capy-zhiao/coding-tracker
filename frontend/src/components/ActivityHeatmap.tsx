// Practice activity: attempts per day as a contribution grid, one column per week.
//
// The grid shows as many whole weeks as fit the card (up to a year), so it reads as a
// year on a desktop and a few months on a phone without scrolling. Days are the user's
// study days, the same ones the streak counts, so an evening session lands on that evening.
import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'

const CELL = 11
const GAP = 3
const STEP = CELL + GAP
const LABEL_W = 28          // weekday labels
const MAX_WEEKS = 53
const MIN_WEEKS = 13
// Enough history for the widest grid: 53 weeks back to a Sunday, plus today
const FETCH_DAYS = MAX_WEEKS * 7

/** Parse YYYY-MM-DD as a local date, not UTC midnight (which is the previous day here). */
function parse(iso: string) {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

function iso(d: Date) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function addDays(d: Date, n: number) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n)
}

// A day's work is a handful of attempts (the default caps are 4 reviews and 3 new), so the
// steps are absolute rather than relative to the busiest day: one busy day shouldn't make
// every ordinary day look idle.
function tone(n: number) {
  if (n === 0) return 'bg-slate-200'            // 100 vanishes on a white card
  if (n === 1) return 'bg-emerald-200'
  if (n === 2) return 'bg-emerald-300'
  if (n <= 4) return 'bg-emerald-500'
  return 'bg-emerald-700'
}

const LEGEND = [0, 1, 2, 3, 5]

export default function ActivityHeatmap() {
  const { me } = useAuth()
  const [counts, setCounts] = useState<Map<string, number> | null>(null)
  const [weeks, setWeeks] = useState(26)
  const [hover, setHover] = useState<string | null>(null)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.heatmap(FETCH_DAYS)
      .then((rows) => setCounts(new Map(rows.map((r) => [r.date, r.count]))))
      .catch(() => setCounts(new Map()))
  }, [])

  useEffect(() => {
    const el = box.current
    if (!el) return
    const fit = () => setWeeks(Math.max(MIN_WEEKS,
      Math.min(MAX_WEEKS, Math.floor((el.clientWidth - LABEL_W + GAP) / STEP))))
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    return () => ro.disconnect()
  }, [counts])

  if (!counts) return null

  const today = me?.today ? parse(me.today) : new Date()
  // The last column is this week; columns start on Sunday
  const start = addDays(today, -today.getDay() - (weeks - 1) * 7)
  const columns = Array.from({ length: weeks }, (_, w) =>
    Array.from({ length: 7 }, (_, d) => addDays(start, w * 7 + d)))

  let total = 0
  let active = 0
  for (const col of columns) {
    for (const day of col) {
      const n = counts.get(iso(day)) ?? 0
      if (day <= today && n > 0) { total += n; active += 1 }
    }
  }

  // A month's name goes over the first week that starts in it. The first column only gets
  // one if the next label is far enough away not to collide with it.
  const months = columns.map((col, w) => {
    const m = col[0].getMonth()
    if (w > 0 && m === columns[w - 1][0].getMonth()) return ''
    if (w === 0) {
      const next = columns.findIndex((c, i) => i > 0 && c[0].getMonth() !== m)
      if (next !== -1 && next < 3) return ''
    }
    return col[0].toLocaleDateString(undefined, { month: 'short' })
  })

  const hovered = hover ? parse(hover) : null
  const hoveredN = hover ? counts.get(hover) ?? 0 : 0
  const span = weeks >= 52 ? 'year' : `${weeks} weeks`

  return (
    <section className="card">
      <div className="flex items-baseline gap-2 flex-wrap">
        <h2 className="font-medium">🔥 Activity</h2>
        <span className="text-xs text-slate-400">
          {total} attempt{total === 1 ? '' : 's'} on {active} day{active === 1 ? '' : 's'} in the last {span}
        </span>
      </div>

      <div ref={box} className="mt-3">
        <div className="flex" style={{ marginLeft: LABEL_W, gap: GAP, height: 14 }} aria-hidden>
          {months.map((m, w) => (
            <span key={w} className="text-[10px] text-slate-400 whitespace-nowrap"
                  style={{ width: CELL, flex: 'none' }}>{m}</span>
          ))}
        </div>

        <div className="flex">
          <div className="grid text-[10px] text-slate-400" aria-hidden
               style={{ width: LABEL_W, gridTemplateRows: `repeat(7, ${CELL}px)`, rowGap: GAP }}>
            {['', 'Mon', '', 'Wed', '', 'Fri', ''].map((d, i) => (
              <span key={i} className="leading-[11px]">{d}</span>
            ))}
          </div>

          <div
            role="img"
            aria-label={`${total} attempts on ${active} days in the last ${span}`}
            className="grid"
            style={{
              gridTemplateRows: `repeat(7, ${CELL}px)`,
              gridAutoColumns: `${CELL}px`,
              gridAutoFlow: 'column',
              gap: GAP,
            }}
            onMouseLeave={() => setHover(null)}
          >
            {columns.flat().map((day) => {
              const key = iso(day)
              if (day > today) return <span key={key} />
              const n = counts.get(key) ?? 0
              const isToday = key === iso(today)
              return (
                <span
                  key={key}
                  className={`rounded-sm ${tone(n)} ${isToday ? 'ring-1 ring-slate-500' : ''} ${
                    hover === key ? 'outline outline-1 outline-slate-600' : ''}`}
                  onMouseEnter={() => setHover(key)}
                  onClick={() => setHover(key)}
                />
              )
            })}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 mt-2 text-xs text-slate-400">
        <span className="min-h-[1rem]">
          {hovered && (
            <>
              {hovered.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}
              {' · '}<b className="text-slate-600">{hoveredN}</b> attempt{hoveredN === 1 ? '' : 's'}
            </>
          )}
        </span>
        <span className="ml-auto">Less</span>
        {LEGEND.map((n) => (
          <span key={n} className={`inline-block rounded-sm ${tone(n)}`} style={{ width: CELL, height: CELL }} />
        ))}
        <span>More</span>
      </div>
    </section>
  )
}
