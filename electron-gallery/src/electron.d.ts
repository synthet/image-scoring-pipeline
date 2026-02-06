export { };

declare global {
    interface Window {
        electron: {
            ping: () => Promise<string>;
            getImageCount: () => Promise<number | { error: string }>;
            getImages: (options?: { limit?: number; offset?: number; folderId?: number }) => Promise<any[]>;
            getImageDetails: (id: number) => Promise<any>;
            getFolders: () => Promise<any[]>;
            log: (level: string, message: string, data?: any) => Promise<boolean>;
            extractNefPreview: (filePath: string) => Promise<{
                success: boolean;
                buffer?: number[];
                fallback?: boolean;
                error?: string;
            }>;
        };
    };
}
