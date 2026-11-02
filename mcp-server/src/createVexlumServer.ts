import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

import { DISPATCH, EXECUTE, RESOLVE, SEARCH, SSE_STATUS, VEXLUM } from "./names.js";
import { dispatchWithPlaywrightProxy, executeWithPlaywrightProxy } from "./utils/proxyDispatch.js";
import { invokePythonTool } from "./utils/pythonBridge.js";

export const VEXLUM_VERSION = "3.0.0";

export interface ToolDef {
    name: string;
    description: string;
    inputSchema: Record<string, unknown>;
    annotations?: Record<string, unknown>;
}

const SOURCE_ENUM = ["tool", "api", "db", "browser", "system"];
const TIER_ENUM = ["read", "write", "destructive"];

export const vexlumToolDefs: ToolDef[] = [
    {
        name: SEARCH,
        description:
            "Step 1 of 3. BM25 search over every Vexlum Scoring capability: Python tools, REST API (api.*), " +
            "PostgreSQL (db.*), browser automation (browser.*). Never executes anything.",
        inputSchema: {
            type: "object",
            properties: {
                query: { type: "string", description: "Natural-language intent or keywords. Empty lists actions." },
                limit: { type: "number", description: "Max results (default 10, max 50)." },
                source: { type: "string", enum: SOURCE_ENUM },
                category: { type: "string", description: "e.g. diagnostics, jobs, data, api.runs, db, browser" },
                tier: { type: "string", enum: TIER_ENUM },
                include_schemas: { type: "boolean", description: "Inline input_schema on each result." },
            },
        },
        annotations: { readOnlyHint: true, destructiveHint: false },
    },
    {
        name: RESOLVE,
        description:
            "Step 2 of 3. Full contract for one action: input_schema, tier, confirmation requirements, example " +
            "call. Accepts action_id, legacy tool name, REST operationId or 'METHOD /path'.",
        inputSchema: {
            type: "object",
            properties: { action_id: { type: "string" } },
            required: ["action_id"],
        },
        annotations: { readOnlyHint: true, destructiveHint: false },
    },
    {
        name: EXECUTE,
        description:
            "Step 3 of 3. Run an action. read: runs. write: confirmed=true. destructive: VEXLUM_ALLOW_ELEVATED=1 on " +
            "the server, dry_run=true first (returns confirm_token), then confirmed=true + confirm_token with the " +
            "same arguments.",
        inputSchema: {
            type: "object",
            properties: {
                action_id: { type: "string" },
                arguments: { type: "object", description: "Arguments matching resolve().input_schema." },
                dry_run: { type: "boolean" },
                confirmed: { type: "boolean" },
                confirm_token: { type: "string" },
                request_id: { type: "string" },
            },
            required: ["action_id"],
        },
        annotations: { readOnlyHint: false, destructiveHint: true },
    },
];

export const deprecatedToolDefs: ToolDef[] = [
    {
        name: DISPATCH,
        description: "DEPRECATED alias of execute (old is-be-mcp contract). Use search -> resolve -> execute.",
        inputSchema: {
            type: "object",
            properties: {
                action_id: { type: "string" },
                arguments: { type: "object" },
                dry_run: { type: "boolean" },
                confirmed: { type: "boolean" },
                request_id: { type: "string" },
                allow_deprecated: { type: "boolean" },
                expected_version: { type: "number" },
            },
            required: ["action_id"],
        },
    },
    {
        name: SSE_STATUS,
        description: "DEPRECATED. Use execute('system.status').",
        inputSchema: { type: "object", properties: {} },
    },
];

export function listToolDefs(includeDeprecated = process.env.VEXLUM_HIDE_DEPRECATED !== "1"): ToolDef[] {
    return includeDeprecated ? [...vexlumToolDefs, ...deprecatedToolDefs] : [...vexlumToolDefs];
}

function toolResult(payload: unknown, isError = false) {
    return {
        content: [{ type: "text" as const, text: JSON.stringify(payload, null, 2) }],
        ...(isError ? { isError: true } : {}),
    };
}

function str(v: unknown): string | undefined {
    return v === undefined || v === null || v === "" ? undefined : String(v);
}

/** Shared by the MCP server and the CLI. */
export async function callVexlumTool(name: string, args: Record<string, unknown>): Promise<Record<string, unknown>> {
    if (name === SEARCH) {
        return invokePythonTool("search", args);
    }
    if (name === RESOLVE) {
        return invokePythonTool("resolve", { action_id: String(args.action_id ?? "") });
    }
    if (name === "list") {
        return invokePythonTool("list", args);
    }
    if (name === EXECUTE || name === DISPATCH) {
        const actionId = String(args.action_id ?? "").trim();
        if (!actionId) {
            return { status: "error", code: "validation_error", message: "action_id is required" };
        }
        const opts = {
            dryRun: args.dry_run === true,
            confirmed: args.confirmed === true,
            confirmToken: str(args.confirm_token),
            requestId: str(args.request_id),
            allowDeprecated: args.allow_deprecated === true,
            expectedVersion: typeof args.expected_version === "number" ? args.expected_version : undefined,
        };
        const callArgs = (args.arguments ?? {}) as Record<string, unknown>;
        return name === EXECUTE
            ? executeWithPlaywrightProxy(actionId, callArgs, opts)
            : dispatchWithPlaywrightProxy(actionId, callArgs, opts);
    }
    if (name === SSE_STATUS) {
        return invokePythonTool("execute", { action_id: "system.status" });
    }
    return { status: "error", code: "unknown_tool", message: `Unknown vexlum tool: ${name}` };
}

export function createVexlumServer(serverName: string = VEXLUM): { server: Server; toolDefs: ToolDef[] } {
    const toolDefs = listToolDefs();
    const server = new Server({ name: serverName, version: VEXLUM_VERSION }, { capabilities: { tools: {} } });

    server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: toolDefs }));

    server.setRequestHandler(CallToolRequestSchema, async (request) => {
        const { name, arguments: toolArgs } = request.params;
        try {
            const result = await callVexlumTool(name, (toolArgs ?? {}) as Record<string, unknown>);
            return toolResult(result, result.status === "error");
        } catch (error: unknown) {
            const msg = error instanceof Error ? error.message : String(error);
            return toolResult({ status: "error", code: "host_error", message: `Error executing ${name}: ${msg}` }, true);
        }
    });

    return { server, toolDefs };
}
