import { app, BrowserWindow, ipcMain, protocol, net } from 'electron';
import path from 'path';
import fs from 'fs';
import os from 'os';
import isDev from 'electron-is-dev';
import * as db from './db';

// Handle creating/removing shortcuts on Windows when installing/uninstalling.
// if (require('electron-squirrel-startup')) {
//     app.quit();
// }

let mainWindow: BrowserWindow | null = null;

// Register secure media protocol
protocol.registerSchemesAsPrivileged([
    { scheme: 'media', privileges: { secure: true, supportFetchAPI: true, standard: true, bypassCSP: true } }
]);

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1200,
        height: 800,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
            webSecurity: false // Temporary for dev, strictly not needed if protocol is correct, but helpful for local setup
        },
    });

    if (isDev) {
        mainWindow.loadURL('http://localhost:5173');
        mainWindow.webContents.openDevTools();
    } else {
        mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
    }

    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

app.whenReady().then(() => {
    // Handle media:// requests
    protocol.handle('media', (request) => {
        let url = request.url.replace('media://', '');
        let filePath = decodeURIComponent(url);
        if (filePath.match(/^\/?mnt\/[a-zA-Z]\//)) {
            filePath = filePath.replace(/^\/?mnt\/([a-zA-Z])\//, '$1:/');
        }
        return net.fetch('file:///' + filePath);
    });

    createWindow();

    // IPC Handlers
    ipcMain.handle('ping', () => 'pong');

    ipcMain.handle('db:get-image-count', async () => {
        try {
            return await db.getImageCount();
        } catch (e: any) {
            console.error('DB Error:', e);
            return { error: e.message };
        }
    });

    ipcMain.handle('db:get-images', async (_, options) => {
        try {
            return await db.getImages(options);
        } catch (e: any) {
            console.error('DB Error:', e);
            return [];
        }
    });

    ipcMain.handle('db:get-image-details', async (_, id) => {
        try {
            return await db.getImageDetails(id);
        } catch (e: any) {
            console.error('DB Error (details):', e);
            return null;
        }
    });

    ipcMain.handle('db:get-folders', async () => {
        try {
            const rawFolders = await db.getFolders();

            // Helper to convert paths (similar to python modules/utils.py)
            const convertPathToLocal = (p: string) => {
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

            const processed = rawFolders.map((f: any) => {
                return { ...f, path: convertPathToLocal(f.path) };
            }).filter((f: any) => {
                if (process.platform === 'win32') {
                    // Only keep paths that look like drive paths (C:/...)
                    // Filter out /mnt, /, ., or relative paths
                    // Must start with X:
                    const isDrivePath = /^[a-zA-Z]:/.test(f.path);
                    if (!isDrivePath) return false;

                    // Filter out strict WSL artifacts if they somehow passed (unlikely if regex matches)
                    if (f.path.startsWith('/mnt') || f.path === '/' || f.path === '.') return false;

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
        } catch (e: any) {
            console.error('DB Error:', e);
            return [];
        }
    });

    ipcMain.handle('debug:log', async (_, { level, message, data, timestamp }) => {
        const logDir = app.getPath('userData');
        const dateStr = new Date().toISOString().split('T')[0];
        const logFile = path.join(logDir, `session_${dateStr}.log`);

        const logEntry = JSON.stringify({
            timestamp,
            level,
            message,
            data
        }) + os.EOL;

        try {
            await fs.promises.appendFile(logFile, logEntry);
            return true;
        } catch (e) {
            console.error('Failed to write log:', e);
            return false;
        }
    });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('activate', () => {
    if (mainWindow === null) {
        createWindow();
    }
});
