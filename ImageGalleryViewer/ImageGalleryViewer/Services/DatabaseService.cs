using System.Text;
using Microsoft.Data.Sqlite;
using ImageGalleryViewer.Models;

namespace ImageGalleryViewer.Services;

/// <summary>
/// Database service for querying the image scoring database
/// </summary>
public class DatabaseService : IDisposable
{
    private readonly IQueryExecutor _executor;
    private bool _disposed;
    
    public bool IsConnected => _executor.IsConnected;
    
    public DatabaseService(IQueryExecutor executor)
    {
        _executor = executor;
    }
    
    /// <summary>
    /// Get total count of images matching filter
    /// </summary>
    public int GetImageCount(FilterState filter)
    {
        var (whereClause, parameters) = BuildWhereClause(filter);
        var sql = $"SELECT COUNT(*) FROM images {whereClause}";
        
        var paramDict = parameters.ToDictionary(p => p.name, p => p.value);
        var result = _executor.ExecuteScalar(sql, paramDict);
        
        return Convert.ToInt32(result);
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
        
        var sql = $@"
            SELECT 
                id, file_path, file_name, file_type,
                score_general, score_technical, score_aesthetic,
                score_spaq, score_ava, score_koniq, score_paq2piq, score_liqe,
                rating, label, keywords, title, description,
                folder_id, stack_id, thumbnail_path, image_hash, created_at
            FROM images 
            {whereClause}
            ORDER BY {orderColumn} {orderDir} NULLS LAST
            OFFSET @offset ROWS FETCH NEXT @limit ROWS ONLY";
            
        var paramDict = parameters.ToDictionary(p => p.name, p => p.value);
        paramDict["@limit"] = filter.PageSize;
        paramDict["@offset"] = offset;
        
        var rows = _executor.ExecuteQuery(sql, paramDict);
        return rows.Select(MapRowToImageRecord).ToList();
    }
    
    /// <summary>
    /// Get a single image by file path
    /// </summary>
    public ImageRecord? GetImageByPath(string filePath)
    {
        var sql = @"
            SELECT 
                id, file_path, file_name, file_type,
                score_general, score_technical, score_aesthetic,
                score_spaq, score_ava, score_koniq, score_paq2piq, score_liqe,
                rating, label, keywords, title, description,
                folder_id, stack_id, thumbnail_path, image_hash, created_at
            FROM images 
            WHERE file_path = @path";
            
        var paramDict = new Dictionary<string, object> { { "@path", filePath } };
        var rows = _executor.ExecuteQuery(sql, paramDict);
        
        return rows.Any() ? MapRowToImageRecord(rows.First()) : null;
    }
    
    /// <summary>
    /// Get all unique folder paths from images
    /// </summary>
    public List<string> GetAllFolders()
    {
        var sql = @"
            SELECT DISTINCT 
                substring(file_path from 1 for char_length(file_path) - char_length(file_name) - 1) as folder_path
            FROM images 
            WHERE file_path IS NOT NULL AND file_path != ''
            ORDER BY folder_path";
            
        var rows = _executor.ExecuteQuery(sql, new Dictionary<string, object>());
        
        var folders = new List<string>();
        foreach (var row in rows)
        {
            if (row.TryGetValue("folder_path", out var val) && val is string folder && !string.IsNullOrWhiteSpace(folder))
            {
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
        var sql = @"
            SELECT 
                substring(file_path from 1 for char_length(file_path) - char_length(file_name) - 1) as folder_path,
                COUNT(*) as count
            FROM images 
            WHERE file_path IS NOT NULL AND file_path != ''
            GROUP BY folder_path
            ORDER BY folder_path";
            
        var rows = _executor.ExecuteQuery(sql, new Dictionary<string, object>());
        var counts = new Dictionary<string, int>();
        
        foreach (var row in rows)
        {
            var folder = row["folder_path"] as string;
            var countObj = row["count"];
            int count = 0;
            if (countObj is int i) count = i;
            else if (countObj is long l) count = (int)l;

            if (!string.IsNullOrWhiteSpace(folder))
            {
                counts[folder] = count;
            }
        }
        return counts;
    }
    
    private ImageRecord MapRowToImageRecord(Dictionary<string, object> row)
    {
        T? Get<T>(string key)
        {
            if (!row.TryGetValue(key, out var val) || val == null || val == DBNull.Value) return default;
            
            // Helper for JSON numeric types which might be long/double
            if (typeof(T) == typeof(int) && val is long l) return (T)(object)(int)l;
            if (typeof(T) == typeof(double) && val is decimal d) return (T)(object)(double)d; 
            if (typeof(T) == typeof(int?) && val is long l2) return (T)(object)(int)l2;
            
            return (T)val;
        }

        var record = new ImageRecord
        {
            Id = Get<int>("id"),
            FilePath = Get<string>("file_path") ?? "",
            FileName = Get<string>("file_name") ?? "",
            FileType = Get<string>("file_type") ?? "",
            ScoreGeneral = Get<double?>("score_general"),
            ScoreTechnical = Get<double?>("score_technical"),
            ScoreAesthetic = Get<double?>("score_aesthetic"),
            ScoreSpaq = Get<double?>("score_spaq"),
            ScoreAva = Get<double?>("score_ava"),
            ScoreKoniq = Get<double?>("score_koniq"),
            ScorePaq2Piq = Get<double?>("score_paq2piq"),
            ScoreLiqe = Get<double?>("score_liqe"),
            Rating = Get<int?>("rating"),
            Label = Get<string>("label"),
            Keywords = Get<string>("keywords"),
            Title = Get<string>("title"),
            Description = Get<string>("description"),
            FolderId = Get<int?>("folder_id"),
            StackId = Get<int?>("stack_id"),
            ThumbnailPath = Get<string>("thumbnail_path"),
            ImageHash = Get<string>("image_hash")
        };
        
        var createdRaw = Get<object>("created_at");
        if (createdRaw is DateTime dt) record.CreatedAt = dt;
        else if (createdRaw is string s && DateTime.TryParse(s, out var dtParsed)) record.CreatedAt = dtParsed;

        // Resolve Windows path
        record.WindowsPath = PathResolver.ToWindowsPath(record.FilePath);
        
        return record;
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
            conditions.Add("CAST(created_at AS DATE) >= @dateFrom");
            parameters.Add(("@dateFrom", filter.DateFrom.Value.ToString("yyyy-MM-dd")));
        }
        
        if (filter.DateTo.HasValue)
        {
            conditions.Add("CAST(created_at AS DATE) <= @dateTo");
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
            _executor.Dispose();
            _disposed = true;
        }
    }
}
