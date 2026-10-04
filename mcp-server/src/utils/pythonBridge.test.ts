import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { resolveWorkerLaunch } from "./pythonBridge.js";

/**
 * Unit tests for request-id response routing (logic mirrored from pythonBridge).
 * Full worker I/O is covered by MCP protocol smoke tests.
 */

function stripRequestId(payload: Record<string, unknown>): Record<string, unknown> {
    if (!("_request_id" in payload)) {
        return payload;
    }
    const { _request_id: _ignored, ...rest } = payload;
    return rest;
}

describe("pythonBridge response routing", () => {
    it("stripRequestId removes _request_id", () => {
        const out = stripRequestId({
            _request_id: "abc",
            ok: true,
            server: "is-be-live",
        });
        assert.deepEqual(out, { ok: true, server: "is-be-live" });
        assert.equal("_request_id" in out, false);
    });

    it("stripRequestId passes through payloads without id", () => {
        const out = stripRequestId({ status: "success" });
        assert.deepEqual(out, { status: "success" });
    });

    it("windows default starts the worker in gpu-shell", () => {
        const launch = resolveWorkerLaunch({}, "win32");
        assert.equal(launch.mode, "gpu-shell");
        assert.equal(launch.command, "docker");
        assert.equal(launch.container, "image-scoring-gpu-shell");
        assert.ok(launch.args.includes("python"));
        assert.ok(launch.args.includes("/app/scripts/mcp/compact_worker.py"));
    });

    it("IS_BE_MCP_USE_WSL=1 keeps the Ubuntu venv worker", () => {
        const launch = resolveWorkerLaunch({ IS_BE_MCP_USE_WSL: "1" }, "win32");
        assert.equal(launch.mode, "wsl");
        assert.equal(launch.command, "wsl");
        assert.ok(launch.args.some((arg) => arg.includes("~/.venvs/tf/bin/activate")));
    });
});
