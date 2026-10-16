// A card's heading: a small tinted tile with a line icon, then the title. One icon set,
// one size, so headings across pages read as a family.
import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

const TONES = {
  sky: 'bg-sky-100 text-sky-600',
  indigo: 'bg-indigo-100 text-indigo-600',
  emerald: 'bg-emerald-100 text-emerald-600',
  amber: 'bg-amber-100 text-amber-600',
  orange: 'bg-orange-100 text-orange-600',
  rose: 'bg-rose-100 text-rose-600',
  cyan: 'bg-cyan-100 text-cyan-600',
}

export type Tone = keyof typeof TONES

export default function SectionTitle({
  icon: Icon, tone = 'sky', children, as: Tag = 'h2', className = '',
}: { icon: LucideIcon; tone?: Tone; children: ReactNode; as?: 'h1' | 'h2'; className?: string }) {
  return (
    <Tag className={`flex items-center gap-2 font-medium ${className}`}>
      <span className={`grid place-items-center w-6 h-6 shrink-0 rounded-md ${TONES[tone]}`}>
        <Icon size={14} strokeWidth={2.25} />
      </span>
      {children}
    </Tag>
  )
}
