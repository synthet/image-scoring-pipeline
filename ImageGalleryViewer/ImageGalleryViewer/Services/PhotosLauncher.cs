using System.IO;
using ImageGalleryViewer.Models;

namespace ImageGalleryViewer.Services;

/// <summary>
/// Launches Windows Photos app with filtered image set navigation
/// </summary>
public class PhotosLauncher
{
    private static readonly string TempFolderBase = Path.Combine(Path.GetTempPath(), "ImageGalleryViewer");
    
    /// <summary>
    /// Open an image in Windows Photos with navigation support for the full filtered set
    /// </summary>
    public void OpenImageInPhotos(List<ImageRecord> images, int startIndex)
    {
        if (images.Count == 0 || startIndex < 0 || startIndex >= images.Count)
            return;
            
        var targetImage = images[startIndex];
        
        // If only one image, just open it directly
        if (images.Count == 1)
        {
            OpenSingleImage(targetImage.WindowsPath);
            return;
        }
        
        // Create temp folder with hard links for navigation
        var sessionFolder = CreateNavigationFolder(images);
        
        if (sessionFolder != null)
        {
            // Find the corresponding link for our start image
            var linkPath = Path.Combine(sessionFolder, 
                $"{startIndex:D5}_{Path.GetFileName(targetImage.WindowsPath)}");
            
            if (File.Exists(linkPath))
            {
                OpenSingleImage(linkPath);
            }
            else
            {
                // Fallback to original
                OpenSingleImage(targetImage.WindowsPath);
            }
            
            // Schedule cleanup
            ScheduleCleanup(sessionFolder);
        }
        else
        {
            // Fallback to opening original directly
            OpenSingleImage(targetImage.WindowsPath);
        }
    }
    
    /// <summary>
    /// Create a temporary folder with hard links to all images for Photos navigation
    /// </summary>
    private string? CreateNavigationFolder(List<ImageRecord> images)
    {
        try
        {
            // Create unique folder
            var sessionId = Guid.NewGuid().ToString("N")[..8];
            var sessionFolder = Path.Combine(TempFolderBase, $"nav_{sessionId}");
            Directory.CreateDirectory(sessionFolder);
            
            // Create hard links (numbered for sort order)
            for (int i = 0; i < images.Count; i++)
            {
                var sourcePath = images[i].WindowsPath;
                if (!File.Exists(sourcePath))
                    continue;
                
                var fileName = Path.GetFileName(sourcePath);
                var linkPath = Path.Combine(sessionFolder, $"{i:D5}_{fileName}");
                
                // Try to create hard link
                if (!CreateHardLink(linkPath, sourcePath))
                {
                    // If hard link fails (e.g., different drives), try copy
                    // Skip for now to keep it fast
                }
            }
            
            return sessionFolder;
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"Error creating navigation folder: {ex.Message}");
            return null;
        }
    }
    
    /// <summary>
    /// Open a single image in Photos
    /// </summary>
    private void OpenSingleImage(string path)
    {
        try
        {
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
            {
                FileName = path,
                UseShellExecute = true
            });
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"Error opening image: {ex.Message}");
        }
    }
    
    /// <summary>
    /// Create a hard link (Windows only)
    /// </summary>
    private static bool CreateHardLink(string linkPath, string sourcePath)
    {
        return NativeMethods.CreateHardLink(linkPath, sourcePath, IntPtr.Zero);
    }
    
    /// <summary>
    /// Schedule cleanup of temp folder
    /// </summary>
    private void ScheduleCleanup(string folderPath)
    {
        // Run cleanup after 1 hour
        Task.Delay(TimeSpan.FromHours(1)).ContinueWith(_ =>
        {
            try
            {
                if (Directory.Exists(folderPath))
                {
                    Directory.Delete(folderPath, recursive: true);
                }
            }
            catch
            {
                // Ignore cleanup errors
            }
        });
    }
    
    /// <summary>
    /// Clean up all old temp folders
    /// </summary>
    public static void CleanupOldFolders()
    {
        try
        {
            if (!Directory.Exists(TempFolderBase))
                return;
                
            var cutoff = DateTime.Now.AddHours(-24);
            
            foreach (var dir in Directory.GetDirectories(TempFolderBase, "nav_*"))
            {
                try
                {
                    var info = new DirectoryInfo(dir);
                    if (info.CreationTime < cutoff)
                    {
                        Directory.Delete(dir, recursive: true);
                    }
                }
                catch
                {
                    // Ignore individual folder errors
                }
            }
        }
        catch
        {
            // Ignore cleanup errors
        }
    }
}

/// <summary>
/// Native Windows API methods
/// </summary>
internal static partial class NativeMethods
{
    [System.Runtime.InteropServices.LibraryImport("kernel32.dll", SetLastError = true, StringMarshalling = System.Runtime.InteropServices.StringMarshalling.Utf16)]
    [return: System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.Bool)]
    internal static partial bool CreateHardLink(string lpFileName, string lpExistingFileName, IntPtr lpSecurityAttributes);
}
