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
        
        Loaded += MainWindow_Loaded;
        ImageGrid.MouseDoubleClick += ImageGrid_MouseDoubleClick;
    }
    
    private async void MainWindow_Loaded(object sender, RoutedEventArgs e)
    {
        if (DataContext is MainViewModel viewModel)
        {
            await viewModel.InitializeAsync();
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
