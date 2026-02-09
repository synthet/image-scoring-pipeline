import React from 'react';

export interface FilterState {
    minRating: number;
    colorLabel?: string;
    keyword?: string;
    sortBy?: string;
    order?: 'ASC' | 'DESC';
}

interface FilterPanelProps {
    filters: FilterState;
    onChange: (filters: FilterState) => void;
}

export const FilterPanel: React.FC<FilterPanelProps> = ({ filters, onChange }) => {

    const handleRatingChange = (r: number) => {
        onChange({ ...filters, minRating: r });
    };

    const handleColorChange = (c?: string) => {
        onChange({ ...filters, colorLabel: c });
    };

    return (
        <div style={{ padding: '10px', borderBottom: '1px solid #333' }}>
            <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: '12px', color: '#888', marginBottom: 5 }}>Minimum Rating</div>
                <div style={{ display: 'flex', gap: 5 }}>
                    {[0, 1, 2, 3, 4, 5].map(r => (
                        <button
                            key={r}
                            onClick={() => handleRatingChange(r)}
                            style={{
                                flex: 1,
                                padding: '4px 0',
                                background: filters.minRating === r ? '#007acc' : '#333',
                                color: '#eee',
                                border: 'none',
                                borderRadius: 4,
                                cursor: 'pointer',
                                fontSize: '11px'
                            }}
                        >
                            {r === 0 ? 'All' : r}
                        </button>
                    ))}
                </div>
            </div>

            <div>
                <div style={{ fontSize: '12px', color: '#888', marginBottom: 5 }}>Color Label</div>
                <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                    <button onClick={() => handleColorChange(undefined)} style={{ padding: '4px 8px', fontSize: 11, background: !filters.colorLabel ? '#555' : '#333', border: 'none', borderRadius: 4, color: '#ddd', cursor: 'pointer' }}>All</button>
                    {[
                        { id: 'Red', color: '#e53935', tooltip: 'Red: Reject (technical failure)' },
                        { id: 'Yellow', color: '#fdd835', tooltip: 'Yellow: Maybe (the middle)' },
                        { id: 'Green', color: '#43a047', tooltip: 'Green: Reference shot (high technical)' },
                        { id: 'Blue', color: '#1e88e5', tooltip: 'Blue: Portfolio shot (high aesthetic & sharp)' },
                        { id: 'Purple', color: '#8e24aa', tooltip: 'Purple: Creative/moody (aesthetic beats technical)' },
                    ].map(({ id, color, tooltip }) => (
                        <button
                            key={id}
                            onClick={() => handleColorChange(id === filters.colorLabel ? undefined : id)}
                            style={{
                                width: 24, height: 24,
                                borderRadius: '50%',
                                background: color,
                                border: filters.colorLabel === id ? '2px solid white' : '2px solid transparent',
                                cursor: 'pointer'
                            }}
                            title={tooltip}
                        />
                    ))}
                </div>
            </div>
        </div>
    );
};
