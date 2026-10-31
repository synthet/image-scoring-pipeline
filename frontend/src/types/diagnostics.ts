export const DIAGNOSTIC_LAYERS = ['sharpness', 'peaking', 'noise', 'mask', 'head'] as const;
export type DiagnosticLayer = typeof DIAGNOSTIC_LAYERS[number];
export type PeakingMode = 'off' | 'outlines' | 'texture' | 'both';
export type DiagnosticState = 'not_requested' | 'queued' | 'running' | 'ready' | 'unavailable' | 'failed';

export interface DiagnosticGrid {
    cells_x: number;
    cells_y: number;
    x_edges: number[];
    y_edges: number[];
    values: Array<number | null>;
    values_normalized: Array<number | null>;
    units: string;
    normalization: 'fixed_display_scale';
}

export interface HeadMeasurements {
    head_bbox?: [number, number, number, number];
    facing_vector?: { x1: number; y1: number; x2: number; y2: number } | null;
    eyes?: Array<{ name: string; x: number; y: number; sharpness_ratio: number | null; evidence_confidence: number; limitation?: string | null }>;
    mean?: number;
    units?: string;
    marks?: number;
    coverage?: number;
    confidence?: number;
    region_background_ratio?: number;
    limitations?: string[];
}

export interface DiagnosticManifest {
    evidence_schema_version: 2;
    image_id: number;
    identity: string;
    extractor_version: string;
    request_id?: string;
    rendition: {
        rendition_hash: string;
        display_width: number;
        display_height: number;
        preview_artifact: string;
        source_resolution: 'decoded_native' | 'reduced';
        coord_space: 'display_normalized';
        decode_route: string;
        pixel_policy: string;
    } | null;
    layers: Record<DiagnosticLayer, {
        state: DiagnosticState;
        reason?: string | null;
        artifacts?: Record<string, string>;
        grid?: DiagnosticGrid;
        measurements?: HeadMeasurements;
        provider_version?: string;
    }>;
}

export interface DiagnosticTransport {
    manifest: (imageId: number) => Promise<DiagnosticManifest>;
    request: (imageId: number, layers: DiagnosticLayer[], refresh?: boolean) => Promise<DiagnosticManifest>;
    cancel: (imageId: number, requestId: string) => Promise<unknown>;
    artifact: (imageId: number, artifactId: string) => Promise<string>;
}
