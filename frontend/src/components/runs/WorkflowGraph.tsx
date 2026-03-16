import { clsx } from 'clsx'
import {
  CheckCircle2, XCircle, Loader2, Circle, MinusCircle, ChevronRight,
} from 'lucide-react'
import { STAGE_DISPLAY } from '@/types/api'
import type { Stage, StageState } from '@/types/api'
import { Progress } from '@/components/ui/progress'
import { useWsStore } from '@/stores/wsStore'

interface WorkflowGraphProps {
  runId: number
  stages: Stage[]
  activeStage: string | null
  onSelectStage: (code: string) => void
}

export function WorkflowGraph({ runId, stages, activeStage, onSelectStage }: WorkflowGraphProps) {
  const progress = useWsStore((s) => s.runProgress[runId])

  return (
    <div className="flex items-start gap-0 overflow-x-auto pb-2">
      {stages.map((stage, i) => {
        const isActive = activeStage === stage.phase_code
        const liveProgress =
          progress && progress.stage === stage.phase_code ? progress : null

        return (
          <div key={stage.phase_code} className="flex items-center">
            <StageNode
              stage={stage}
              liveProgress={liveProgress}
              isSelected={isActive}
              onClick={() => onSelectStage(stage.phase_code)}
            />
            {i < stages.length - 1 && (
              <ChevronRight size={16} className="text-[#30363d] shrink-0 mx-0.5" />
            )}
          </div>
        )
      })}
    </div>
  )
}

interface StageNodeProps {
  stage: Stage
  liveProgress: { items_done: number; items_total: number; throughput: number; eta_seconds: number } | null
  isSelected: boolean
  onClick: () => void
}

function StageNode({ stage, liveProgress, isSelected, onClick }: StageNodeProps) {
  const display = STAGE_DISPLAY[stage.phase_code as keyof typeof STAGE_DISPLAY]
  const pct = liveProgress
    ? (liveProgress.items_total > 0 ? Math.round((liveProgress.items_done / liveProgress.items_total) * 100) : 0)
    : stage.items_done != null && stage.items_total != null && stage.items_total > 0
      ? Math.round((stage.items_done / stage.items_total) * 100)
      : null

  return (
    <button
      onClick={onClick}
      className={clsx(
        'flex flex-col items-center gap-1.5 rounded-md p-3 min-w-[110px] max-w-[140px] text-left transition-all border',
        'hover:border-[#388bfd]',
        isSelected
          ? 'border-[#388bfd] bg-[#051d3a]'
          : 'border-[#30363d] bg-[#161b22]',
      )}
    >
      <div className="flex items-center gap-1.5 w-full">
        <StateIcon state={stage.state} />
        <span className="text-xs font-medium text-[#e6edf3] truncate">
          {display?.name ?? stage.phase_code}
        </span>
      </div>

      <div className="w-full">
        <div className="flex items-center justify-between mb-1">
          <StageBadgeText state={stage.state} />
          {pct != null && stage.state === 'running' && (
            <span className="text-[10px] text-[#8b949e]">{pct}%</span>
          )}
        </div>

        {stage.state === 'running' && pct != null && (
          <Progress value={pct} size="sm" color="blue" />
        )}

        {stage.state === 'completed' && <DurationText stage={stage} />}
        {stage.state === 'failed' && (
          <span className="text-[10px] text-[#f85149] truncate block">Failed</span>
        )}
      </div>

      {liveProgress && liveProgress.throughput > 0 && (
        <div className="text-[10px] text-[#6e7681]">
          {liveProgress.throughput.toFixed(1)} img/s · ETA {formatEta(liveProgress.eta_seconds)}
        </div>
      )}
    </button>
  )
}

function StateIcon({ state }: { state: StageState }) {
  switch (state) {
    case 'completed':
      return <CheckCircle2 size={14} className="text-[#3fb950] shrink-0" />
    case 'running':
      return <Loader2 size={14} className="text-[#388bfd] shrink-0 animate-spin" />
    case 'failed':
      return <XCircle size={14} className="text-[#f85149] shrink-0" />
    case 'skipped':
      return <MinusCircle size={14} className="text-[#6e7681] shrink-0" />
    default:
      return <Circle size={14} className="text-[#30363d] shrink-0" />
  }
}

function StageBadgeText({ state }: { state: StageState }) {
  const colors: Record<StageState, string> = {
    pending: 'text-[#6e7681]',
    running: 'text-[#388bfd]',
    completed: 'text-[#3fb950]',
    failed: 'text-[#f85149]',
    skipped: 'text-[#6e7681]',
  }
  const labels: Record<StageState, string> = {
    pending: 'Pending',
    running: 'Running',
    completed: 'Done',
    failed: 'Failed',
    skipped: 'Skipped',
  }
  return <span className={clsx('text-[10px]', colors[state])}>{labels[state]}</span>
}

function DurationText({ stage }: { stage: Stage }) {
  if (!stage.started_at || !stage.completed_at) return null
  const ms = new Date(stage.completed_at).getTime() - new Date(stage.started_at).getTime()
  return <span className="text-[10px] text-[#6e7681]">{formatMs(ms)}</span>
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`
}

function formatEta(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}s`
  return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`
}
