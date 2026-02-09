"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
const path_1 = __importDefault(require("path"));
const fs_1 = __importDefault(require("fs"));
const os_1 = __importDefault(require("os"));
const electron_is_dev_1 = __importDefault(require("electron-is-dev"));
const db = __importStar(require("./db"));
const nefExtractor_1 = require("./nefExtractor");
// Handle creating/removing shortcuts on Windows when installing/uninstalling.
// if (require('electron-squirrel-startup')) {
//     app.quit();
// }
let mainWindow = null;
// Register secure media protocol
electron_1.protocol.registerSchemesAsPrivileged([
    { scheme: 'media', privileges: { secure: true, supportFetchAPI: true, standard: true, bypassCSP: true } }
]);
function createWindow() {
    mainWindow = new electron_1.BrowserWindow({
        width: 1200,
        height: 800,
        webPreferences: {
            preload: path_1.default.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
            webSecurity: true // Enable web security (media:// protocol is already registered as privileged)
        },
    });
    if (electron_is_dev_1.default) {
        mainWindow.loadURL('http://localhost:5173');
        mainWindow.webContents.openDevTools();
    }
    else {
        mainWindow.loadFile(path_1.default.join(__dirname, '../dist/index.html'));
    }
    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}
electron_1.app.whenReady().then(() => {
    // Handle media:// requests
    electron_1.protocol.handle('media', (request) => {
        let url = request.url.replace('media://', '');
        let filePath = decodeURIComponent(url);
        if (filePath.match(/^\/?mnt\/[a-zA-Z]\//)) {
            filePath = filePath.replace(/^\/?mnt\/([a-zA-Z])\//, '$1:/');
        }
        return electron_1.net.fetch('file:///' + filePath);
    });
    createWindow();
    // IPC Handlers
    electron_1.ipcMain.handle('ping', () => 'pong');
    electron_1.ipcMain.handle('db:get-image-count', async (_, options) => {
        try {
            return await db.getImageCount(options);
        }
        catch (e) {
            console.error('DB Error:', e);
            return { error: e.message };
        }
    });
    electron_1.ipcMain.handle('db:get-images', async (_, options) => {
        try {
            return await db.getImages(options);
        }
        catch (e) {
            console.error('DB Error:', e);
            return [];
        }
    });
    electron_1.ipcMain.handle('db:get-image-details', async (_, id) => {
        try {
            console.log(`[Main] Getting image details for ID: ${id}`);
            const result = await db.getImageDetails(id);
            console.log(`[Main] Image details result:`, result ? 'Data received' : 'NULL returned');
            if (result) {
                console.log(`[Main] Image details keys:`, Object.keys(result));
            }
            return result;
        }
        catch (e) {
            console.error('[Main] DB Error (details):', e);
            console.error('[Main] Error stack:', e.stack);
            throw e; // Re-throw so the error reaches the renderer
        }
    });
    electron_1.ipcMain.handle('db:get-keywords', async () => {
        try {
            return await db.getKeywords();
        }
        catch (e) {
            console.error('DB Error (keywords):', e);
            return [];
        }
    });
    electron_1.ipcMain.handle('db:get-folders', async () => {
        try {
            const rawFolders = await db.getFolders();
            // Helper to convert paths (similar to python modules/utils.py)
            const convertPathToLocal = (p) => {
                const isWindows = process.platform === 'win32';
                if (isWindows) {
                    const pStr = p.replace(/\\/g, '/');
                    if (pStr.startsWith('/mnt/')) {
                        // /mnt/d/foo -> parts=["", "mnt", "d", "foo"]
                        const parts = pStr.split('/');
                        if (parts.length > 2 && parts[2].length === 1) {
                            const drive = parts[2].toUpperCase();
                            const rest = parts.slice(3).join('/');
                            // Handle root of drive case /mnt/d -> D:/
                            return `${drive}:/${rest}`;
                        }
                    }
                }
                return p;
            };
            const processed = rawFolders.map((f) => {
                return { ...f, path: convertPathToLocal(f.path) };
            }).filter((f) => {
                if (process.platform === 'win32') {
                    // Only keep paths that look like drive paths (C:/...)
                    // Filter out /mnt, /, ., or relative paths
                    // Must start with X:
                    const isDrivePath = /^[a-zA-Z]:/.test(f.path);
                    if (!isDrivePath)
                        return false;
                    // Filter out strict WSL artifacts if they somehow passed (unlikely if regex matches)
                    if (f.path.startsWith('/mnt') || f.path === '/' || f.path === '.')
                        return false;
                    return true;
                }
                return true;
            });
            // Deduplicate by path (if multiple DB entries map to same local path)
            // But we need to keep IDs. 
            // If we have duplicates, we might have issues with parent_id linkage?
            // For now, let's just return the processed list. The frontend uses IDs.
            // If ID 1 maps to D:/ and ID 2 maps to D:/, and ID 3 parent is 1...
            // It should be fine.
            return processed;
        }
        catch (e) {
            console.error('DB Error:', e);
            return [];
        }
    });
    electron_1.ipcMain.handle('nef:extract-preview', async (_, filePath) => {
        try {
            console.log(`[Main] NEF preview requested for: ${filePath}`);
            // Convert WSL path to Windows path if needed
            let convertedPath = filePath;
            if (process.platform === 'win32' && filePath.match(/^\/mnt\/[a-zA-Z]\//)) {
                // /mnt/d/foo -> D:/foo
                convertedPath = filePath.replace(/^\/mnt\/([a-zA-Z])\//, '$1:/');
                console.log(`[Main] Converted WSL path: ${filePath} -> ${convertedPath}`);
            }
            // Check if file is actually a NEF file
            const ext = path_1.default.extname(convertedPath).toLowerCase();
            if (ext !== '.nef') {
                console.log(`[Main] Skipping non-NEF file (${ext}), returning fallback`);
                // Return file buffer for client-side processing (might be JPG, etc.)
                const fileBuffer = await fs_1.default.promises.readFile(convertedPath);
                return {
                    success: false,
                    fallback: true,
                    buffer: Array.from(new Uint8Array(fileBuffer))
                };
            }
            // Tier 1: Try exiftool-vendored extraction
            const buffer = await nefExtractor_1.nefExtractor.extractPreview(convertedPath);
            if (buffer) {
                // Success! Return the JPEG buffer
                return {
                    success: true,
                    buffer: Array.from(new Uint8Array(buffer))
                };
            }
            // Tier 1 failed, return file buffer for client-side fallback
            console.log('[Main] Tier 1 failed, falling back to client-side extraction');
            const fileBuffer = await fs_1.default.promises.readFile(convertedPath);
            return {
                success: false,
                fallback: true,
                buffer: Array.from(new Uint8Array(fileBuffer))
            };
        }
        catch (e) {
            console.error('[Main] NEF extraction error:', e);
            return {
                success: false,
                error: e.message
            };
        }
    });
    electron_1.ipcMain.handle('debug:log', async (_, { level, message, data, timestamp }) => {
        const logDir = electron_1.app.getPath('userData');
        const dateStr = new Date().toISOString().split('T')[0];
        const logFile = path_1.default.join(logDir, `session_${dateStr}.log`);
        const logEntry = JSON.stringify({
            timestamp,
            level,
            message,
            data
        }) + os_1.default.EOL;
        try {
            await fs_1.default.promises.appendFile(logFile, logEntry);
            return true;
        }
        catch (e) {
            console.error('Failed to write log:', e);
            return false;
        }
    });
});
electron_1.app.on('window-all-closed', async () => {
    // Cleanup exiftool resources
    await nefExtractor_1.nefExtractor.cleanup();
    if (process.platform !== 'darwin') {
        electron_1.app.quit();
    }
});
electron_1.app.on('activate', () => {
    if (mainWindow === null) {
        createWindow();
    }
});
