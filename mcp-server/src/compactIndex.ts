#!/usr/bin/env node
/**
 * DEPRECATED entry point (old `is-be-mcp` key). Starts the vexlum MCP server under the old
 * name so existing configs keep working. Point configs at dist/vexlum.js instead.
 */
import { BE_MCP } from "./names.js";
import { runMcpServer } from "./vexlum.js";

console.error(`[deprecated] ${BE_MCP} (dist/compactIndex.js) -> vexlum. Update your MCP config to dist/vexlum.js.`);

runMcpServer(BE_MCP).catch((error) => {
    console.error("Fatal error running vexlum (is-be-mcp shim):", error);
    process.exit(1);
});
