"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.nefExtractor = exports.NefExtractor = void 0;
const exiftool_vendored_1 = require("exiftool-vendored");
const promises_1 = __importDefault(require("fs/promises"));
const path_1 = __importDefault(require("path"));
const os_1 = __importDefault(require("os"));
/**
 * Server-side NEF preview extractor using exiftool-vendored
 * Handles all Nikon formats including Z8 HE/HE*, Z9, Z6II, D90
 */
class NefExtractor {
    static instance;
    constructor() { }
    static getInstance() {
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
    async extractPreview(nefPath) {
        const tempDir = os_1.default.tmpdir();
        const tempJpeg = path_1.default.join(tempDir, `preview_${Date.now()}_${Math.random().toString(36).substring(7)}.jpg`);
        try {
            console.log(`[NefExtractor] Attempting exiftool extraction for: ${nefPath}`);
            // extractJpgFromRaw automatically finds the best/largest preview
            await exiftool_vendored_1.exiftool.extractJpgFromRaw(nefPath, tempJpeg);
            const buffer = await promises_1.default.readFile(tempJpeg);
            console.log(`[NefExtractor] ✓ Tier 1: exiftool extracted preview (${(buffer.length / 1024).toFixed(1)} KB)`);
            // Cleanup temp file
            await promises_1.default.unlink(tempJpeg).catch(() => { }); // Ignore cleanup errors
            return buffer;
        }
        catch (e) {
            // Log the actual error message for debugging
            const errorMsg = e.code === 'ENOENT' ? `File not found - ${nefPath}` : e.message;
            console.warn(`[NefExtractor] ✗ Tier 1 failed: ${errorMsg}`);
            // Cleanup temp file if it exists
            await promises_1.default.unlink(tempJpeg).catch(() => { });
            return null;
        }
    }
    /**
     * Cleanup resources when shutting down
     */
    async cleanup() {
        try {
            await exiftool_vendored_1.exiftool.end();
            console.log('[NefExtractor] Cleaned up exiftool resources');
        }
        catch (e) {
            console.error('[NefExtractor] Cleanup error:', e);
        }
    }
}
exports.NefExtractor = NefExtractor;
exports.nefExtractor = NefExtractor.getInstance();
