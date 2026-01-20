using System.Windows;
using System.IO;
using System;
using System.Threading.Tasks;
using System.Windows.Threading;
using ImageGalleryViewer.Services;

namespace ImageGalleryViewer;

/// <summary>
/// Application entry point
/// </summary>
public partial class App : Application
{
    public static SettingsService Settings { get; private set; } = null!;
    public static DatabaseService Database { get; private set; } = null!;
    public static ThumbnailService Thumbnails { get; private set; } = null!;
    
    protected override void OnStartup(StartupEventArgs e)
    {
        File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "startup_trace.log"), 
            $"[Trace] OnStartup called at {DateTime.Now}\n");
            
        // Global exception handling
        DispatcherUnhandledException += (s, args) =>
        {
            var crashLog = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "crash.log");
            File.AppendAllText(crashLog, $"[Dispatcher] Timestamp: {DateTime.Now}\nMessage: {args.Exception.Message}\nStack Trace:\n{args.Exception.StackTrace}\n\n");
            
            MessageBox.Show($"Unhandled Error:\n\n{args.Exception.Message}\n\nStack Trace:\n{args.Exception.StackTrace}", 
                "Image Gallery Viewer Crash", 
                MessageBoxButton.OK, 
                MessageBoxImage.Error);
            args.Handled = true;
            Shutdown(1);
        };

        TaskScheduler.UnobservedTaskException += (s, args) =>
        {
             var crashLog = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "crash.log");
             File.AppendAllText(crashLog, $"[Task] Timestamp: {DateTime.Now}\nMessage: {args.Exception.Message}\nStack Trace:\n{args.Exception.StackTrace}\n\n");
             
             MessageBox.Show($"Task Error:\n\n{args.Exception.Message}\n\nStack Trace:\n{args.Exception.StackTrace}", 
                "Image Gallery Viewer Crash", 
                MessageBoxButton.OK, 
                MessageBoxImage.Error);
             args.SetObserved();
        };

        try 
        {
            // Initialize services
            Settings = new SettingsService();
            // Settings.Load() is called manually in constructor now? No, I removed it from constructor. 
            // Wait, I need to call Settings.Load() if I removed it from constructor!
            Settings.Load();
            
            // Firebird Embedded
            // We expect scoring_history.fdb in the project root
            string dbPath = @"d:\Projects\image-scoring\scoring_history.fdb";
            
            // Ensure FirebirdQueryExecutor is used
            IQueryExecutor executor;
            try 
            {
                executor = new FirebirdQueryExecutor(dbPath);
                File.AppendAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "startup_trace.log"), 
                     $"[Database] Using Firebird Embedded at {dbPath}\n");
            }
            catch (Exception ex)
            {
                 // Fatal
                 MessageBox.Show($"Failed to initialize Firebird: {ex.Message}");
                 throw;
            }

            Database = new DatabaseService(executor);
            Thumbnails = new ThumbnailService(160, Settings.ThumbnailCacheSizeMb);
            
            // Cleanup old temp folders from Photos integration
            PhotosLauncher.CleanupOldFolders();
            
            // Base OnStartup will handle StartupUri
            base.OnStartup(e);
        }
        catch (Exception ex)
        {
            var crashLog = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "crash.log");
            File.WriteAllText(crashLog, $"[Startup] Timestamp: {DateTime.Now}\nMessage: {ex.Message}\nStack Trace:\n{ex.StackTrace}");
            
            MessageBox.Show($"Startup Error:\n\n{ex.Message}\n\nStack Trace:\n{ex.StackTrace}", 
                "Image Gallery Viewer Crash", 
                MessageBoxButton.OK, 
                MessageBoxImage.Error);
            Shutdown(1);
        }
    }
    
    protected override void OnExit(ExitEventArgs e)
    {
        base.OnExit(e);
        
        // Cleanup
        Thumbnails?.Dispose();
        Database?.Dispose();
        Settings?.Save();
    }
}

