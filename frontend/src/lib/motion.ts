// Small motion helpers. Everything here is decoration: with reduced motion it jumps
// straight to the end state.
import { useEffect, useRef, useState } from 'react'

const reduced = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** Counts from the value on screen up (or down) to `target`, easing out. */
export function useCountUp(target: number, durationMs = 900) {
  const [value, setValue] = useState(reduced() ? target : 0)
  const shown = useRef(value)
  shown.current = value

  useEffect(() => {
    if (reduced()) { setValue(target); return }
    const from = shown.current
    const start = performance.now()
    let frame = 0
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs)
      setValue(from + (target - from) * (1 - (1 - t) ** 3))
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [target, durationMs])

  return value
}
