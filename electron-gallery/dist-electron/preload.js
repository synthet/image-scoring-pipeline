"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
electron_1.contextBridge.exposeInMainWorld('electron', {
    ping: () => electron_1.ipcRenderer.invoke('ping'),
    getImageCount: () => electron_1.ipcRenderer.invoke('db:get-image-count'),
    getImages: (options) => electron_1.ipcRenderer.invoke('db:get-images', options),
    getFolders: () => electron_1.ipcRenderer.invoke('db:get-folders'),
    log: (level, message, data) => electron_1.ipcRenderer.invoke('debug:log', { level, message, data, timestamp: Date.now() }),
});
