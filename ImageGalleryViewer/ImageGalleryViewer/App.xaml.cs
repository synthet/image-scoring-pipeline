using System.Windows;
using ImageGalleryViewer.Services;

namespace ImageGalleryViewer;

/// <summary>
/// Application entry point
/// </summary>
public partial class App : Application
{
    public static SettingsService Settings { get; private set; } = null!;
    public static DatabaseService Database { get; private set; } = null!;
    
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        
        // Initialize services
        Settings = new SettingsService();
        Database = new DatabaseService(Settings.DatabasePath);
    }
    
    protected override void OnExit(ExitEventArgs e)
    {
        base.OnExit(e);
        
        // Cleanup
        Database?.Dispose();
        Settings?.Save();
    }
}
