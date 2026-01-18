namespace ImageGalleryViewer.Models;

/// <summary>
/// Filter state for gallery queries
/// </summary>
public class FilterState
{
    // Rating filter (null = all)
    public List<int>? Ratings { get; set; }
    
    // Label filter (null = all)
    public List<string>? Labels { get; set; }
    
    // Score minimums
    public double MinScoreGeneral { get; set; }
    public double MinScoreAesthetic { get; set; }
    public double MinScoreTechnical { get; set; }
    
    // Date range
    public DateTime? DateFrom { get; set; }
    public DateTime? DateTo { get; set; }
    
    // Keyword search
    public string? KeywordSearch { get; set; }
    
    // Folder filter
    public string? FolderPath { get; set; }
    
    // Stack filter
    public int? StackId { get; set; }
    
    // Sorting
    public string SortBy { get; set; } = "score_general";
    public bool SortDescending { get; set; } = true;
    
    // Pagination
    public int Page { get; set; } = 1;
    public int PageSize { get; set; } = 50;
    
    /// <summary>
    /// Creates a copy of this filter state
    /// </summary>
    public FilterState Clone()
    {
        return new FilterState
        {
            Ratings = Ratings?.ToList(),
            Labels = Labels?.ToList(),
            MinScoreGeneral = MinScoreGeneral,
            MinScoreAesthetic = MinScoreAesthetic,
            MinScoreTechnical = MinScoreTechnical,
            DateFrom = DateFrom,
            DateTo = DateTo,
            KeywordSearch = KeywordSearch,
            FolderPath = FolderPath,
            StackId = StackId,
            SortBy = SortBy,
            SortDescending = SortDescending,
            Page = Page,
            PageSize = PageSize
        };
    }
    
    /// <summary>
    /// Reset to default values
    /// </summary>
    public void Reset()
    {
        Ratings = null;
        Labels = null;
        MinScoreGeneral = 0;
        MinScoreAesthetic = 0;
        MinScoreTechnical = 0;
        DateFrom = null;
        DateTo = null;
        KeywordSearch = null;
        FolderPath = null;
        StackId = null;
        Page = 1;
    }
}

/// <summary>
/// Available sort options
/// </summary>
public static class SortOptions
{
    public static readonly (string Display, string Value)[] Options = new[]
    {
        ("📅 Date Added", "created_at"),
        ("🆔 ID", "id"),
        ("⭐ General Score", "score_general"),
        ("🔧 Technical Score", "score_technical"),
        ("🎨 Aesthetic Score", "score_aesthetic")
    };
}

/// <summary>
/// Available color labels
/// </summary>
public static class ColorLabels
{
    public static readonly string[] All = { "Red", "Yellow", "Green", "Blue", "Purple", "None" };
}
