import type { ReactNode } from 'react'
import { clsx } from 'clsx'
import { AlertTriangle, CheckCircle2, Info, Loader2, XCircle } from 'lucide-react'
import { isNotPostgres, type SeriesMeta, type Severity } from './api'
import { dimensionBadge, dimensionLabel } from './data'
import { seriesColor } from './palette'

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className,
}: {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section
      className={clsx(
        'rounded-md border border-[var(--color-border-muted)] bg-[var(--color-bg-secondary)] p-3',
        className,
      )}
    >
      {(title || actions) && (
        <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
          <div>
            {title && <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">{title}</h2>}
            {subtitle && <p className="text-xs text-[var(--color-text-muted)] mt-0.5">{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  )
}

export function StatTile({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="rounded-md border border-[var(--color-border-muted)] bg-[var(--color-bg-tertiary)] px-3 py-2 min-w-[7rem]">
      <div className="text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">{label}</div>
      <div className="text-lg font-semibold text-[var(--color-text-primary)]">{value}</div>
      {hint && <div className="text-[11px] text-[var(--color-text-secondary)]">{hint}</div>}
    </div>
  )
}

export function Swatch({ dim, size = 10 }: { dim: string; size?: number }) {
  return (
    <span
      aria-hidden
      className="inline-block rounded-sm shrink-0"
      style={{ width: size, height: size, background: seriesColor(dim) }}
    />
  )
}

export function DimName({ dim, meta }: { dim: string; meta?: SeriesMeta }) {
  const badge = dimensionBadge(dim, meta)
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <Swatch dim={dim} />
      <span className="text-[var(--color-text-primary)]">{dimensionLabel(dim)}</span>
      {badge && (
        <span className="rounded px-1 text-[10px] uppercase tracking-wide bg-[var(--color-bg-elevated)] text-[var(--color-text-secondary)]">
          {badge}
        </span>
      )}
    </span>
  )
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
}: {
  value: T
  options: { id: T; label: string; title?: string }[]
  onChange: (v: T) => void
  ariaLabel: string
}) {
  return (
    <div role="radiogroup" aria-label={ariaLabel} className="inline-flex rounded-md border border-[var(--color-border)] overflow-hidden">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          role="radio"
          aria-checked={value === o.id}
          title={o.title}
          onClick={() => onChange(o.id)}
          className={clsx(
            'px-2.5 py-1 text-xs transition-colors',
            value === o.id
              ? 'bg-[var(--color-accent)] text-[var(--color-text-on-accent)]'
              : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-elevated)]',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function DimSelect({
  value,
  keys,
  meta,
  onChange,
  label,
}: {
  value: string
  keys: string[]
  meta: Record<string, SeriesMeta>
  onChange: (v: string) => void
  label: string
}) {
  return (
    <label className="inline-flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] px-2 py-1 text-xs text-[var(--color-text-primary)]"
      >
        {keys.map((k) => {
          const badge = dimensionBadge(k, meta[k])
          return (
            <option key={k} value={k}>
              {dimensionLabel(k)}
              {badge ? ` (${badge})` : ''}
            </option>
          )
        })}
      </select>
    </label>
  )
}

const SEVERITY: Record<Severity, { icon: typeof Info; color: string; label: string }> = {
  high: { icon: XCircle, color: 'var(--color-danger)', label: 'High' },
  warn: { icon: AlertTriangle, color: 'var(--color-warning)', label: 'Warning' },
  info: { icon: Info, color: 'var(--color-info)', label: 'Info' },
  ok: { icon: CheckCircle2, color: 'var(--color-success)', label: 'OK' },
}

export function SeverityRow({ severity, message }: { severity: Severity; message: string }) {
  const s = SEVERITY[severity]
  const Icon = s.icon
  return (
    <li className="flex items-start gap-2 text-xs">
      <Icon size={14} style={{ color: s.color }} className="shrink-0 mt-0.5" aria-hidden />
      <span className="font-semibold shrink-0 w-14" style={{ color: s.color }}>
        {s.label}
      </span>
      <span className="text-[var(--color-text-primary)]">{message}</span>
    </li>
  )
}

export function Loading({ what }: { what: string }) {
  return (
    <div className="flex items-center gap-2 p-6 text-xs text-[var(--color-text-secondary)]">
      <Loader2 size={14} className="animate-spin" /> Loading {what}…
    </div>
  )
}

export function ErrorState({ error }: { error: unknown }) {
  const msg = isNotPostgres(error)
    ? 'Score analytics require PostgreSQL (database.engine = "postgres").'
    : error instanceof Error
      ? error.message
      : String(error)
  return (
    <div className="flex items-start gap-2 p-4 text-xs text-[var(--color-danger)]">
      <XCircle size={14} className="shrink-0 mt-0.5" /> {msg}
    </div>
  )
}

export function Th({ children, className, align }: { children?: ReactNode; className?: string; align?: 'left' }) {
  return (
    <th
      className={clsx(
        'px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)] whitespace-nowrap',
        align === 'left' ? 'text-left' : 'text-right first:text-left',
        className,
      )}
    >
      {children}
    </th>
  )
}

export function Td({
  children,
  className,
  title,
  align,
}: {
  children?: ReactNode
  className?: string
  title?: string
  align?: 'left'
}) {
  return (
    <td
      title={title}
      className={clsx(
        'px-2 py-1 tabular-nums',
        align === 'left' ? 'text-left whitespace-normal' : 'text-right first:text-left whitespace-nowrap',
        className,
      )}
    >
      {children}
    </td>
  )
}

export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs text-[var(--color-text-primary)] [&_tbody_tr]:border-t [&_tbody_tr]:border-[var(--color-border-muted)] [&_tbody_tr:hover]:bg-[var(--color-bg-tertiary)]">
        {children}
      </table>
    </div>
  )
}
