import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChartLine, X } from 'lucide-react'
import { keywordsApi } from '@/api/keywords'
import { scoreAnalyticsApi } from './api'
import { fmtInt } from './data'
import { CorrelationsTab } from './CorrelationsTab'
import { DistributionsTab } from './DistributionsTab'
import { KeywordsTab } from './KeywordsTab'
import { RankCurvesTab } from './RankCurvesTab'
import { RegressionTab } from './RegressionTab'
import { StacksTab } from './StacksTab'
import { SuitabilityTab } from './SuitabilityTab'
import { ErrorState, Loading } from './ui'

const TABS = [
  { id: 'curves', label: 'Rank curves' },
  { id: 'distributions', label: 'Distributions' },
  { id: 'correlations', label: 'Correlations' },
  { id: 'regression', label: 'Regression' },
  { id: 'stacks', label: 'Stacks (culling)' },
  { id: 'suitability', label: 'Suitability Nₐ/Nᵦ' },
  { id: 'keywords', label: 'Keyword layers' },
] as const
type TabId = (typeof TABS)[number]['id']

const QUERY_OPTS = { staleTime: 5 * 60_000, gcTime: 30 * 60_000, retry: false } as const

function LayerPicker({ keyword, onChange }: { keyword: string | null; onChange: (kw: string | null) => void }) {
  const [draft, setDraft] = useState(keyword ?? '')
  const cloud = useQuery({
    queryKey: ['keywords', 'cloud', 'general', 300],
    queryFn: () => keywordsApi.cloud('general', { limit: 300 }),
    staleTime: 10 * 60_000,
  })
  return (
    <form
      className="flex items-center gap-2 text-xs"
      onSubmit={(e) => {
        e.preventDefault()
        onChange(draft.trim() || null)
      }}
    >
      <span className="text-[var(--color-text-secondary)]">Layer</span>
      <input
        list="score-analytics-keywords"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="All images — type a keyword"
        aria-label="Keyword layer"
        className="w-56 rounded border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] px-2 py-1 text-xs text-[var(--color-text-primary)] placeholder:text-[var(--color-text-placeholder)]"
      />
      <datalist id="score-analytics-keywords">
        {cloud.data?.keywords.map((k) => (
          <option key={k.keyword_norm} value={k.keyword_norm}>
            {k.count} images
          </option>
        ))}
      </datalist>
      <button
        type="submit"
        className="rounded border border-[var(--color-accent)] px-2 py-1 text-[var(--color-accent-bright)] hover:bg-[var(--color-accent-dim)]"
      >
        Apply
      </button>
      {keyword && (
        <button
          type="button"
          onClick={() => {
            setDraft('')
            onChange(null)
          }}
          className="inline-flex items-center gap-1 rounded bg-[var(--color-bg-elevated)] px-2 py-1 text-[var(--color-text-primary)]"
          title="Back to all images"
        >
          {keyword} <X size={12} />
        </button>
      )}
    </form>
  )
}

export function ScoreAnalyticsPage() {
  const [params, setParams] = useSearchParams()
  const tab = (TABS.find((t) => t.id === params.get('tab'))?.id ?? 'curves') as TabId
  const keyword = params.get('keyword')
  const pickedParam = params.get('dim')

  const update = (patch: Record<string, string | null>) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        for (const [k, v] of Object.entries(patch)) {
          if (v === null) next.delete(k)
          else next.set(k, v)
        }
        return next
      },
      { replace: true },
    )

  const needsMatrix = tab === 'curves'
  const needsStats = tab === 'distributions' || tab === 'correlations' || tab === 'regression'
  const matrix = useQuery({
    queryKey: ['score-analytics', 'matrix', keyword],
    queryFn: () => scoreAnalyticsApi.matrix(keyword),
    enabled: needsMatrix,
    ...QUERY_OPTS,
  })
  const stats = useQuery({
    queryKey: ['score-analytics', 'stats', keyword],
    queryFn: () => scoreAnalyticsApi.stats(keyword),
    enabled: needsStats,
    ...QUERY_OPTS,
  })

  const keys = matrix.data?.keys ?? stats.data?.keys ?? []
  const picked = pickedParam && keys.includes(pickedParam) ? pickedParam : keys.includes('general') ? 'general' : keys[0]
  const imageCount = matrix.data?.image_count ?? stats.data?.image_count

  const body = () => {
    if (tab === 'keywords') return <KeywordsTab onPickKeyword={(kw) => update({ keyword: kw, tab: 'curves' })} />
    if (tab === 'stacks') return <StacksTab keyword={keyword} />
    if (tab === 'suitability') return <SuitabilityTab keyword={keyword} />
    const q = needsMatrix ? matrix : stats
    if (q.isLoading) return <Loading what={needsMatrix ? 'score matrix' : 'statistics'} />
    if (q.error) return <ErrorState error={q.error} />
    if (imageCount === 0 || !keys.length || !picked)
      return (
        <p className="p-4 text-xs text-[var(--color-text-muted)]">
          No scored images{keyword ? ` for keyword “${keyword}”` : ''}.
        </p>
      )
    if (tab === 'curves' && matrix.data)
      return <RankCurvesTab key={keyword ?? ''} matrix={matrix.data} picked={picked} onPick={(k) => update({ dim: k })} />
    if (!stats.data) return null
    if (tab === 'distributions') return <DistributionsTab stats={stats.data} picked={picked} />
    if (tab === 'correlations') return <CorrelationsTab stats={stats.data} />
    return <RegressionTab key={keyword ?? ''} stats={stats.data} keyword={keyword} />
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="shrink-0 border-b border-[var(--color-border-muted)] px-4 pt-4 bg-[var(--color-bg-secondary)]">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <ChartLine size={16} className="text-[var(--color-accent-bright)] shrink-0" />
              <h1 className="text-base font-semibold text-[var(--color-text-primary)]">Score analytics</h1>
            </div>
            <p className="text-xs text-[var(--color-text-muted)] mt-1">
              Every scoring dimension side by side
              {imageCount != null && ` · ${fmtInt(imageCount)} images`}
              {keyword ? ` tagged “${keyword}”` : ' in the library'}. Values are normalized 0–1.
            </p>
          </div>
          {tab !== 'keywords' && (
            <LayerPicker key={keyword ?? ''} keyword={keyword} onChange={(kw) => update({ keyword: kw })} />
          )}
        </div>
        <nav className="flex gap-1 mt-3 overflow-x-auto" role="tablist" aria-label="Score analytics views">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => update({ tab: t.id })}
              className={`px-3 py-1.5 text-xs border-b-2 -mb-px whitespace-nowrap transition-colors ${
                tab === t.id
                  ? 'border-[var(--color-accent-bright)] text-[var(--color-text-primary)]'
                  : 'border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-3">{body()}</div>
    </div>
  )
}
