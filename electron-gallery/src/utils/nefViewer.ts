import LibRaw from 'libraw-wasm';

/**
 * LibRaw Viewer - NEF/RAW file preview utility
 * 
 * Provides multi-tier extraction with graceful fallbacks:
 * 1. Server-side exiftool extraction (via IPC) - Most reliable
 * 2. Client-side TIFF SubIFD parsing - Handles Z9/Z6II formats
 * 3. Client-side JPEG marker scanning - Final fallback
 * 4. Full RAW decode via LibRaw-WASM (on-demand, slow)
 */
export class NefViewer {
    private static instance: NefViewer;
    private libraw: any | null = null;

    private constructor() { }

    public static getInstance(): NefViewer {
        if (!NefViewer.instance) {
            NefViewer.instance = new NefViewer();
        }
        return NefViewer.instance;
    }

    /**
     * Main entry point: Extract preview with multi-tier fallback.
     * 
     * @param filePath - Absolute path to NEF file
     * @returns Blob containing JPEG, or null if all methods fail
     */
    public async extractWithFallback(filePath: string): Promise<Blob | null> {
        console.log('[NefViewer] 🔍 Starting extraction for:', filePath);

        // Try server-side extraction first (Tier 1: exiftool-vendored)
        if (window.electron) {
            console.log('[NefViewer] Electron API available, calling IPC...');
            try {
                const result = await window.electron.extractNefPreview(filePath);

                if (result.success && result.buffer) {
                    // Tier 1 succeeded - exiftool found a preview
                    console.log(`[NefViewer] ✓ Tier 1 succeeded (server-side), buffer size: ${result.buffer.length}`);
                    return new Blob([new Uint8Array(result.buffer)], { type: 'image/jpeg' });
                } else if (result.fallback && result.buffer) {
                    console.log(`[NefViewer] Tier 1 failed, received fallback buffer (${result.buffer.length} bytes)`);
                    // Tier 1 failed, try client-side methods with the file buffer
                    console.log(`[NefViewer] Tier 1 failed, trying client-side fallbacks`);
                    const arrayBuffer = new Uint8Array(result.buffer).buffer;

                    // Tier 2: TIFF SubIFD parsing
                    let blob = this.extractFromSubIFD(arrayBuffer);
                    if (blob) {
                        console.log(`[NefViewer] ✓ Tier 2 succeeded (SubIFD parsing)`);
                        return blob;
                    }

                    // Tier 3: JPEG marker scanning
                    blob = await this.extractEmbeddedJpeg(arrayBuffer);
                    if (blob) {
                        console.log(`[NefViewer] ✓ Tier 3 succeeded (marker scanning)`);
                        return blob;
                    }

                    console.warn('[NefViewer] ✗ All tiers failed - returning null');
                } else {
                    console.error('[NefViewer] ✗ Unexpected result from IPC:', result);
                }
            } catch (e) {
                console.error('[NefViewer] Extraction error:', e);
            }
        } else {
            console.warn('[NefViewer] ✗ No Electron API - cannot extract NEF');
        }

        console.warn('[NefViewer] ✗ Returning null - will fallback to thumbnail');
        return null;
    }

    /**
     * Tier 2: Extract preview from TIFF SubIFD structure.
     * Many Nikon cameras (Z9, Z6II) store the full preview in SubIFD0.
     * 
     * TIFF structure:
     * - Tag 0x014a in IFD0 points to SubIFD offsets
     * - Tag 0x0201/0x0202 within SubIFD contain JPEG offset/length
     * 
     * @param buffer - Raw NEF file bytes
     * @returns Blob containing JPEG, or null if not found
     */
    private extractFromSubIFD(buffer: ArrayBuffer): Blob | null {
        try {
            const view = new DataView(buffer);

            // Parse TIFF header to get byte order and IFD0 offset
            const { littleEndian, ifd0Offset } = this.parseTiffHeader(view);
            if (ifd0Offset === null) return null;

            // Find SubIFD offsets from IFD0
            const subIFDOffsets = this.findSubIFDOffsets(view, ifd0Offset, littleEndian);
            if (subIFDOffsets.length === 0) return null;

            console.log(`[NefViewer] Found ${subIFDOffsets.length} SubIFD(s) at offsets: ${subIFDOffsets.join(', ')}`);

            // Try each SubIFD (usually SubIFD0 has the best preview)
            for (const subIFDOffset of subIFDOffsets) {
                const jpeg = this.extractJpegFromIFD(view, subIFDOffset, littleEndian);
                if (jpeg) return jpeg;
            }

            return null;
        } catch (e) {
            console.warn('[NefViewer] SubIFD extraction failed:', e);
            return null;
        }
    }

    /**
     * Parse TIFF header and determine byte order.
     */
    private parseTiffHeader(view: DataView): { littleEndian: boolean; ifd0Offset: number | null } {
        // Check TIFF magic number (bytes 0-1)
        const byte0 = view.getUint8(0);
        const byte1 = view.getUint8(1);

        let littleEndian: boolean;
        if (byte0 === 0x49 && byte1 === 0x49) {
            // "II" - Intel (little-endian)
            littleEndian = true;
        } else if (byte0 === 0x4D && byte1 === 0x4D) {
            // "MM" - Motorola (big-endian)
            littleEndian = false;
        } else {
            console.warn('[NefViewer] Invalid TIFF header');
            return { littleEndian: false, ifd0Offset: null };
        }

        // Check TIFF version (bytes 2-3, should be 42 or 0x2A)
        const version = view.getUint16(2, littleEndian);
        if (version !== 42) {
            console.warn('[NefViewer] Invalid TIFF version:', version);
            return { littleEndian, ifd0Offset: null };
        }

        // Get IFD0 offset (bytes 4-7)
        const ifd0Offset = view.getUint32(4, littleEndian);

        return { littleEndian, ifd0Offset };
    }

    /**
     * Find SubIFD offsets from IFD0 (tag 0x014a).
     */
    private findSubIFDOffsets(view: DataView, ifdOffset: number, littleEndian: boolean): number[] {
        try {
            const numEntries = view.getUint16(ifdOffset, littleEndian);
            let offset = ifdOffset + 2;

            for (let i = 0; i < numEntries; i++) {
                const tag = view.getUint16(offset, littleEndian);
                const count = view.getUint32(offset + 4, littleEndian);
                const valueOffset = offset + 8;

                if (tag === 0x014a) {
                    // SubIFDs tag found
                    // count is number of SubIFDs
                    const subIFDOffsets: number[] = [];

                    for (let j = 0; j < count; j++) {
                        let subOffset: number;
                        if (count === 1) {
                            // Value is inline (4 bytes at valueOffset)
                            subOffset = view.getUint32(valueOffset, littleEndian);
                        } else {
                            // Value points to an offset containing the array
                            const arrayOffset = view.getUint32(valueOffset, littleEndian);
                            subOffset = view.getUint32(arrayOffset + j * 4, littleEndian);
                        }
                        subIFDOffsets.push(subOffset);
                    }

                    return subIFDOffsets;
                }

                offset += 12; // Each IFD entry is 12 bytes
            }

            return [];
        } catch (e) {
            console.warn('[NefViewer] Error finding SubIFD offsets:', e);
            return [];
        }
    }

    /**
     * Extract JPEG from an IFD using tags 0x0201 (JPEGInterchangeFormat) and 0x0202 (JPEGInterchangeFormatLength).
     */
    private extractJpegFromIFD(view: DataView, ifdOffset: number, littleEndian: boolean): Blob | null {
        try {
            const numEntries = view.getUint16(ifdOffset, littleEndian);
            let offset = ifdOffset + 2;

            let jpegOffset: number | null = null;
            let jpegLength: number | null = null;

            for (let i = 0; i < numEntries; i++) {
                const tag = view.getUint16(offset, littleEndian);
                const valueOffset = offset + 8;

                if (tag === 0x0201) {
                    // JPEGInterchangeFormat - offset to JPEG data
                    jpegOffset = view.getUint32(valueOffset, littleEndian);
                } else if (tag === 0x0202) {
                    // JPEGInterchangeFormatLength - size of JPEG data
                    jpegLength = view.getUint32(valueOffset, littleEndian);
                }

                if (jpegOffset !== null && jpegLength !== null) {
                    // Found both tags, extract JPEG
                    // Create a proper copy of the bytes to avoid SharedArrayBuffer issues
                    const jpegBytes = new Uint8Array(jpegLength);
                    const sourceBytes = new Uint8Array(view.buffer, jpegOffset, jpegLength);
                    jpegBytes.set(sourceBytes);
                    console.log(`[NefViewer] SubIFD JPEG found: offset=${jpegOffset}, length=${(jpegLength / 1024).toFixed(1)} KB`);
                    return new Blob([jpegBytes], { type: 'image/jpeg' });
                }

                offset += 12;
            }

            return null;
        } catch (e) {
            console.warn('[NefViewer] Error extracting JPEG from IFD:', e);
            return null;
        }
    }

    /**
     * Tier 3: Extract embedded JPEG preview using SOI/EOI marker scanning.
     * This is the original method, kept as final fallback.
     * 
     * @param buffer - Raw NEF file bytes
     * @returns Blob containing the JPEG, or null if not found
     */
    public async extractEmbeddedJpeg(buffer: ArrayBuffer): Promise<Blob | null> {
        const bytes = new Uint8Array(buffer);

        interface JpegCandidate {
            start: number;
            end: number;
            size: number;
        }

        const soiMarkers: number[] = [];

        // Search for JPEG SOI markers (0xFF 0xD8)
        for (let i = 512; i < bytes.length - 1; i++) {
            if (bytes[i] === 0xFF && bytes[i + 1] === 0xD8) {
                soiMarkers.push(i);
            }
        }

        if (soiMarkers.length === 0) {
            console.warn('[NefViewer] No embedded JPEG found (no SOI markers)');
            return null;
        }

        console.log(`[NefViewer] Found ${soiMarkers.length} JPEG SOI marker(s)`);

        // For each SOI, find its corresponding EOI and calculate size
        const candidates: JpegCandidate[] = [];

        for (const start of soiMarkers) {
            // Find the next EOI marker (0xFF 0xD9) after this SOI
            let end = -1;
            for (let i = start + 2; i < bytes.length - 1; i++) {
                if (bytes[i] === 0xFF && bytes[i + 1] === 0xD9) {
                    end = i + 2; // Include the marker
                    break;
                }
            }

            if (end !== -1) {
                const size = end - start;
                // Only consider JPEGs larger than 10KB to filter out thumbnails
                if (size > 10000) {
                    candidates.push({ start, end, size });
                }
            }
        }

        if (candidates.length === 0) {
            console.warn('[NefViewer] No valid JPEG found (no complete JPEG > 10KB)');
            return null;
        }

        // Sort by size descending and pick the LARGEST
        candidates.sort((a, b) => b.size - a.size);

        console.log(`[NefViewer] Found ${candidates.length} complete JPEG(s), sizes: ${candidates.map(c => `${(c.size / 1024).toFixed(1)}KB`).join(', ')}`);

        const largest = candidates[0];
        const jpegBytes = bytes.slice(largest.start, largest.end);
        console.log(`[NefViewer] Using largest JPEG (${(largest.size / 1024).toFixed(1)} KB) from offset ${largest.start} to ${largest.end}`);

        return new Blob([jpegBytes], { type: 'image/jpeg' });
    }

    /**
     * Tier 4: Decode full RAW data using LibRaw-WASM (slow, on-demand only).
     */
    public async decodeRaw(buffer: ArrayBuffer): Promise<ImageData | null> {
        try {
            if (!this.libraw) {
                // @ts-ignore
                this.libraw = new LibRaw();
            }

            const bytes = new Uint8Array(buffer);
            await this.libraw.open(bytes);

            const decoded = await this.libraw.imageData();

            return new ImageData(
                new Uint8ClampedArray(decoded.data),
                decoded.width,
                decoded.height
            );

        } catch (e) {
            console.error('[NefViewer] RAW decode failed', e);
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
