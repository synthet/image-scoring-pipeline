import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { runsApi } from '@/api/runs'
import { RunCard } from '@/components/runs/RunCard'
import { Button } from '@/components/ui/button'
import { useWsStore } from '@/stores/wsStore'
import { useUiStore } from '@/stores/uiStore'
import { Plus, Inbox } from 'lucide-react'
import type { Run } from '@/types/api'

type TabFilter = 'active' | 'queue' | 'history'

export function RunsPage() {
  const { openNewRun } = useUiStore()
  const runsVersion = useWsStore((s) => s.runsVersion)
  const [tab, setTab] = useState<TabFilter>('active')

  const { data: runs = [], isLoading } = useQuery({
    queryKey: ['runs', runsVersion],
    queryFn: () => runsApi.list({ limit: 100 }),
    refetchInterval: 5000,
  })

  const active = runs.filter((r) => r.status === 'running' || r.status === 'paused')
  const queued = runs.filter((r) => r.status === 'queued' || r.status === 'pending')
  const history = runs.filter(
    (r) =>
      r.status === 'completed' ||
      r.status === 'failed' ||
      r.status === 'canceled' ||
      r.status === 'interrupted',
  )

  const displayed: Run[] =
    tab === 'active' ? [...active, ...queued] : tab === 'queue' ? queued : history

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-lg font-semibold text-[#e6edf3]">Runs</h1>
        <Button variant="primary" size="sm" onClick={() => openNewRun()}>
          <Plus size={13} />
          New Run
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 mb-5 border-b border-[#21262d]">
        <TabButton label="Active" count={active.length} active={tab === 'active'} onClick={() => setTab('active')} />
        <TabButton label="Queued" count={queued.length} active={tab === 'queue'} onClick={() => setTab('queue')} />
        <TabButton label="History" count={history.length} active={tab === 'history'} onClick={() => setTab('history')} />
      </div>

      {isLoading && (
        <div className="text-sm text-[#6e7681]">Loading…</div>
      )}

      {!isLoading && displayed.length === 0 && (
        <EmptyState tab={tab} onNewRun={() => openNewRun()} />
      )}

      <div className="space-y-3">
        {displayed.map((run) => (
          <RunCard key={run.id} run={run} />
        ))}
      </div>
    </div>
  )
}

function TabButton({
  label, count, active, onClick,
}: {
  label: string
  count: number
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={`
        flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px
        ${active
          ? 'border-[#388bfd] text-[#e6edf3]'
          : 'border-transparent text-[#8b949e] hover:text-[#e6edf3]'
        }
      `}
    >
      {label}
      {count > 0 && (
        <span className="bg-[#30363d] text-[#8b949e] text-xs rounded-full px-1.5 py-0.5 min-w-[20px] text-center">
          {count}
        </span>
      )}
    </button>
  )
}

function EmptyState({ tab, onNewRun }: { tab: TabFilter; onNewRun: () => void }) {
  const messages: Record<TabFilter, string> = {
    active: 'No active runs. Start a new run to begin processing.',
    queue: 'Queue is empty.',
    history: 'No completed runs yet.',
  }
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-center">
      <Inbox size={32} className="text-[#30363d]" />
      <p className="text-sm text-[#6e7681]">{messages[tab]}</p>
      {tab === 'active' && (
        <Button variant="primary" size="sm" onClick={onNewRun}>
          <Plus size={13} />
          New Run
        </Button>
      )}
    </div>
  )
}
