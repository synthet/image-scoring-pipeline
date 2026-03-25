import { useQuery } from '@tanstack/react-query'
import { Activity, Database, Cpu, HardDrive, Info, RefreshCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'

const REFETCH_INTERVAL = 60000 // 1 minute for diagnostics

export function DiagnosticsPage() {
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['diagnostics'],
    queryFn: async () => {
      const resp = await fetch('/api/diagnostics')
      if (!resp.ok) throw new Error('Failed to fetch diagnostics')
      return resp.json()
    },
    refetchInterval: REFETCH_INTERVAL,
  })

  if (isLoading) {
    return (
      <div className="p-8 flex items-center justify-center h-full text-[#9d9d9d] animate-pulse">
        Collecting system diagnostics…
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="p-8 text-[#f44747]">
        <h1 className="text-xl font-semibold mb-4 text-[#cccccc]">Diagnostics Error</h1>
        <p>Could not load diagnostics data. Ensure the backend is running and /api/diagnostics is available.</p>
        <Button variant="secondary" onClick={() => refetch()} className="mt-4">
          Retry
        </Button>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <header className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-[#cccccc] flex items-center gap-2">
            <Activity className="text-[#4fc1ff]" size={24} />
            System Diagnostics
          </h1>
          <p className="text-sm text-[#9d9d9d] mt-1">
            Real-time status of backend services, database, and hardware.
          </p>
        </div>
        <Button 
          variant="secondary" 
          size="sm" 
          onClick={() => refetch()} 
          disabled={isFetching}
          className="gap-2"
        >
          <RefreshCcw size={14} className={isFetching ? 'animate-spin' : ''} />
          {isFetching ? 'Refreshing...' : 'Refresh'}
        </Button>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* System Info */}
        <DiagCard 
          title="System" 
          icon={<Cpu size={18} className="text-[#cca700]" />}
          data={[
            { label: 'OS', value: `${data.system.os} ${data.system.os_release}` },
            { label: 'Python', value: data.system.python_version.split(' ')[0] },
            { label: 'Memory', value: data.system.memory_total_gb ? `${data.system.memory_available_gb} / ${data.system.memory_total_gb} GB (${data.system.memory_percent}%)` : 'psutil unavailable' },
            { label: 'CPU Cores', value: data.system.cpu_count },
          ]}
        />

        {/* Database Info */}
        <DiagCard 
          title="Database" 
          icon={<Database size={18} className="text-[#89d185]" />}
          status={data.database.reachable ? 'healthy' : 'failed'}
          data={[
            { label: 'Type', value: data.database.type },
            { label: 'Size', value: `${data.database.size_mb} MB` },
            { label: 'Path', value: data.database.path, tooltip: data.database.path },
            { label: 'Modified', value: new Date(data.database.last_modified).toLocaleString() },
          ]}
        />

        {/* Models & GPU */}
        <DiagCard 
          title="Models & GPU" 
          icon={<Activity size={18} className="text-[#4fc1ff]" />}
          data={[
            { label: 'GPU Available', value: data.models.gpu_available ? 'YES' : 'NO', highlight: data.models.gpu_available },
            { label: 'Device', value: data.models.torch_gpu_name || 'CPU' },
            { label: 'Frameworks', value: data.models.frameworks.join(', ') },
            { label: 'CUDA', value: data.models.cuda_version || 'N/A' },
          ]}
        />

        {/* Filesystem */}
        <DiagCard 
          title="Filesystem" 
          icon={<HardDrive size={18} className="text-[#9d9d9d]" />}
          data={[
            { label: 'Root', value: data.filesystem.root_dir, tooltip: data.filesystem.root_dir },
            { label: 'Free Space', value: `${data.filesystem.free_space_gb} GB` },
            { label: 'Thumbnails', value: data.filesystem.thumbnails_dir, tooltip: data.filesystem.thumbnails_dir },
          ]}
        />

        {/* Runner Status */}
        <DiagCard 
          title="Runners" 
          icon={<RefreshCcw size={18} className="text-[#4fc1ff]" />}
          data={Object.entries(data.runners).map(([k, v]) => ({
            label: k.charAt(0).toUpperCase() + k.slice(1),
            value: String(v).toUpperCase(),
            highlight: v === 'available' || v === 'active'
          }))}
        />

        {/* Configuration */}
        <DiagCard 
          title="Configuration" 
          icon={<Info size={18} className="text-[#6d6d6d]" />}
          data={[
            { label: 'Debug Mode', value: data.config.debug ? 'ON' : 'OFF', highlight: data.config.debug },
            { label: 'REST Port', value: data.config.webui_port },
            { label: 'Allowed Paths', value: data.config.allowed_paths_count },
          ]}
        />
      </div>

      <footer className="mt-8 pt-6 border-t border-[#333333] text-[10px] text-[#6d6d6d] flex justify-between">
        <span>Backend Timestamp: {new Date(data.timestamp).toISOString()}</span>
        <span>Diagnostics v1.0.0</span>
      </footer>
    </div>
  )
}

function DiagCard({ title, icon, data, status, statusMsg }: any) {
  return (
    <div className="bg-[#252526] border border-[#333333] rounded-lg p-5 hover:border-[#444444] transition-colors">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-[#cccccc] flex items-center gap-2">
          {icon}
          {title}
        </h3>
        {status && (
          <div 
            className={`w-2 h-2 rounded-full ${status === 'healthy' ? 'bg-[#89d185]' : 'bg-[#f44747]'}`} 
            title={statusMsg || status}
          />
        )}
      </div>
      <div className="space-y-2">
        {data.map((item: any, i: number) => (
          <div key={i} className="flex justify-between text-xs overflow-hidden">
            <span className="text-[#9d9d9d] shrink-0 mr-4">{item.label}</span>
            <span 
              className={`truncate font-medium ${item.highlight ? 'text-[#4fc1ff]' : 'text-[#cccccc]'}`}
              title={item.tooltip || String(item.value)}
            >
              {String(item.value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
