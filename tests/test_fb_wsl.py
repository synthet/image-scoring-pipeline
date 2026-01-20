try:
    from firebird.driver import connect, driver_config
    print("Import Success: firebird.driver found")
    
    try:
        # Just try to resolve the client library. 
        # We don't have a running server yet, so connection might fail, 
        # but if DLL is missing, it fails earlier.
        # We try to connect to a dummy string to trigger library load
        connect('localhost:dummy.fdb', user='sysdba', password='masterkey')
    except Exception as e:
        print(f"Connection/Library Error: {e}")
        import ctypes
        try:
            ctypes.CDLL("libfbclient.so.2")
            print("CTypes: libfbclient.so.2 found")
        except:
            print("CTypes: libfbclient.so.2 NOT found")

except ImportError:
    print("Import Error: firebird-driver not installed")
