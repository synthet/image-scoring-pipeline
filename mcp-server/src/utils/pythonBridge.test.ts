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

    it("windows default starts the vexlum worker in gpu-shell", () => {
        const launch = resolveWorkerLaunch({}, "win32");
        assert.equal(launch.mode, "gpu-shell");
        assert.equal(launch.command, "docker");
        assert.equal(launch.container, "image-scoring-gpu-shell");
        const tail = launch.args.slice(-4);
        assert.deepEqual(tail, ["python", "-m", "modules.vexlum", "worker"]);
    });

    it("forwards vexlum policy env into gpu-shell", () => {
        const launch = resolveWorkerLaunch({ VEXLUM_ALLOW_ELEVATED: "1", UNRELATED: "x" }, "win32");
        assert.ok(launch.args.includes("VEXLUM_ALLOW_ELEVATED=1"));
        assert.ok(!launch.args.some((a) => a.startsWith("UNRELATED")));
    });

    it("VEXLUM_GPU_SHELL overrides the container; IS_BE_MCP_GPU_SHELL still honoured", () => {
        assert.equal(resolveWorkerLaunch({ VEXLUM_GPU_SHELL: "c1" }, "win32").container, "c1");
        assert.equal(resolveWorkerLaunch({ IS_BE_MCP_GPU_SHELL: "c2" }, "win32").container, "c2");
    });

    it("IS_BE_MCP_USE_WSL=1 keeps the Ubuntu venv worker", () => {
        const launch = resolveWorkerLaunch({ IS_BE_MCP_USE_WSL: "1" }, "win32");
        assert.equal(launch.mode, "wsl");
        assert.equal(launch.command, "wsl");
        assert.ok(launch.args.some((arg) => arg.includes("~/.venvs/tf/bin/activate")));
        assert.ok(launch.args.some((arg) => arg.includes("python -m modules.vexlum worker")));
    });
});
