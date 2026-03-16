import { clsx } from 'clsx'

interface ProgressProps {
  value: number   // 0–100
  color?: 'blue' | 'green' | 'yellow' | 'red'
  size?: 'sm' | 'md'
  className?: string
  showLabel?: boolean
}

export function Progress({ value, color = 'blue', size = 'md', className, showLabel = false }: ProgressProps) {
  const pct = Math.min(100, Math.max(0, value))
  return (
    <div className={clsx('flex items-center gap-2', className)}>
      <div
        className={clsx(
          'flex-1 rounded-full overflow-hidden bg-[#21262d]',
          size === 'sm' ? 'h-1' : 'h-2',
        )}
      >
        <div
          style={{ width: `${pct}%` }}
          className={clsx(
            'h-full rounded-full transition-[width] duration-300',
            color === 'blue' && 'bg-[#388bfd]',
            color === 'green' && 'bg-[#3fb950]',
            color === 'yellow' && 'bg-[#d29922]',
            color === 'red' && 'bg-[#f85149]',
          )}
        />
      </div>
      {showLabel && (
        <span className="text-xs text-[#8b949e] w-10 text-right">{Math.round(pct)}%</span>
      )}
    </div>
  )
}
