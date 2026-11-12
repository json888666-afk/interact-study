import { useEffect, useState } from 'react'

const DURATION_MS = 2000
const MAX_WAIT_PERCENT = 99

export function LoadingProgress({ label, rendering = false, duration = DURATION_MS }: {
  label: string; rendering?: boolean; duration?: number
}) {
  const [percent, setPercent] = useState(0)

  useEffect(() => {
    if (rendering || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const start = performance.now()
    let frame = 0

    function tick(now: number) {
      const elapsed = Math.min(1, Math.max(0, (now - start) / duration))
      setPercent(Math.floor(MAX_WAIT_PERCENT * (1 - (1 - elapsed) ** 2)))
      if (elapsed < 1) frame = window.requestAnimationFrame(tick)
    }

    frame = window.requestAnimationFrame(tick)
    return () => window.cancelAnimationFrame(frame)
  }, [rendering, duration])

  const displayed = rendering || window.matchMedia('(prefers-reduced-motion: reduce)').matches ? MAX_WAIT_PERCENT : percent
  return (
    <div className="loading-progress" role="status">
      <div className="loading-progress-caption">
        <span>{label}</span>
        <span className="loading-progress-percent" aria-hidden="true">{displayed}%</span>
      </div>
      <div className="loading-progress-track" aria-hidden="true">
        <div className="loading-progress-fill" style={{ width: displayed + '%' }} />
      </div>
    </div>
  )
}
