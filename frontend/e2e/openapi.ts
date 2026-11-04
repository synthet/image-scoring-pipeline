/**
 * openapi.json (repo root) as the contract for faked responses.
 *
 * - `operationFor(method, path)` finds the documented operation for a concrete request path.
 * - `validateResponse(...)` checks a fixture body against the documented 2xx JSON schema when
 *   one exists. 99 of 163 operations document no response schema; for those the check is
 *   skipped and the fixture shape must come from the router code (see the test catalog).
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import Ajv2020, { type ValidateFunction } from 'ajv/dist/2020.js'

const here = path.dirname(fileURLToPath(import.meta.url))
export const OPENAPI_PATH = path.resolve(here, '../../openapi.json')

type Json = Record<string, unknown>
interface Operation {
  method: string
  template: string
  regex: RegExp
  op: Json
}

const spec = JSON.parse(readFileSync(OPENAPI_PATH, 'utf8')) as Json
const METHODS = ['get', 'post', 'put', 'patch', 'delete']

function templateRegex(template: string): RegExp {
  const escaped = template
    .split(/(\{[^}]+\})/)
    .map((part) => (part.startsWith('{') ? '[^/]+' : part.replace(/[.*+?^$()|[\]\\]/g, '\\$&')))
    .join('')
  return new RegExp(`^${escaped}$`)
}

const operations: Operation[] = []
for (const [template, item] of Object.entries((spec.paths ?? {}) as Record<string, Json>)) {
  for (const method of METHODS) {
    const op = item[method] as Json | undefined
    if (op) operations.push({ method: method.toUpperCase(), template, regex: templateRegex(template), op })
  }
}
// Literal segments must win over parameters (/api/images/by-uuid/x before /api/images/{image_id}).
const paramCount = (o: Operation) => o.template.match(/\{/g)?.length ?? 0
operations.sort((a, b) => paramCount(a) - paramCount(b))

export function operationFor(method: string, pathname: string): Operation | undefined {
  const m = method.toUpperCase()
  return operations.find((o) => o.method === m && o.regex.test(pathname))
}

export function hasTemplate(method: string, template: string): boolean {
  const m = method.toUpperCase()
  return operations.some((o) => o.method === m && o.template === template)
}

export function allOperations(): ReadonlyArray<Pick<Operation, 'method' | 'template'>> {
  return operations.map(({ method, template }) => ({ method, template }))
}

const ajv = new Ajv2020({ strict: false, validateFormats: false, allErrors: true })
ajv.addSchema({ $id: 'oas', components: spec.components ?? {} })
const compiled = new Map<string, ValidateFunction | null>()

function rewriteRefs(node: unknown): unknown {
  if (Array.isArray(node)) return node.map(rewriteRefs)
  if (node && typeof node === 'object') {
    const out: Json = {}
    for (const [k, v] of Object.entries(node as Json)) {
      out[k] = k === '$ref' && typeof v === 'string' && v.startsWith('#/') ? `oas${v}` : rewriteRefs(v)
    }
    return out
  }
  return node
}

function responseSchema(op: Json, status: number): Json | undefined {
  const responses = (op.responses ?? {}) as Record<string, Json>
  const entry = responses[String(status)] ?? (status >= 200 && status < 300 ? responses['2XX'] : undefined)
  const schema = ((entry?.content as Json | undefined)?.['application/json'] as Json | undefined)?.schema as
    | Json
    | undefined
  if (!schema || Object.keys(schema).length === 0) return undefined
  return schema
}

/** Returns error strings; an empty list means valid or undocumented. */
export function validateResponse(method: string, template: string, status: number, body: unknown): string[] {
  const key = `${method.toUpperCase()} ${template} ${status}`
  if (!compiled.has(key)) {
    const op = operations.find((o) => o.method === method.toUpperCase() && o.template === template)
    const schema = op ? responseSchema(op.op, status) : undefined
    compiled.set(key, schema ? ajv.compile(rewriteRefs(schema) as Json) : null)
  }
  const validate = compiled.get(key)
  if (!validate || validate(body)) return []
  return (validate.errors ?? []).map((e) => `${key}: ${e.instancePath || '(root)'} ${e.message}`)
}

export function isDocumentedResponse(method: string, template: string, status: number): boolean {
  const op = operations.find((o) => o.method === method.toUpperCase() && o.template === template)
  return Boolean(op && responseSchema(op.op, status))
}
