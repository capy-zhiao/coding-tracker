// Upcoming review load.
//
// Today's number is split out as a sentence rather than drawn as a bar. It is a backlog —
// everything overdue piled up — while every other day is "newly due that day". Drawn on
// one scale, a backlog of 78 flattened a week of 1-7s into slivers a few pixels tall, so
// the chart could not show the one thing it is for: spotting a pile-up ahead.
import { useState } from 'react'
import { TrendingUp } from 'lucide-react'
import SectionTitle from './SectionTitle'

export interface ForecastRow { date: string; count: number; overdue: number }

const PLOT_PX = 72          // tallest bar
const HEADROOM_PX = 28      // above the tallest bar: room for its value label or the tooltip

/** Parse YYYY-MM-DD as a local date. new Date('2026-09-25') is UTC midnight, which is
 *  still the 24th anywhere west of Greenwich. */
function localDate(iso: string) {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

function axisLabel(iso: string, i: number) {
  if (i === 0) return 'Today'
  const d = localDate(iso)
  return d.getDate() === 1
    ? d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
    : String(d.getDate())
}

function longLabel(iso: string) {
  return localDate(iso).toLocaleDateString(undefined, {
    weekday: 'short', month: 'short', day: 'numeric',
  })
}

export default function LoadChart({ rows, reviewCap }: { rows: ForecastRow[]; reviewCap: number }) {
  const [hover, setHover] = useState<number | null>(null)
  if (!rows.length) return null

  const backlog = rows[0].overdue
  const days = rows.map((r) => ({ date: r.date, n: r.count - r.overdue }))
  const max = Math.max(0, ...days.map((d) => d.n))
  const peak = max > 0 ? days.findIndex((d) => d.n === max) : -1
  // "At least": new reviews keep arriving while the backlog is being worked off.
  const daysToClear = reviewCap > 0 ? Math.ceil(backlog / reviewCap) : null

  return (
    <div className="card">
      <div className="flex items-baseline gap-2">
        <SectionTitle icon={TrendingUp} tone="cyan">Review load, next 14 days</SectionTitle>
        <span className="text-xs text-slate-400">newly due each day</span>
      </div>

      {backlog > 0 && (
        <p className="text-sm text-slate-600 mt-1">
          <b>{backlog}</b> overdue on top of this
          {daysToClear !== null && (
            <> — at {reviewCap} a day, at least <b>{daysToClear} day{daysToClear === 1 ? '' : 's'}</b> to clear</>
          )}
        </p>
      )}

      {max === 0 ? (
        <p className="text-sm text-slate-400 mt-3">Nothing new comes due in the next 14 days.</p>
      ) : (
        <div role="list" aria-label="Reviews newly due per day" className="flex gap-1 mt-3">
          {days.map((d, i) => {
            const h = d.n > 0 ? Math.max(3, Math.round((d.n / max) * PLOT_PX)) : 0
            const active = hover === i
            return (
              <div
                key={d.date}
                role="listitem"
                aria-label={`${longLabel(d.date)}: ${d.n} newly due${
                  i === 0 && backlog > 0 ? `, plus ${backlog} overdue` : ''}`}
                // The whole column is the hover target, not just the (possibly 3px) bar
                className="relative flex-1 min-w-0 flex flex-col items-center cursor-default"
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
              >
                {/* Plot band: fixed pixel height, so bar heights never depend on a
                    percentage of an auto-sized parent (which resolves to zero). */}
                <div
                  className="relative w-full flex flex-col items-center justify-end border-b border-slate-200"
                  style={{ height: PLOT_PX + HEADROOM_PX }}
                >
                  {active && (
                    // Anchored to the top of this bar and kept inside the plot band, so it
                    // never covers the text above the chart. Edge columns align inwards so
                    // the tooltip does not spill past the card.
                    <div
                      className={`absolute z-10 whitespace-nowrap rounded-md bg-slate-900 px-2 py-1
                                  text-xs text-white shadow ${
                        i < 2 ? 'left-0' : i > days.length - 3 ? 'right-0' : 'left-1/2 -translate-x-1/2'
                      }`}
                      style={{ bottom: h + 4 }}
                    >
                      {longLabel(d.date)} · <b>{d.n}</b> newly due
                      {i === 0 && backlog > 0 && <> + <b>{backlog}</b> overdue</>}
                    </div>
                  )}
                  {i === peak && (
                    <span className="text-[11px] font-medium text-slate-600 mb-0.5">{d.n}</span>
                  )}
                  {h > 0 && (
                    <div
                      className={`load-bar w-full max-w-[24px] rounded-t ${active ? 'is-active' : ''}`}
                      style={{ height: h, animationDelay: `${i * 40}ms` }}
                    />
                  )}
                </div>
                <span className={`mt-1 text-[10px] ${i === 0 ? 'text-slate-600 font-medium' : 'text-slate-400'}`}>
                  {axisLabel(d.date, i)}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
