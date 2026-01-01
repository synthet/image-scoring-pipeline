import os
import platform
import warnings
from modules.ui import app

# Suppress TensorFlow logging
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# Suppress Gradio 6.0 deprecation warnings
warnings.filterwarnings("ignore", message="The 'css' parameter in the Blocks constructor")
warnings.filterwarnings("ignore", message="The 'head' parameter in the Blocks constructor")

def main():
    # Cache platform check
    is_windows = platform.system() == "Windows"
    
    # MCP Server Integration (optional - for Cursor debugging)
    mcp_enabled = os.environ.get('ENABLE_MCP_SERVER', '0') == '1'
    mcp_available = False
    try:
        from modules import mcp_server
        mcp_available = True
    except ImportError:
        pass
    
    # Create UI and initialize engines
    demo, runner, tagging_runner = app.create_ui()
    
    # Setup MCP server if enabled
    if mcp_available and mcp_enabled:
        mcp_server.set_runners(runner, tagging_runner)
        mcp_server.start_mcp_server_background()
        print("MCP Server: Started in background for debugging access")
    
    # Configure server endpoints (RAW preview, etc.)
    app.setup_server_endpoints(demo)
    
    # Launch
    allowed_paths = [os.path.abspath("."), os.path.abspath("thumbnails")]
    if is_windows:
        allowed_paths.append("D:/")
    else:
        allowed_paths.append("/mnt/")
        
    print(f"Starting WebUI on {platform.system()}...")
    demo.queue().launch(inbrowser=False, allowed_paths=allowed_paths)

if __name__ == "__main__":
    main()
