import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { CliUsageError, formatResult, parseCliArgs } from "./cli.js";
import { listToolDefs } from "./createVexlumServer.js";

describe("vexlum CLI parser", () => {
    it("defaults to the MCP server", () => {
        assert.equal(parseCliArgs([]).command, "mcp");
        assert.equal(parseCliArgs(["mcp"]).command, "mcp");
    });

    it("parses search with filters", () => {
        const cmd = parseCliArgs(["search", "why", "did", "scoring", "fail", "--source", "tool", "--limit", "3"]);
        assert.equal(cmd.tool, "search");
        assert.deepEqual(cmd.args, { query: "why did scoring fail", source: "tool", limit: 3 });
    });

    it("parses exec with JSON args, dry run, confirm and token", () => {
        const cmd = parseCliArgs([
            "exec", "db.execute", "--args", '{"query":"UPDATE x SET y=1"}', "--dry-run", "--json",
        ]);
        assert.equal(cmd.tool, "execute");
        assert.equal(cmd.json, true);
        assert.deepEqual(cmd.args, { action_id: "db.execute", arguments: { query: "UPDATE x SET y=1" }, dry_run: true });

        const confirm = parseCliArgs(["exec", "db.execute", "--confirm", "--token", "123.abc"]);
        assert.deepEqual(confirm.args, {
            action_id: "db.execute",
            arguments: {},
            confirmed: true,
            confirm_token: "123.abc",
        });
    });

    it("maps status to execute(system.status)", () => {
        const cmd = parseCliArgs(["status"]);
        assert.equal(cmd.tool, "execute");
        assert.deepEqual(cmd.args, { action_id: "system.status" });
    });

    it("rejects bad input", () => {
        assert.throws(() => parseCliArgs(["exec"]), CliUsageError);
        assert.throws(() => parseCliArgs(["exec", "x", "--args", "[1]"]), CliUsageError);
        assert.throws(() => parseCliArgs(["exec", "x", "--args", "{bad"]), CliUsageError);
        assert.throws(() => parseCliArgs(["search", "--bogus"]), CliUsageError);
        assert.throws(() => parseCliArgs(["frobnicate"]), CliUsageError);
    });

    it("formats errors and search rows", () => {
        const err = formatResult(parseCliArgs(["status"]), { status: "error", code: "x", message: "boom" });
        assert.match(err, /error \[x\]: boom/);
        const rows = formatResult(parseCliArgs(["search", "q"]), {
            results: [{ action_id: "db.query", tier: "read", confidence: 1, title: "SQL", required_args: ["query"] }],
        });
        assert.match(rows, /db\.query/);
        assert.match(rows, /\[req: query\]/);
    });
});

describe("vexlum MCP tool list", () => {
    it("lists search, resolve, execute first; deprecated aliases optional", () => {
        assert.deepEqual(
            listToolDefs(false).map((t) => t.name),
            ["search", "resolve", "execute"],
        );
        assert.deepEqual(
            listToolDefs(true).map((t) => t.name),
            ["search", "resolve", "execute", "dispatch", "sse_status"],
        );
    });
});
