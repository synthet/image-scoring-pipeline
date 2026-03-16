import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Star, Filter, X } from 'lucide-react'
import { galleryApi, type ImageFilters } from '@/api/gallery'
import { Button } from '@/components/ui/button'
import type { Image } from '@/types/api'

const LABELS = ['Pick', 'Reject', 'Normal']
const PER_PAGE = 60

export function GalleryPage() {
  const [filters, setFilters] = useState<ImageFilters>({ limit: PER_PAGE, offset: 0 })
  const [selected, setSelected] = useState<Image | null>(null)
  const [filterOpen, setFilterOpen] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['gallery', filters],
    queryFn: () => galleryApi.list(filters),
    placeholderData: (prev) => prev,
  })

  const images = data?.images ?? []
  const total = data?.total ?? 0

  function updateFilter(patch: Partial<ImageFilters>) {
    setFilters((prev) => ({ ...prev, ...patch, offset: 0 }))
  }

  return (
    <div className="flex h-full min-h-0">
      {/* Filters sidebar */}
      {filterOpen && (
        <aside className="w-56 shrink-0 border-r border-[#21262d] bg-[#161b22] p-4 overflow-y-auto">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-semibold text-[#8b949e] uppercase tracking-wider">Filters</span>
            <button onClick={() => setFilterOpen(false)} className="text-[#6e7681] hover:text-[#e6edf3]">
              <X size={13} />
            </button>
          </div>

          <FilterSection label="Min Rating">
            <div className="flex gap-1">
              {[0, 1, 2, 3, 4, 5].map((r) => (
                <button
                  key={r}
                  onClick={() => updateFilter({ min_rating: r === filters.min_rating ? undefined : r })}
                  className={clsx(
                    'w-7 h-7 flex items-center justify-center rounded text-xs border transition-colors',
                    filters.min_rating === r
                      ? 'bg-[#051d3a] border-[#1f6feb] text-[#388bfd]'
                      : 'border-[#30363d] text-[#8b949e] hover:border-[#388bfd]',
                  )}
                >
                  {r === 0 ? 'Any' : <Star size={10} fill={r <= (filters.min_rating ?? 0) ? 'currentColor' : 'none'} />}
                </button>
              ))}
            </div>
          </FilterSection>

          <FilterSection label="Label">
            <div className="space-y-1">
              {LABELS.map((l) => (
                <button
                  key={l}
                  onClick={() => updateFilter({ label: l === filters.label ? undefined : l })}
                  className={clsx(
                    'w-full text-left text-xs px-2 py-1 rounded border transition-colors',
                    filters.label === l
                      ? 'bg-[#051d3a] border-[#1f6feb] text-[#388bfd]'
                      : 'border-transparent text-[#8b949e] hover:bg-[#21262d]',
                  )}
                >
                  {l}
                </button>
              ))}
            </div>
          </FilterSection>

          <FilterSection label="Min Score">
            <input
              type="range"
              min={0}
              max={100}
              value={filters.min_score ?? 0}
              onChange={(e) => updateFilter({ min_score: parseInt(e.target.value) || undefined })}
              className="w-full"
            />
            <div className="text-xs text-[#6e7681] text-right">{filters.min_score ?? 0}</div>
          </FilterSection>

          <FilterSection label="Keyword">
            <input
              value={filters.keyword ?? ''}
              onChange={(e) => updateFilter({ keyword: e.target.value || undefined })}
              placeholder="landscape, portrait…"
              className="w-full bg-[#0d1117] border border-[#30363d] rounded px-2 py-1 text-xs text-[#e6edf3] outline-none focus:border-[#388bfd] placeholder:text-[#6e7681]"
            />
          </FilterSection>

          <Button
            size="xs"
            variant="ghost"
            onClick={() => setFilters({ limit: PER_PAGE, offset: 0 })}
            className="mt-3"
          >
            Clear all filters
          </Button>
        </aside>
      )}

      {/* Main gallery */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Toolbar */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[#21262d] shrink-0">
          <Button
            variant={filterOpen ? 'outline' : 'secondary'}
            size="sm"
            onClick={() => setFilterOpen((v) => !v)}
          >
            <Filter size={12} />
            Filters
          </Button>
          <span className="text-xs text-[#6e7681]">
            {total.toLocaleString()} image{total !== 1 ? 's' : ''}
          </span>
        </div>

        {/* Grid */}
        <div className="flex-1 overflow-y-auto p-4">
          {isLoading && images.length === 0 && (
            <div className="text-sm text-[#6e7681]">Loading gallery…</div>
          )}

          <div className="grid gap-1" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))' }}>
            {images.map((img) => (
              <ImageTile
                key={img.id}
                image={img}
                selected={selected?.id === img.id}
                onClick={() => setSelected(img)}
              />
            ))}
          </div>

          {/* Pagination */}
          {total > PER_PAGE && (
            <div className="flex items-center justify-center gap-3 mt-6">
              <Button
                size="sm"
                variant="secondary"
                disabled={(filters.offset ?? 0) <= 0}
                onClick={() => setFilters((f) => ({ ...f, offset: Math.max(0, (f.offset ?? 0) - PER_PAGE) }))}
              >
                Previous
              </Button>
              <span className="text-xs text-[#6e7681]">
                {Math.floor((filters.offset ?? 0) / PER_PAGE) + 1} / {Math.ceil(total / PER_PAGE)}
              </span>
              <Button
                size="sm"
                variant="secondary"
                disabled={(filters.offset ?? 0) + PER_PAGE >= total}
                onClick={() => setFilters((f) => ({ ...f, offset: (f.offset ?? 0) + PER_PAGE }))}
              >
                Next
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Detail panel */}
      {selected && (
        <ImageDetailPanel image={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  )
}

function FilterSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6e7681] mb-2">{label}</div>
      {children}
    </div>
  )
}

function ImageTile({
  image, selected, onClick,
}: {
  image: Image
  selected: boolean
  onClick: () => void
}) {
  const src = image.thumbnail_path
    ? `/source-image?path=${encodeURIComponent(image.thumbnail_path)}&thumb=1`
    : null

  return (
    <div
      onClick={onClick}
      className={clsx(
        'relative aspect-square rounded overflow-hidden cursor-pointer border-2 transition-all',
        selected ? 'border-[#388bfd]' : 'border-transparent hover:border-[#30363d]',
      )}
    >
      {src ? (
        <img
          src={src}
          alt={image.filename}
          className="w-full h-full object-cover"
          loading="lazy"
        />
      ) : (
        <div className="w-full h-full bg-[#21262d] flex items-center justify-center text-[#6e7681] text-xs">
          No preview
        </div>
      )}
      {image.rating != null && image.rating > 0 && (
        <div className="absolute bottom-1 left-1 flex">
          {Array.from({ length: image.rating }).map((_, i) => (
            <Star key={i} size={8} className="text-[#d29922]" fill="currentColor" />
          ))}
        </div>
      )}
      {image.composite_score != null && (
        <div className="absolute top-1 right-1 bg-black/70 text-white text-[9px] px-1 rounded">
          {Math.round(image.composite_score)}
        </div>
      )}
    </div>
  )
}

function ImageDetailPanel({ image, onClose }: { image: Image; onClose: () => void }) {
  return (
    <aside className="w-72 shrink-0 border-l border-[#21262d] bg-[#161b22] overflow-y-auto">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#21262d]">
        <span className="text-sm font-semibold text-[#e6edf3] truncate">{image.filename}</span>
        <button onClick={onClose} className="text-[#6e7681] hover:text-[#e6edf3] shrink-0">
          <X size={14} />
        </button>
      </div>

      <div className="p-4 space-y-4">
        {/* Scores */}
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6e7681] mb-2">
            Quality Scores
          </div>
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: 'MUSIQ', value: image.musiq_score },
              { label: 'LIQE', value: image.liqe_score },
              { label: 'TOPIQ', value: image.topiq_score },
              { label: 'Q-Align', value: image.qalign_score },
            ].map(({ label, value }) => (
              <ScoreCell key={label} label={label} value={value} />
            ))}
          </div>
          {image.composite_score != null && (
            <div className="mt-2 flex items-center justify-between">
              <span className="text-xs text-[#8b949e]">Composite</span>
              <span className="text-sm font-bold text-[#388bfd]">
                {image.composite_score.toFixed(1)}
              </span>
            </div>
          )}
        </div>

        {/* Metadata */}
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6e7681] mb-2">
            Metadata
          </div>
          <dl className="space-y-1 text-xs">
            {image.width && image.height && (
              <MetaRow label="Size" value={`${image.width} × ${image.height}`} />
            )}
            {image.camera_model && (
              <MetaRow label="Camera" value={`${image.camera_make ?? ''} ${image.camera_model}`.trim()} />
            )}
            {image.file_size && (
              <MetaRow label="File" value={formatBytes(image.file_size)} />
            )}
          </dl>
        </div>

        {/* Rating */}
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6e7681] mb-2">Rating</div>
          <div className="flex gap-1">
            {[1, 2, 3, 4, 5].map((r) => (
              <Star
                key={r}
                size={16}
                className={clsx(
                  'cursor-pointer transition-colors',
                  r <= (image.rating ?? 0)
                    ? 'text-[#d29922] fill-[#d29922]'
                    : 'text-[#30363d]',
                )}
              />
            ))}
          </div>
        </div>

        {/* Keywords */}
        {image.keywords && image.keywords.length > 0 && (
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6e7681] mb-2">Keywords</div>
            <div className="flex flex-wrap gap-1">
              {image.keywords.map((kw) => (
                <span
                  key={kw}
                  className="bg-[#21262d] text-[#8b949e] text-xs px-2 py-0.5 rounded border border-[#30363d]"
                >
                  {kw}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}

function ScoreCell({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="bg-[#0d1117] rounded p-2 border border-[#21262d]">
      <div className="text-[10px] text-[#6e7681]">{label}</div>
      <div className="text-sm font-semibold text-[#e6edf3]">
        {value != null ? value.toFixed(1) : '—'}
      </div>
    </div>
  )
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-[#6e7681]">{label}</dt>
      <dd className="text-[#8b949e] text-right truncate">{value}</dd>
    </div>
  )
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}
