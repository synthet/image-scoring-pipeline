using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;

namespace ImageGalleryViewer.Models;

/// <summary>
/// Represents a folder node in the tree hierarchy
/// </summary>
public partial class FolderNode : ObservableObject
{
    public string Name { get; set; } = string.Empty;
    public string Path { get; set; } = string.Empty;
    public string WindowsPath { get; set; } = string.Empty;
    public int ImageCount { get; set; }
    
    [ObservableProperty]
    private bool _isExpanded = true;
    
    [ObservableProperty]
    private bool _isSelected;
    
    public ObservableCollection<FolderNode> Children { get; } = new();
    
    /// <summary>
    /// Display name with image count
    /// </summary>
    public string DisplayName => ImageCount > 0 
        ? $"📁 {Name} ({ImageCount})" 
        : $"📁 {Name}";
}
