using System.IO;
using Xunit;
using ImageGalleryViewer.Models;
using ImageGalleryViewer.Services;

namespace ImageGalleryViewer.Tests;

/// <summary>
/// Unit tests for PhotosLauncher hard link functionality
/// </summary>
public class PhotosLauncherTests
{
    private readonly string _testFolder;
    
    public PhotosLauncherTests()
    {
        _testFolder = Path.Combine(Path.GetTempPath(), "ImageGalleryViewerTests", Guid.NewGuid().ToString("N")[..8]);
        Directory.CreateDirectory(_testFolder);
    }
    
    [Fact]
    public void CleanupOldFolders_DoesNotThrow()
    {
        // Act - should not throw even with no folders
        var exception = Record.Exception(() => PhotosLauncher.CleanupOldFolders());
        
        // Assert
        Assert.Null(exception);
    }
    
    [Fact]
    public void OpenImageInPhotos_WithEmptyList_DoesNotThrow()
    {
        // Arrange
        var launcher = new PhotosLauncher();
        var images = new List<ImageRecord>();
        
        // Act - should not throw with empty list
        var exception = Record.Exception(() => launcher.OpenImageInPhotos(images, 0));
        
        // Assert
        Assert.Null(exception);
    }
    
    [Fact]
    public void OpenImageInPhotos_WithInvalidIndex_DoesNotThrow()
    {
        // Arrange
        var launcher = new PhotosLauncher();
        var images = new List<ImageRecord>
        {
            new ImageRecord { WindowsPath = @"C:\nonexistent\test.jpg" }
        };
        
        // Act - should not throw with out of range index
        var exception = Record.Exception(() => launcher.OpenImageInPhotos(images, -1));
        
        // Assert
        Assert.Null(exception);
    }
    
    [Fact]
    public void ImageRecord_WindowsPath_ReturnsSetValue()
    {
        // Arrange
        var record = new ImageRecord
        {
            FilePath = "/mnt/d/Photos/test.jpg",
            WindowsPath = @"D:\Photos\test.jpg"
        };
        
        // Assert
        Assert.Equal(@"D:\Photos\test.jpg", record.WindowsPath);
    }
    
    [Fact]
    public void ImageRecord_ScoreDisplay_FormatsCorrectly()
    {
        // Arrange
        var record = new ImageRecord { ScoreGeneral = 0.85 };
        
        // Act
        var display = record.ScoreDisplay;
        
        // Assert - score should be ~0.85 regardless of culture formatting
        Assert.True(double.TryParse(display.Replace(',', '.'), 
            System.Globalization.NumberStyles.Any, 
            System.Globalization.CultureInfo.InvariantCulture, 
            out var parsed));
        Assert.Equal(0.85, parsed, 2);
    }
    
    [Fact]
    public void ImageRecord_RatingDisplay_ShowsStars()
    {
        // Arrange
        var record = new ImageRecord { Rating = 4 };
        
        // Act
        var display = record.RatingDisplay;
        
        // Assert
        Assert.Contains("★", display);
    }
    
    [Fact]
    public void ImageRecord_RatingDisplay_NoRating_ReturnsEmptyStars()
    {
        // Arrange
        var record = new ImageRecord { Rating = null };
        
        // Act
        var display = record.RatingDisplay;
        
        // Assert - returns 5 empty stars when no rating
        Assert.Equal("☆☆☆☆☆", display);
    }
}
