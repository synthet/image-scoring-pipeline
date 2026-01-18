using System.IO;
using System.Text.RegularExpressions;

namespace ImageGalleryViewer.Services;

/// <summary>
/// Converts paths between WSL and Windows formats
/// </summary>
public static partial class PathResolver
{
    // Match WSL mount paths like /mnt/d/path or /mnt/c/path
    [GeneratedRegex(@"^/mnt/([a-zA-Z])(/.*)?$")]
    private static partial Regex WslMountPathRegex();
    
    /// <summary>
    /// Convert a path to Windows format
    /// </summary>
    /// <param name="path">Path in WSL or Windows format</param>
    /// <returns>Windows path</returns>
    public static string ToWindowsPath(string? path)
    {
        if (string.IsNullOrWhiteSpace(path))
            return string.Empty;
            
        path = path.Trim();
        
        // Already Windows format (starts with drive letter)
        if (path.Length >= 2 && char.IsLetter(path[0]) && path[1] == ':')
        {
            // Normalize slashes
            return path.Replace('/', '\\');
        }
        
        // WSL mount path format: /mnt/d/path -> D:\path
        var match = WslMountPathRegex().Match(path);
        if (match.Success)
        {
            char driveLetter = char.ToUpper(match.Groups[1].Value[0]);
            string rest = match.Groups[2].Success ? match.Groups[2].Value : "";
            
            // Replace forward slashes with backslashes
            rest = rest.Replace('/', '\\');
            
            return $"{driveLetter}:{rest}";
        }
        
        // Unknown format - return as-is with normalized slashes
        return path.Replace('/', '\\');
    }
    
    /// <summary>
    /// Convert a Windows path to WSL format
    /// </summary>
    /// <param name="path">Path in Windows format</param>
    /// <returns>WSL path</returns>
    public static string ToWslPath(string? path)
    {
        if (string.IsNullOrWhiteSpace(path))
            return string.Empty;
            
        path = path.Trim();
        
        // Already WSL format
        if (path.StartsWith("/mnt/"))
            return path;
            
        // Windows format: D:\path -> /mnt/d/path
        if (path.Length >= 2 && char.IsLetter(path[0]) && path[1] == ':')
        {
            char driveLetter = char.ToLower(path[0]);
            string rest = path.Length > 2 ? path.Substring(2) : "";
            
            // Replace backslashes with forward slashes
            rest = rest.Replace('\\', '/');
            
            return $"/mnt/{driveLetter}{rest}";
        }
        
        // Unknown format - return with forward slashes
        return path.Replace('\\', '/');
    }
    
    /// <summary>
    /// Check if a file exists at the given path
    /// </summary>
    public static bool FileExists(string? path)
    {
        if (string.IsNullOrWhiteSpace(path))
            return false;
            
        try
        {
            var windowsPath = ToWindowsPath(path);
            return File.Exists(windowsPath);
        }
        catch
        {
            return false;
        }
    }
    
    /// <summary>
    /// Get the best available path for display/access
    /// </summary>
    public static string GetAccessiblePath(string? dbPath, string? thumbnailPath = null)
    {
        // Prefer thumbnail if available and exists
        if (!string.IsNullOrWhiteSpace(thumbnailPath))
        {
            var thumbWindows = ToWindowsPath(thumbnailPath);
            if (File.Exists(thumbWindows))
                return thumbWindows;
        }
        
        // Fall back to main file path
        return ToWindowsPath(dbPath);
    }
}
