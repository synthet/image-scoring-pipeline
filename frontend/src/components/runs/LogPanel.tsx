import { useEffect, useRef, useState } from 'react'
import { clsx } from 'clsx'
import { useWsStore } from '@/stores/wsStore'
import type { WsLogLine } from '@/types/api'

interface LogPanelProps {
  runId: number
}

type LogLevel = 'ALL' | 'INFO' | 'WARNING' | 'ERROR'

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'text-[#6e7681]',
  INFO: 'text-[#8b949e]',
  WARNING: 'text-[#d29922]',
  ERROR: 'text-[#f85149]',
}

export function LogPanel({ runId }: LogPanelProps) {
  const lines = useWsStore((s) => s.logLines[runId] ?? [])
  const [filter, setFilter] = useState<LogLevel>('INFO')
  const [autoScroll, setAutoScroll] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)

  const filtered = lines.filter((l) => {
    if (filter === 'ALL') return true
    if (filter === 'ERROR') return l.level === 'ERROR'
    if (filter === 'WARNING') return l.level === 'WARNING' || l.level === 'ERROR'
    return true // INFO: show all non-DEBUG
  }).filter((l) => filter === 'ALL' || l.level !== 'DEBUG')

  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [filtered.length, autoScroll])

  return (
    <div className="rounded-md border border-[#30363d] bg-[#161b22] flex flex-col">
      <div className="flex items-center justify-between px-4 py-2 border-b border-[#21262d] shrink-0">
        <span className="text-xs font-semibold text-[#e6edf3]">Log</span>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1">
            {(['ALL', 'INFO', 'WARNING', 'ERROR'] as LogLevel[]).map((l) => (
              <button
                key={l}
                onClick={() => setFilter(l)}
                className={clsx(
                  'px-2 py-0.5 rounded text-[10px] font-medium transition-colors',
                  filter === l
                    ? 'bg-[#21262d] text-[#e6edf3]'
                    : 'text-[#6e7681] hover:text-[#8b949e]',
                )}
              >
                {l}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-1 text-[10px] text-[#6e7681] cursor-pointer">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="w-3 h-3"
            />
            Auto-scroll
          </label>
        </div>
      </div>

      <div
        className="flex-1 overflow-y-auto font-mono text-[11px] px-4 py-2 min-h-[120px] max-h-[240px]"
        onScroll={(e) => {
          const el = e.currentTarget
          const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30
          setAutoScroll(atBottom)
        }}
      >
        {filtered.length === 0 ? (
          <span className="text-[#6e7681] italic">No log output yet…</span>
        ) : (
          filtered.map((line, i) => (
            <LogLine key={i} line={line} />
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

function LogLine({ line }: { line: WsLogLine }) {
  const ts = new Date(line.ts).toLocaleTimeString()
  return (
    <div className="flex gap-2 leading-5 hover:bg-[#1c2128] px-1 rounded">
      <span className="text-[#6e7681] shrink-0">{ts}</span>
      <span
        className={clsx(
          'shrink-0 w-14 font-semibold',
          LEVEL_COLORS[line.level] ?? 'text-[#8b949e]',
        )}
      >
        {line.level}
      </span>
      <span className="text-[#c9d1d9] whitespace-pre-wrap break-all">{line.message}</span>
    </div>
  )
}
