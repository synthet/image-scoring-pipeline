-- Migration: Add resolved_paths table for Windows Native Viewer
-- Purpose: Store verified Windows paths for fast file access
-- Date: 2025-01-XX

-- Create resolved_paths table
CREATE TABLE IF NOT EXISTS resolved_paths (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL,
    windows_path TEXT NOT NULL,  -- Always Windows format (D:\...)
    is_verified INTEGER DEFAULT 0,  -- 0 = not verified, 1 = file exists on disk
    verification_date TIMESTAMP,
    last_checked TIMESTAMP,
    FOREIGN KEY(image_id) REFERENCES images(id),
    UNIQUE(image_id, windows_path)
);

-- Create indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_resolved_paths_image ON resolved_paths(image_id);
CREATE INDEX IF NOT EXISTS idx_resolved_paths_verified ON resolved_paths(is_verified, windows_path);
CREATE INDEX IF NOT EXISTS idx_resolved_paths_windows_path ON resolved_paths(windows_path);

-- Optional: Create view for easy querying of verified paths
CREATE VIEW IF NOT EXISTS images_with_resolved_paths AS
SELECT 
    i.*,
    rp.windows_path as resolved_path,
    rp.is_verified,
    rp.verification_date
FROM images i
LEFT JOIN resolved_paths rp ON i.id = rp.image_id AND rp.is_verified = 1;
