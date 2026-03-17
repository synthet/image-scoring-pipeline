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
          'flex-1 rounded-full overflow-hidden bg-[#3c3c3c]',
          size === 'sm' ? 'h-1' : 'h-2',
        )}
      >
        <div
          style={{ width: `${pct}%` }}
          className={clsx(
            'h-full rounded-full transition-[width] duration-300',
            color === 'blue' && 'bg-[#4fc1ff]',
            color === 'green' && 'bg-[#89d185]',
            color === 'yellow' && 'bg-[#cca700]',
            color === 'red' && 'bg-[#f44747]',
          )}
        />
      </div>
      {showLabel && (
        <span className="text-xs text-[#9d9d9d] w-10 text-right">{Math.round(pct)}%</span>
      )}
    </div>
  )
}
