import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { BE_LIVE, BE_MCP, DISPATCH, EXECUTE, RESOLVE, SEARCH, SSE_STATUS, VEXLUM } from "./names.js";

describe("vexlum names", () => {
    it("exports the single entry point and its three tools", () => {
        assert.equal(VEXLUM, "vexlum");
        assert.equal(SEARCH, "search");
        assert.equal(RESOLVE, "resolve");
        assert.equal(EXECUTE, "execute");
    });

    it("keeps deprecated is-be-* names for shims", () => {
        assert.equal(BE_MCP, "is-be-mcp");
        assert.equal(BE_LIVE, "is-be-live");
        assert.equal(DISPATCH, "dispatch");
        assert.equal(SSE_STATUS, "sse_status");
    });
});
