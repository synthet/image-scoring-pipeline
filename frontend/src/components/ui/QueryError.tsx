import { Button } from '@/components/ui/button'

interface QueryErrorProps {
  message: string
  onRetry: () => void
  className?: string
}

/** A failed load: says so and offers Retry, so a backend failure never reads as "not found" or as no data. */
export function QueryError({ message, onRetry, className }: QueryErrorProps) {
  return (
    <div role="alert" className={className}>
      <p className="text-sm text-[var(--color-danger)]">{message} Ensure the backend is running.</p>
      <Button variant="secondary" size="sm" onClick={onRetry} className="mt-2">
        Retry
      </Button>
    </div>
  )
}
