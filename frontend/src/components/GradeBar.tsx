// The four grade buttons. The selected one is highlighted.
import { CircleAlert, CircleCheck, CircleX, Zap, type LucideIcon } from 'lucide-react'
import type { Grade } from '../lib/types'

const GRADES: { id: Grade; label: string; icon: LucideIcon; sub: string; color: string; ink: string }[] = [
  { id: 'again', label: 'Again', icon: CircleX,     sub: 'saw the solution', color: 'bg-red-100 border-red-300 text-red-700',             ink: 'text-red-500' },
  { id: 'hard',  label: 'Hard',  icon: CircleAlert, sub: 'struggled / bugs', color: 'bg-amber-100 border-amber-300 text-amber-700',       ink: 'text-amber-500' },
  { id: 'good',  label: 'Good',  icon: CircleCheck, sub: 'solved smoothly',  color: 'bg-emerald-100 border-emerald-300 text-emerald-700', ink: 'text-emerald-500' },
  { id: 'easy',  label: 'Easy',  icon: Zap,         sub: 'first try, fast',  color: 'bg-sky-100 border-sky-300 text-sky-700',             ink: 'text-sky-500' },
]

export default function GradeBar({
  value, onChange,
}: { value: Grade | null; onChange: (g: Grade) => void }) {
  return (
    <div className="grid grid-cols-4 gap-2">
      {GRADES.map((g) => (
        <button
          key={g.id}
          onClick={() => onChange(g.id)}
          className={`rounded-lg border-2 px-2 py-2 text-left transition active:scale-[0.97] ${
            value === g.id ? g.color + ' -translate-y-0.5 shadow-md'
                           : 'bg-white border-slate-200 hover:border-slate-400 hover:-translate-y-0.5'
          }`}
        >
          <div className="text-sm font-medium flex items-center gap-1.5">
            <g.icon size={15} className={value === g.id ? '' : g.ink} />{g.label}
          </div>
          <div className="text-[11px] text-slate-500">{g.sub}</div>
        </button>
      ))}
    </div>
  )
}
