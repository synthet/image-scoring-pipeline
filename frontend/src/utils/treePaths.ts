/** Normalize for tree path comparison (slashes, trim, case-insensitive). */
export function normalizeTreePath(p: string): string {
  return p
    .trim()
    .replace(/\\/g, '/')
    .replace(/\/+$/, '')
    .toLowerCase()
}

/** True if `target` is this folder or a descendant (path segment boundary). */
export function pathTargetsRevealFolder(nodePath: string, targets: string[] | null | undefined): boolean {
  if (!targets?.length) return false
  const np = normalizeTreePath(nodePath)
  return targets.some((t) => {
    const tp = normalizeTreePath(t)
    return tp === np || tp.startsWith(np + '/')
  })
}
