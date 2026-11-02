import { randomUUID } from "node:crypto";
import { spawn, spawnSync, type ChildProcessWithoutNullStreams } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const PROJECT_ROOT = path.resolve(__dirname, "..", "..", "..");

/** Python core entry: `python -m modules.vexlum worker` (JSONL over stdio). */
const WORKER_MODULE_FILE = path.join(PROJECT_ROOT, "modules", "vexlum", "__main__.py");
const DEFAULT_VENV = "~/.venvs/tf/bin/activate";
const DEFAULT_GPU_SHELL = "image-scoring-gpu-shell";

export interface WorkerLaunch {
    command: string;
    args: string[];
    mode: "custom" | "wsl" | "bash" | "gpu-shell";
    container?: string;
}

interface PendingRequest {
    tool: string;
    resolve: (value: Record<string, unknown>) => void;
    reject: (reason: Error) => void;
    timer: ReturnType<typeof setTimeout>;
}

let worker: ChildProcessWithoutNullStreams | null = null;
const pendingById = new Map<string, PendingRequest>();
let buffer = "";
let writeChain: Promise<void> = Promise.resolve();

function windowsPathToWsl(winPath: string): string {
    const normalized = path.resolve(winPath).replace(/\\/g, "/");
    const match = /^([A-Za-z]):\/(.*)$/.exec(normalized);
    if (!match) return normalized;
    const drive = match[1].toLowerCase();
    return `/mnt/${drive}/${match[2]}`;
}

/** VEXLUM_<name>, falling back to the deprecated IS_BE_MCP_<name>. */
function envOpt(env: NodeJS.ProcessEnv, name: string): string | undefined {
    const v = env[`VEXLUM_${name}`]?.trim() || env[`IS_BE_MCP_${name}`]?.trim();
    return v || undefined;
}

/** How the Node host starts the Python vexlum worker. */
export function resolveWorkerLaunch(
    env: NodeJS.ProcessEnv = process.env,
    platform: NodeJS.Platform = process.platform,
): WorkerLaunch {
    const custom = envOpt(env, "WORKER_SHELL");
    if (custom) {
        return { command: "bash", args: ["-lc", custom], mode: "custom" };
    }

    const useWsl = platform === "win32" && envOpt(env, "USE_WSL") === "1";
    if (platform === "win32" && !useWsl) {
        const container = envOpt(env, "GPU_SHELL") || DEFAULT_GPU_SHELL;
        return {
            command: "docker",
            container,
            args: [
                "exec",
                "-i",
                "-w",
                "/app",
                "-e",
                "PYTHONPATH=/app",
                "-e",
                "ENABLE_MCP_SERVER=1",
                ...passthroughEnvArgs(env),
                container,
                "python",
                "-m",
                "modules.vexlum",
                "worker",
            ],
            mode: "gpu-shell",
        };
    }

    const venvActivate = envOpt(env, "VENV_ACTIVATE") || DEFAULT_VENV;
    const root = useWsl ? windowsPathToWsl(PROJECT_ROOT) : PROJECT_ROOT;
    const inner = `cd '${root.replace(/'/g, `'\\''`)}' && export ENABLE_MCP_SERVER=1 && export PYTHONPATH=. && source ${venvActivate} && python -m modules.vexlum worker`;

    if (useWsl) {
        return { command: "wsl", args: ["bash", "-lc", inner], mode: "wsl" };
    }
    return { command: "bash", args: ["-lc", inner], mode: "bash" };
}

/** Policy env the Python side reads; forwarded into gpu-shell so the host config controls it. */
const PASSTHROUGH_ENV = [
    "VEXLUM_ALLOW_ELEVATED",
    "VEXLUM_API_URL",
    "VEXLUM_MAX_RESPONSE_BYTES",
    "VEXLUM_TOKEN_SECRET",
    "MCP_PLAYWRIGHT_ENABLED",
];

function passthroughEnvArgs(env: NodeJS.ProcessEnv): string[] {
    const out: string[] = [];
    for (const name of PASSTHROUGH_ENV) {
        const v = env[name];
        if (v !== undefined && v !== "") {
            out.push("-e", `${name}=${v}`);
        }
    }
    return out;
}

function workerShellCommand(): WorkerLaunch {
    return resolveWorkerLaunch();
}

function ensureGpuShell(container: string): void {
    const started = spawnSync("docker", ["start", container], {
        windowsHide: true,
        stdio: "ignore",
    });
    if (started.status !== 0) {
        throw new Error(
            `could not start ${container} for the MCP Python worker. Run: docker compose --profile gpu-shell up -d db gpu-shell`,
        );
    }
}

function stripRequestId(payload: Record<string, unknown>): Record<string, unknown> {
    if (!("_request_id" in payload)) {
        return payload;
    }
    const { _request_id: _ignored, ...rest } = payload;
    return rest;
}

function rejectAllPending(error: Error): void {
    for (const entry of pendingById.values()) {
        clearTimeout(entry.timer);
        entry.reject(error);
    }
    pendingById.clear();
}

function resolvePending(id: string, payload: Record<string, unknown>): void {
    const entry = pendingById.get(id);
    if (!entry) {
        return;
    }
    pendingById.delete(id);
    clearTimeout(entry.timer);
    entry.resolve(stripRequestId(payload));
}

function rejectPending(id: string, error: Error): void {
    const entry = pendingById.get(id);
    if (!entry) {
        return;
    }
    pendingById.delete(id);
    clearTimeout(entry.timer);
    entry.reject(error);
}

function flushBuffer(): void {
    while (true) {
        const newline = buffer.indexOf("\n");
        if (newline < 0) {
            break;
        }
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        if (!line) {
            continue;
        }

        let parsed: Record<string, unknown>;
        try {
            parsed = JSON.parse(line) as Record<string, unknown>;
        } catch (err) {
            rejectAllPending(err instanceof Error ? err : new Error(String(err)));
            return;
        }

        const reqId = parsed._request_id;
        if (typeof reqId !== "string" || !reqId) {
            rejectAllPending(new Error("Python worker response missing _request_id"));
            return;
        }
        resolvePending(reqId, parsed);
    }
}

function enqueueWrite(proc: ChildProcessWithoutNullStreams, payload: string): Promise<void> {
    writeChain = writeChain.then(
        () =>
            new Promise<void>((resolve, reject) => {
                proc.stdin.write(payload, (err) => {
                    if (err) {
                        reject(err);
                    } else {
                        resolve();
                    }
                });
            }),
    );
    return writeChain;
}

function ensureWorker(): ChildProcessWithoutNullStreams {
    if (worker && !worker.killed) {
        return worker;
    }

    if (!fs.existsSync(WORKER_MODULE_FILE)) {
        throw new Error(`vexlum Python core not found: ${WORKER_MODULE_FILE}`);
    }

    buffer = "";
    writeChain = Promise.resolve();

    const launch = workerShellCommand();
    if (launch.mode === "gpu-shell") {
        ensureGpuShell(launch.container || DEFAULT_GPU_SHELL);
    }
    const { command, args } = launch;
    worker = spawn(command, args, {
        stdio: ["pipe", "pipe", "pipe"],
        windowsHide: true,
    });

    worker.stdout.setEncoding("utf8");
    worker.stdout.on("data", (chunk: string) => {
        buffer += chunk;
        flushBuffer();
    });

    worker.stderr.on("data", (chunk: Buffer | string) => {
        process.stderr.write(String(chunk));
    });

    worker.on("error", (err) => {
        rejectAllPending(err);
        worker = null;
    });

    worker.on("exit", (code, signal) => {
        worker = null;
        rejectAllPending(
            new Error(`vexlum Python worker exited (code=${code ?? "null"}, signal=${signal ?? "null"})`),
        );
    });

    return worker;
}

export async function invokePythonTool(
    tool: string,
    args: Record<string, unknown> = {},
    timeoutMs = 120_000,
): Promise<Record<string, unknown>> {
    const proc = ensureWorker();
    const id = randomUUID();

    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
            rejectPending(id, new Error(`vexlum tool '${tool}' timed out after ${timeoutMs}ms`));
        }, timeoutMs);

        pendingById.set(id, { tool, resolve, reject, timer });

        const payload = JSON.stringify({ id, tool, args }) + "\n";
        enqueueWrite(proc, payload).catch((err) => {
            rejectPending(id, err instanceof Error ? err : new Error(String(err)));
        });
    });
}

/** Start the worker early (MCP server startup); it warms the catalog + tool stack itself. */
export function warmPythonWorker(): void {
    if (process.env.VEXLUM_WARM === "0") {
        return;
    }
    try {
        ensureWorker();
    } catch (err) {
        console.error(`vexlum: worker warm-up skipped: ${err instanceof Error ? err.message : String(err)}`);
    }
}

export function shutdownPythonWorker(): void {
    if (worker && !worker.killed) {
        try {
            void enqueueWrite(worker, "__shutdown__\n");
        } catch {
            worker.kill();
        }
        worker = null;
    }
    rejectAllPending(new Error("vexlum Python worker shut down"));
}

process.on("exit", () => shutdownPythonWorker());

/** Test helper: number of in-flight + queued MCP→Python requests. */
export function pendingPythonRequestCount(): number {
    return pendingById.size;
}
