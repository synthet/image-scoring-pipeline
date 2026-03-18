import { api } from './client'
import type { ScopePreviewResult, FolderNode } from '@/types/api'

export const scopeApi = {
  preview: (paths: string[], recursive: boolean) =>
    api.post<ScopePreviewResult>('/scope/preview', { paths, recursive }),

  tree: () => api.get<FolderNode[]>('/scope/tree'),

  // Fallback: /folders/tree returns { tree, count }, normalize to FolderNode[]
  foldersTree: () =>
    api
      .get<{ tree?: FolderNode[]; count?: number }>('/folders/tree')
      .then((r) => (Array.isArray(r?.tree) ? r.tree : [])),
}
