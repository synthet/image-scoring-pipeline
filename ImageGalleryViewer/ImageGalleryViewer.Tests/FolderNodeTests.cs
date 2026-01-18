using ImageGalleryViewer.Models;
using Xunit;

namespace ImageGalleryViewer.Tests;

public class FolderNodeTests
{
    [Fact]
    public void DisplayName_WithImages_ShowsCount()
    {
        // Arrange
        var node = new FolderNode
        {
            Name = "Photos",
            ImageCount = 42
        };

        // Act
        var display = node.DisplayName;

        // Assert
        Assert.Equal("📁 Photos (42)", display);
    }

    [Fact]
    public void DisplayName_NoImages_ShowsOnlyName()
    {
        // Arrange
        var node = new FolderNode
        {
            Name = "Empty",
            ImageCount = 0
        };

        // Act
        var display = node.DisplayName;

        // Assert
        Assert.Equal("📁 Empty", display);
    }

    [Fact]
    public void Hierarchy_AddChild_UpdatesChildrenCollection()
    {
        // Arrange
        var parent = new FolderNode { Name = "Parent" };
        var child = new FolderNode { Name = "Child" };

        // Act
        parent.Children.Add(child);

        // Assert
        Assert.Single(parent.Children);
        Assert.Equal(child, parent.Children[0]);
    }
}
