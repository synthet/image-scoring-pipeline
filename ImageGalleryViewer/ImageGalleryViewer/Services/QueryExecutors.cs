using System.Data;
using System.IO;
using System.Text.Json;
using System.Windows;
using FirebirdSql.Data.FirebirdClient;

namespace ImageGalleryViewer.Services;

public interface IQueryExecutor : IDisposable
{
    List<Dictionary<string, object>> ExecuteQuery(string query, Dictionary<string, object> parameters);
    object? ExecuteScalar(string query, Dictionary<string, object> parameters);
    bool IsConnected { get; }
}

public class FirebirdQueryExecutor : IQueryExecutor
{
    private string _connectionString = string.Empty;
    private FbConnection? _connection;

    public bool IsConnected => _connection?.State == ConnectionState.Open;

    public FirebirdQueryExecutor(string databasePath)
    {
        // Construct Firebird connection string for Embedded
        var builder = new FbConnectionStringBuilder
        {
            Database = databasePath,
            UserID = "sysdba",
            Password = "masterkey",
            ServerType = FbServerType.Embedded,
            ClientLibrary = "fbclient.dll", 
            Charset = "UTF8",
            Pooling = true
        };
        
        // Point to the specific client library if we can
        // To be safe, we assume fbclient.dll is in strict location?
        // Let's assume it's in a 'Firebird' subfolder near the exe or project root.
        // For development, we hardcode lookup.
        
        var baseDir = AppDomain.CurrentDomain.BaseDirectory;
        // In dev: d:\Projects\...\bin\Debug\net8.0-windows\
        // We put Firebird at d:\Projects\image-scoring\Firebird\
        
        // Try to find fbclient.dll
        var possiblePaths = new[]
        {
            Path.Combine(baseDir, "fbclient.dll"),
            Path.Combine(baseDir, "Firebird", "fbclient.dll"),
            @"d:\Projects\image-scoring\Firebird\fbclient.dll"
        };
        
        foreach (var p in possiblePaths)
        {
            if (File.Exists(p))
            {
                builder.ClientLibrary = p;
                break; 
            }
        }

        _connectionString = builder.ToString();
        
        InitializeConnection();
    }

    private void InitializeConnection()
    {
        // Strategy:
        // 1. Try TCP Connection (Client/Server) - Allows concurrency.
        // 2. If fails, try to Launch Firebird Server (-a application mode) and retry TCP.
        // 3. If everything fails, Fallback to Embedded (Exclusive Lock).

        if (TryTcpConnection()) 
            return;

        // TCP Failed. Try to launch server.
        System.Diagnostics.Debug.WriteLine("[DB] TCP Connection failed. Attempting to launch Firebird Server...");
        LaunchFirebirdServer();

        // Retry TCP
        if (TryTcpConnection())
            return;

        // Fallback to Embedded
        System.Diagnostics.Debug.WriteLine("[DB] TCP failed after server launch. Falling back to Embedded mode.");
        InitializeEmbeddedConnection();
    }

    private bool TryTcpConnection()
    {
        try
        {
            // Update connection string to Server Mode
            var builder = new FbConnectionStringBuilder(_connectionString)
            {
                ServerType = FbServerType.Default,
                DataSource = "localhost",
                Pooling = true
            };
            
            var serverConnString = builder.ToString();
            var conn = new FbConnection(serverConnString);
            conn.Open();

            // Success! Replace our state
            if (_connection != null) _connection.Dispose();
            _connection = conn;
            _connectionString = serverConnString; // Store success
            
            System.Diagnostics.Debug.WriteLine("[DB] Connected via TCP (Client/Server).");
            return true;
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"[DB] TCP Attempt failed: {ex.Message}");
            return false;
        }
    }

    private void InitializeEmbeddedConnection()
    {
        try
        {
            if (_connection != null) _connection.Dispose();
            
            // Ensure connection string is set to Embedded
            var builder = new FbConnectionStringBuilder(_connectionString)
            {
                ServerType = FbServerType.Embedded,
                DataSource = null // Clear localhost
            };

            _connectionString = builder.ToString();
            _connection = new FbConnection(_connectionString);
            _connection.Open();
            
            System.Diagnostics.Debug.WriteLine("[DB] Connected via Embedded (Exclusive).");
        }
        catch (Exception ex)
        {
            MessageBox.Show($"Failed to connect to Firebird database.\n\n" +
                            $"All connection methods failed.\n" +
                            $"Error: {ex.Message}", 
                            "Database Error", MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }

    private void LaunchFirebirdServer()
    {
        try
        {
            // Locate Firebird executable
            // We expect it in a folder named 'Firebird' relative to app
            var baseDir = AppDomain.CurrentDomain.BaseDirectory;
            var fbExe = Path.Combine(baseDir, "Firebird", "firebird.exe");

            if (!File.Exists(fbExe))
            {
                // Fallback for dev environment hardcoded path
                if (File.Exists(@"d:\Projects\image-scoring\Firebird\firebird.exe"))
                    fbExe = @"d:\Projects\image-scoring\Firebird\firebird.exe";
                else
                {
                    System.Diagnostics.Debug.WriteLine("[DB] firebird.exe not found. Cannot launch server.");
                    return;
                }
            }

            var procInfo = new System.Diagnostics.ProcessStartInfo
            {
                FileName = fbExe,
                Arguments = "-a", // Application mode
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true
            };

            System.Diagnostics.Process.Start(procInfo);
            
            // Give it a moment to start
            System.Threading.Thread.Sleep(2000); 
            System.Diagnostics.Debug.WriteLine($"[DB] Firebird Server launched: {fbExe}");
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"[DB] Failed to launch Firebird Server: {ex.Message}");
        }
    }

    public List<Dictionary<string, object>> ExecuteQuery(string query, Dictionary<string, object> parameters)
    {
        if (_connection == null || _connection.State != ConnectionState.Open)
            InitializeConnection();

        if (_connection == null || _connection.State != ConnectionState.Open)
            return new List<Dictionary<string, object>>();

        var results = new List<Dictionary<string, object>>();

        try
        {
            using var command = new FbCommand(query, _connection);
            foreach (var param in parameters)
            {
                command.Parameters.AddWithValue(param.Key, param.Value ?? DBNull.Value);
            }

            using var reader = command.ExecuteReader();
            while (reader.Read())
            {
                var row = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);
                for (int i = 0; i < reader.FieldCount; i++)
                {
                    row[reader.GetName(i)] = reader.GetValue(i);
                }
                results.Add(row);
            }
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"Query Error: {ex.Message}");
            throw;
        }

        return results;
    }

    public object? ExecuteScalar(string query, Dictionary<string, object> parameters)
    {
        if (_connection == null || _connection.State != ConnectionState.Open)
            InitializeConnection();
            
        try
        {
            using var command = new FbCommand(query, _connection);
            foreach (var param in parameters)
            {
                command.Parameters.AddWithValue(param.Key, param.Value ?? DBNull.Value);
            }
            return command.ExecuteScalar();
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"Scalar Error: {ex.Message}");
            return null;
        }
    }

    public void Dispose()
    {
        _connection?.Close();
        _connection?.Dispose();
    }
}
