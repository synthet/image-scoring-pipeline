#!/usr/bin/env node
/**
 * vexlum — single entry point for Vexlum Scoring (image-scoring-pipeline).
 *
 *   node dist/vexlum.js            stdio MCP server: search, resolve, execute
 *   node dist/vexlum.js search ... CLI (same worker, browser.* included)
 *
 * The Python core (modules/vexlum) runs in image-scoring-gpu-shell; this host adds the
 * Playwright child for browser.* actions. Contract: docs/technical/VEXLUM_MCP.md
 */
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { CliUsageError, formatResult, parseCliArgs, USAGE } from "./cli.js";
import { callVexlumTool, createVexlumServer, VEXLUM_VERSION } from "./createVexlumServer.js";
import { VEXLUM } from "./names.js";
import { shutdownPlaywrightClient } from "./utils/playwrightBridge.js";
import { shutdownPythonWorker, warmPythonWorker } from "./utils/pythonBridge.js";

export async function runMcpServer(serverName: string = VEXLUM): Promise<void> {
    const { server, toolDefs } = createVexlumServer(serverName);
    const transport = new StdioServerTransport();
    await server.connect(transport);
    warmPythonWorker();
    console.error(`${serverName} MCP v${VEXLUM_VERSION} — tools: ${toolDefs.map((t) => t.name).join(", ")}`);
}

async function runCli(argv: string[]): Promise<number> {
    let cmd;
    try {
        cmd = parseCliArgs(argv);
    } catch (err) {
        if (err instanceof CliUsageError) {
            process.stderr.write(`vexlum: ${err.message}\n\n${USAGE}`);
            return 2;
        }
        throw err;
    }
    if (cmd.command === "help") {
        process.stdout.write(USAGE);
        return 0;
    }
    if (cmd.command === "mcp") {
        await runMcpServer();
        return -1; // keep running
    }
    try {
        const result = await callVexlumTool(cmd.tool ?? "", cmd.args);
        process.stdout.write(formatResult(cmd, result) + "\n");
        return result.status === "error" ? 1 : 0;
    } finally {
        shutdownPythonWorker();
        await shutdownPlaywrightClient().catch(() => undefined);
    }
}

const isMain = process.argv[1] && /vexlum(\.js)?$/.test(process.argv[1].replace(/\\/g, "/"));
if (isMain) {
    runCli(process.argv.slice(2))
        .then((code) => {
            if (code >= 0) process.exit(code);
        })
        .catch((error) => {
            console.error("vexlum fatal error:", error);
            process.exit(1);
        });
}
