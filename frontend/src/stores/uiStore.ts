import { create } from 'zustand'

interface UiStore {
  sidebarOpen: boolean
  setSidebarOpen: (v: boolean) => void
  toggleSidebar: () => void

  selectedScopePath: string | null
  setSelectedScopePath: (path: string | null) => void

  newRunModalOpen: boolean
  setNewRunModalOpen: (v: boolean) => void
  newRunInitialPath: string | null
  openNewRun: (path?: string) => void
}

export const useUiStore = create<UiStore>((set) => ({
  sidebarOpen: true,
  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),

  selectedScopePath: null,
  setSelectedScopePath: (selectedScopePath) => set({ selectedScopePath }),

  newRunModalOpen: false,
  setNewRunModalOpen: (newRunModalOpen) => set({ newRunModalOpen }),
  newRunInitialPath: null,
  openNewRun: (path) => set({ newRunModalOpen: true, newRunInitialPath: path ?? null }),
}))
