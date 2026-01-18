using Xunit;
using ImageGalleryViewer.Services;

namespace ImageGalleryViewer.Tests;

/// <summary>
/// Unit tests for PathResolver
/// </summary>
public class PathResolverTests
{
    [Theory]
    [InlineData("/mnt/d/Photos/file.jpg", "D:\\Photos\\file.jpg")]
    [InlineData("/mnt/c/Users/test/image.png", "C:\\Users\\test\\image.png")]
    [InlineData("/mnt/e/Backup/2024/photo.nef", "E:\\Backup\\2024\\photo.nef")]
    public void ToWindowsPath_ConvertsMountPaths(string wslPath, string expectedWindowsPath)
    {
        var result = PathResolver.ToWindowsPath(wslPath);
        Assert.Equal(expectedWindowsPath, result);
    }
    
    [Theory]
    [InlineData("D:\\Photos\\file.jpg")]
    [InlineData("C:\\Users\\test\\image.png")]
    public void ToWindowsPath_PreservesWindowsPaths(string windowsPath)
    {
        var result = PathResolver.ToWindowsPath(windowsPath);
        Assert.Equal(windowsPath, result);
    }
    
    [Theory]
    [InlineData("D:/Photos/file.jpg", "D:\\Photos\\file.jpg")]
    [InlineData("C:/Users/test/image.png", "C:\\Users\\test\\image.png")]
    public void ToWindowsPath_NormalizesForwardSlashes(string inputPath, string expected)
    {
        var result = PathResolver.ToWindowsPath(inputPath);
        Assert.Equal(expected, result);
    }
    
    [Theory]
    [InlineData("D:\\Photos\\file.jpg", "/mnt/d/Photos/file.jpg")]
    [InlineData("C:\\Users\\test\\image.png", "/mnt/c/Users/test/image.png")]
    public void ToWslPath_ConvertsWindowsPaths(string windowsPath, string expectedWslPath)
    {
        var result = PathResolver.ToWslPath(windowsPath);
        Assert.Equal(expectedWslPath, result);
    }
    
    [Theory]
    [InlineData("/mnt/d/Photos/file.jpg")]
    [InlineData("/mnt/c/path/to/image.jpg")]
    public void ToWslPath_PreservesWslPaths(string wslPath)
    {
        var result = PathResolver.ToWslPath(wslPath);
        Assert.Equal(wslPath, result);
    }
    
    [Fact]
    public void ToWindowsPath_HandlesEmptyString()
    {
        Assert.Equal(string.Empty, PathResolver.ToWindowsPath(""));
        Assert.Equal(string.Empty, PathResolver.ToWindowsPath(null));
        Assert.Equal(string.Empty, PathResolver.ToWindowsPath("   "));
    }
    
    [Fact]
    public void ToWslPath_HandlesEmptyString()
    {
        Assert.Equal(string.Empty, PathResolver.ToWslPath(""));
        Assert.Equal(string.Empty, PathResolver.ToWslPath(null));
        Assert.Equal(string.Empty, PathResolver.ToWslPath("   "));
    }
    
    [Fact]
    public void RoundTrip_PreservesPath()
    {
        var originalWsl = "/mnt/d/Photos/2024/vacation/image.jpg";
        var windows = PathResolver.ToWindowsPath(originalWsl);
        var backToWsl = PathResolver.ToWslPath(windows);
        
        Assert.Equal(originalWsl, backToWsl);
    }
}
