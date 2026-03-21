import type { WsLogLine } from '@/types/api'

/** Parse newline-separated job log from the API into UI log lines (no per-line timestamps in DB). */
export function parsePersistedRunLog(raw: string, runId: number, startedAt: string | null): WsLogLine[] {
  const base = startedAt ? new Date(startedAt).getTime() : Date.now()
  return raw
    .split('\n')
    .map((l) => l.trimEnd())
    .filter((line) => line.length > 0)
    .map((message, i) => ({
      type: 'log_line' as const,
      run_id: runId,
      level: 'INFO' as const,
      message,
      ts: new Date(base + i).toISOString(),
    }))
}
