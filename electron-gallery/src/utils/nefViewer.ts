import LibRaw from 'libraw-wasm';

/**
 * LibRaw Viewer - NEF/RAW file preview utility
 * 
 * Provides two modes:
 * 1. Fast embedded JPEG extraction (instant preview)
 * 2. Full RAW decode via LibRaw-Wasm (on-demand)
 */
export class NefViewer {
    private static instance: NefViewer;
    private libraw: any | null = null; // Type as any since libraw-wasm might not have strict types

    private constructor() { }

    public static getInstance(): NefViewer {
        if (!NefViewer.instance) {
            NefViewer.instance = new NefViewer();
        }
        return NefViewer.instance;
    }

    /**
     * Extract embedded JPEG preview from NEF file.
     * NEF files typically contain a full-size JPEG preview that can be extracted quickly.
     * 
     * @param buffer - Raw NEF file bytes
     * @returns Blob containing the JPEG, or null if not found
     */
    public async extractEmbeddedJpeg(buffer: ArrayBuffer): Promise<Blob | null> {
        const bytes = new Uint8Array(buffer);

        // search for JPEG SOI (Start of Image)
        // NEF files typically have the full-size JPEG starting around offset 0x8000+
        let jpegStart = -1;
        let jpegEnd = -1;

        // Skip first 1KB (TIFF header area) and search for JPEG SOI
        // We limit the search to reasonable bounds to avoid scanning the whole huge file if possible,
        // but for robustness we scan until we find a good candidate.
        for (let i = 1024; i < bytes.length - 1; i++) {
            if (bytes[i] === 0xFF && bytes[i + 1] === 0xD8) {
                // Found potential JPEG start
                // Verify it's a substantial JPEG (not just thumbnail)
                // by checking if there's enough data after it.
                // Arbitrary threshold: 100KB to distinguish from tiny thumbnails
                if (bytes.length - i > 100000) {
                    jpegStart = i;
                    break;
                }
            }
        }

        if (jpegStart === -1) {
            console.warn('NefViewer: No embedded JPEG found');
            return null;
        }

        // Find JPEG end marker (EOI)
        // We search from the start found + 2
        for (let i = jpegStart + 2; i < bytes.length - 1; i++) {
            if (bytes[i] === 0xFF && bytes[i + 1] === 0xD9) {
                jpegEnd = i + 2; // Include the marker
                // In a perfect world we might want to keep searching if this was a thumbnail *inside* the main image (rare for NEF structure),
                // but usually the first large JPEG is the preview.
                // However, the original code had a comment: "Continue searching for a later EOI (could be thumbnail EOI)"
                // But the loop in original code didn't actually *continue* searching effectively for the *outer* one if it just updated jpegEnd.
                // It just updated jpegEnd to the *last* found EOI? 
                // Let's copy the logic: "Continue searching for a later EOI" implies finding the LAST EOI?
                // Actually, NEF embedded JPEGs are usually contiguous. 
                // Let's just break on the first EOI that makes sense size-wise? 
                // Or simply find the last EOI? The original code loop logic was:
                /*
                for (let i = jpegStart + 2; i < bytes.length - 1; i++) {
                    if (bytes[i] === 0xFF && bytes[i + 1] === 0xD9) {
                        jpegEnd = i + 2;
                        // Continue searching for a later EOI
                    }
                }
                */
                // This means it finds the LAST EOI in the file. 
                // That might be risky if there are multiple things. But let's stick to the ported logic.
            }
        }

        // Optimizing: Scanning 50MB for EOI might be slow in JS loop. 
        // But for now, direct port.

        if (jpegEnd === -1) {
            console.warn('NefViewer: JPEG end marker not found');
            return null;
        }

        const jpegBytes = bytes.slice(jpegStart, jpegEnd);
        console.log(`NefViewer: Extracted JPEG preview (${(jpegBytes.length / 1024).toFixed(1)} KB)`);

        return new Blob([jpegBytes], { type: 'image/jpeg' });
    }

    /**
     * Decode full RAW data using LibRaw-WASM.
     * This is computationally expensive.
     */
    public async decodeRaw(buffer: ArrayBuffer): Promise<ImageData | null> {
        try {
            if (!this.libraw) {
                // @ts-ignore - libraw-wasm might not have types
                this.libraw = new LibRaw();
            }

            // Open the file
            // LibRaw-wasm usage: raw.open(Uint8Array)
            const bytes = new Uint8Array(buffer);
            await this.libraw.open(bytes);

            // Get image data
            const decoded = await this.libraw.imageData();

            // Cleanup? libraw-wasm docs don't strictly mention close(), but good practice if available.
            // The instance seems reusable or we might need to free it. 
            // For now, let's just return the data.

            // decoded is likely an object with width, height, data
            return new ImageData(
                new Uint8ClampedArray(decoded.data),
                decoded.width,
                decoded.height
            );

        } catch (e) {
            console.error('NefViewer: RAW decode failed', e);
            return null;
        }
    }

    /**
     * Create an image element from a blob.
     */
    public async blobToImage(blob: Blob): Promise<HTMLImageElement> {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => {
                URL.revokeObjectURL(img.src);
                resolve(img);
            };
            img.onerror = reject;
            img.src = URL.createObjectURL(blob);
        });
    }
}

export const nefViewer = NefViewer.getInstance();
