namespace ImageGalleryViewer.Models;

/// <summary>
/// Represents an image record from the database
/// </summary>
public class ImageRecord
{
    public int Id { get; set; }
    public string FilePath { get; set; } = string.Empty;
    public string FileName { get; set; } = string.Empty;
    public string FileType { get; set; } = string.Empty;
    
    // Scores
    public double? ScoreGeneral { get; set; }
    public double? ScoreTechnical { get; set; }
    public double? ScoreAesthetic { get; set; }
    public double? ScoreSpaq { get; set; }
    public double? ScoreAva { get; set; }
    public double? ScoreKoniq { get; set; }
    public double? ScorePaq2Piq { get; set; }
    public double? ScoreLiqe { get; set; }
    
    // Metadata
    public int? Rating { get; set; }
    public string? Label { get; set; }
    public string? Keywords { get; set; }
    public string? Title { get; set; }
    public string? Description { get; set; }
    
    // Relationships
    public int? FolderId { get; set; }
    public int? StackId { get; set; }
    
    // Paths
    public string? ThumbnailPath { get; set; }
    public string? ImageHash { get; set; }
    
    // Timestamps
    public DateTime? CreatedAt { get; set; }
    
    /// <summary>
    /// Resolved Windows path (computed from FilePath)
    /// </summary>
    public string WindowsPath { get; set; } = string.Empty;
    
    /// <summary>
    /// Whether the file exists on disk
    /// </summary>
    public bool FileExists { get; set; }
    
    /// <summary>
    /// Display score as formatted string
    /// </summary>
    public string ScoreDisplay => ScoreGeneral.HasValue 
        ? $"{ScoreGeneral.Value:F2}" 
        : "N/A";
    
    /// <summary>
    /// Display label with emoji indicator
    /// </summary>
    public string LabelDisplay => Label switch
    {
        "Red" => "🔴",
        "Yellow" => "🟡",
        "Green" => "🟢",
        "Blue" => "🔵",
        "Purple" => "🟣",
        _ => ""
    };
    
    /// <summary>
    /// Rating as star display
    /// </summary>
    public string RatingDisplay => Rating.HasValue && Rating.Value > 0
        ? new string('★', Rating.Value) + new string('☆', 5 - Rating.Value)
        : "☆☆☆☆☆";
}
