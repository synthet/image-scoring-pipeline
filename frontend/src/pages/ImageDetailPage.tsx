import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { galleryApi } from '@/api/gallery'
import { ImageDetailContent } from '@/components/gallery/ImageDetailPanel'
import type { ImageDetail } from '@/types/api'

function detailPreviewSrc(image: ImageDetail): string | null {
  const full = image.resolved_path || image.file_path
  if (full) return `/source-image?path=${encodeURIComponent(full)}`
  if (image.thumbnail_path) {
    return `/source-image?path=${encodeURIComponent(image.thumbnail_path)}&thumb=1`
  }
  return null
}

export function ImageDetailPage() {
  const { imageKey } = useParams<{ imageKey: string }>()
  const decoded = imageKey ? decodeURIComponent(imageKey) : ''

  const { data, isLoading, error } = useQuery({
    queryKey: ['image', decoded],
    queryFn: () => galleryApi.getByKey(decoded),
    enabled: Boolean(decoded),
  })

  if (!decoded) {
    return <div className="p-4 text-sm text-[#6d6d6d]">Missing image key.</div>
  }

  if (isLoading) {
    return <div className="p-4 text-sm text-[#6d6d6d]">Loading image…</div>
  }

  if (error || !data) {
    return (
      <div className="p-4 space-y-2">
        <div className="text-sm text-[#f44747]">Could not load image.</div>
        <Link to="/gallery" className="text-xs text-[#4fc1ff] hover:underline">
          Back to gallery
        </Link>
      </div>
    )
  }

  const src = detailPreviewSrc(data)
  const subIds = [data.image_uuid && `uuid ${data.image_uuid}`, data.image_hash && `hash ${data.image_hash}`]
    .filter(Boolean)
    .join(' · ')

  return (
    <div className="flex flex-col lg:flex-row h-full min-h-0 overflow-auto lg:overflow-hidden bg-[#1e1e1e]">
      <div className="flex-1 flex flex-col min-w-0 min-h-0 lg:min-h-0">
        <div className="flex items-center gap-3 px-4 py-2 border-b border-[#3c3c3c] shrink-0">
          <Link to="/gallery" className="text-xs text-[#4fc1ff] hover:underline shrink-0">
            ← Gallery
          </Link>
          <span className="text-sm font-medium text-[#cccccc] truncate">{data.file_name}</span>
          <span className="text-[10px] text-[#6d6d6d] ml-auto shrink-0 hidden sm:inline">
            id {data.id}
            {subIds ? ` · ${subIds}` : ''}
          </span>
        </div>
        <div className="flex-1 min-h-[40vh] lg:min-h-0 overflow-auto flex items-center justify-center p-4 bg-[#141414]">
          {src ? (
            <img
              src={src}
              alt={data.file_name}
              className="max-w-full max-h-full w-auto h-auto object-contain shadow-lg"
            />
          ) : (
            <div className="text-sm text-[#6d6d6d]">No preview path available.</div>
          )}
        </div>
      </div>
      <aside className="w-full lg:w-72 shrink-0 border-t lg:border-t-0 lg:border-l border-[#3c3c3c] bg-[#252526] overflow-y-auto">
        <div className="px-4 py-3 border-b border-[#3c3c3c]">
          <span className="text-sm font-semibold text-[#cccccc]">Details</span>
        </div>
        <ImageDetailContent image={data} />
      </aside>
    </div>
  )
}
