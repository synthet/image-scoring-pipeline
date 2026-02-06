import { exiftool } from "exiftool-vendored";
import fs from "fs/promises";
import path from "path";
import os from "os";

/**
 * Server-side NEF preview extractor using exiftool-vendored
 * Handles all Nikon formats including Z8 HE/HE*, Z9, Z6II, D90
 */
export class NefExtractor {
    private static instance: NefExtractor;

    private constructor() { }

    public static getInstance(): NefExtractor {
        if (!NefExtractor.instance) {
            NefExtractor.instance = new NefExtractor();
        }
        return NefExtractor.instance;
    }

    /**
     * Extract the largest/best JPEG preview using exiftool.
     * This is the most reliable method for all Nikon formats.
     * 
     * @param nefPath - Absolute path to the NEF file
     * @returns Buffer containing JPEG data, or null if extraction failed
     */
    public async extractPreview(nefPath: string): Promise<Buffer | null> {
        const tempDir = os.tmpdir();
        const tempJpeg = path.join(tempDir, `preview_${Date.now()}_${Math.random().toString(36).substring(7)}.jpg`);

        try {
            console.log(`[NefExtractor] Attempting exiftool extraction for: ${nefPath}`);

            // extractJpgFromRaw automatically finds the best/largest preview
            await exiftool.extractJpgFromRaw(nefPath, tempJpeg);

            const buffer = await fs.readFile(tempJpeg);
            console.log(`[NefExtractor] ✓ Tier 1: exiftool extracted preview (${(buffer.length / 1024).toFixed(1)} KB)`);

            // Cleanup temp file
            await fs.unlink(tempJpeg).catch(() => { }); // Ignore cleanup errors

            return buffer;
        } catch (e: any) {
            // Log the actual error message for debugging
            const errorMsg = e.code === 'ENOENT' ? `File not found - ${nefPath}` : e.message;
            console.warn(`[NefExtractor] ✗ Tier 1 failed: ${errorMsg}`);

            // Cleanup temp file if it exists
            await fs.unlink(tempJpeg).catch(() => { });

            return null;
        }
    }

    /**
     * Cleanup resources when shutting down
     */
    public async cleanup(): Promise<void> {
        try {
            await exiftool.end();
            console.log('[NefExtractor] Cleaned up exiftool resources');
        } catch (e) {
            console.error('[NefExtractor] Cleanup error:', e);
        }
    }
}

export const nefExtractor = NefExtractor.getInstance();
