/** @deprecated use createVexlumServer (vexlum). Kept for imports from older scripts. */
import { BE_MCP } from "./names.js";
import { createVexlumServer } from "./createVexlumServer.js";

export function createBackendCompactMcpServer() {
    return createVexlumServer(BE_MCP);
}
