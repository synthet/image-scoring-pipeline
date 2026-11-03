/**
 * Test fixtures for the hermetic tier (Tier 1).
 *
 * - `api`  — fakes every backend HTTP call. Handlers are keyed by the openapi.json path template,
 *            so a test cannot fake an endpoint the contract does not have. JSON replies are
 *            validated against the documented response schema. A request with no handler gets a
 *            404 and fails the test unless it was declared with `allowUnhandled`.
 * - `ws`   — fakes /ws/updates; tests push backend-shaped messages with `ws.send(...)`.
 * - `allowErrors` — page errors and console errors fail the test unless a test lists them here
 *            with a reason. Never list a real error to make a test pass; find the cause.
 * - Any request that leaves the preview origin is aborted and fails the test, so nothing can
 *   reach the developer's live instance on port 7860.
 */
import { test as base, expect, type Page, type Route, type WebSocketRoute } from '@playwright/test'
import { hasTemplate, operationFor, validateResponse } from './openapi'
import { installBaseline } from './builders'

export interface ApiRequest {
  method: string
  path: string
  template: string
  params: Record<string, string>
  query: URLSearchParams
  body: unknown
}

export interface ApiReply {
  status?: number
  json?: unknown
  body?: string | Buffer
  contentType?: string
  delayMs?: number
  /** Simulate a network failure instead of replying. */
  abort?: boolean
}

export type ApiHandler = (req: ApiRequest) => ApiReply | Promise<ApiReply>

interface Registered {
  method: string
  template: string
  regex: RegExp
  paramNames: string[]
  handler: ApiHandler
}

export interface LoggedRequest {
  method: string
  path: string
  template: string | null
  status: number
  handled: boolean
}

function compileTemplate(template: string): { regex: RegExp; paramNames: string[] } {
  const paramNames: string[] = []
  const pattern = template
    .split(/(\{[^}]+\})/)
    .map((part) => {
      if (part.startsWith('{')) {
        paramNames.push(part.slice(1, -1))
        return '([^/]+)'
      }
      return part.replace(/[.*+?^$()|[\]\\]/g, '\\$&')
    })
    .join('')
  return { regex: new RegExp(`^${pattern}$`), paramNames }
}

export class ApiFake {
  private handlers: Registered[] = []
  private allowed = new Set<string>()
  readonly requests: LoggedRequest[] = []
  readonly unexpected: string[] = []
  readonly schemaErrors: string[] = []

  /** Register a handler. Later registrations win, so tests can override the baseline. */
  on(method: string, template: string, reply: ApiHandler | ApiReply): this {
    const m = method.toUpperCase()
    if (!hasTemplate(m, template)) {
      throw new Error(`${m} ${template} is not in openapi.json; fake only documented endpoints`)
    }
    const { regex, paramNames } = compileTemplate(template)
    const handler: ApiHandler = typeof reply === 'function' ? reply : () => reply
    this.handlers.push({ method: m, template, regex, paramNames, handler })
    return this
  }

  /** Let a documented endpoint go unanswered (404) without failing the test. */
  allowUnhandled(method: string, template: string): this {
    this.allowed.add(`${method.toUpperCase()} ${template}`)
    return this
  }

  calls(method: string, template: string): LoggedRequest[] {
    const m = method.toUpperCase()
    return this.requests.filter((r) => r.method === m && r.template === template)
  }

  async attach(page: Page, origin: string): Promise<void> {
    const handle = (route: Route) => this.handle(route, origin)
    await page.route('**/api/**', handle)
    await page.route('**/public/api/**', handle)
    await page.route('**/source-image/**', handle)
  }

  private async handle(route: Route, origin: string): Promise<void> {
    const request = route.request()
    const url = new URL(request.url())
    if (url.origin !== origin) {
      await route.fallback() // the origin guard records and aborts it
      return
    }
    const method = request.method().toUpperCase()
    const documented = operationFor(method, url.pathname)?.template ?? null
    const match = [...this.handlers]
      .reverse()
      .map((h) => ({ h, m: h.method === method ? h.regex.exec(url.pathname) : null }))
      .find((x) => x.m)

    if (!match) {
      const key = `${method} ${documented ?? url.pathname}`
      if (!(documented && this.allowed.has(`${method} ${documented}`))) this.unexpected.push(key)
      this.requests.push({ method, path: url.pathname + url.search, template: documented, status: 404, handled: false })
      await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'not faked' }) })
      return
    }

    const { h, m } = match
    const params = Object.fromEntries(h.paramNames.map((n, i) => [n, decodeURIComponent(m![i + 1])]))
    let body: unknown = undefined
    const raw = request.postData()
    if (raw) {
      try {
        body = JSON.parse(raw)
      } catch {
        body = raw
      }
    }
    const reply = await h.handler({ method, path: url.pathname, template: h.template, params, query: url.searchParams, body })
    if (reply.delayMs) await new Promise((r) => setTimeout(r, reply.delayMs))
    if (reply.abort) {
      this.requests.push({ method, path: url.pathname + url.search, template: h.template, status: 0, handled: true })
      await route.abort('connectionrefused')
      return
    }
    const status = reply.status ?? 200
    if (reply.json !== undefined && status >= 200 && status < 300) {
      this.schemaErrors.push(...validateResponse(method, h.template, status, reply.json))
    }
    this.requests.push({ method, path: url.pathname + url.search, template: h.template, status, handled: true })
    await route.fulfill({
      status,
      contentType: reply.contentType ?? (reply.json !== undefined ? 'application/json' : 'text/plain'),
      body: reply.json !== undefined ? JSON.stringify(reply.json) : reply.body ?? '',
    })
  }
}

export type WsMode = 'accept' | 'refuse'

export class WsFake {
  mode: WsMode = 'accept'
  connections = 0
  readonly clientMessages: string[] = []
  private open: WebSocketRoute[] = []

  async attach(page: Page): Promise<void> {
    await page.routeWebSocket(/\/ws\/updates$/, (ws) => this.onConnect(ws))
  }

  private onConnect(ws: WebSocketRoute): void {
    this.connections += 1
    if (this.mode === 'refuse') {
      void ws.close({ code: 1011, reason: 'refused by test' })
      return
    }
    // No connectToServer(): the socket is fully mocked and opens immediately.
    this.open.push(ws)
    ws.onMessage((m) => this.clientMessages.push(String(m)))
    ws.onClose(() => {
      this.open = this.open.filter((s) => s !== ws)
    })
  }

  get openCount(): number {
    return this.open.length
  }

  /** Send one backend-shaped message (see modules/events.py) to every open socket. */
  send(message: Record<string, unknown>): void {
    const text = JSON.stringify(message)
    for (const ws of this.open) ws.send(text)
  }

  async closeAll(code = 1001): Promise<void> {
    const sockets = [...this.open]
    this.open = []
    await Promise.all(sockets.map((ws) => ws.close({ code, reason: 'closed by test' })))
  }

  async waitForOpen(count = 1): Promise<void> {
    await expect.poll(() => this.openCount, { message: 'WebSocket connections' }).toBeGreaterThanOrEqual(count)
  }
}

export interface AllowedError {
  pattern: RegExp
  reason: string
}

interface Fixtures {
  api: ApiFake
  ws: WsFake
  allowErrors: AllowedError[]
  /** Requests that tried to leave the preview origin (always a failure). */
  externalRequests: string[]
  /** Auto fixture: teardown checks shared by every test. */
  _checks: void
}

const pageErrors = new WeakMap<Page, string[]>()

export const test = base.extend<Fixtures>({
  allowErrors: async ({}, use) => {
    await use([])
  },

  externalRequests: async ({ page, baseURL }, use) => {
    const blocked: string[] = []
    const origin = new URL(baseURL ?? 'http://127.0.0.1').origin
    await page.route('**/*', async (route) => {
      const url = route.request().url()
      if (url.startsWith('data:') || url.startsWith('blob:') || new URL(url).origin === origin) {
        await route.fallback()
        return
      }
      blocked.push(url)
      await route.abort('blockedbyclient')
    })
    await use(blocked)
  },

  api: async ({ page, baseURL, externalRequests }, use) => {
    void externalRequests // registered first, so the api routes below take precedence
    const api = new ApiFake()
    installBaseline(api)
    await api.attach(page, new URL(baseURL ?? 'http://127.0.0.1').origin)
    await use(api)
  },

  ws: async ({ page }, use) => {
    const ws = new WsFake()
    await ws.attach(page)
    await use(ws)
  },

  page: async ({ page }, use) => {
    const errors: string[] = []
    pageErrors.set(page, errors)
    page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`))
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(`console.error: ${msg.text()}`)
    })
    await use(page)
  },

  _checks: [
    async ({ page, api, ws, allowErrors, externalRequests }, use) => {
      void ws // set up for every test so a stray connection is always faked
      await use()
      expect(externalRequests, 'requests that left the preview origin').toEqual([])
      expect(api.unexpected, 'unfaked /api requests (fake them or allowUnhandled)').toEqual([])
      expect(api.schemaErrors, 'fixture bodies that do not match openapi.json').toEqual([])
      const unexplained = (pageErrors.get(page) ?? []).filter((e) => !allowErrors.some((a) => a.pattern.test(e)))
      expect(unexplained, 'page or console errors (list known ones in allowErrors with a reason)').toEqual([])
    },
    { auto: true },
  ],
})

export { expect }
