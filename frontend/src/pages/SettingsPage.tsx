import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Button } from '@/components/ui/button'
import { clsx } from 'clsx'
import { CheckCircle2, AlertCircle } from 'lucide-react'

type SettingsSection = 'scoring' | 'processing' | 'clustering' | 'tagging' | 'system'

interface HealthResponse {
  status: string
  scoring_available: boolean
  tagging_available: boolean
  clustering_available: boolean
}

export function SettingsPage() {
  const [section, setSection] = useState<SettingsSection>('scoring')
  const [saveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => api.get<HealthResponse>('/health'),
    refetchInterval: 15000,
  })

  const { data: config = {} } = useQuery({
    queryKey: ['config'],
    queryFn: () => api.get<Record<string, unknown>>('/config'),
  })

  const SECTIONS: { id: SettingsSection; label: string }[] = [
    { id: 'scoring', label: 'Quality Analysis' },
    { id: 'processing', label: 'Processing' },
    { id: 'clustering', label: 'Similarity Clustering' },
    { id: 'tagging', label: 'Tagging' },
    { id: 'system', label: 'System' },
  ]

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-lg font-semibold text-[#e6edf3] mb-5">Settings</h1>

      {/* Health */}
      <div className="rounded-md border border-[#30363d] bg-[#161b22] p-4 mb-5">
        <div className="text-xs font-semibold uppercase tracking-wider text-[#6e7681] mb-3">System Health</div>
        <div className="grid grid-cols-4 gap-3">
          <HealthItem label="API" ok={health?.status === 'ok'} />
          <HealthItem label="Quality Analysis" ok={health?.scoring_available} />
          <HealthItem label="Tagging" ok={health?.tagging_available} />
          <HealthItem label="Clustering" ok={health?.clustering_available} />
        </div>
      </div>

      <div className="flex gap-5">
        {/* Sidebar */}
        <nav className="w-44 shrink-0">
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              onClick={() => setSection(s.id)}
              className={clsx(
                'w-full text-left text-sm px-3 py-2 rounded transition-colors',
                section === s.id
                  ? 'bg-[#21262d] text-[#e6edf3] font-medium'
                  : 'text-[#8b949e] hover:text-[#e6edf3] hover:bg-[#1c2128]',
              )}
            >
              {s.label}
            </button>
          ))}
        </nav>

        {/* Content */}
        <div className="flex-1 rounded-md border border-[#30363d] bg-[#161b22] p-5">
          <ConfigSection section={section} config={config} />

          <div className="mt-5 pt-4 border-t border-[#21262d] flex items-center gap-3">
            <Button
              variant="primary"
              size="sm"
              disabled={saveState === 'saving'}
              loading={saveState === 'saving'}
            >
              Save Changes
            </Button>
            {saveState === 'saved' && (
              <span className="text-xs text-[#3fb950] flex items-center gap-1">
                <CheckCircle2 size={12} /> Saved
              </span>
            )}
            {saveState === 'error' && (
              <span className="text-xs text-[#f85149] flex items-center gap-1">
                <AlertCircle size={12} /> Save failed
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function HealthItem({ label, ok }: { label: string; ok?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <div
        className={clsx(
          'w-2 h-2 rounded-full',
          ok === true && 'bg-[#3fb950]',
          ok === false && 'bg-[#f85149]',
          ok == null && 'bg-[#6e7681]',
        )}
      />
      <span className="text-xs text-[#8b949e]">{label}</span>
    </div>
  )
}

function ConfigSection({ section, config }: { section: SettingsSection; config: Record<string, unknown> }) {
  const sectionConfig = (config[section] as Record<string, unknown>) ?? {}

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-semibold text-[#e6edf3]">
        {section === 'scoring' ? 'Quality Analysis' :
         section === 'clustering' ? 'Similarity Clustering' :
         section.charAt(0).toUpperCase() + section.slice(1)} Settings
      </h2>

      {Object.entries(sectionConfig).length === 0 ? (
        <p className="text-xs text-[#6e7681]">No configurable settings for this section yet.</p>
      ) : (
        Object.entries(sectionConfig).map(([key, value]) => (
          <ConfigField key={key} name={key} value={value} />
        ))
      )}
    </div>
  )
}

function ConfigField({ name, value }: { name: string; value: unknown }) {
  const label = name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

  if (typeof value === 'boolean') {
    return (
      <label className="flex items-center justify-between py-1">
        <span className="text-sm text-[#8b949e]">{label}</span>
        <input type="checkbox" defaultChecked={value} className="w-4 h-4" />
      </label>
    )
  }

  if (typeof value === 'number') {
    return (
      <div className="flex items-center justify-between py-1 gap-4">
        <span className="text-sm text-[#8b949e]">{label}</span>
        <input
          type="number"
          defaultValue={value}
          className="w-32 bg-[#0d1117] border border-[#30363d] rounded px-2 py-1 text-sm text-[#e6edf3] outline-none focus:border-[#388bfd]"
        />
      </div>
    )
  }

  return (
    <div className="py-1">
      <label className="block text-sm text-[#8b949e] mb-1">{label}</label>
      <input
        type="text"
        defaultValue={String(value)}
        className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-1.5 text-sm text-[#e6edf3] outline-none focus:border-[#388bfd]"
      />
    </div>
  )
}
