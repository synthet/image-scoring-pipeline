/**
 * LibRaw Viewer - In-browser NEF/RAW file preview
 * 
 * Provides two modes:
 * 1. Fast embedded JPEG extraction (instant preview)
 * 2. Full RAW decode via LibRaw-WASM (on-demand)
 */

class NefViewer {
    constructor() {
        this.wasmLoaded = false;
        this.libraw = null;
    }

    /**
     * Extract embedded JPEG preview from NEF file.
     * NEF files contain a full-size JPEG preview that can be extracted quickly.
     * 
     * @param {ArrayBuffer} buffer - Raw NEF file bytes
     * @returns {Promise<Blob|null>} - JPEG blob or null if not found
     */
    async extractEmbeddedJpeg(buffer) {
        const bytes = new Uint8Array(buffer);

        // JPEG markers
        const JPEG_SOI = 0xFFD8;  // Start of Image
        const JPEG_EOI = 0xFFD9;  // End of Image

        // Search for embedded JPEG (usually after EXIF data)
        // NEF files typically have the full-size JPEG starting around offset 0x8000+
        let jpegStart = -1;
        let jpegEnd = -1;

        // Skip first 1KB (TIFF header area) and search for JPEG SOI
        for (let i = 1024; i < bytes.length - 1; i++) {
            if (bytes[i] === 0xFF && bytes[i + 1] === 0xD8) {
                // Found potential JPEG start
                // Verify it's a substantial JPEG (not just thumbnail)
                // by checking if there's enough data after it
                if (bytes.length - i > 100000) {  // At least 100KB remaining
                    jpegStart = i;
                    break;
                }
            }
        }

        if (jpegStart === -1) {
            console.log('NefViewer: No embedded JPEG found');
            return null;
        }

        // Find JPEG end marker
        for (let i = jpegStart + 2; i < bytes.length - 1; i++) {
            if (bytes[i] === 0xFF && bytes[i + 1] === 0xD9) {
                jpegEnd = i + 2;
                // Continue searching for a later EOI (could be thumbnail EOI)
            }
        }

        if (jpegEnd === -1) {
            console.log('NefViewer: JPEG end marker not found');
            return null;
        }

        // Extract JPEG bytes
        const jpegBytes = bytes.slice(jpegStart, jpegEnd);
        console.log(`NefViewer: Extracted JPEG preview (${(jpegBytes.length / 1024).toFixed(1)} KB)`);

        return new Blob([jpegBytes], { type: 'image/jpeg' });
    }

    /**
     * Load LibRaw WASM module for full RAW decoding.
     * Only loads when needed (lazy loading).
     */
    async loadWasm() {
        if (this.wasmLoaded) return true;

        try {
            // Dynamic import of libraw-wasm
            // Note: User needs to provide the WASM file
            const wasmPath = '/file=static/wasm/libraw.wasm';

            // Check if libraw-wasm is available
            if (typeof LibRaw !== 'undefined') {
                this.libraw = new LibRaw();
                await this.libraw.init(wasmPath);
                this.wasmLoaded = true;
                console.log('NefViewer: LibRaw WASM loaded');
                return true;
            } else {
                console.warn('NefViewer: LibRaw-WASM not available, using embedded JPEG only');
                return false;
            }
        } catch (e) {
            console.error('NefViewer: Failed to load WASM', e);
            return false;
        }
    }

    /**
     * Decode full RAW data using LibRaw-WASM.
     * This is computationally expensive (2-5 seconds for 45MP).
     * 
     * @param {ArrayBuffer} buffer - Raw NEF file bytes
     * @returns {Promise<ImageData|null>} - Decoded image data
     */
    async decodeRaw(buffer) {
        if (!await this.loadWasm()) {
            console.error('NefViewer: WASM not available for RAW decode');
            return null;
        }

        try {
            const result = await this.libraw.decode(new Uint8Array(buffer));
            return new ImageData(
                new Uint8ClampedArray(result.data),
                result.width,
                result.height
            );
        } catch (e) {
            console.error('NefViewer: RAW decode failed', e);
            return null;
        }
    }

    /**
     * Create an image element from a blob.
     * 
     * @param {Blob} blob - Image blob (JPEG)
     * @returns {Promise<HTMLImageElement>}
     */
    async blobToImage(blob) {
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

    /**
     * Render ImageData to a canvas element.
     * 
     * @param {ImageData} imageData - Decoded RAW image data
     * @param {HTMLCanvasElement} canvas - Target canvas
     */
    renderToCanvas(imageData, canvas) {
        canvas.width = imageData.width;
        canvas.height = imageData.height;
        const ctx = canvas.getContext('2d');
        ctx.putImageData(imageData, 0, 0);
    }
}

// Global instance
window.NefViewer = new NefViewer();

/**
 * Preview a NEF file by extracting embedded JPEG.
 * Called from Gradio button click handlers.
 * 
 * @param {string} filePath - Path to NEF file
 * @param {string} targetElementId - ID of img/canvas element to render to
 */
async function previewNefFile(filePath, targetElementId) {
    const statusEl = document.getElementById('raw-preview-status');
    if (statusEl) statusEl.textContent = 'Loading...';

    try {
        // Fetch NEF file
        const response = await fetch(filePath);
        if (!response.ok) throw new Error(`Failed to fetch: ${response.status}`);

        const buffer = await response.arrayBuffer();
        console.log(`NefViewer: Loaded ${(buffer.byteLength / 1024 / 1024).toFixed(1)} MB`);

        // Try embedded JPEG extraction first (fast path)
        const jpegBlob = await window.NefViewer.extractEmbeddedJpeg(buffer);

        if (jpegBlob) {
            const img = await window.NefViewer.blobToImage(jpegBlob);
            const target = document.getElementById(targetElementId);

            if (target && target.tagName === 'IMG') {
                target.src = URL.createObjectURL(jpegBlob);
            } else if (target && target.tagName === 'CANVAS') {
                const ctx = target.getContext('2d');
                target.width = img.width;
                target.height = img.height;
                ctx.drawImage(img, 0, 0);
            }

            if (statusEl) statusEl.textContent = `Preview: ${img.width}x${img.height}`;
        } else {
            if (statusEl) statusEl.textContent = 'No embedded preview found';
        }
    } catch (e) {
        console.error('NefViewer: Preview failed', e);
        if (statusEl) statusEl.textContent = `Error: ${e.message}`;
    }
}

// Export for global access
window.previewNefFile = previewNefFile;

/**
 * Generic RAW preview handler with progress indicator.
 * Uses server-side extraction endpoint for optimized performance (faster than client-side).
 * Falls back to client-side extraction if server endpoint fails.
 * 
 * @param {string} filePath - Path to the NEF file
 * @param {HTMLElement} statusEl - Status display element
 * @param {HTMLElement} canvas - Canvas to render preview
 */
async function handleRawPreview(filePath, statusEl, canvas) {
    if (!filePath) {
        if (statusEl) statusEl.innerHTML = '<span style="color: #f85149;">❌ No file path provided. Select an image first.</span>';
        return;
    }

    // Check if NEF file (extended to support more RAW formats)
    const lowerPath = filePath.toLowerCase();
    const supportedFormats = ['.nef', '.nrw', '.cr2', '.cr3', '.arw', '.orf', '.rw2', '.dng'];
    const isRaw = supportedFormats.some(ext => lowerPath.endsWith(ext));
    
    if (!isRaw) {
        if (statusEl) statusEl.innerHTML = '<span style="color: #d29922;">⚠️ Selected file is not a supported RAW format.</span>';
        return;
    }

    const fileName = filePath.split(/[/\\]/).pop();

    // Show loading status
    if (statusEl) {
        statusEl.innerHTML = `
            <div style="color: #58a6ff; margin-bottom: 8px;">📥 Extracting preview from ${fileName}...</div>
            <div style="background: #21262d; border-radius: 4px; height: 8px; overflow: hidden;">
                <div id="nef-progress-bar" style="width: 0%; height: 100%; background: linear-gradient(90deg, #58a6ff 0%, #a371f7 100%); transition: width 0.3s ease;"></div>
            </div>
        `;
    }

    try {
        // Method 1: Try server-side extraction endpoint (fast - ~2-5MB JPEG vs 20-60MB NEF)
        const encodedPath = encodeURIComponent(filePath);
        const previewUrl = `/api/raw-preview?path=${encodedPath}`;
        
        const response = await fetch(previewUrl);
        
        if (response.ok) {
            // Server-side extraction successful
            const jpegBlob = await response.blob();
            
            if (jpegBlob && jpegBlob.size > 1000) {
                const img = await window.NefViewer.blobToImage(jpegBlob);

                if (canvas) {
                    canvas.style.display = 'block';
                    canvas.width = Math.min(img.width, 800);
                    canvas.height = (img.height / img.width) * canvas.width;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                }

                if (statusEl) {
                    statusEl.innerHTML = `<span style="color: #3fb950;">✅ Preview: ${img.width}x${img.height} (${(jpegBlob.size / 1024).toFixed(0)} KB) - Server-extracted</span>`;
                }
                return; // Success, exit early
            }
        }
        
        // Method 2: Fallback to client-side extraction (if server endpoint fails)
        console.log('NefViewer: Server-side extraction failed or unavailable, falling back to client-side extraction');
        if (statusEl) {
            statusEl.innerHTML = `<span style="color: #d29922;">⚠️ Server extraction failed, trying client-side...</span>`;
        }

        // Convert WSL path to Windows path for fetch
        let fetchPath = filePath;
        if (filePath.startsWith('/mnt/')) {
            const parts = filePath.split('/');
            const driveLetter = parts[2].toUpperCase();
            const rest = parts.slice(3).join('/');
            fetchPath = `${driveLetter}:/${rest}`;
        }

        // Use Gradio's file serving endpoint
        const fileUrl = `/file=${fetchPath}`;
        
        // Fetch full file with progress tracking
        const fileResponse = await fetch(fileUrl);
        if (!fileResponse.ok) throw new Error(`HTTP ${fileResponse.status}`);

        const contentLength = fileResponse.headers.get('content-length');
        const total = parseInt(contentLength, 10) || 0;
        
        const reader = fileResponse.body.getReader();
        let receivedLength = 0;
        const chunks = [];
        const progressBar = document.getElementById('nef-progress-bar');

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            chunks.push(value);
            receivedLength += value.length;
            
            if (progressBar && total > 0) {
                const percent = Math.round((receivedLength / total) * 100);
                progressBar.style.width = `${percent}%`;
            }
        }

        // Combine chunks into a single buffer
        const buffer = new Uint8Array(receivedLength);
        let position = 0;
        for (const chunk of chunks) {
            buffer.set(chunk, position);
            position += chunk.length;
        }

        const sizeMB = (buffer.byteLength / 1024 / 1024).toFixed(1);
        if (statusEl) statusEl.innerHTML = `<span style="color: #58a6ff;">🔍 Extracting preview from ${sizeMB} MB file...</span>`;

        const jpegBlob = await window.NefViewer.extractEmbeddedJpeg(buffer.buffer);

        if (jpegBlob) {
            const img = await window.NefViewer.blobToImage(jpegBlob);

            if (canvas) {
                canvas.style.display = 'block';
                canvas.width = Math.min(img.width, 800);
                canvas.height = (img.height / img.width) * canvas.width;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            }

            if (statusEl) {
                statusEl.innerHTML = `<span style="color: #3fb950;">✅ Extracted preview: ${img.width}x${img.height} (${(jpegBlob.size / 1024).toFixed(0)} KB) - Client-extracted</span>`;
            }
        } else {
            // Fallback message with suggestions
            if (statusEl) {
                statusEl.innerHTML = `
                    <div style="color: #d29922;">⚠️ No embedded JPEG found in this RAW file.</div>
                    <div style="color: #8b949e; font-size: 0.85em; margin-top: 8px;">
                        Some RAW files may not contain embedded previews, or the format may not be supported yet.
                        The server-generated thumbnail (if available) can be used instead.
                    </div>
                `;
            }
        }
    } catch (ex) {
        console.error('NefViewer:', ex);
        if (statusEl) {
            statusEl.innerHTML = `
                <div style="color: #f85149;">❌ Error: ${ex.message}</div>
                <div style="color: #8b949e; font-size: 0.85em; margin-top: 8px;">
                    Check browser console for details. The file may be too large or inaccessible.
                </div>
            `;
        }
    }
}

/**
 * Initialize RAW preview buttons across all tabs.
 * Supports Gallery, Stacks, and Culling tabs.
 */
function initRawPreviewButtons() {
    // Configuration for each preview context
    const previewConfigs = [
        {
            buttonId: 'raw-preview-btn',
            statusId: 'raw-preview-status',
            canvasId: 'raw-preview-canvas',
            pathSource: 'textbox',  // Use hidden textbox with elem_id
            pathElementId: 'gallery-selected-path',  // Gradio element ID
            name: 'Gallery'
        },
        {
            buttonId: 'stacks-raw-preview-btn',
            statusId: 'stacks-raw-preview-status',
            canvasId: 'stacks-raw-preview-canvas',
            pathSource: 'textbox',  // Find path from nearby textbox
            name: 'Stacks'
        },
        {
            buttonId: 'cull-raw-preview-btn',
            statusId: 'cull-raw-preview-status',
            canvasId: 'cull-raw-preview-canvas',
            pathSource: 'textbox',  // Find path from nearby textbox
            name: 'Culling'
        }
    ];

    const checkInterval = setInterval(() => {
        let allInitialized = true;

        previewConfigs.forEach(config => {
            const btn = document.getElementById(config.buttonId);
            
            if (btn && !btn.hasAttribute('data-nef-initialized')) {
                btn.setAttribute('data-nef-initialized', 'true');
                
                btn.addEventListener('click', async (e) => {
                    e.preventDefault();
                    e.stopPropagation();

                    const statusEl = document.getElementById(config.statusId);
                    const canvas = document.getElementById(config.canvasId);
                    
                    let filePath = null;

                    // Find the file path based on context
                    if (config.pathSource === 'textbox') {
                        // Gallery/Stacks/Culling tab: find from textbox (Gradio state)
                        if (config.pathElementId) {
                            // Use specific element ID (Gallery tab uses hidden textbox)
                            // Gradio textboxes: try direct ID first, then look for textarea/input inside
                            let pathEl = document.getElementById(config.pathElementId);
                            if (!pathEl) {
                                // Sometimes Gradio adds prefixes, try with common prefixes
                                pathEl = document.querySelector(`[id*="${config.pathElementId}"]`);
                            }
                            if (pathEl) {
                                // For Gradio textboxes, the value is in the textarea or input element
                                const input = pathEl.querySelector('textarea, input[type="text"]') || pathEl;
                                if (input && input.value) {
                                    filePath = input.value;
                                } else if (pathEl.value) {
                                    // Sometimes the element itself has the value
                                    filePath = pathEl.value;
                                }
                            }
                        }
                        
                        // Fallback: find from nearby textbox (Stacks/Culling tabs)
                        if (!filePath) {
                            // Stacks/Culling tab: find from Gradio textbox near the button
                            // Look for textarea with the selected path value
                            const accordion = btn.closest('.accordion');
                            if (accordion) {
                                const textareas = accordion.querySelectorAll('textarea');
                                textareas.forEach(ta => {
                                    if (ta.value && (ta.value.includes('\\') || ta.value.includes('/'))) {
                                        filePath = ta.value;
                                    }
                                });
                            }
                            
                            // Fallback: try finding by looking at nearby input elements
                            if (!filePath) {
                                const row = btn.closest('.row');
                                if (row) {
                                    const textareas = row.querySelectorAll('textarea');
                                    textareas.forEach(ta => {
                                        if (ta.value && (ta.value.includes('\\') || ta.value.includes('/'))) {
                                            filePath = ta.value;
                                        }
                                    });
                                }
                            }
                        }
                    }

                    await handleRawPreview(filePath, statusEl, canvas);
                });

                console.log(`NefViewer: ${config.name} preview button initialized`);
            } else if (!btn) {
                allInitialized = false;
            }
        });

        // Stop checking once all buttons are initialized (or after timeout)
        if (allInitialized) {
            clearInterval(checkInterval);
        }
    }, 1000);

    // Stop checking after 30 seconds
    setTimeout(() => clearInterval(checkInterval), 30000);
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initRawPreviewButtons);
} else {
    initRawPreviewButtons();
}

console.log('NefViewer: Module loaded');
