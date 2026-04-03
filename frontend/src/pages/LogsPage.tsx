import { useQuery } from '@tanstack/react-query'
import { RefreshCcw, ScrollText } from 'lucide-react'
import { Button } from '@/components/ui/button'

const REFETCH_INTERVAL = 2000

export interface StatusLogsPayload {
  ts: string
  log: string
}

export function LogsPage() {
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['status-logs'],
    queryFn: async (): Promise<StatusLogsPayload> => {
      const resp = await fetch('/api/status/logs')
      if (!resp.ok) throw new Error('Failed to fetch logs')
      return resp.json()
    },
    refetchInterval: REFETCH_INTERVAL,
  })

  if (isLoading) {
    return (
      <div className="p-8 flex items-center justify-center h-full text-[#9d9d9d] animate-pulse">
        Loading log sources…
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="p-8 text-[#f44747]">
        <h1 className="text-xl font-semibold mb-4 text-[#cccccc]">Logs unavailable</h1>
        <p>Could not load logs. Ensure the backend is running and /api/status/logs is available.</p>
        <Button variant="secondary" onClick={() => refetch()} className="mt-4">
          Retry
        </Button>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <header className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-[#cccccc] flex items-center gap-2">
            <ScrollText className="text-[#4fc1ff]" size={24} />
            Logs
          </h1>
          <p className="text-sm text-[#9d9d9d] mt-1">
            Application and debug log tails (same sources as the /app operator page). Updates every few seconds.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-[#6d6d6d]">Updated {data.ts}</span>
          <Button variant="secondary" size="sm" onClick={() => refetch()} disabled={isFetching} className="gap-2">
            <RefreshCcw size={14} className={isFetching ? 'animate-spin' : ''} />
            {isFetching ? 'Refreshing…' : 'Refresh'}
          </Button>
        </div>
      </header>

      <div
        className="rounded-lg border border-[#333333] bg-[#1a1a1a] p-4 max-h-[calc(100vh-8rem)] overflow-y-auto text-[#e0e0e0]"
        // Trusted first-party HTML from backend (matches /app status log section)
        dangerouslySetInnerHTML={{ __html: data.log }}
      />
    </div>
  )
}
