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

  /**
   * Fake an endpoint the SPA calls but openapi.json does not document. Requires the issue that
   * tracks the gap (see src/test/contract.test.ts KNOWN_UNDOCUMENTED); recorded in `undocumented`.
   */
  onUndocumented(method: string, template: string, issue: string, reply: ApiHandler | ApiReply): this {
    const m = method.toUpperCase()
    if (hasTemplate(m, template)) throw new Error(`${m} ${template} is documented; use on()`)
    if (!/^#\d+$/.test(issue)) throw new Error(`onUndocumented needs a tracking issue like '#770', got '${issue}'`)
    const { regex, paramNames } = compileTemplate(template)
    const handler: ApiHandler = typeof reply === 'function' ? reply : () => reply
    this.handlers.push({ method: m, template, regex, paramNames, handler })
    this.undocumented.add(`${m} ${template} (${issue})`)
    return this
  }

  readonly undocumented = new Set<string>()

  /**
   * While set, every request (registered or not) gets this reply instead — the backend is down.
   * Requests are still logged; none count as unexpected. `null` restores normal handling.
   */
  outage: ApiReply | null = null

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
    await page.route(/\/source-image(?:[/?]|$)/, handle)
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
    if (this.outage) {
      const o = this.outage
      this.requests.push({ method, path: url.pathname + url.search, template: documented, status: o.abort ? 0 : (o.status ?? 503), handled: false })
      if (o.delayMs) await new Promise((r) => setTimeout(r, o.delayMs))
      if (o.abort) await route.abort('connectionrefused').catch(() => undefined)
      else
        await route
          .fulfill({ status: o.status ?? 503, contentType: 'application/json', body: JSON.stringify(o.json ?? { detail: 'backend down (test)' }) })
          .catch(() => undefined)
      return
    }
    // A documented path resolves to exactly one template (literal segments win, so
    // /api/jobs/recent never reaches a /api/jobs/{job_id} handler); undocumented paths match by regex.
    const match = [...this.handlers]
      .reverse()
      .map((h) => ({
        h,
        m: h.method === method && (documented === null || h.template === documented) ? h.regex.exec(url.pathname) : null,
      }))
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

/** Closed local port: a WebSocket to it fails the handshake for real (no network traffic). */
const REFUSED_WS_URL = 'ws://127.0.0.1:9/ws/updates'

export class WsFake {
  connections = 0
  readonly clientMessages: string[] = []
  private open: WebSocketRoute[] = []
  private page: Page | null = null

  async attach(page: Page, origin: string): Promise<void> {
    this.page = page
    const wsOrigin = origin.replace(/^http/, 'ws').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    // Register the route first: it installs Playwright's WebSocket mock, which the patch below
    // must wrap (a patch installed earlier would be replaced by the mock).
    await page.routeWebSocket(new RegExp(`^${wsOrigin}/ws/updates$`), (ws) => this.onConnect(ws))
    // Playwright cannot refuse a routed handshake (a mocked socket always opens), so refusal is
    // done in the page: while window.__wsRefuse is true, new /ws/updates sockets are pointed at a
    // closed local port and fail exactly like a backend that is down.
    await page.addInitScript((refusedUrl) => {
      const w = window as unknown as { __wsRefuse?: boolean; WebSocket: typeof WebSocket }
      const Original = w.WebSocket
      w.WebSocket = class extends Original {
        constructor(url: string | URL, protocols?: string | string[]) {
          super(w.__wsRefuse && String(url).endsWith('/ws/updates') ? refusedUrl : url, protocols)
        }
      }
    }, REFUSED_WS_URL)
  }

  /**
   * Refuse (true) or accept (false) new connections. Call before page.goto to refuse from the
   * first visit; call later to take the backend down or bring it back.
   */
  async setRefuse(refuse: boolean): Promise<void> {
    const page = this.page!
    await page.addInitScript((v) => ((window as unknown as { __wsRefuse?: boolean }).__wsRefuse = v), refuse)
    await page.evaluate((v) => ((window as unknown as { __wsRefuse?: boolean }).__wsRefuse = v), refuse).catch(() => undefined)
  }

  private onConnect(ws: WebSocketRoute): void {
    this.connections += 1
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

  ws: async ({ page, baseURL }, use) => {
    const ws = new WsFake()
    await ws.attach(page, new URL(baseURL ?? 'http://127.0.0.1').origin)
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
