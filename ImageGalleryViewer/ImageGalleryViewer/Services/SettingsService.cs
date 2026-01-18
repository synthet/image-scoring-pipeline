using System.IO;
using System.Text.Json;

namespace ImageGalleryViewer.Services;

/// <summary>
/// Application settings with persistence
/// </summary>
public class SettingsService
{
    private static readonly string SettingsPath = 
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "ImageGalleryViewer", "settings.json");
    
    public string DatabasePath { get; set; }
    public int PageSize { get; set; } = 50;
    public string DefaultSortBy { get; set; } = "score_general";
    public bool DefaultSortDescending { get; set; } = true;
    public double WindowWidth { get; set; } = 1400;
    public double WindowHeight { get; set; } = 900;
    public double FilterPanelWidth { get; set; } = 280;
    public int ThumbnailCacheSizeMb { get; set; } = 200;
    public bool AutoVerifyPaths { get; set; } = true;
    
    // Filter presets
    public List<int>? LastRatingFilter { get; set; }
    public List<string>? LastLabelFilter { get; set; }
    
    public SettingsService()
    {
        // Default database path - look in typical locations
        DatabasePath = FindDatabasePath();
        
        Load();
    }
    
    private static string FindDatabasePath()
    {
        // Check common locations for the database
        var candidates = new[]
        {
            @"D:\Projects\image-scoring\scoring_history.db",
            @"C:\Projects\image-scoring\scoring_history.db",
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                "image-scoring", "scoring_history.db"),
            "scoring_history.db"
        };
        
        foreach (var path in candidates)
        {
            if (File.Exists(path))
                return path;
        }
        
        // Return the most likely default
        return candidates[0];
    }
    
    public void Load()
    {
        try
        {
            if (File.Exists(SettingsPath))
            {
                var json = File.ReadAllText(SettingsPath);
                var loaded = JsonSerializer.Deserialize<SettingsService>(json);
                if (loaded != null)
                {
                    DatabasePath = loaded.DatabasePath ?? DatabasePath;
                    PageSize = loaded.PageSize;
                    DefaultSortBy = loaded.DefaultSortBy;
                    DefaultSortDescending = loaded.DefaultSortDescending;
                    WindowWidth = loaded.WindowWidth;
                    WindowHeight = loaded.WindowHeight;
                    FilterPanelWidth = loaded.FilterPanelWidth;
                    ThumbnailCacheSizeMb = loaded.ThumbnailCacheSizeMb;
                    AutoVerifyPaths = loaded.AutoVerifyPaths;
                    LastRatingFilter = loaded.LastRatingFilter;
                    LastLabelFilter = loaded.LastLabelFilter;
                }
            }
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"Error loading settings: {ex.Message}");
        }
    }
    
    public void Save()
    {
        try
        {
            var directory = Path.GetDirectoryName(SettingsPath);
            if (!string.IsNullOrEmpty(directory))
                Directory.CreateDirectory(directory);
                
            var json = JsonSerializer.Serialize(this, new JsonSerializerOptions { WriteIndented = true });
            File.WriteAllText(SettingsPath, json);
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"Error saving settings: {ex.Message}");
        }
    }
}
