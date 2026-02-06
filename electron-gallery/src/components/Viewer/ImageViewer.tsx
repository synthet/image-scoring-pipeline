import React, { useEffect } from 'react';
import { X, Star, FileText } from 'lucide-react';

interface Image {
    id: number;
    file_path: string;
    file_name: string;
    score_general: number;
    rating: number;
    label: string | null;
    created_at?: string;
    thumbnail_path?: string;
}

interface ImageViewerProps {
    image: Image;
    onClose: () => void;
    allImages?: Image[];
    currentIndex?: number;
    onNavigate?: (newIndex: number) => void;
}

const isWebSafe = (filename: string) => {
    const ext = filename.split('.').pop()?.toLowerCase() || '';
    return ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'].includes(ext);
};

const isRaw = (filename: string) => {
    const ext = filename.split('.').pop()?.toLowerCase() || '';
    return ['nef', 'nrw', 'cr2', 'cr3', 'arw', 'orf', 'rw2', 'dng'].includes(ext);
};


const ScoreBar = ({ label, value, color = '#ff9800' }: { label: string, value: number, color?: string }) => (
    <div style={{ marginBottom: 10 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8em', color: '#888', textTransform: 'uppercase', marginBottom: 2 }}>
            <span>{label}</span>
            <span>{Math.round(value * 100)}%</span>
        </div>
        <div style={{ height: 4, background: '#333', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{ width: `${value * 100}%`, height: '100%', background: color }} />
        </div>
    </div>
);

export const ImageViewer: React.FC<ImageViewerProps> = ({
    image: initialImage,
    onClose,
    allImages = [],
    currentIndex = 0,
    onNavigate
}) => {
    const [image, setImage] = React.useState<any>(initialImage);
    const [detailsLoaded, setDetailsLoaded] = React.useState(false);

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                onClose();
            } else if (e.key === 'ArrowLeft' && onNavigate && currentIndex > 0) {
                onNavigate(currentIndex - 1);
            } else if (e.key === 'ArrowRight' && onNavigate && allImages && currentIndex < allImages.length - 1) {
                onNavigate(currentIndex + 1);
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [onClose, onNavigate, currentIndex, allImages]);

    // Update image when navigating
    useEffect(() => {
        if (allImages && allImages[currentIndex]) {
            setImage(allImages[currentIndex]);
            setDetailsLoaded(false);
        }
    }, [currentIndex, allImages]);

    // Fetch full details
    useEffect(() => {
        let active = true;
        const fetchDetails = async () => {
            if (!window.electron) return;
            try {
                console.log('[ImageViewer] Fetching details for image ID:', image.id);
                const details = await window.electron.getImageDetails(image.id);
                console.log('[ImageViewer] Received details:', details);
                if (active && details) {
                    setImage(details);
                    setDetailsLoaded(true);
                    console.log('[ImageViewer] Details loaded successfully');
                } else {
                    console.warn('[ImageViewer] No details returned or component unmounted');
                }
            } catch (e) {
                console.error("Failed to fetch image details:", e);
            }
        };
        fetchDetails();
        return () => { active = false; };
    }, [image.id]);

    const [previewSrc, setPreviewSrc] = React.useState<string>('');
    const [loading, setLoading] = React.useState(false);
    const [error, setError] = React.useState<string | null>(null);

    // Load image effect
    useEffect(() => {
        let active = true;
        let objectUrl: string | null = null;

        const loadImage = async () => {
            setLoading(true);
            setError(null);
            setPreviewSrc('');

            try {
                // Use win_path if available (from detailed fetch), else fallback to file_path
                const pathSchema = image.win_path || image.file_path;

                // Case 1: Web safe image - use direct path
                if (isWebSafe(image.file_name)) {
                    if (active) setPreviewSrc(`media://${pathSchema}`);
                    return;
                }

                // Case 2: RAW image - try to extract/decode
                if (isRaw(image.file_name)) {
                    try {
                        // Use new extractWithFallback method which:
                        // 1. Tries server-side exiftool extraction (best for Z9/Z6/Z8)
                        // 2. Falls back to client-side TIFF SubIFD parsing
                        // 3. Falls back to JPEG marker scanning
                        const { nefViewer } = await import('../../utils/nefViewer');
                        const blob = await nefViewer.extractWithFallback(pathSchema);

                        if (blob && active) {
                            objectUrl = URL.createObjectURL(blob);
                            setPreviewSrc(objectUrl);
                            return;
                        }
                    } catch (err) {
                        console.error('Failed to process RAW file:', err);
                        // Fallthrough to thumbnail
                    }
                }

                // Case 3: Fallback to thumbnail (server generated) or show error
                if (image.thumbnail_path && active) {
                    setPreviewSrc(`media://${image.thumbnail_path}`);
                } else if (active) {
                    setError('No preview available');
                }

            } catch (err) {
                console.error('Image loading error:', err);
                if (active) setError('Failed to load image');
            } finally {
                if (active) setLoading(false);
            }
        };

        loadImage();

        return () => {
            active = false;
            if (objectUrl) URL.revokeObjectURL(objectUrl);
        };
    }, [image]);

    const src = previewSrc;

    // Format date
    const dateStr = image.created_at ? new Date(image.created_at).toLocaleString() : 'Unknown';

    // Label color
    const labelColor = image.label === 'Red' ? '#e53935' :
        image.label === 'Yellow' ? '#fdd835' :
            image.label === 'Green' ? '#43a047' :
                image.label === 'Blue' ? '#1e88e5' :
                    image.label === 'Purple' ? '#8e24aa' : 'None';

    return (
        <div style={{
            position: 'fixed',
            top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.95)',
            zIndex: 1000,
            display: 'flex',
            flexDirection: 'row'
        }}>
            {/* Main Image Area */}
            <div style={{ flex: 1, position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
                <button
                    onClick={onClose}
                    style={{
                        position: 'absolute',
                        top: 20,
                        left: 20,
                        background: 'rgba(0,0,0,0.5)',
                        border: 'none',
                        borderRadius: '50%',
                        width: 40,
                        height: 40,
                        color: 'white',
                        cursor: 'pointer',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        zIndex: 10
                    }}
                >
                    <X size={24} />
                </button>

                {/* Image Position Indicator */}
                {allImages && allImages.length > 1 && (
                    <div style={{
                        position: 'absolute',
                        top: 20,
                        right: 20,
                        background: 'rgba(0,0,0,0.7)',
                        padding: '8px 16px',
                        borderRadius: 4,
                        color: '#ccc',
                        fontSize: '0.9em',
                        zIndex: 10
                    }}>
                        {currentIndex + 1} / {allImages.length}
                    </div>
                )}

                {loading ? (
                    <div style={{ color: '#aaa' }}>Loading preview...</div>
                ) : src ? (
                    <img
                        src={src}
                        alt={image.file_name}
                        style={{ maxWidth: '95%', maxHeight: '95%', objectFit: 'contain', boxShadow: '0 0 20px rgba(0,0,0,0.5)' }}
                    />
                ) : (
                    <div style={{ color: '#666' }}>{error || 'Image not found'}</div>
                )}
            </div>

            {/* Metadata Sidebar */}
            <div style={{
                width: 350,
                backgroundColor: '#1e1e1e',
                borderLeft: '1px solid #333',
                padding: 20,
                display: 'flex',
                flexDirection: 'column',
                gap: 20,
                overflowY: 'auto'
            }}>
                <div>
                    <h2 style={{ fontSize: '1.2em', margin: '0 0 10px 0', wordBreak: 'break-all' }}>{image.file_name}</h2>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#aaa', fontSize: '0.9em' }}>
                        <FileText size={14} />
                        <span style={{ wordBreak: 'break-all' }}>{image.win_path || image.file_path}</span>
                    </div>
                    <div style={{ marginTop: 5, fontSize: '0.8em', color: '#666' }}>
                        {dateStr}
                    </div>
                </div>

                {image.title && (
                    <div>
                        <div style={{ fontSize: '0.8em', color: '#888', marginBottom: 4 }}>TITLE</div>
                        <div style={{ fontSize: '1em' }}>{image.title}</div>
                    </div>
                )}

                {image.description && (
                    <div>
                        <div style={{ fontSize: '0.8em', color: '#888', marginBottom: 4 }}>DESCRIPTION</div>
                        <div style={{ fontSize: '0.9em', color: '#ccc', whiteSpace: 'pre-wrap' }}>{image.description}</div>
                    </div>
                )}

                <div style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '10px 0', borderTop: '1px solid #333', borderBottom: '1px solid #333' }}>
                    <div style={{ flex: 1 }}>
                        <div style={{ fontSize: '0.8em', color: '#888', marginBottom: 4 }}>RATING</div>
                        <div style={{ color: '#ffd700', fontSize: '1.1em', display: 'flex', alignItems: 'center' }}>
                            <Star fill="#ffd700" size={16} style={{ marginRight: 4 }} />
                            {image.rating}
                        </div>
                    </div>

                    <div style={{ width: 1, height: 30, background: '#333' }}></div>

                    <div style={{ flex: 1 }}>
                        <div style={{ fontSize: '0.8em', color: '#888', marginBottom: 4 }}>SCORE</div>
                        <div style={{ fontSize: '1.1em', fontWeight: 'bold' }}>{image.score_general?.toFixed(1) || '0.0'}</div>
                    </div>
                </div>

                <div>
                    <div style={{ fontSize: '0.8em', color: '#888', marginBottom: 8 }}>LABEL</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{
                            width: 16, height: 16, borderRadius: '50%',
                            backgroundColor: labelColor,
                            border: labelColor === 'None' ? '1px solid #555' : 'none'
                        }} />
                        <span>{image.label || 'None'}</span>
                    </div>
                </div>

                {!detailsLoaded && (
                    <div style={{ borderTop: '1px solid #333', paddingTop: 15, color: '#888', fontSize: '0.85em', fontStyle: 'italic' }}>
                        Loading detailed information...
                    </div>
                )}

                {detailsLoaded && (
                    <>
                        {/* Scores Section */}
                        <div style={{ borderTop: '1px solid #333', paddingTop: 15 }}>
                            <div style={{ fontSize: '0.9em', fontWeight: 'bold', marginBottom: 15, color: '#ddd' }}>Model Scores</div>

                            <ScoreBar label="General" value={image.score_general} color="#ff5722" />
                            <ScoreBar label="Technical" value={image.score_technical} />
                            <ScoreBar label="Aesthetic" value={image.score_aesthetic} />

                            {image.score_spaq > 0 && <ScoreBar label="SPAQ" value={image.score_spaq} />}
                            {image.score_ava > 0 && <ScoreBar label="AVA" value={image.score_ava} />}
                            {image.score_koniq > 0 && <ScoreBar label="KonIQ" value={image.score_koniq} />}
                            {image.score_paq2piq > 0 && <ScoreBar label="PaQ2PiQ" value={image.score_paq2piq} />}
                            {image.score_liqe > 0 && <ScoreBar label="LIQE" value={image.score_liqe} />}
                        </div>

                        {/* Keywords / Tags */}
                        {image.keywords && (
                            <div style={{ borderTop: '1px solid #333', paddingTop: 15 }}>
                                <div style={{ fontSize: '0.8em', color: '#888', marginBottom: 8 }}>KEYWORDS</div>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                    {image.keywords.split(',').map((tag: string, i: number) => (
                                        <span key={i} style={{
                                            background: '#333',
                                            padding: '2px 8px',
                                            borderRadius: 4,
                                            fontSize: '0.8em',
                                            color: '#ccc'
                                        }}>
                                            {tag.trim()}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Technical Info */}
                        <div style={{ borderTop: '1px solid #333', paddingTop: 15 }}>
                            <div style={{ fontSize: '0.9em', fontWeight: 'bold', marginBottom: 10, color: '#ddd' }}>Technical Info</div>
                            <div style={{ fontSize: '0.85em', display: 'flex', flexDirection: 'column', gap: 6 }}>
                                {image.file_type && (
                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                        <span style={{ color: '#888' }}>File Type:</span>
                                        <span style={{ fontFamily: 'monospace' }}>{image.file_type}</span>
                                    </div>
                                )}
                                {image.image_hash && (
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                                        <span style={{ color: '#888' }}>Hash (SHA256):</span>
                                        <span style={{ fontFamily: 'monospace', fontSize: '0.75em', wordBreak: 'break-all', color: '#999' }}>
                                            {image.image_hash}
                                        </span>
                                    </div>
                                )}
                                {image.model_version && (
                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                        <span style={{ color: '#888' }}>Model Version:</span>
                                        <span>{image.model_version}</span>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Stack/Burst Info */}
                        {(image.stack_id || image.burst_uuid) && (
                            <div style={{ borderTop: '1px solid #333', paddingTop: 15 }}>
                                <div style={{ fontSize: '0.9em', fontWeight: 'bold', marginBottom: 10, color: '#ddd' }}>Stack/Burst</div>
                                <div style={{ fontSize: '0.85em', display: 'flex', flexDirection: 'column', gap: 6 }}>
                                    {image.stack_id && (
                                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                            <span style={{ color: '#888' }}>Stack ID:</span>
                                            <span>{image.stack_id}</span>
                                        </div>
                                    )}
                                    {image.burst_uuid && (
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                                            <span style={{ color: '#888' }}>Burst UUID:</span>
                                            <span style={{ fontFamily: 'monospace', fontSize: '0.75em', wordBreak: 'break-all', color: '#999' }}>
                                                {image.burst_uuid}
                                            </span>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {/* Database IDs */}
                        <div style={{ borderTop: '1px solid #333', paddingTop: 15 }}>
                            <div style={{ fontSize: '0.9em', fontWeight: 'bold', marginBottom: 10, color: '#ddd' }}>Database Info</div>
                            <div style={{ fontSize: '0.85em', display: 'flex', flexDirection: 'column', gap: 6 }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                    <span style={{ color: '#888' }}>Image ID:</span>
                                    <span>{image.id}</span>
                                </div>
                                {image.job_id && (
                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                        <span style={{ color: '#888' }}>Job ID:</span>
                                        <span>{image.job_id}</span>
                                    </div>
                                )}
                                {image.folder_id && (
                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                        <span style={{ color: '#888' }}>Folder ID:</span>
                                        <span>{image.folder_id}</span>
                                    </div>
                                )}
                            </div>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
};
