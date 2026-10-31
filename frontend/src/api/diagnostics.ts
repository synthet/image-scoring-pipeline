import { api } from './client'
import type { DiagnosticManifest, DiagnosticTransport } from '../types/diagnostics'

export const diagnosticsTransport: DiagnosticTransport = {
  manifest: imageId => api.get<DiagnosticManifest>(`/images/${imageId}/evidence?schema_version=2`),
  request: (imageId, layers, refresh) => api.post<DiagnosticManifest>(`/images/${imageId}/evidence/requests`, { layers, refresh }),
  cancel: async (imageId, requestId) => {
    const response = await fetch(`/api/images/${imageId}/evidence/requests/${encodeURIComponent(requestId)}`, { method: 'DELETE' })
    if (!response.ok) throw new Error('Could not cancel diagnostics')
  },
  artifact: async (imageId, artifactId) => {
    if (!/^[a-f0-9]{64}_[a-f0-9]{64}\.(png|jpg)$/.test(artifactId)) throw new Error('Invalid diagnostic artifact')
    return `/api/images/${imageId}/evidence/artifacts/${artifactId}`
  },
}
