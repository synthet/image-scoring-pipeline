"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
electron_1.contextBridge.exposeInMainWorld('electron', {
    ping: () => electron_1.ipcRenderer.invoke('ping'),
    getImageCount: (options) => electron_1.ipcRenderer.invoke('db:get-image-count', options),
    getImages: (options) => electron_1.ipcRenderer.invoke('db:get-images', options),
    getImageDetails: (id) => electron_1.ipcRenderer.invoke('db:get-image-details', id),
    getFolders: () => electron_1.ipcRenderer.invoke('db:get-folders'),
    getKeywords: () => electron_1.ipcRenderer.invoke('db:get-keywords'),
    log: (level, message, data) => electron_1.ipcRenderer.invoke('debug:log', { level, message, data, timestamp: Date.now() }),
    extractNefPreview: (filePath) => electron_1.ipcRenderer.invoke('nef:extract-preview', filePath),
});
