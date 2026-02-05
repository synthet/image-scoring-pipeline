import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electron', {
    ping: () => ipcRenderer.invoke('ping'),
    getImageCount: () => ipcRenderer.invoke('db:get-image-count'),
    getImages: (options?: any) => ipcRenderer.invoke('db:get-images', options),
    getFolders: () => ipcRenderer.invoke('db:get-folders'),
    log: (level: string, message: string, data?: any) => ipcRenderer.invoke('debug:log', { level, message, data, timestamp: Date.now() }),
});
