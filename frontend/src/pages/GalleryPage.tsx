import { useState, useCallback, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Star, Filter, X } from 'lucide-react'
import { VirtuosoGrid } from 'react-virtuoso'
import { galleryApi, type ImageFilters } from '@/api/gallery'
import { Button } from '@/components/ui/button'
import type { Image } from '@/types/api'

const LABELS = ['Pick', 'Reject', 'Normal']
const PER_PAGE = 100

export function GalleryPage() {
  const [baseFilters, setBaseFilters] = useState<Omit<ImageFilters, 'offset' | 'limit'>>({})
  const [selected, setSelected] = useState<Image | null>(null)
  const [filterOpen, setFilterOpen] = useState(false)
  const [loadedImages, setLoadedImages] = useState<Image[]>([])
  const [offset, setOffset] = useState(0)
  const [total, setTotal] = useState(0)
  const loadingRef = useRef(false)

  const filters: ImageFilters = { ...baseFilters, limit: PER_PAGE, offset: 0 }

  // Initial/filter-change load
  const { isLoading } = useQuery({
    queryKey: ['gallery', baseFilters],
    queryFn: async () => {
      const res = await galleryApi.list({ ...baseFilters, limit: PER_PAGE, offset: 0 })
      setLoadedImages(res.images)
      setTotal(res.total)
      setOffset(res.images.length)
      return res
    },
  })

  const loadMore = useCallback(async () => {
    if (loadingRef.current || loadedImages.length >= total) return
    loadingRef.current = true
    try {
      const res = await galleryApi.list({ ...baseFilters, limit: PER_PAGE, offset })
      setLoadedImages((prev) => [...prev, ...res.images])
      setOffset((prev) => prev + res.images.length)
      setTotal(res.total)
    } finally {
      loadingRef.current = false
    }
  }, [baseFilters, offset, loadedImages.length, total])

  function updateFilter(patch: Partial<Omit<ImageFilters, 'offset' | 'limit'>>) {
    setBaseFilters((prev) => ({ ...prev, ...patch }))
  }

  // suppress unused warning — filters used only for query key derivation
  void filters

  return (
    <div className="flex h-full min-h-0">
      {/* Filters sidebar */}
      {filterOpen && (
        <aside className="w-56 shrink-0 border-r border-[#3c3c3c] bg-[#252526] p-4 overflow-y-auto">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-semibold text-[#9d9d9d] uppercase tracking-wider">Filters</span>
            <button onClick={() => setFilterOpen(false)} className="text-[#6d6d6d] hover:text-[#cccccc]">
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
                      ? 'bg-[#003f6e] border-[#007acc] text-[#4fc1ff]'
                      : 'border-[#474747] text-[#9d9d9d] hover:border-[#4fc1ff]',
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
                      ? 'bg-[#003f6e] border-[#007acc] text-[#4fc1ff]'
                      : 'border-transparent text-[#9d9d9d] hover:bg-[#3c3c3c]',
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
            <div className="text-xs text-[#6d6d6d] text-right">{filters.min_score ?? 0}</div>
          </FilterSection>

          <FilterSection label="Keyword">
            <input
              value={filters.keyword ?? ''}
              onChange={(e) => updateFilter({ keyword: e.target.value || undefined })}
              placeholder="landscape, portrait…"
              className="w-full bg-[#1e1e1e] border border-[#474747] rounded px-2 py-1 text-xs text-[#cccccc] outline-none focus:border-[#4fc1ff] placeholder:text-[#6d6d6d]"
            />
          </FilterSection>

          <Button
            size="xs"
            variant="ghost"
            onClick={() => setBaseFilters({})}
            className="mt-3"
          >
            Clear all filters
          </Button>
        </aside>
      )}

      {/* Main gallery */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Toolbar */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[#3c3c3c] shrink-0">
          <Button
            variant={filterOpen ? 'outline' : 'secondary'}
            size="sm"
            onClick={() => setFilterOpen((v) => !v)}
          >
            <Filter size={12} />
            Filters
          </Button>
          <span className="text-xs text-[#6d6d6d]">
            {total.toLocaleString()} image{total !== 1 ? 's' : ''}
          </span>
        </div>

        {/* Virtualized Grid */}
        <div className="flex-1 min-h-0 relative">
          {isLoading && loadedImages.length === 0 && (
            <div className="p-4 text-sm text-[#6d6d6d]">Loading gallery…</div>
          )}
          {!isLoading && loadedImages.length === 0 && (
            <div className="p-4 text-sm text-[#6d6d6d]">No images found.</div>
          )}
          {loadedImages.length > 0 && (
            <VirtuosoGrid
              style={{ height: '100%' }}
              totalCount={loadedImages.length}
              overscan={200}
              endReached={loadMore}
              listClassName="grid gap-1 p-4"
              itemClassName=""
              computeItemKey={(index) => loadedImages[index]?.id ?? index}
              itemContent={(index) => {
                const img = loadedImages[index]
                if (!img) return null
                return (
                  <ImageTile
                    image={img}
                    selected={selected?.id === img.id}
                    onClick={() => setSelected(img)}
                  />
                )
              }}
            />
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
      <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6d6d6d] mb-2">{label}</div>
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
        selected ? 'border-[#4fc1ff]' : 'border-transparent hover:border-[#474747]',
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
        <div className="w-full h-full bg-[#3c3c3c] flex items-center justify-center text-[#6d6d6d] text-xs">
          No preview
        </div>
      )}
      {image.rating != null && image.rating > 0 && (
        <div className="absolute bottom-1 left-1 flex">
          {Array.from({ length: image.rating }).map((_, i) => (
            <Star key={i} size={8} className="text-[#cca700]" fill="currentColor" />
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
    <aside className="w-72 shrink-0 border-l border-[#3c3c3c] bg-[#252526] overflow-y-auto">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#3c3c3c]">
        <span className="text-sm font-semibold text-[#cccccc] truncate">{image.filename}</span>
        <button onClick={onClose} className="text-[#6d6d6d] hover:text-[#cccccc] shrink-0">
          <X size={14} />
        </button>
      </div>

      <div className="p-4 space-y-4">
        {/* Scores */}
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6d6d6d] mb-2">
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
              <span className="text-xs text-[#9d9d9d]">Composite</span>
              <span className="text-sm font-bold text-[#4fc1ff]">
                {image.composite_score.toFixed(1)}
              </span>
            </div>
          )}
        </div>

        {/* Metadata */}
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6d6d6d] mb-2">
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
          <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6d6d6d] mb-2">Rating</div>
          <div className="flex gap-1">
            {[1, 2, 3, 4, 5].map((r) => (
              <Star
                key={r}
                size={16}
                className={clsx(
                  'cursor-pointer transition-colors',
                  r <= (image.rating ?? 0)
                    ? 'text-[#cca700] fill-[#cca700]'
                    : 'text-[#474747]',
                )}
              />
            ))}
          </div>
        </div>

        {/* Keywords */}
        {image.keywords && image.keywords.length > 0 && (
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6d6d6d] mb-2">Keywords</div>
            <div className="flex flex-wrap gap-1">
              {image.keywords.map((kw) => (
                <span
                  key={kw}
                  className="bg-[#3c3c3c] text-[#9d9d9d] text-xs px-2 py-0.5 rounded border border-[#474747]"
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

function ScoreCell({ label, value }: { label: string; value: number | null | undefined }) {
  return (
    <div className="bg-[#1e1e1e] rounded p-2 border border-[#3c3c3c]">
      <div className="text-[10px] text-[#6d6d6d]">{label}</div>
      <div className="text-sm font-semibold text-[#cccccc]">
        {value != null ? value.toFixed(1) : '—'}
      </div>
    </div>
  )
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-[#6d6d6d]">{label}</dt>
      <dd className="text-[#9d9d9d] text-right truncate">{value}</dd>
    </div>
  )
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}
