using System.Collections.ObjectModel;
using System.IO;
using System.Windows.Input;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ImageGalleryViewer.Models;
using ImageGalleryViewer.Services;

namespace ImageGalleryViewer.ViewModels;

/// <summary>
/// Main view model for the gallery application
/// </summary>
public partial class MainViewModel : ObservableObject
{
    #region Observable Properties
    
    [ObservableProperty]
    private ObservableCollection<ImageRecord> _images = new();
    
    [ObservableProperty]
    private ImageRecord? _selectedImage;
    
    [ObservableProperty]
    private ObservableCollection<FolderNode> _folderTree = new();
    
    [ObservableProperty]
    private FolderNode? _selectedFolder;
    
    [ObservableProperty]
    private string _folderFilter = string.Empty;
    
    [ObservableProperty]
    private int? _stackFilter;
    
    [ObservableProperty]
    private int _totalImages;
    
    [ObservableProperty]
    private int _totalPages = 1;
    
    [ObservableProperty]
    private int _currentPage = 1;
    
    [ObservableProperty]
    private string _statusText = "Ready";
    
    [ObservableProperty]
    private bool _isLoading;
    
    // Filter properties
    [ObservableProperty]
    private bool _filterRating1;
    
    [ObservableProperty]
    private bool _filterRating2;
    
    [ObservableProperty]
    private bool _filterRating3;
    
    [ObservableProperty]
    private bool _filterRating4;
    
    [ObservableProperty]
    private bool _filterRating5;
    
    [ObservableProperty]
    private bool _filterLabelRed;
    
    [ObservableProperty]
    private bool _filterLabelYellow;
    
    [ObservableProperty]
    private bool _filterLabelGreen;
    
    [ObservableProperty]
    private bool _filterLabelBlue;
    
    [ObservableProperty]
    private bool _filterLabelPurple;
    
    [ObservableProperty]
    private bool _filterLabelNone;
    
    [ObservableProperty]
    private double _minScoreGeneral;
    
    [ObservableProperty]
    private double _minScoreAesthetic;
    
    [ObservableProperty]
    private double _minScoreTechnical;
    
    [ObservableProperty]
    private DateTime? _dateFrom;
    
    [ObservableProperty]
    private DateTime? _dateTo;
    
    [ObservableProperty]
    private string _keywordSearch = string.Empty;
    
    [ObservableProperty]
    private int _selectedSortIndex;
    
    [ObservableProperty]
    private bool _sortDescending = true;
    
    [ObservableProperty]
    private int _pageSize = 50;
    
    [ObservableProperty]
    private bool _isDetailsPanelVisible = true;
    
    #endregion
    
    #region Computed Properties
    
    public string PageInfo => $"Page {CurrentPage} of {TotalPages} ({TotalImages} images)";
    
    public bool CanGoBack => CurrentPage > 1;
    public bool CanGoForward => CurrentPage < TotalPages;
    
    public static string[] SortOptions => new[]
    {
        "📅 Date Added",
        "🆔 ID", 
        "⭐ General Score",
        "🔧 Technical Score",
        "🎨 Aesthetic Score"
    };
    
    public static int[] PageSizeOptions => new[] { 25, 50, 100, 200 };
    
    #endregion
    
    #region Folder Tree Methods
    
    private void LoadFolderTree()
    {
        try
        {
            var folders = App.Database.GetAllFolders();
            var counts = App.Database.GetFolderImageCounts();
            var roots = BuildFolderTree(folders, counts);
            
            FolderTree.Clear();
            foreach (var root in roots)
                FolderTree.Add(root);
        }
        catch (Exception ex)
        {
            StatusText = $"Error loading folders: {ex.Message}";
        }
    }
    
    private List<FolderNode> BuildFolderTree(List<string> wslPaths, Dictionary<string, int> counts)
    {
        var nodes = new Dictionary<string, FolderNode>();
        var roots = new List<FolderNode>();
        
        foreach (var wslPath in wslPaths.OrderBy(p => p))
        {
            var winPath = PathResolver.ToWindowsPath(wslPath);
            if (string.IsNullOrWhiteSpace(winPath)) continue;
            
            // Get parent path
            var parent = System.IO.Path.GetDirectoryName(winPath);
            var name = System.IO.Path.GetFileName(winPath);
            if (string.IsNullOrEmpty(name)) name = winPath;
            
            counts.TryGetValue(wslPath, out var count);
            
            var node = new FolderNode
            {
                Name = name,
                Path = wslPath,
                WindowsPath = winPath,
                ImageCount = count
            };
            nodes[winPath] = node;
            
            // Find parent
            if (!string.IsNullOrEmpty(parent) && nodes.TryGetValue(parent, out var parentNode))
            {
                parentNode.Children.Add(node);
            }
            else
            {
                roots.Add(node);
            }
        }
        
        return roots;
    }
    
    partial void OnSelectedFolderChanged(FolderNode? value)
    {
        if (value != null)
        {
            FolderFilter = value.WindowsPath;
            StatusText = $"Filtering by folder: {value.Name}";
            _ = LoadImagesAsync();
        }
    }
    
    [RelayCommand]
    private void ClearFolderFilter()
    {
        SelectedFolder = null;
        FolderFilter = string.Empty;
        _ = LoadImagesAsync();
    }
    
    [RelayCommand]
    private void FilterByStack()
    {
        if (SelectedImage?.StackId == null) return;
        
        StackFilter = SelectedImage.StackId;
        StatusText = $"Filtering by stack ID: {StackFilter}";
        _ = LoadImagesAsync();
    }
    
    [RelayCommand]
    private void ClearStackFilter()
    {
        StackFilter = null;
        _ = LoadImagesAsync();
    }
    
    #endregion
    
    #region Commands
    
    [RelayCommand]
    private void ToggleDetailsPanel()
    {
        IsDetailsPanelVisible = !IsDetailsPanelVisible;
    }

    [RelayCommand]
    private async Task RefreshAsync()
    {
        await LoadImagesAsync();
    }
    
    [RelayCommand]
    private async Task FirstPageAsync()
    {
        CurrentPage = 1;
        await LoadImagesAsync();
    }
    
    [RelayCommand]
    private async Task PreviousPageAsync()
    {
        if (CurrentPage > 1)
        {
            CurrentPage--;
            await LoadImagesAsync();
        }
    }
    
    [RelayCommand]
    private async Task NextPageAsync()
    {
        if (CurrentPage < TotalPages)
        {
            CurrentPage++;
            await LoadImagesAsync();
        }
    }
    
    [RelayCommand]
    private async Task LastPageAsync()
    {
        CurrentPage = TotalPages;
        await LoadImagesAsync();
    }
    
    [RelayCommand]
    private async Task ApplyFiltersAsync()
    {
        CurrentPage = 1;
        await LoadImagesAsync();
    }
    
    [RelayCommand]
    private async Task ResetFiltersAsync()
    {
        FilterRating1 = FilterRating2 = FilterRating3 = FilterRating4 = FilterRating5 = false;
        FilterLabelRed = FilterLabelYellow = FilterLabelGreen = FilterLabelBlue = FilterLabelPurple = FilterLabelNone = false;
        MinScoreGeneral = MinScoreAesthetic = MinScoreTechnical = 0;
        DateFrom = DateTo = null;
        MinScoreGeneral = MinScoreAesthetic = MinScoreTechnical = 0;
        DateFrom = DateTo = null;
        KeywordSearch = string.Empty;
        StackFilter = null;
        CurrentPage = 1;
        await LoadImagesAsync();
    }
    
    [RelayCommand]
    private void OpenInPhotos()
    {
        if (SelectedImage == null) return;
        
        try
        {
            var launcher = new PhotosLauncher();
            launcher.OpenImageInPhotos(Images.ToList(), Images.IndexOf(SelectedImage));
            StatusText = $"Opened in Photos: {SelectedImage.FileName}";
        }
        catch (Exception ex)
        {
            StatusText = $"Error opening Photos: {ex.Message}";
        }
    }
    
    [RelayCommand]
    private void OpenInExplorer()
    {
        if (SelectedImage == null) return;
        
        try
        {
            var path = SelectedImage.WindowsPath;
            if (File.Exists(path))
            {
                System.Diagnostics.Process.Start("explorer.exe", $"/select,\"{path}\"");
                StatusText = $"Opened folder: {Path.GetDirectoryName(path)}";
            }
            else
            {
                StatusText = $"File not found: {path}";
            }
        }
        catch (Exception ex)
        {
            StatusText = $"Error: {ex.Message}";
        }
    }
    
    [RelayCommand]
    private void CopyPath()
    {
        if (SelectedImage == null) return;
        
        try
        {
            System.Windows.Clipboard.SetText(SelectedImage.WindowsPath);
            StatusText = $"Copied: {SelectedImage.WindowsPath}";
        }
        catch (Exception ex)
        {
            StatusText = $"Error: {ex.Message}";
        }
    }
    
    #endregion
    
    #region Methods
    
    public async Task InitializeAsync()
    {
        StatusText = "Connecting to database...";
        LoadFolderTree();
        await LoadImagesAsync();
    }
    
    private async Task LoadImagesAsync()
    {
        IsLoading = true;
        StatusText = "Loading images...";
        
        try
        {
            var filter = BuildFilterState();
            
            await Task.Run(() =>
            {
                TotalImages = App.Database.GetImageCount(filter);
                TotalPages = Math.Max(1, (TotalImages + PageSize - 1) / PageSize);
                
                // Adjust current page if needed
                if (CurrentPage > TotalPages) CurrentPage = TotalPages;
                if (CurrentPage < 1) CurrentPage = 1;
                
                filter.Page = CurrentPage;
                var results = App.Database.GetImages(filter);
                
                // Update UI on main thread
                System.Windows.Application.Current.Dispatcher.Invoke(() =>
                {
                    Images.Clear();
                    foreach (var img in results)
                    {
                        // Verify file exists (can be slow, do in background later)
                        img.FileExists = File.Exists(img.WindowsPath);
                        Images.Add(img);
                    }
                });
            });
            
            OnPropertyChanged(nameof(PageInfo));
            OnPropertyChanged(nameof(CanGoBack));
            OnPropertyChanged(nameof(CanGoForward));
            
            StatusText = $"Loaded {Images.Count} images";
        }
        catch (Exception ex)
        {
            StatusText = $"Error: {ex.Message}";
        }
        finally
        {
            IsLoading = false;
        }
    }
    
    private FilterState BuildFilterState()
    {
        var filter = new FilterState
        {
            PageSize = PageSize,
            MinScoreGeneral = MinScoreGeneral,
            MinScoreAesthetic = MinScoreAesthetic,
            MinScoreTechnical = MinScoreTechnical,
            DateFrom = DateFrom,
            DateTo = DateTo,
            KeywordSearch = string.IsNullOrWhiteSpace(KeywordSearch) ? null : KeywordSearch,
            SortDescending = SortDescending
        };
        
        // Ratings
        var ratings = new List<int>();
        if (FilterRating1) ratings.Add(1);
        if (FilterRating2) ratings.Add(2);
        if (FilterRating3) ratings.Add(3);
        if (FilterRating4) ratings.Add(4);
        if (FilterRating5) ratings.Add(5);
        if (ratings.Count > 0) filter.Ratings = ratings;
        
        // Labels
        var labels = new List<string>();
        if (FilterLabelRed) labels.Add("Red");
        if (FilterLabelYellow) labels.Add("Yellow");
        if (FilterLabelGreen) labels.Add("Green");
        if (FilterLabelBlue) labels.Add("Blue");
        if (FilterLabelPurple) labels.Add("Purple");
        if (FilterLabelNone) labels.Add("None");
        if (labels.Count > 0) filter.Labels = labels;
        
        // Sort
        filter.SortBy = SelectedSortIndex switch
        {
            0 => "created_at",
            1 => "id",
            2 => "score_general",
            3 => "score_technical",
            4 => "score_aesthetic",
            _ => "score_general"
        };
        
        if (!string.IsNullOrWhiteSpace(FolderFilter))
        {
            filter.FolderPath = FolderFilter;
        }
        
        // Stack filter
        filter.StackId = StackFilter;
        
        return filter;
    }
    
    partial void OnSelectedImageChanged(ImageRecord? value)
    {
        if (value != null)
        {
            StatusText = $"Selected: {value.FileName} | Score: {value.ScoreDisplay} | {value.RatingDisplay}";
        }
    }
    
    partial void OnCurrentPageChanged(int value)
    {
        OnPropertyChanged(nameof(PageInfo));
        OnPropertyChanged(nameof(CanGoBack));
        OnPropertyChanged(nameof(CanGoForward));
    }
    
    partial void OnTotalPagesChanged(int value)
    {
        OnPropertyChanged(nameof(PageInfo));
        OnPropertyChanged(nameof(CanGoBack));
        OnPropertyChanged(nameof(CanGoForward));
    }
    
    #endregion
}
