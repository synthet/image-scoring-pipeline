import Firebird from 'node-firebird';
import path from 'path';
import { app } from 'electron';

// Database options
// __dirname is dist-electron/
// We need to go up: dist-electron -> electron-gallery -> image-scoring
const dbPath = path.resolve(path.join(__dirname, '../../SCORING_HISTORY.FDB'));

console.log('Connecting to DB at:', dbPath);

const options: Firebird.Options = {
    host: '127.0.0.1',
    port: 3050,
    database: dbPath,
    user: 'sysdba',
    password: 'masterkey',
    lowercase_keys: true,
    role: '',
    pageSize: 4096
};

// Also support connecting to the file directly if we used Embedded, 
// but node-firebird is a pure JS client (requires server) or uses native bindings?
// 'node-firebird' is a pure JS implementation of the wire protocol. It NEEDS a running Firebird server.
// It cannot open FDB files directly without a server process listening on a port.

// This means the Python script or a service MUST be running.
// We will assume server is running on localhost:3050.

export async function connectDB(): Promise<Firebird.Database> {
    return new Promise((resolve, reject) => {
        Firebird.attach(options, (err, db) => {
            if (err) return reject(err);
            resolve(db);
        });
    });
}

export async function query<T = any>(sql: string, params: any[] = []): Promise<T[]> {
    return new Promise((resolve, reject) => {
        Firebird.attach(options, (err, db) => {
            if (err) return reject(err);

            db.query(sql, params, (err, result) => {
                db.detach(); // Always detach after query
                if (err) return reject(err);

                // Convert buffers to strings if needed (blob text)
                // Firebird returns BLOBs as Buffers or streams?
                // node-firebird usually handles text BLOBs if specified?
                // We'll see.

                resolve(result as T[]);
            });
        });
    });
}

export async function getImageCount(): Promise<number> {
    const rows = await query<{ count: number }>('SELECT COUNT(*) as "count" FROM images');
    return rows[0]?.count || 0;
}

export interface ImageQueryOptions {
    limit?: number;
    offset?: number;
    folderId?: number;
    minRating?: number;
    colorLabel?: string;
}

export async function getImages(options: ImageQueryOptions = {}): Promise<any[]> {
    const { limit = 50, offset = 0, folderId, minRating, colorLabel } = options;
    const params: any[] = [];
    const whereParts: string[] = [];

    if (folderId) {
        whereParts.push('folder_id = ?');
        params.push(folderId);
    }

    if (minRating !== undefined && minRating > 0) {
        whereParts.push('rating >= ?');
        params.push(minRating);
    }

    if (colorLabel) {
        whereParts.push('label = ?');
        params.push(colorLabel);
    }

    const whereClause = whereParts.length > 0 ? 'WHERE ' + whereParts.join(' AND ') : '';

    // Note: Offset/Limit in Firebird 3+ is OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
    // But we need to put params in order. WHERE params come first.

    params.push(offset, limit);

    const sql = `
        SELECT 
            i.id, 
            COALESCE(rp.windows_path, i.file_path) as file_path, 
            i.file_name, 
            i.score_general, 
            i.rating, 
            i.label, 
            i.created_at, 
            i.thumbnail_path
        FROM images i
        LEFT JOIN resolved_paths rp ON i.id = rp.image_id
        ${whereClause}
        ORDER BY i.score_general DESC
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
    `;
    return query(sql, params);
}

export async function getImageDetails(id: number): Promise<any> {
    const sql = `
        SELECT 
            i.*,
            fp.path as win_path
        FROM images i
        LEFT JOIN file_paths fp ON i.id = fp.image_id AND fp.path_type = 'WIN'
        WHERE i.id = ?
    `;
    const rows = await query(sql, [id]);
    const image = rows[0];

    if (image) {
        // Convert BLOBs to strings if they are buffers
        const blobFields = ['KEYWORDS', 'DESCRIPTION', 'METADATA', 'SCORES_JSON'];
        for (const field of blobFields) {
            // Firebird node driver returns numeric BLOBs as byte buffers usually
            // but node-firebird might return them as Buffers if we are lucky
            // or we need to handle them. 
            // In the query function we see no special hadling.
            // Let's assume they come as Strings or Buffers.
            const lowerField = field.toLowerCase();
            if (image[lowerField] && Buffer.isBuffer(image[lowerField])) {
                image[lowerField] = image[lowerField].toString('utf8');
            }
        }
    }

    return image;
}

export async function getFolders(): Promise<any[]> {
    return query('SELECT id, path, parent_id, is_fully_scored FROM folders ORDER BY path ASC');
}
