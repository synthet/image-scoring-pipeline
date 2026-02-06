declare module 'libraw-wasm' {
    export default class LibRaw {
        constructor();
        open(buffer: Uint8Array): Promise<void>;
        metadata(fullOutput?: boolean): Promise<any>;
        imageData(): Promise<{
            width: number;
            height: number;
            data: Uint8Array | Uint8ClampedArray;
        }>;
    }
}
