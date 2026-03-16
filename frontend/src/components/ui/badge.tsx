import { type ReactNode } from 'react'
import { clsx } from 'clsx'
import type { RunStatus, StageState } from '@/types/api'

interface BadgeProps {
  children: ReactNode
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'muted' | 'running'
  size?: 'sm' | 'md'
  dot?: boolean
  className?: string
}

export function Badge({ children, variant = 'default', size = 'md', dot = false, className }: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full font-medium',
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs',
        variant === 'default' && 'bg-[#21262d] text-[#8b949e] border border-[#30363d]',
        variant === 'success' && 'bg-[#0f2a1a] text-[#3fb950] border border-[#196127]',
        variant === 'warning' && 'bg-[#271d04] text-[#d29922] border border-[#5a3e0a]',
        variant === 'danger' && 'bg-[#2a0d0d] text-[#f85149] border border-[#6e0e0a]',
        variant === 'info' && 'bg-[#051d3a] text-[#79c0ff] border border-[#0d419d]',
        variant === 'running' && 'bg-[#051d3a] text-[#388bfd] border border-[#1f6feb]',
        variant === 'muted' && 'bg-[#161b22] text-[#6e7681] border border-[#21262d]',
        className,
      )}
    >
      {dot && (
        <span
          className={clsx(
            'w-1.5 h-1.5 rounded-full',
            variant === 'running' && 'bg-[#388bfd] animate-pulse',
            variant === 'success' && 'bg-[#3fb950]',
            variant === 'warning' && 'bg-[#d29922]',
            variant === 'danger' && 'bg-[#f85149]',
            variant === 'muted' && 'bg-[#6e7681]',
            variant === 'info' && 'bg-[#79c0ff]',
          )}
        />
      )}
      {children}
    </span>
  )
}

export function statusVariant(status: RunStatus | StageState | string): BadgeProps['variant'] {
  switch (status) {
    case 'completed':
    case 'done':
      return 'success'
    case 'running':
      return 'running'
    case 'failed':
      return 'danger'
    case 'paused':
    case 'interrupted':
      return 'warning'
    case 'skipped':
      return 'muted'
    case 'pending':
    case 'queued':
      return 'info'
    case 'canceled':
      return 'muted'
    default:
      return 'default'
  }
}

export function statusLabel(status: RunStatus | StageState | string): string {
  const labels: Record<string, string> = {
    not_started: 'Not Started',
    pending: 'Pending',
    queued: 'Queued',
    running: 'Running',
    paused: 'Paused',
    completed: 'Completed',
    done: 'Done',
    failed: 'Failed',
    canceled: 'Canceled',
    interrupted: 'Interrupted',
    skipped: 'Skipped',
  }
  return labels[status] ?? status
}

export function RunBadge({ status }: { status: RunStatus }) {
  return (
    <Badge variant={statusVariant(status)} dot>
      {statusLabel(status)}
    </Badge>
  )
}

export function StageBadge({ state }: { state: StageState }) {
  return (
    <Badge variant={statusVariant(state)} dot size="sm">
      {statusLabel(state)}
    </Badge>
  )
}
