export { };

declare global {
    interface Window {
        electron: {
            ping: () => Promise<string>;
            getImageCount: () => Promise<number | { error: string }>;
            getImages: (options?: { limit?: number; offset?: number; folderId?: number }) => Promise<any[]>;
            getFolders: () => Promise<any[]>;
            log: (level: string, message: string, data?: any) => Promise<boolean>;
        };
    };
}
