import { api } from './client'
import type { ScopePreviewResult, FolderNode } from '@/types/api'

export const scopeApi = {
  preview: (paths: string[], recursive: boolean) =>
    api.post<ScopePreviewResult>('/scope/preview', { paths, recursive }),

  tree: () => api.get<FolderNode[]>('/scope/tree'),

  // Fallback to existing endpoint if /scope/tree not yet implemented
  foldersTree: () => api.get<FolderNode[]>('/folders/tree'),
}
