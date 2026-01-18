using System.Globalization;
using System.IO;
using System.Windows;
using System.Windows.Data;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace ImageGalleryViewer.Converters;

/// <summary>
/// Converts a file path to a thumbnail image asynchronously
/// </summary>
public class PathToThumbnailConverter : IValueConverter
{
    private static readonly BitmapImage PlaceholderImage;
    
    static PathToThumbnailConverter()
    {
        // Create a simple placeholder
        PlaceholderImage = new BitmapImage();
    }
    
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        if (value is not string path || string.IsNullOrWhiteSpace(path))
            return DependencyProperty.UnsetValue;
            
        // Get thumbnail from service
        var thumbnail = App.Thumbnails?.GetThumbnail(path);
        
        if (thumbnail != null)
            return thumbnail;
            
        // Return placeholder and queue async load
        QueueAsyncLoad(path);
        return DependencyProperty.UnsetValue;
    }
    
    private void QueueAsyncLoad(string path)
    {
        // Load in background thread, then update UI
        System.Threading.Tasks.Task.Run(() =>
        {
            var thumbnail = App.Thumbnails?.GetThumbnail(path);
            // The binding will be re-evaluated when the image scrolls back into view
        });
    }
    
    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
    {
        throw new NotImplementedException();
    }
}

/// <summary>
/// Converts a label name to a color brush
/// </summary>
public class LabelToColorConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        var label = value as string;
        
        return label?.ToLowerInvariant() switch
        {
            "red" => new SolidColorBrush(Color.FromRgb(229, 57, 53)),     // Red
            "yellow" => new SolidColorBrush(Color.FromRgb(253, 216, 53)), // Yellow
            "green" => new SolidColorBrush(Color.FromRgb(67, 160, 71)),   // Green
            "blue" => new SolidColorBrush(Color.FromRgb(30, 136, 229)),   // Blue
            "purple" => new SolidColorBrush(Color.FromRgb(142, 36, 170)), // Purple
            _ => new SolidColorBrush(Colors.Transparent)
        };
    }
    
    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
    {
        throw new NotImplementedException();
    }
}

/// <summary>
/// Converts a score value (0-1) to a color representing quality
/// </summary>
public class ScoreToColorConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        double score = value switch
        {
            double d => d,
            float f => f,
            _ => 0
        };
        
        // Gradient from red (0) through yellow (0.5) to green (1)
        if (score < 0.5)
        {
            // Red to Yellow
            var factor = score * 2;
            return new SolidColorBrush(Color.FromRgb(
                229, 
                (byte)(57 + factor * 159), 
                53));
        }
        else
        {
            // Yellow to Green
            var factor = (score - 0.5) * 2;
            return new SolidColorBrush(Color.FromRgb(
                (byte)(253 - factor * 186),
                (byte)(216 - factor * 56),
                (byte)(53 + factor * 18)));
        }
    }
    
    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
    {
        throw new NotImplementedException();
    }
}

/// <summary>
/// Boolean to visibility converter
/// </summary>
public class BoolToVisibilityConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        return value is true ? Visibility.Visible : Visibility.Collapsed;
    }
    
    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
    {
        return value is Visibility.Visible;
    }
}
