/** MCP server + tool names. */

/** Single entry point (MCP server key and CLI command). */
export const VEXLUM = "vexlum";

export const SEARCH = "search";
export const RESOLVE = "resolve";
export const EXECUTE = "execute";

/** @deprecated old is-be-mcp key; use VEXLUM. */
export const BE_MCP = "is-be-mcp";
/** @deprecated optional SSE key; vexlum stdio covers it (WebUI /mcp/sse serves vexlum tools). */
export const BE_LIVE = "is-be-live";
/** @deprecated alias of EXECUTE. */
export const DISPATCH = "dispatch";
/** @deprecated alias of execute("system.status"). */
export const SSE_STATUS = "sse_status";
