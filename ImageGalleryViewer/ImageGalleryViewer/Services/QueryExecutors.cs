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
    private readonly string _connectionString;
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
            ServerType = FbServerType.Default, // Use Client/Server to connect to the running firebird.exe
            DataSource = "localhost",
            Port = 3050,
            ClientLibrary = "fbclient.dll", // Must be in PATH or local
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
        try
        {
            _connection = new FbConnection(_connectionString);
            _connection.Open();
        }
        catch (Exception ex)
        {
            MessageBox.Show($"Failed to connect to Firebird: {ex.Message}", "Database Error", MessageBoxButton.OK, MessageBoxImage.Error);
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
