import { NavLink, Outlet } from 'react-router-dom'
import { clsx } from 'clsx'
import { PanelLeft, Zap, Image, Settings, Activity } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { useUiStore } from '@/stores/uiStore'
import { useWsStore } from '@/stores/wsStore'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useQuery } from '@tanstack/react-query'
import { runsApi } from '@/api/runs'

export function Shell() {
  useWebSocket()

  const { sidebarOpen, toggleSidebar } = useUiStore()
  const connected = useWsStore((s) => s.connected)
  const runsVersion = useWsStore((s) => s.runsVersion)

  const { data: runs } = useQuery({
    queryKey: ['runs-active', runsVersion],
    queryFn: () => runsApi.list({ limit: 50 }),
    refetchInterval: 5000,
  })

  const activeCount = runs?.filter((r) => r.status === 'running').length ?? 0
  const queuedCount = runs?.filter((r) => r.status === 'queued' || r.status === 'pending').length ?? 0

  return (
    <div className="flex h-full flex-col bg-[#0d1117]">
      {/* Top nav */}
      <header className="flex h-12 items-center gap-3 border-b border-[#21262d] bg-[#161b22] px-4 shrink-0">
        <button
          onClick={toggleSidebar}
          className="p-1 rounded text-[#8b949e] hover:text-[#e6edf3] hover:bg-[#21262d] transition-colors"
        >
          <PanelLeft size={16} />
        </button>

        <div className="flex items-center gap-2 mr-4">
          <Zap size={16} className="text-[#388bfd]" />
          <span className="text-sm font-semibold text-[#e6edf3]">Image Scoring</span>
        </div>

        <nav className="flex items-center gap-1">
          <NavItem to="/runs" icon={<Activity size={14} />} label="Runs" />
          <NavItem to="/gallery" icon={<Image size={14} />} label="Gallery" />
          <NavItem to="/settings" icon={<Settings size={14} />} label="Settings" />
        </nav>

        <div className="ml-auto flex items-center gap-3">
          {(activeCount > 0 || queuedCount > 0) && (
            <NavLink to="/runs" className="text-xs text-[#8b949e] hover:text-[#388bfd] transition-colors">
              {activeCount > 0 && (
                <span className="text-[#388bfd] font-medium">{activeCount} active</span>
              )}
              {activeCount > 0 && queuedCount > 0 && <span className="mx-1">·</span>}
              {queuedCount > 0 && <span>{queuedCount} queued</span>}
            </NavLink>
          )}

          <div className="flex items-center gap-1.5">
            <div
              className={clsx(
                'w-2 h-2 rounded-full',
                connected ? 'bg-[#3fb950]' : 'bg-[#6e7681]',
              )}
              title={connected ? 'Live updates active' : 'Disconnected'}
            />
            <span className="text-xs text-[#6e7681]">{connected ? 'Live' : 'Offline'}</span>
          </div>
        </div>
      </header>

      {/* Body */}
      <div className="flex flex-1 min-h-0">
        {sidebarOpen && <Sidebar />}
        <main className="flex-1 min-w-0 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

function NavItem({ to, icon, label }: { to: string; icon: React.ReactNode; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        clsx(
          'flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors',
          isActive
            ? 'text-[#e6edf3] bg-[#21262d]'
            : 'text-[#8b949e] hover:text-[#e6edf3] hover:bg-[#21262d]',
        )
      }
    >
      {icon}
      {label}
    </NavLink>
  )
}
