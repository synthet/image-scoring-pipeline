using System.Globalization;
using System.Windows;
using ImageGalleryViewer.Converters;
using Xunit;

namespace ImageGalleryViewer.Tests;

public class NullToVisibilityConverterTests
{
    private readonly NullToVisibilityConverter _converter = new();

    [Fact]
    public void Convert_Null_ReturnsCollapsed()
    {
        var result = _converter.Convert(null, typeof(Visibility), null, CultureInfo.InvariantCulture);
        Assert.Equal(Visibility.Collapsed, result);
    }

    [Fact]
    public void Convert_NotNull_ReturnsVisible()
    {
        var result = _converter.Convert(new object(), typeof(Visibility), null, CultureInfo.InvariantCulture);
        Assert.Equal(Visibility.Visible, result);
    }

    [Fact]
    public void Convert_Null_Inverted_ReturnsVisible()
    {
        var result = _converter.Convert(null, typeof(Visibility), "Inverted", CultureInfo.InvariantCulture);
        Assert.Equal(Visibility.Visible, result);
    }

    [Fact]
    public void Convert_NotNull_Inverted_ReturnsCollapsed()
    {
        var result = _converter.Convert(new object(), typeof(Visibility), "Inverted", CultureInfo.InvariantCulture);
        Assert.Equal(Visibility.Collapsed, result);
    }
}
