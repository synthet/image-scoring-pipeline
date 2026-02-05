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

    ipcMain.handle('db:get-folders', async () => {
        try {
            return await db.getFolders();
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
