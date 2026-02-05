import React, { useEffect } from 'react';
import { X, Star, FileText, Calendar, Tag } from 'lucide-react';

interface Image {
    id: number;
    file_path: string;
    file_name: string;
    score_general: number;
    rating: number;
    label: string | null;
    created_at?: string;
    // Add other fields if needed from DB
}

interface ImageViewerProps {
    image: Image;
    onClose: () => void;
}

export const ImageViewer: React.FC<ImageViewerProps> = ({ image, onClose }) => {

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [onClose]);

    // Construct media URL
    // Ensure file_path is valid for media:// protocol
    const src = image.file_path ? `media://${image.file_path}` : '';

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

                {src ? (
                    <img
                        src={src}
                        alt={image.file_name}
                        style={{ maxWidth: '95%', maxHeight: '95%', objectFit: 'contain', boxShadow: '0 0 20px rgba(0,0,0,0.5)' }}
                    />
                ) : (
                    <div style={{ color: '#666' }}>Image not found</div>
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
                        <span style={{ wordBreak: 'break-all' }}>{image.file_path}</span>
                    </div>
                </div>

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

                <div>
                    <div style={{ fontSize: '0.8em', color: '#888', marginBottom: 8 }}>DETAILS</div>
                    <div style={{ fontSize: '0.9em', display: 'flex', flexDirection: 'column', gap: 8 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <Calendar size={14} color="#888" />
                            <span>{dateStr}</span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <Tag size={14} color="#888" />
                            <span>ID: {image.id}</span>
                        </div>
                    </div>
                </div>

                {/* Placeholder for tags/keywords if we implemented them */}
            </div>
        </div>
    );
};
