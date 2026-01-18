using System.IO;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace ImageGalleryViewer.Services;

/// <summary>
/// Extracts thumbnails using Windows Shell APIs for fast, native thumbnail generation
/// </summary>
public class ThumbnailService : IDisposable
{
    private readonly int _thumbnailSize;
    private readonly Dictionary<string, BitmapSource?> _cache = new();
    private readonly object _cacheLock = new();
    private readonly int _maxCacheSize;
    private bool _disposed;
    
    public ThumbnailService(int thumbnailSize = 160, int maxCacheSizeMb = 200)
    {
        _thumbnailSize = thumbnailSize;
        // Rough estimate: ~50KB per thumbnail at 160x120
        _maxCacheSize = (maxCacheSizeMb * 1024 * 1024) / (50 * 1024);
    }
    
    /// <summary>
    /// Get thumbnail for an image file
    /// </summary>
    public BitmapSource? GetThumbnail(string filePath)
    {
        if (string.IsNullOrWhiteSpace(filePath))
            return null;
            
        // Check cache first
        lock (_cacheLock)
        {
            if (_cache.TryGetValue(filePath, out var cached))
                return cached;
        }
        
        // Generate thumbnail
        var thumbnail = ExtractThumbnail(filePath);
        
        // Add to cache
        lock (_cacheLock)
        {
            if (_cache.Count >= _maxCacheSize)
            {
                // Simple eviction: remove first quarter of entries
                var toRemove = _cache.Keys.Take(_maxCacheSize / 4).ToList();
                foreach (var key in toRemove)
                    _cache.Remove(key);
            }
            
            _cache[filePath] = thumbnail;
        }
        
        return thumbnail;
    }
    
    /// <summary>
    /// Clear the thumbnail cache
    /// </summary>
    public void ClearCache()
    {
        lock (_cacheLock)
        {
            _cache.Clear();
        }
    }
    
    /// <summary>
    /// Extract thumbnail using Windows Shell
    /// </summary>
    private BitmapSource? ExtractThumbnail(string filePath)
    {
        if (!File.Exists(filePath))
            return null;
            
        try
        {
            // Use Shell to get thumbnail
            var result = NativeMethods.SHCreateItemFromParsingName(
                filePath, 
                IntPtr.Zero, 
                typeof(IShellItem).GUID, 
                out var shellItem);
                
            if (result != 0 || shellItem == null)
                return null;
                
            try
            {
                var factory = (IShellItemImageFactory)shellItem;
                var size = new SIZE { cx = _thumbnailSize, cy = _thumbnailSize };
                
                result = factory.GetImage(size, SIIGBF.SIIGBF_THUMBNAILONLY | SIIGBF.SIIGBF_BIGGERSIZEOK, out var hBitmap);
                
                if (result != 0 || hBitmap == IntPtr.Zero)
                {
                    // Try without THUMBNAILONLY flag
                    result = factory.GetImage(size, SIIGBF.SIIGBF_BIGGERSIZEOK, out hBitmap);
                }
                
                if (result == 0 && hBitmap != IntPtr.Zero)
                {
                    try
                    {
                        var source = Imaging.CreateBitmapSourceFromHBitmap(
                            hBitmap,
                            IntPtr.Zero,
                            Int32Rect.Empty,
                            BitmapSizeOptions.FromEmptyOptions());
                            
                        source.Freeze(); // Make it cross-thread accessible
                        return source;
                    }
                    finally
                    {
                        NativeMethods.DeleteObject(hBitmap);
                    }
                }
            }
            finally
            {
                Marshal.ReleaseComObject(shellItem);
            }
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"Thumbnail extraction failed for {filePath}: {ex.Message}");
        }
        
        return null;
    }
    
    public void Dispose()
    {
        if (!_disposed)
        {
            ClearCache();
            _disposed = true;
        }
    }
}

#region COM Interop

[StructLayout(LayoutKind.Sequential)]
internal struct SIZE
{
    public int cx;
    public int cy;
}

[Flags]
internal enum SIIGBF : uint
{
    SIIGBF_RESIZETOFIT = 0x00000000,
    SIIGBF_BIGGERSIZEOK = 0x00000001,
    SIIGBF_MEMORYONLY = 0x00000002,
    SIIGBF_ICONONLY = 0x00000004,
    SIIGBF_THUMBNAILONLY = 0x00000008,
    SIIGBF_INCACHEONLY = 0x00000010,
    SIIGBF_CROPTOSQUARE = 0x00000020,
    SIIGBF_WIDETHUMBNAILS = 0x00000040,
    SIIGBF_ICONBACKGROUND = 0x00000080,
    SIIGBF_SCALEUP = 0x00000100,
}

[ComImport]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
[Guid("43826d1e-e718-42ee-bc55-a1e261c37bfe")]
internal interface IShellItem
{
    void BindToHandler(IntPtr pbc, [MarshalAs(UnmanagedType.LPStruct)] Guid bhid, [MarshalAs(UnmanagedType.LPStruct)] Guid riid, out IntPtr ppv);
    void GetParent(out IShellItem ppsi);
    void GetDisplayName(uint sigdnName, out IntPtr ppszName);
    void GetAttributes(uint sfgaoMask, out uint psfgaoAttribs);
    void Compare(IShellItem psi, uint hint, out int piOrder);
}

[ComImport]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
[Guid("bcc18b79-ba16-442f-80c4-8a59c30c463b")]
internal interface IShellItemImageFactory
{
    [PreserveSig]
    int GetImage(SIZE size, SIIGBF flags, out IntPtr phbm);
}

internal static partial class NativeMethods
{
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = true)]
    internal static extern int SHCreateItemFromParsingName(
        [MarshalAs(UnmanagedType.LPWStr)] string pszPath,
        IntPtr pbc,
        [MarshalAs(UnmanagedType.LPStruct)] Guid riid,
        [MarshalAs(UnmanagedType.Interface)] out IShellItem ppv);
        
    [DllImport("gdi32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool DeleteObject(IntPtr hObject);
}

#endregion
