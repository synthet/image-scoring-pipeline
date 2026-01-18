using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using ImageGalleryViewer.ViewModels;

namespace ImageGalleryViewer;

/// <summary>
/// Main window code-behind
/// </summary>
public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        
        // Restore window size from settings
        if (App.Settings.WindowWidth > 0)
            Width = App.Settings.WindowWidth;
        if (App.Settings.WindowHeight > 0)
            Height = App.Settings.WindowHeight;
        
        Loaded += MainWindow_Loaded;
        Closing += MainWindow_Closing;
        ImageGrid.MouseDoubleClick += ImageGrid_MouseDoubleClick;
        PreviewKeyDown += MainWindow_PreviewKeyDown;
    }
    
    private async void MainWindow_Loaded(object sender, RoutedEventArgs e)
    {
        if (DataContext is MainViewModel viewModel)
        {
            await viewModel.InitializeAsync();
        }
        
        // Focus the image grid for keyboard navigation
        ImageGrid.Focus();
    }
    
    private void MainWindow_Closing(object? sender, System.ComponentModel.CancelEventArgs e)
    {
        // Save window size
        App.Settings.WindowWidth = Width;
        App.Settings.WindowHeight = Height;
        App.Settings.Save();
    }
    
    private void MainWindow_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (DataContext is not MainViewModel viewModel) return;
        
        switch (e.Key)
        {
            case Key.F5:
                // Refresh
                viewModel.RefreshCommand.Execute(null);
                e.Handled = true;
                break;
                
            case Key.Enter:
                // Open in Photos
                if (viewModel.SelectedImage != null)
                {
                    viewModel.OpenInPhotosCommand.Execute(null);
                    e.Handled = true;
                }
                break;
                
            case Key.PageDown:
                // Next page
                if (viewModel.CanGoForward)
                {
                    viewModel.NextPageCommand.Execute(null);
                    e.Handled = true;
                }
                break;
                
            case Key.PageUp:
                // Previous page
                if (viewModel.CanGoBack)
                {
                    viewModel.PreviousPageCommand.Execute(null);
                    e.Handled = true;
                }
                break;
                
            case Key.Home:
                // First page (Ctrl+Home)
                if (Keyboard.Modifiers == ModifierKeys.Control)
                {
                    viewModel.FirstPageCommand.Execute(null);
                    e.Handled = true;
                }
                break;
                
            case Key.End:
                // Last page (Ctrl+End)
                if (Keyboard.Modifiers == ModifierKeys.Control)
                {
                    viewModel.LastPageCommand.Execute(null);
                    e.Handled = true;
                }
                break;
                
            case Key.E:
                // Show in Explorer (Ctrl+E)
                if (Keyboard.Modifiers == ModifierKeys.Control && viewModel.SelectedImage != null)
                {
                    viewModel.OpenInExplorerCommand.Execute(null);
                    e.Handled = true;
                }
                break;
                
            case Key.C:
                // Copy path (Ctrl+Shift+C)
                if (Keyboard.Modifiers == (ModifierKeys.Control | ModifierKeys.Shift) && viewModel.SelectedImage != null)
                {
                    viewModel.CopyPathCommand.Execute(null);
                    e.Handled = true;
                }
                break;
        }
    }
    
    private void ImageGrid_MouseDoubleClick(object sender, MouseButtonEventArgs e)
    {
        if (DataContext is MainViewModel viewModel && viewModel.SelectedImage != null)
        {
            viewModel.OpenInPhotosCommand.Execute(null);
        }
    }
}

