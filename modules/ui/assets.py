"""
UI assets module for CSS and JavaScript.

This module provides:
- get_css(): Returns the complete CSS stylesheet for the dark theme UI
- get_tree_js(): Returns JavaScript for folder tree interactions and gallery enhancements

The CSS includes styling for:
- Dark theme with GitHub-inspired color palette
- Gallery grid and lightbox preview
- Folder tree navigation
- Stack badges and preview popups
- Image comparison modal
- Lazy loading for full-resolution images

The JavaScript includes:
- Folder tree selection handling
- Gallery lightbox close button
- Stack badge overlays
- Keyboard shortcuts for stack operations
- Image comparison mode
- Lazy full-resolution image loading
"""
# Custom CSS for modern dark UI
custom_css = """
/* ========== ROOT THEME VARIABLES ========== */
:root {
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --bg-tertiary: #21262d;
    --bg-elevated: #30363d;
    --border-color: #30363d;
    --border-subtle: #21262d;
    --text-primary: #e6edf3;
    --text-secondary: #8b949e;
    --text-muted: #6e7681;
    --accent-primary: #58a6ff;
    --accent-success: #3fb950;
    --accent-warning: #d29922;
    --accent-danger: #f85149;
    --accent-purple: #a371f7;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
    --shadow-md: 0 4px 12px rgba(0,0,0,0.4);
    --shadow-lg: 0 8px 24px rgba(0,0,0,0.5);
    --radius-sm: 6px;
    --radius-md: 8px;
    --radius-lg: 12px;
    --transition-fast: 150ms ease;
    --transition-normal: 250ms ease;
}

/* ========== GLOBAL STYLES ========== */
.gradio-container {
    background: linear-gradient(135deg, var(--bg-primary) 0%, #0a0d12 100%) !important;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

.dark {
    --block-background-fill: var(--bg-secondary) !important;
    --block-border-color: var(--border-color) !important;
    --body-background-fill: var(--bg-primary) !important;
    --button-primary-background-fill: var(--accent-primary) !important;
    --button-primary-background-fill-hover: #4895ef !important;
    --input-background-fill: var(--bg-tertiary) !important;
}

/* ========== COMPACT LAYOUT ========== */
/* Reduce vertical gaps between rows and blocks */
.contain > .column > .row,
.contain > .column > .block,
.contain > .column > .form {
    margin-bottom: 8px !important;
}

.contain > .column > .accordion {
    margin-bottom: 8px !important;
}

/* Reduce padding on blocks */
.block {
    padding-top: 8px !important;
    padding-bottom: 8px !important;
}

/* Compact rows */
.row {
    gap: 8px !important;
}

/* ========== HEADER ========== */
h1 {
    font-size: 1.75rem !important;
    font-weight: 600 !important;
    letter-spacing: -0.5px !important;
    color: var(--text-primary) !important;
    margin-bottom: 0.5rem !important;
}

/* ========== TABS ========== */
.tab-nav {
    background: var(--bg-secondary) !important;
    border-radius: var(--radius-lg) !important;
    padding: 4px !important;
    gap: 4px !important;
    border: 1px solid var(--border-color) !important;
}

.tab-nav button {
    background: transparent !important;
    border: none !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-secondary) !important;
    font-weight: 500 !important;
    padding: 10px 20px !important;
    transition: all var(--transition-fast) !important;
}

.tab-nav button:hover {
    background: var(--bg-tertiary) !important;
    color: var(--text-primary) !important;
}

.tab-nav button.selected {
    background: var(--accent-primary) !important;
    color: white !important;
    box-shadow: var(--shadow-sm) !important;
}

/* ========== TREE VIEW ========== */
.tree-content { 
    cursor: pointer; 
    padding: 6px 12px; 
    border-radius: var(--radius-sm); 
    display: inline-block; 
    user-select: none; 
    color: var(--text-secondary);
    transition: all var(--transition-fast);
}

.tree-content:hover { 
    background-color: var(--bg-tertiary); 
    color: var(--text-primary);
}

summary { outline: none; cursor: pointer; }
#folder_tree_selection { display: none; } 

/* ========== GALLERY HEADER ========== */
.gallery-header {
    display: flex !important;
    align-items: center !important;
    gap: 12px !important;
    padding: 16px 20px !important;
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-lg) !important;
    margin-bottom: 16px !important;
}

.folder-badge {
    display: inline-flex !important;
    align-items: center !important;
    gap: 8px !important;
    padding: 8px 16px !important;
    background: linear-gradient(135deg, var(--accent-primary) 0%, var(--accent-purple) 100%) !important;
    border-radius: 20px !important;
    color: white !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    box-shadow: var(--shadow-sm) !important;
}

.folder-badge::before {
    content: "📁";
    font-size: 1rem;
}

/* ========== BUTTONS ========== */
.primary-btn {
    background: linear-gradient(135deg, var(--accent-primary) 0%, #4895ef 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    padding: 10px 24px !important;
    border-radius: var(--radius-md) !important;
    box-shadow: var(--shadow-sm) !important;
    transition: all var(--transition-fast) !important;
}

.primary-btn:hover {
    transform: translateY(-1px) !important;
    box-shadow: var(--shadow-md) !important;
}

.secondary-btn {
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-color) !important;
    color: var(--text-primary) !important;
    font-weight: 500 !important;
    padding: 10px 20px !important;
    border-radius: var(--radius-md) !important;
    transition: all var(--transition-fast) !important;
}

.secondary-btn:hover {
    background: var(--bg-elevated) !important;
    border-color: var(--accent-primary) !important;
}

.danger-btn {
    background: linear-gradient(135deg, var(--accent-danger) 0%, #da3633 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
}

/* ========== GALLERY GRID ========== */
.gallery-container {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-lg) !important;
    padding: 16px !important;
}

/* Reset Gradio gallery wrapper positioning in preview mode */
.gallery-container .wrap,
.gallery-container > div {
    padding: 0 !important;
    margin: 0 !important;
}

/* Ensure the gallery block fills properly */
.block.gallery-container {
    padding: 0 !important;
}

.gallery .gallery-item {
    border-radius: var(--radius-md) !important;
    overflow: hidden !important;
    transition: all var(--transition-normal) !important;
    border: 2px solid transparent !important;
}

.gallery .gallery-item:hover {
    transform: scale(1.02) !important;
    border-color: var(--accent-primary) !important;
    box-shadow: var(--shadow-md) !important;
}

.gallery .gallery-item.selected {
    border-color: var(--accent-success) !important;
    box-shadow: 0 0 0 3px rgba(63, 185, 80, 0.3) !important;
}

/* ========== DETAILS PANEL ========== */
.details-panel {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-lg) !important;
    padding: 20px !important;
}

.score-card {
    background: linear-gradient(135deg, var(--bg-tertiary) 0%, var(--bg-secondary) 100%) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    padding: 16px !important;
    text-align: center !important;
}

.score-value {
    font-size: 2rem !important;
    font-weight: 700 !important;
    color: var(--accent-primary) !important;
}

.score-label {
    font-size: 0.85rem !important;
    color: var(--text-secondary) !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
}

/* ========== INPUTS ========== */
.input-container input,
.input-container textarea {
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-primary) !important;
    padding: 12px 16px !important;
    transition: all var(--transition-fast) !important;
}

.input-container input:focus,
.input-container textarea:focus {
    border-color: var(--accent-primary) !important;
    box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.2) !important;
    outline: none !important;
}

/* ========== DROPDOWNS ========== */
.dropdown-container {
    position: relative !important;
}

select, .svelte-dropdown {
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-primary) !important;
    padding: 10px 14px !important;
}

/* ========== ACCORDION ========== */
.accordion {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-lg) !important;
    overflow: hidden !important;
    margin-bottom: 4px !important;
}

.accordion > .label-wrap {
    background: var(--bg-tertiary) !important;
    padding: 10px 16px !important;
    font-weight: 600 !important;
    color: var(--text-primary) !important;
    border-bottom: 1px solid var(--border-color) !important;
}

/* ========== PAGINATION ========== */
.pagination-container {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 4px !important;
    padding: 6px 12px !important;
    margin: 0 !important;
}

.page-btn {
    min-width: 40px !important;
    padding: 8px 12px !important;
    font-size: 1rem !important;
}

.page-btn:hover {
    background: var(--accent-primary) !important;
    color: white !important;
    font-weight: bold !important;
}

.page-indicator {
    background: var(--bg-tertiary) !important;
    padding: 8px 20px !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-primary) !important;
    font-weight: 500 !important;
    border: 1px solid var(--border-color) !important;
    min-width: 120px !important;
    text-align: center !important;
}

/* ========== MODAL & LIGHTBOX ========== */
/* Only target the main preview image, not thumbnails */
.preview .media-button img, 
.lightbox img, 
.modal img {
    object-fit: contain !important;
    width: auto !important;
    height: auto !important;
    max-width: 100% !important;
    max-height: calc(100% - 80px) !important;
    margin: auto;
}

/* Ensure thumbnail images display properly */
.gallery .thumbnails img,
.gallery .thumbnail-item img,
.thumbnails img,
.thumbnail-item img {
    width: 100% !important;
    height: 100% !important;
    object-fit: cover !important;
    display: block !important;
    opacity: 1 !important;
    visibility: visible !important;
}

/* Gradio Gallery Lightbox/Preview Mode Styling */
.gallery .preview,
.gallery button.preview {
    position: relative !important;
    width: 100% !important;
    display: block !important;
    padding: 0 !important;
    margin: 0 !important;
    left: 0 !important;
    right: 0 !important;
    box-sizing: border-box !important;
}

/* Gallery container should clip images but not buttons (buttons are fixed positioned) */
.gallery-container {
    overflow: hidden !important;
    padding: 0 !important;
}

/* The media-button contains the preview image - make it fill the container */
.gallery button.preview .media-button,
.gallery .preview .media-button {
    overflow: hidden !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 100% !important;
    max-width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
    left: 0 !important;
    right: 0 !important;
    position: relative !important;
    box-sizing: border-box !important;
}

.gallery button.preview .media-button img,
.gallery .preview .media-button img {
    object-fit: contain !important;
    max-width: 100% !important;
    max-height: 100% !important;
    width: auto !important;
    height: auto !important;
    display: block !important;
    margin: 0 auto !important;
}

/* Override hide-top-corner to show controls - be more specific */
/* Since icon-button-wrapper is position:fixed, parent overflow doesn't affect it */
.gallery .hide-top-corner,
.gallery .top-panel,
.gallery .top-panel.hide-top-corner,
.gallery .icon-button-wrapper.hide-top-corner,
.gallery .icon-button-wrapper.top-panel.hide-top-corner {
    opacity: 1 !important;
    visibility: visible !important;
    display: flex !important;
    clip: auto !important;
    clip-path: none !important;
}

/* Style the built-in gallery controls (download, fullscreen, close) */
/* position:fixed removes element from document flow - parent overflow doesn't affect it */
.gallery .icon-buttons,
.gallery .icon-button-wrapper,
.gallery .icon-button-wrapper.top-panel {
    position: fixed !important;
    top: 15px !important;
    right: 180px !important;
    z-index: 99998 !important;
    display: flex !important;
    flex-direction: row !important;
    gap: 8px !important;
    opacity: 1 !important;
    visibility: visible !important;
    width: auto !important;
    max-width: none !important;
    transform: none !important;
}

.gallery .icon-buttons button,
.gallery .icon-button-wrapper button {
    background: var(--bg-elevated) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    padding: 10px 14px !important;
    color: var(--text-primary) !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    opacity: 1 !important;
    visibility: visible !important;
    display: inline-flex !important;
    min-width: auto !important;
    flex-shrink: 0 !important;
}

.gallery .icon-buttons button:hover,
.gallery .icon-button-wrapper button:hover {
    background: var(--accent-primary) !important;
    border-color: var(--accent-primary) !important;
}

/* Navigation hint text at bottom of preview */
.gallery button.preview::after {
    content: "Press ESC or click '✕ Back to Grid' to return" !important;
    position: fixed !important;
    bottom: 80px !important;
    left: 50% !important;
    transform: translateX(-50%) !important;
    z-index: 99990 !important;
    background: rgba(0, 0, 0, 0.85) !important;
    color: #a0a0a0 !important;
    padding: 12px 24px !important;
    border-radius: 25px !important;
    font-size: 13px !important;
    pointer-events: none !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
}

/* Thumbnail strip styling */
.gallery .thumbnails {
    background: rgba(0, 0, 0, 0.9) !important;
    padding: 12px !important;
    border-radius: var(--radius-lg) !important;
    margin: 16px auto 0 auto !important;
    width: 100% !important;
    max-width: 100% !important;
    display: flex !important;
    justify-content: center !important;
    flex-wrap: wrap !important;
    gap: 8px !important;
}

.gallery .thumbnails button,
.gallery .thumbnail-item {
    border-radius: var(--radius-sm) !important;
    border: 2px solid transparent !important;
    transition: all 0.2s ease !important;
    overflow: visible !important;
    background-size: cover !important;
    background-position: center !important;
    background-repeat: no-repeat !important;
}

.gallery .thumbnails button:hover,
.gallery .thumbnail-item:hover {
    border-color: var(--accent-primary) !important;
}

.gallery .thumbnails button.selected,
.gallery .thumbnail-item.selected {
    border-color: var(--accent-warning) !important;
    box-shadow: 0 0 0 2px rgba(210, 153, 34, 0.3) !important;
}

/* Ensure thumbnail images are visible */
.gallery .thumbnails button img,
.gallery .thumbnail-item img {
    width: 100% !important;
    height: 100% !important;
    object-fit: cover !important;
    display: block !important;
    visibility: visible !important;
    opacity: 1 !important;
}

/* Ensure the preview backdrop is clickable to close */
.gallery .preview > div:first-child {
    cursor: pointer !important;
}

/* Preview content divs should contain images properly and be centered */
/* Exclude icon-button-wrapper and thumbnails from these styles */
.gallery button.preview > div:not(.icon-button-wrapper):not(.thumbnails),
.gallery .preview > div:not(.icon-button-wrapper):not(.thumbnails) {
    overflow: hidden !important;
    width: 100% !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    margin: 0 !important;
    padding: 0 !important;
    left: 0 !important;
    right: 0 !important;
    box-sizing: border-box !important;
}

/* Svelte gallery specific overrides */
.svelte-ao1xvt.preview,
button.preview.svelte-ao1xvt {
    padding: 0 !important;
    margin: 0 !important;
    width: 100% !important;
    left: 0 !important;
}

.svelte-ao1xvt.media-button,
button.media-button.svelte-ao1xvt {
    margin: 0 !important;
    padding: 0 !important;
    width: 100% !important;
    left: 0 !important;
}

/* Specifically target the close button in gallery preview */
.gallery button.preview .icon-button-wrapper button,
.gallery .preview .icon-button-wrapper button,
.gallery [class*="close"],
.gallery button[aria-label*="close"],
.gallery button[aria-label*="Close"] {
    opacity: 1 !important;
    visibility: visible !important;
    display: inline-flex !important;
    pointer-events: auto !important;
}

.full-res-modal {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    width: 100% !important;
    height: 100% !important;
    background-color: rgba(0, 0, 0, 0.95) !important;
    z-index: 9999 !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    backdrop-filter: blur(10px) !important;
}

.modal-close-btn {
    position: absolute !important;
    top: 20px !important;
    right: 30px !important;
    z-index: 10000 !important;
    background: var(--bg-elevated) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    padding: 10px 20px !important;
}

.modal-image-container {
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    width: 95% !important;
    height: 90% !important;
    border: none !important;
    background-color: transparent !important;
}

.modal-image-container img {
    max-height: 90vh !important;
    max-width: 95vw !important;
    object-fit: contain !important;
    border-radius: var(--radius-lg) !important;
}

/* ========== STATUS INDICATORS ========== */
.status-badge {
    display: inline-flex !important;
    align-items: center !important;
    gap: 6px !important;
    padding: 6px 12px !important;
    border-radius: 20px !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
}

.status-badge.success {
    background: rgba(63, 185, 80, 0.15) !important;
    color: var(--accent-success) !important;
    border: 1px solid rgba(63, 185, 80, 0.3) !important;
}

.status-badge.warning {
    background: rgba(210, 153, 34, 0.15) !important;
    color: var(--accent-warning) !important;
    border: 1px solid rgba(210, 153, 34, 0.3) !important;
}

/* ========== PROGRESS BAR ========== */
.progress-container {
    background: var(--bg-tertiary) !important;
    border-radius: var(--radius-md) !important;
    height: 8px !important;
    overflow: hidden !important;
}

.progress-bar {
    height: 100% !important;
    background: linear-gradient(90deg, var(--accent-primary) 0%, var(--accent-purple) 100%) !important;
    border-radius: var(--radius-md) !important;
    transition: width var(--transition-normal) !important;
}

/* ========== LABELS ========== */
.label {
    color: var(--text-secondary) !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
    margin-bottom: 6px !important;
}

/* ========== CARDS ========== */
.card {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-lg) !important;
    padding: 20px !important;
    transition: all var(--transition-fast) !important;
}

.card:hover {
    border-color: var(--accent-primary) !important;
    box-shadow: var(--shadow-md) !important;
}

/* ========== EMPTY STATE ========== */
.empty-state {
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 60px 20px !important;
    color: var(--text-muted) !important;
}

.empty-state-icon {
    font-size: 3rem !important;
    margin-bottom: 16px !important;
    opacity: 0.5 !important;
}

/* ========== SCROLLBAR ========== */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

::-webkit-scrollbar-track {
    background: var(--bg-primary);
}

::-webkit-scrollbar-thumb {
    background: var(--bg-elevated);
    border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
    background: var(--text-muted);
}

/* ========== ANIMATION ========== */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

.animate-in {
    animation: fadeIn var(--transition-normal) ease-out !important;
}

/* ========== FILTER CHIPS ========== */
.filter-chip {
    display: inline-flex !important;
    align-items: center !important;
    gap: 6px !important;
    padding: 6px 14px !important;
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 20px !important;
    font-size: 0.85rem !important;
    color: var(--text-secondary) !important;
    transition: all var(--transition-fast) !important;
}

.filter-chip:hover {
    border-color: var(--accent-primary) !important;
    color: var(--text-primary) !important;
}

.filter-chip.active {
    background: var(--accent-primary) !important;
    border-color: var(--accent-primary) !important;
    color: white !important;
}

/* ========== FOLDER CONTEXT BAR ========== */
.folder-context-bar {
    background: linear-gradient(135deg, rgba(88, 166, 255, 0.1) 0%, rgba(163, 113, 247, 0.1) 100%) !important;
    border: 1px solid rgba(88, 166, 255, 0.3) !important;
    border-radius: var(--radius-lg) !important;
    padding: 16px 24px !important;
    margin-bottom: 16px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
}

.folder-path-display {
    display: flex !important;
    align-items: center !important;
    gap: 12px !important;
    color: var(--text-primary) !important;
    font-weight: 500 !important;
}

.folder-icon {
    font-size: 1.5rem !important;
}

/* ========== FOLDER TREE CONTAINER ========== */
.folder-tree-container {
    max-height: 550px !important;
    overflow-y: auto !important;
    overflow-x: hidden !important;
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    padding: 12px !important;
}

/* Folder Tree Status Label - smaller font */
.tree-status-label .output-class {
    font-size: 0.9rem !important;
    font-weight: 400 !important;
    color: var(--text-secondary) !important;
    padding: 8px 12px !important;
}

.folder-tree-container::-webkit-scrollbar {
    width: 8px;
}

.folder-tree-container::-webkit-scrollbar-track {
    background: var(--bg-tertiary);
    border-radius: 4px;
}

.folder-tree-container::-webkit-scrollbar-thumb {
    background: var(--bg-elevated);
    border-radius: 4px;
}

.folder-tree-container::-webkit-scrollbar-thumb:hover {
    background: var(--accent-primary);
}

/* ========== HIGHLIGHTED TEXT (KEYWORDS) ========== */
/* Hide category labels (C0, C1, etc.) */
[data-testid="highlighted-text"] .label {
    display: none !important;
}

/* Hide close/cross button */
[data-testid="highlighted-text"] .label-clear-button {
    display: none !important;
}

/* White text for keyword tags */
[data-testid="highlighted-text"] .textspan {
    color: white !important;
    font-weight: 500 !important;
    padding: 4px 12px !important;
    border-radius: 6px !important;
    margin: 2px !important;
}

[data-testid="highlighted-text"] .text {
    color: white !important;
}

/* ========== STACK BADGE OVERLAY ========== */
.stack-badge {
    position: absolute;
    top: 6px;
    right: 6px;
    background: linear-gradient(135deg, #58a6ff 0%, #a371f7 100%);
    color: white;
    font-size: 11px;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 10px;
    min-width: 20px;
    text-align: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.5);
    z-index: 10;
    pointer-events: none;
    font-family: system-ui, -apple-system, sans-serif;
}

.stack-badge.large {
    background: linear-gradient(135deg, #3fb950 0%, #238636 100%);
}

/* ========== STACK INLINE PREVIEW (Hover Expand) ========== */
.stack-preview-popup {
    position: fixed;
    background: var(--bg-secondary, #161b22);
    border: 1px solid var(--border-color, #30363d);
    border-radius: 12px;
    padding: 12px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
    z-index: 9999;
    max-width: 400px;
    display: none;
}

.stack-preview-popup.visible {
    display: block;
    animation: fadeInScale 0.15s ease-out;
}

@keyframes fadeInScale {
    from {
        opacity: 0;
        transform: scale(0.95);
    }
    to {
        opacity: 1;
        transform: scale(1);
    }
}

.stack-preview-header {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary, #e6edf3);
    margin-bottom: 8px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--border-subtle, #21262d);
}

.stack-preview-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
}

.stack-preview-thumb {
    width: 80px;
    height: 80px;
    object-fit: cover;
    border-radius: 6px;
    border: 2px solid transparent;
    transition: border-color 0.15s ease;
}

.stack-preview-thumb:hover {
    border-color: var(--accent-primary, #58a6ff);
}

.stack-preview-thumb.best {
    border-color: var(--accent-success, #3fb950);
}

.stack-preview-more {
    width: 80px;
    height: 80px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-tertiary, #21262d);
    border-radius: 6px;
    color: var(--text-secondary, #8b949e);
    font-size: 12px;
    font-weight: 500;
}

/* ========== IMAGE COMPARISON VIEW ========== */
.compare-modal {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    width: 100% !important;
    height: 100% !important;
    background: rgba(0, 0, 0, 0.95) !important;
    z-index: 10000 !important;
    display: flex !important;
    flex-direction: column !important;
    padding: 20px !important;
    box-sizing: border-box !important;
}

.compare-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 20px;
    background: var(--bg-secondary, #161b22);
    border-radius: 10px;
    margin-bottom: 15px;
}

.compare-title {
    font-size: 1.2rem;
    font-weight: 600;
    color: var(--text-primary, #e6edf3);
}

.compare-grid {
    display: grid;
    gap: 15px;
    flex: 1;
    overflow: hidden;
}

.compare-grid.cols-2 {
    grid-template-columns: repeat(2, 1fr);
}

.compare-grid.cols-3 {
    grid-template-columns: repeat(3, 1fr);
}

.compare-grid.cols-4 {
    grid-template-columns: repeat(2, 1fr);
    grid-template-rows: repeat(2, 1fr);
}

.compare-item {
    background: var(--bg-secondary, #161b22);
    border: 1px solid var(--border-color, #30363d);
    border-radius: 10px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}

.compare-item img {
    width: 100%;
    height: calc(100% - 60px);
    object-fit: contain;
    background: var(--bg-primary, #0d1117);
}

.compare-item-info {
    padding: 10px 15px;
    background: var(--bg-tertiary, #21262d);
    color: var(--text-primary, #e6edf3);
    font-size: 0.9rem;
}

.compare-item-score {
    display: flex;
    gap: 15px;
    margin-top: 5px;
}

.compare-item-score span {
    color: var(--accent-primary, #58a6ff);
    font-weight: 600;
}
"""

def get_css():
    return custom_css

tree_js = r"""
<script src="/file=static/js/libraw-viewer.js"></script>
<script>
window.selectFolder = function(e, path) {
    e.preventDefault();
    e.stopPropagation();
    
    // Clear selection style
    var all = document.querySelectorAll('.tree-content');
    for (var i=0; i<all.length; i++) {
        all[i].style.backgroundColor = '';
        all[i].style.color = '';
    }
    
    // Set new style
    e.target.style.backgroundColor = '#2196f3';
    e.target.style.color = 'white';
    
    // Update hidden input
    var ta = document.querySelector('#folder_tree_selection textarea');
    if (ta) {
        var descriptor = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value");
        descriptor.set.call(ta, path);
        ta.dispatchEvent(new Event('input', { bubbles: true }));
    }
}

// Gallery lightbox close button handler
function initGalleryCloseButton() {
    let closeBtn = null;
    
    function createCloseButton() {
        if (closeBtn && document.body.contains(closeBtn)) return closeBtn;
        
        closeBtn = document.createElement('button');
        closeBtn.id = 'gallery-close-btn';
        closeBtn.innerHTML = '✕ Back to Grid';
        closeBtn.style.cssText = `
            position: fixed;
            top: 15px;
            right: 15px;
            z-index: 99999;
            background: linear-gradient(135deg, #f85149 0%, #da3633 100%);
            color: white;
            padding: 14px 28px;
            border-radius: 10px;
            font-size: 15px;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 4px 20px rgba(248, 81, 73, 0.5);
            border: 2px solid rgba(255,255,255,0.2);
            transition: all 0.2s ease;
            font-family: system-ui, -apple-system, sans-serif;
            letter-spacing: 0.5px;
        `;
        closeBtn.onmouseenter = function() {
            this.style.transform = 'scale(1.08)';
            this.style.boxShadow = '0 6px 25px rgba(248, 81, 73, 0.7)';
        };
        closeBtn.onmouseleave = function() {
            this.style.transform = 'scale(1)';
            this.style.boxShadow = '0 4px 20px rgba(248, 81, 73, 0.5)';
        };
        closeBtn.onclick = function(e) {
            e.preventDefault();
            e.stopPropagation();
            closePreview();
        };
        return closeBtn;
    }
    
    function closePreview() {
        // Method 1: Find and click the grid/thumbnail view
        const gridButtons = document.querySelectorAll('.gallery button, .gallery .thumbnail, .gallery [class*="grid"]');
        
        // Method 2: Simulate Escape key
        document.dispatchEvent(new KeyboardEvent('keydown', { 
            key: 'Escape', 
            code: 'Escape', 
            keyCode: 27, 
            which: 27, 
            bubbles: true,
            cancelable: true
        }));
        
        // Method 3: Find preview container and trigger close
        const previewBtn = document.querySelector('.gallery button.preview');
        if (previewBtn) {
            // Try to find a close mechanism
            const svgIcons = previewBtn.querySelectorAll('svg');
            svgIcons.forEach(svg => {
                if (svg.closest('button')) {
                    svg.closest('button').click();
                }
            });
        }
        
        // Method 4: Click on the preview backdrop area
        setTimeout(() => {
            const preview = document.querySelector('.gallery .preview, .gallery button.preview');
            if (preview) {
                // Dispatch escape again
                preview.dispatchEvent(new KeyboardEvent('keydown', { 
                    key: 'Escape', 
                    bubbles: true 
                }));
            }
            removeCloseButton();
        }, 100);
    }
    
    function removeCloseButton() {
        const btn = document.getElementById('gallery-close-btn');
        if (btn) btn.remove();
        closeBtn = null;
    }
    
    function checkForPreviewMode() {
        // Check if gallery is in preview/lightbox mode
        const previewActive = document.querySelector('.gallery button.preview');
        const hasLargeImage = document.querySelector('.gallery .preview img, .gallery button.preview img');
        const thumbnailStrip = document.querySelector('.gallery .thumbnails, .gallery [class*="thumbnail"]');
        
        // If preview mode detected (large image with thumbnail strip)
        if (previewActive || (hasLargeImage && thumbnailStrip)) {
            if (!document.getElementById('gallery-close-btn')) {
                const btn = createCloseButton();
                document.body.appendChild(btn);
            }
        } else {
            removeCloseButton();
        }
    }
    
    // Watch for DOM changes
    const observer = new MutationObserver(function(mutations) {
        checkForPreviewMode();
    });
    
    observer.observe(document.body, { 
        childList: true, 
        subtree: true, 
        attributes: true,
        attributeFilter: ['class', 'style']
    });
    
    // Also check periodically for edge cases
    setInterval(checkForPreviewMode, 500);
    
    // Initial check
    setTimeout(checkForPreviewMode, 1000);
}

// Handle Escape key globally
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const btn = document.getElementById('gallery-close-btn');
        if (btn) btn.remove();
    }
});

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initGalleryCloseButton);
} else {
    initGalleryCloseButton();
}

// ========== STACK BADGE OVERLAY ==========
function initStackBadges() {
    function addBadgesToStackGallery() {
        // Find the Stacks tab gallery (first gallery in the Stacks tab)
        const stacksTab = document.querySelector('[id*="stacks"]');
        if (!stacksTab) return;
        
        // Find all gallery items in the stacks section
        const galleries = document.querySelectorAll('.gallery');
        
        galleries.forEach(gallery => {
            // Look for stack gallery items (they have captions with "X imgs")
            const items = gallery.querySelectorAll('.thumbnail-item, .gallery-item, [class*="thumbnail"]');
            
            items.forEach(item => {
                // Skip if already has badge
                if (item.querySelector('.stack-badge')) return;
                
                // Get the caption/label
                const caption = item.querySelector('.caption, .label, [class*="caption"]');
                if (!caption) return;
                
                const text = caption.textContent || '';
                // Match pattern like "(5 imgs)" or "(12 imgs)"
                const match = text.match(/\((\d+)\s*imgs?\)/i);
                
                if (match) {
                    const count = parseInt(match[1], 10);
                    if (count >= 2) {
                        // Make item position relative if not already
                        const computed = window.getComputedStyle(item);
                        if (computed.position === 'static') {
                            item.style.position = 'relative';
                        }
                        
                        // Create and add badge
                        const badge = document.createElement('span');
                        badge.className = 'stack-badge' + (count >= 10 ? ' large' : '');
                        badge.textContent = count;
                        item.appendChild(badge);
                    }
                }
            });
        });
    }
    
    // Watch for DOM changes (galleries update dynamically)
    const badgeObserver = new MutationObserver(function(mutations) {
        // Debounce
        clearTimeout(window._stackBadgeTimeout);
        window._stackBadgeTimeout = setTimeout(addBadgesToStackGallery, 200);
    });
    
    badgeObserver.observe(document.body, { 
        childList: true, 
        subtree: true 
    });
    
    // Initial run
    setTimeout(addBadgesToStackGallery, 1000);
    
    // Also run on tab changes
    document.addEventListener('click', function(e) {
        if (e.target.closest('[role="tab"]')) {
            setTimeout(addBadgesToStackGallery, 300);
        }
    });
}

// Initialize stack badges
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initStackBadges);
} else {
    initStackBadges();
}

// ========== KEYBOARD SHORTCUTS FOR STACK OPERATIONS ==========
function initStackKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        // Only trigger if no input/textarea is focused
        const activeEl = document.activeElement;
        if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA')) {
            return;
        }
        
        // Ctrl+G -> Group Selected
        if (e.ctrlKey && !e.shiftKey && e.key.toLowerCase() === 'g') {
            e.preventDefault();
            const groupBtn = document.getElementById('stack-group-btn');
            if (groupBtn) {
                groupBtn.click();
                console.log('Keyboard: Ctrl+G -> Group Selected');
            }
        }
        
        // Ctrl+Shift+G -> Ungroup All
        if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'g') {
            e.preventDefault();
            const ungroupBtn = document.getElementById('stack-ungroup-btn');
            if (ungroupBtn) {
                ungroupBtn.click();
                console.log('Keyboard: Ctrl+Shift+G -> Ungroup All');
            }
        }
        
        // Ctrl+R -> Remove from Stack
        if (e.ctrlKey && !e.shiftKey && e.key.toLowerCase() === 'r') {
            // Check if we're on stacks tab to avoid conflicts
            const stacksTab = document.querySelector('[id*="stacks"].tabitem--selected, [id*="stacks"][aria-selected="true"]');
            if (stacksTab) {
                e.preventDefault();
                const removeBtn = document.getElementById('stack-remove-btn');
                if (removeBtn) {
                    removeBtn.click();
                    console.log('Keyboard: Ctrl+R -> Remove from Stack');
                }
            }
        }
    });
    
    console.log('Stack keyboard shortcuts initialized: Ctrl+G (Group), Ctrl+Shift+G (Ungroup), Ctrl+R (Remove)');
}

// Initialize keyboard shortcuts
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initStackKeyboardShortcuts);
} else {
    initStackKeyboardShortcuts();
}

// ========== STACK INLINE EXPAND/COLLAPSE ==========
function initStackExpandCollapse() {
    let currentExpandedStack = null;
    
    // Add visual feedback for expand/collapse state
    function updateExpandState() {
        const stacksTab = document.querySelector('[id*="stacks"]');
        if (!stacksTab) return;
        
        // Find the content gallery section
        const contentSection = stacksTab.querySelector('[id*="stack"][class*="gallery"]');
        const stackItems = stacksTab.querySelectorAll('.gallery .thumbnail-item, .gallery .gallery-item, .gallery [class*="thumbnail"]');
        
        // Add expand indicator to stack items
        stackItems.forEach((item, index) => {
            if (item.querySelector('.expand-indicator')) return;
            
            const indicator = document.createElement('span');
            indicator.className = 'expand-indicator';
            indicator.style.cssText = `
                position: absolute;
                bottom: 6px;
                left: 6px;
                font-size: 14px;
                opacity: 0.7;
                pointer-events: none;
                transition: transform 0.2s ease;
            `;
            indicator.textContent = '▼';
            
            const computed = window.getComputedStyle(item);
            if (computed.position === 'static') {
                item.style.position = 'relative';
            }
            item.appendChild(indicator);
        });
    }
    
    // Create collapse button for content gallery
    function addCollapseButton() {
        const stacksTab = document.querySelector('[id*="stacks"]');
        if (!stacksTab) return;
        
        // Find the content gallery header
        const contentHeaders = stacksTab.querySelectorAll('h3, .markdown');
        contentHeaders.forEach(header => {
            if (header.textContent.includes('Stack Contents') && !header.querySelector('.collapse-btn')) {
                const btn = document.createElement('button');
                btn.className = 'collapse-btn';
                btn.innerHTML = '▲ Collapse';
                btn.style.cssText = `
                    margin-left: 10px;
                    padding: 4px 12px;
                    font-size: 11px;
                    background: var(--bg-tertiary, #21262d);
                    border: 1px solid var(--border-color, #30363d);
                    border-radius: 6px;
                    color: var(--text-secondary, #8b949e);
                    cursor: pointer;
                    vertical-align: middle;
                `;
                btn.onclick = function(e) {
                    e.preventDefault();
                    const gallery = this.closest('[id*="stacks"]').querySelector('.gallery:not(:first-child)');
                    if (gallery) {
                        const isCollapsed = gallery.style.display === 'none';
                        gallery.style.display = isCollapsed ? '' : 'none';
                        this.innerHTML = isCollapsed ? '▲ Collapse' : '▼ Expand';
                    }
                };
                header.appendChild(btn);
            }
        });
    }
    
    // Observe DOM changes
    const expandObserver = new MutationObserver(function() {
        clearTimeout(window._expandTimeout);
        window._expandTimeout = setTimeout(() => {
            updateExpandState();
            addCollapseButton();
        }, 300);
    });
    
    expandObserver.observe(document.body, { childList: true, subtree: true });
    
    // Initial setup
    setTimeout(() => {
        updateExpandState();
        addCollapseButton();
    }, 1500);
}

// Initialize expand/collapse
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initStackExpandCollapse);
} else {
    initStackExpandCollapse();
}

// ========== IMAGE COMPARISON VIEW ==========
window.compareImages = [];
window.maxCompareImages = 4;

function initCompareMode() {
    // Add compare button to image details
    const addBtn = document.getElementById('compare-add-btn');
    if (addBtn && !addBtn.hasAttribute('data-compare-init')) {
        addBtn.setAttribute('data-compare-init', 'true');
        addBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            // Get current image path from JSON details
            let imagePath = null;
            const jsonElements = document.querySelectorAll('.json-holder pre, [data-testid="json"] pre');
            jsonElements.forEach(el => {
                try {
                    const data = JSON.parse(el.textContent);
                    if (data && data.file_path) {
                        imagePath = data.file_path;
                    }
                } catch (ex) {}
            });
            
            if (!imagePath) {
                alert('Select an image first');
                return;
            }
            
            // Add to compare list (max 4)
            if (window.compareImages.length >= window.maxCompareImages) {
                window.compareImages.shift(); // Remove oldest
            }
            
            if (!window.compareImages.includes(imagePath)) {
                window.compareImages.push(imagePath);
            }
            
            // Show visual feedback
            const count = window.compareImages.length;
            this.textContent = `📊 Compare (${count}/${window.maxCompareImages})`;
            
            if (count >= 2) {
                showCompareView();
            }
        });
    }
}

function showCompareView() {
    if (window.compareImages.length < 2) {
        alert('Add at least 2 images to compare');
        return;
    }
    
    // Create modal
    const modal = document.createElement('div');
    modal.className = 'compare-modal';
    modal.innerHTML = `
        <div class="compare-header">
            <span class="compare-title">📊 Image Comparison (${window.compareImages.length} images)</span>
            <button onclick="closeCompareView()" style="background: #f85149; border: none; color: white; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600;">✕ Close</button>
        </div>
        <div class="compare-grid cols-${Math.min(window.compareImages.length, 4)}">
            ${window.compareImages.map((path, i) => `
                <div class="compare-item">
                    <img src="/file=${path.replace(/\\\\/g, '/')}" alt="Image ${i+1}">
                    <div class="compare-item-info">
                        <strong>${path.split(/[/\\\\]/).pop()}</strong>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
    
    document.body.appendChild(modal);
}

function closeCompareView() {
    const modal = document.querySelector('.compare-modal');
    if (modal) {
        modal.remove();
    }
    window.compareImages = [];
    
    // Reset button text
    const addBtn = document.getElementById('compare-add-btn');
    if (addBtn) {
        addBtn.textContent = '📊 Add to Compare';
    }
}

// Initialize compare mode
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCompareMode);
} else {
    initCompareMode();
}

// Re-init on DOM changes (Gradio rerenders)
const compareObserver = new MutationObserver(() => {
    clearTimeout(window._compareInitTimeout);
    window._compareInitTimeout = setTimeout(initCompareMode, 500);
});
compareObserver.observe(document.body, { childList: true, subtree: true });

// ========== LAZY LOAD FULL RESOLUTION ==========
function initLazyFullResolution() {
    console.log("Initializing Lazy Full Resolution Loader");
    let currentPreviewId = 0;
    let loadTimeout = null;
    let abortController = null;
    let previousObjectURL = null;  // Track ObjectURL for cleanup
    const LOAD_DELAY_MS = 600;  // Wait 600ms before loading full res (debounce)
    
    // Find the preview image element
    function getCurrentPreviewImg() {
        // Gradio 3/4 structure vary, check multiple selectors
        return document.querySelector('.gallery .preview img, .gallery button.preview img, img.preview-image');
    }
    
    // Show a subtle loading indicator
    function showLoadingIndicator(img) {
        if (!img || img.parentNode.querySelector('.full-res-loader')) return;
        
        const loader = document.createElement('div');
        loader.className = 'full-res-loader';
        loader.innerHTML = `
            <div style="
                position: absolute; 
                top: 50%; 
                left: 50%; 
                transform: translate(-50%, -50%);
                background: rgba(0,0,0,0.6);
                color: white;
                padding: 8px 16px;
                border-radius: 20px;
                font-size: 13px;
                pointer-events: none;
                z-index: 10;
                backdrop-filter: blur(4px);
                border: 1px solid rgba(255,255,255,0.1);
                display: flex;
                align-items: center;
                gap: 8px;
            ">
                <div class="spinner" style="
                    width: 14px; 
                    height: 14px; 
                    border: 2px solid rgba(255,255,255,0.3); 
                    border-top: 2px solid white; 
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                "></div>
                <span>Loading Full Res...</span>
            </div>
            <style>@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }</style>
        `;
        
        // Position relative to parent if needed
        if (getComputedStyle(img.parentNode).position === 'static') {
            img.parentNode.style.position = 'relative';
        }
        
        img.parentNode.appendChild(loader);
    }
    
    function hideLoadingIndicator(img) {
        if (!img) return;
        const loader = img.parentNode.querySelector('.full-res-loader');
        if (loader) loader.remove();
    }
    
    // BETTER APPROACH: Use the selected gallery item data
    function getSelectedImagePath() {
        // Try to find the file path from the details panel (which updates instantly on click)
        // This is robust because it comes from the server metadata
        const jsonElements = document.querySelectorAll('.json-holder pre, [data-testid="json"] pre');
        for (const el of jsonElements) {
            try {
                const data = JSON.parse(el.textContent);
                if (data && data.file_path) {
                    return data.file_path;
                }
            } catch (e) {}
        }
        
        // Fallback: visible path textbox?
        // In webui.py we have 'stacks_selected_path' or similar components
        const pathInputs = document.querySelectorAll('textarea[label="Selected Image"], input[label="Selected Image"]');
        for (const input of pathInputs) {
            if (input.value && input.value.trim().length > 1) {
                return input.value;
            }
        }
        
        return null;
    }
    
    function loadFullResolution(imgPath, previewId, imgElement) {
        // Cancel previous load
        if (abortController) {
            abortController.abort();
            abortController = null;
        }
        
        // Cleanup previous ObjectURL to prevent memory leak
        if (previousObjectURL) {
            URL.revokeObjectURL(previousObjectURL);
            previousObjectURL = null;
        }
        
        // If previewId changed, don't load (stale)
        if (previewId !== currentPreviewId) return;
        
        abortController = new AbortController();
        
        // Determine URL
        // If it's a RAW file, use our API. Else use /file=
        const ext = imgPath.split('.').pop().toLowerCase();
        const isRaw = ['nef', 'cr2', 'arw', 'dng', 'orf', 'nrw', 'cr3', 'rw2'].includes(ext);
        
        let url = '';
        if (isRaw) {
             url = `/api/raw-preview?path=${encodeURIComponent(imgPath)}`;
        } else {
             // For standard images, append a distinct param to bypass cache or ensure full load
             url = `/file=${imgPath}`;
        }
        
        showLoadingIndicator(imgElement);
        
        fetch(url, { signal: abortController.signal })
            .then(response => {
                if (!response.ok) throw new Error('Network response was not ok');
                return response.blob();
            })
            .then(blob => {
                if (previewId !== currentPreviewId) {
                    // Changed, discard blob (no need to create ObjectURL just to revoke)
                    return;
                }
                
                const objectURL = URL.createObjectURL(blob);
                previousObjectURL = objectURL;  // Track for cleanup
                imgElement.onload = () => {
                   hideLoadingIndicator(imgElement);
                };
                imgElement.src = objectURL;
                
                // Cleanup controller
                abortController = null;
            })
            .catch(err => {
                if (err.name !== 'AbortError') {
                    console.error('Full res load error:', err);
                }
                hideLoadingIndicator(imgElement);
            });
    }
    
    function handlePreviewChange() {
        const img = getCurrentPreviewImg();
        
        // If no preview image, we might be in grid mode.
        if (!img) {
            // Cancel any pending
            if (loadTimeout) clearTimeout(loadTimeout);
            if (abortController) abortController.abort();
            
            // Cleanup previous ObjectURL
            if (previousObjectURL) {
                URL.revokeObjectURL(previousObjectURL);
                previousObjectURL = null;
            }
            
            currentPreviewId++; 
            return;
        }
        
        // Retrieve path
        const path = getSelectedImagePath();
        if (!path) return; // Wait until details populate
        
        // Check if we already loaded this path for this session?
        if (img.dataset.fullResPath === path) {
             return; // Already initiated or loaded
        }
        
        // New image detected!
        currentPreviewId++;
        const myPreviewId = currentPreviewId;
        
        img.dataset.fullResPath = path; // Mark as handled
        
        // Cancel previous
        if (loadTimeout) clearTimeout(loadTimeout);
        if (abortController) abortController.abort();
        
        // Cleanup previous ObjectURL (if we are switching faster than load completes)
        if (previousObjectURL) {
            URL.revokeObjectURL(previousObjectURL);
            previousObjectURL = null;
        }
        
        // Set delay
        loadTimeout = setTimeout(() => {
            loadFullResolution(path, myPreviewId, img);
        }, LOAD_DELAY_MS);
    }
    
    // Watch for DOM changes to detect when preview opens or changes
    // The gallery preview creates a new <img> or changes src
    const observer = new MutationObserver((mutations) => {
        // Quick check if preview exists
        if (document.querySelector('.gallery .preview')) {
             handlePreviewChange();
        }
    });
    
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['src', 'style'] });
}

// Initialize Lazy Loader
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initLazyFullResolution);
} else {
    initLazyFullResolution();
}

</script>
"""

def get_tree_js():
    return tree_js
