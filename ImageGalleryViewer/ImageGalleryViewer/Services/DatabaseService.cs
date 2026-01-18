using System.Text;
using Microsoft.Data.Sqlite;
using ImageGalleryViewer.Models;

namespace ImageGalleryViewer.Services;

/// <summary>
/// Database service for querying the image scoring database
/// </summary>
public class DatabaseService : IDisposable
{
    private readonly SqliteConnection _connection;
    private bool _disposed;
    
    public string DatabasePath { get; }
    public bool IsConnected => _connection.State == System.Data.ConnectionState.Open;
    
    public DatabaseService(string databasePath)
    {
        DatabasePath = databasePath;
        
        var connectionString = new SqliteConnectionStringBuilder
        {
            DataSource = databasePath,
            Mode = SqliteOpenMode.ReadWrite,
            Cache = SqliteCacheMode.Shared
        }.ToString();
        
        _connection = new SqliteConnection(connectionString);
        _connection.Open();
        
        // Enable WAL mode for better concurrent access
        using var cmd = _connection.CreateCommand();
        cmd.CommandText = "PRAGMA journal_mode=WAL; PRAGMA cache_size=-64000;";
        cmd.ExecuteNonQuery();
    }
    
    /// <summary>
    /// Get total count of images matching filter
    /// </summary>
    public int GetImageCount(FilterState filter)
    {
        var (whereClause, parameters) = BuildWhereClause(filter);
        
        using var cmd = _connection.CreateCommand();
        cmd.CommandText = $"SELECT COUNT(*) FROM images {whereClause}";
        
        foreach (var (name, value) in parameters)
            cmd.Parameters.AddWithValue(name, value);
            
        return Convert.ToInt32(cmd.ExecuteScalar());
    }
    
    /// <summary>
    /// Get paginated images matching filter
    /// </summary>
    public List<ImageRecord> GetImages(FilterState filter)
    {
        var (whereClause, parameters) = BuildWhereClause(filter);
        
        var orderColumn = filter.SortBy switch
        {
            "id" => "id",
            "created_at" => "created_at",
            "score_technical" => "score_technical",
            "score_aesthetic" => "score_aesthetic",
            _ => "score_general"
        };
        var orderDir = filter.SortDescending ? "DESC" : "ASC";
        
        var offset = (filter.Page - 1) * filter.PageSize;
        
        using var cmd = _connection.CreateCommand();
        cmd.CommandText = $@"
            SELECT 
                id, file_path, file_name, file_type,
                score_general, score_technical, score_aesthetic,
                score_spaq, score_ava, score_koniq, score_paq2piq, score_liqe,
                rating, label, keywords, title, description,
                folder_id, stack_id, thumbnail_path, image_hash, created_at
            FROM images 
            {whereClause}
            ORDER BY {orderColumn} {orderDir} NULLS LAST
            LIMIT @limit OFFSET @offset";
            
        cmd.Parameters.AddWithValue("@limit", filter.PageSize);
        cmd.Parameters.AddWithValue("@offset", offset);
        
        foreach (var (name, value) in parameters)
            cmd.Parameters.AddWithValue(name, value);
            
        var results = new List<ImageRecord>();
        
        using var reader = cmd.ExecuteReader();
        while (reader.Read())
        {
            var record = new ImageRecord
            {
                Id = reader.GetInt32(0),
                FilePath = reader.IsDBNull(1) ? "" : reader.GetString(1),
                FileName = reader.IsDBNull(2) ? "" : reader.GetString(2),
                FileType = reader.IsDBNull(3) ? "" : reader.GetString(3),
                ScoreGeneral = reader.IsDBNull(4) ? null : reader.GetDouble(4),
                ScoreTechnical = reader.IsDBNull(5) ? null : reader.GetDouble(5),
                ScoreAesthetic = reader.IsDBNull(6) ? null : reader.GetDouble(6),
                ScoreSpaq = reader.IsDBNull(7) ? null : reader.GetDouble(7),
                ScoreAva = reader.IsDBNull(8) ? null : reader.GetDouble(8),
                ScoreKoniq = reader.IsDBNull(9) ? null : reader.GetDouble(9),
                ScorePaq2Piq = reader.IsDBNull(10) ? null : reader.GetDouble(10),
                ScoreLiqe = reader.IsDBNull(11) ? null : reader.GetDouble(11),
                Rating = reader.IsDBNull(12) ? null : reader.GetInt32(12),
                Label = reader.IsDBNull(13) ? null : reader.GetString(13),
                Keywords = reader.IsDBNull(14) ? null : reader.GetString(14),
                Title = reader.IsDBNull(15) ? null : reader.GetString(15),
                Description = reader.IsDBNull(16) ? null : reader.GetString(16),
                FolderId = reader.IsDBNull(17) ? null : reader.GetInt32(17),
                StackId = reader.IsDBNull(18) ? null : reader.GetInt32(18),
                ThumbnailPath = reader.IsDBNull(19) ? null : reader.GetString(19),
                ImageHash = reader.IsDBNull(20) ? null : reader.GetString(20),
                CreatedAt = reader.IsDBNull(21) ? null : DateTime.Parse(reader.GetString(21))
            };
            
            // Resolve Windows path
            record.WindowsPath = PathResolver.ToWindowsPath(record.FilePath);
            
            results.Add(record);
        }
        
        return results;
    }
    
    /// <summary>
    /// Get a single image by file path
    /// </summary>
    public ImageRecord? GetImageByPath(string filePath)
    {
        using var cmd = _connection.CreateCommand();
        cmd.CommandText = @"
            SELECT 
                id, file_path, file_name, file_type,
                score_general, score_technical, score_aesthetic,
                score_spaq, score_ava, score_koniq, score_paq2piq, score_liqe,
                rating, label, keywords, title, description,
                folder_id, stack_id, thumbnail_path, image_hash, created_at
            FROM images 
            WHERE file_path = @path";
        cmd.Parameters.AddWithValue("@path", filePath);
        
        using var reader = cmd.ExecuteReader();
        if (reader.Read())
        {
            return new ImageRecord
            {
                Id = reader.GetInt32(0),
                FilePath = reader.IsDBNull(1) ? "" : reader.GetString(1),
                FileName = reader.IsDBNull(2) ? "" : reader.GetString(2),
                FileType = reader.IsDBNull(3) ? "" : reader.GetString(3),
                ScoreGeneral = reader.IsDBNull(4) ? null : reader.GetDouble(4),
                ScoreTechnical = reader.IsDBNull(5) ? null : reader.GetDouble(5),
                ScoreAesthetic = reader.IsDBNull(6) ? null : reader.GetDouble(6),
                ScoreSpaq = reader.IsDBNull(7) ? null : reader.GetDouble(7),
                ScoreAva = reader.IsDBNull(8) ? null : reader.GetDouble(8),
                ScoreKoniq = reader.IsDBNull(9) ? null : reader.GetDouble(9),
                ScorePaq2Piq = reader.IsDBNull(10) ? null : reader.GetDouble(10),
                ScoreLiqe = reader.IsDBNull(11) ? null : reader.GetDouble(11),
                Rating = reader.IsDBNull(12) ? null : reader.GetInt32(12),
                Label = reader.IsDBNull(13) ? null : reader.GetString(13),
                Keywords = reader.IsDBNull(14) ? null : reader.GetString(14),
                Title = reader.IsDBNull(15) ? null : reader.GetString(15),
                Description = reader.IsDBNull(16) ? null : reader.GetString(16),
                FolderId = reader.IsDBNull(17) ? null : reader.GetInt32(17),
                StackId = reader.IsDBNull(18) ? null : reader.GetInt32(18),
                ThumbnailPath = reader.IsDBNull(19) ? null : reader.GetString(19),
                ImageHash = reader.IsDBNull(20) ? null : reader.GetString(20),
                CreatedAt = reader.IsDBNull(21) ? null : DateTime.Parse(reader.GetString(21)),
                WindowsPath = PathResolver.ToWindowsPath(reader.IsDBNull(1) ? "" : reader.GetString(1))
            };
        }
        
        return null;
    }
    
    /// <summary>
    /// Get all unique folder paths from images
    /// </summary>
    public List<string> GetAllFolders()
    {
        using var cmd = _connection.CreateCommand();
        cmd.CommandText = @"
            SELECT DISTINCT 
                substr(file_path, 1, length(file_path) - length(file_name) - 1) as folder_path
            FROM images 
            WHERE file_path IS NOT NULL AND file_path != ''
            ORDER BY folder_path";
            
        var folders = new List<string>();
        using var reader = cmd.ExecuteReader();
        while (reader.Read())
        {
            if (!reader.IsDBNull(0))
            {
                var folder = reader.GetString(0);
                if (!string.IsNullOrWhiteSpace(folder))
                    folders.Add(folder);
            }
        }
        return folders;
    }
    
    /// <summary>
    /// Get count of images per folder (for tree display)
    /// </summary>
    public Dictionary<string, int> GetFolderImageCounts()
    {
        using var cmd = _connection.CreateCommand();
        cmd.CommandText = @"
            SELECT 
                substr(file_path, 1, length(file_path) - length(file_name) - 1) as folder_path,
                COUNT(*) as count
            FROM images 
            WHERE file_path IS NOT NULL AND file_path != ''
            GROUP BY folder_path
            ORDER BY folder_path";
            
        var counts = new Dictionary<string, int>();
        using var reader = cmd.ExecuteReader();
        while (reader.Read())
        {
            if (!reader.IsDBNull(0))
            {
                var folder = reader.GetString(0);
                var count = reader.GetInt32(1);
                if (!string.IsNullOrWhiteSpace(folder))
                    counts[folder] = count;
            }
        }
        return counts;
    }
    
    /// <summary>
    /// Build WHERE clause from filter state
    /// </summary>
    private (string whereClause, List<(string name, object value)> parameters) BuildWhereClause(FilterState filter)
    {
        var conditions = new List<string>();
        var parameters = new List<(string name, object value)>();
        
        // Rating filter
        if (filter.Ratings?.Count > 0)
        {
            var ratingParams = new List<string>();
            for (int i = 0; i < filter.Ratings.Count; i++)
            {
                var paramName = $"@rating{i}";
                ratingParams.Add(paramName);
                parameters.Add((paramName, filter.Ratings[i]));
            }
            conditions.Add($"rating IN ({string.Join(", ", ratingParams)})");
        }
        
        // Label filter
        if (filter.Labels?.Count > 0)
        {
            var labelConditions = new List<string>();
            var labelParams = new List<string>();
            
            for (int i = 0; i < filter.Labels.Count; i++)
            {
                if (filter.Labels[i] == "None")
                {
                    labelConditions.Add("(label IS NULL OR label = '')");
                }
                else
                {
                    var paramName = $"@label{i}";
                    labelParams.Add(paramName);
                    parameters.Add((paramName, filter.Labels[i]));
                }
            }
            
            if (labelParams.Count > 0)
                labelConditions.Add($"label IN ({string.Join(", ", labelParams)})");
                
            conditions.Add($"({string.Join(" OR ", labelConditions)})");
        }
        
        // Score filters
        if (filter.MinScoreGeneral > 0)
        {
            conditions.Add("score_general >= @minGeneral");
            parameters.Add(("@minGeneral", filter.MinScoreGeneral));
        }
        
        if (filter.MinScoreAesthetic > 0)
        {
            conditions.Add("score_aesthetic >= @minAesthetic");
            parameters.Add(("@minAesthetic", filter.MinScoreAesthetic));
        }
        
        if (filter.MinScoreTechnical > 0)
        {
            conditions.Add("score_technical >= @minTechnical");
            parameters.Add(("@minTechnical", filter.MinScoreTechnical));
        }
        
        // Date filters
        if (filter.DateFrom.HasValue)
        {
            conditions.Add("DATE(created_at) >= @dateFrom");
            parameters.Add(("@dateFrom", filter.DateFrom.Value.ToString("yyyy-MM-dd")));
        }
        
        if (filter.DateTo.HasValue)
        {
            conditions.Add("DATE(created_at) <= @dateTo");
            parameters.Add(("@dateTo", filter.DateTo.Value.ToString("yyyy-MM-dd")));
        }
        
        // Keyword search
        if (!string.IsNullOrWhiteSpace(filter.KeywordSearch))
        {
            conditions.Add("keywords LIKE @keyword");
            parameters.Add(("@keyword", $"%{filter.KeywordSearch}%"));
        }
        
        // Folder filter
        if (!string.IsNullOrWhiteSpace(filter.FolderPath))
        {
            // Convert to WSL path for DB comparison
            var wslPath = PathResolver.ToWslPath(filter.FolderPath);
            conditions.Add("file_path LIKE @folderPath");
            parameters.Add(("@folderPath", $"{wslPath}%"));
        }
        
        // Stack filter
        if (filter.StackId.HasValue)
        {
            conditions.Add("stack_id = @stackId");
            parameters.Add(("@stackId", filter.StackId.Value));
        }
        
        var whereClause = conditions.Count > 0 
            ? $"WHERE {string.Join(" AND ", conditions)}" 
            : "";
            
        return (whereClause, parameters);
    }
    
    public void Dispose()
    {
        if (!_disposed)
        {
            _connection.Close();
            _connection.Dispose();
            _disposed = true;
        }
    }
}
