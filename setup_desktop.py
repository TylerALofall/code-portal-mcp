"""
Setup Desktop Installation
========================
This script sets up CodePortal with a desktop shortcut and required dependencies.
Run this script to configure everything automatically.
"""

import os
import sys
import subprocess
import shutil
import platform
import time
import ctypes

def is_admin():
    """Check if the script is running with admin rights"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def install_dependencies():
    """Install required Python dependencies"""
    print("Installing required dependencies...")
    
    # Core dependencies
    dependencies = [
        "fastapi",
        "uvicorn",
        "pydantic",
        "winshell",
        "pywin32",
        "requests"
    ]
    
    for dep in dependencies:
        print(f"Installing {dep}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
        except Exception as e:
            print(f"Error installing {dep}: {e}")
            print("You may need to install this manually: pip install " + dep)
    
    print("Dependencies installed successfully.")

def create_desktop_shortcut():
    """Create the desktop shortcut using the dedicated module"""
    try:
        print("Creating desktop shortcut...")
        from create_desktop_shortcut import create_desktop_shortcut
        success = create_desktop_shortcut()
        if success:
            print("Desktop shortcut created successfully!")
        else:
            print("Failed to create desktop shortcut.")
    except Exception as e:
        print(f"Error creating shortcut: {e}")
        print("You may need to run the script with administrator privileges.")

def update_mcp_config():
    """Update Codeium MCP config to include CodePortal"""
    try:
        import json
        
        # Get script directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Path to the server script
        server_path = os.path.join(script_dir, "code_portal_mcp.py")
        
        # Path to Codeium MCP config
        mcp_config_path = os.path.join(os.path.expanduser("~"), ".codeium", "windsurf", "mcp_config.json")
        
        if os.path.exists(mcp_config_path):
            # Load existing config
            with open(mcp_config_path, 'r') as f:
                config = json.load(f)
            
            # Ensure mcpServers section exists
            if "mcpServers" not in config:
                config["mcpServers"] = {}
            
            # Add CodePortal to MCP servers
            config["mcpServers"]["codePortal"] = {
                "command": "python",
                "args": [server_path]
            }
            
            # Save updated config
            with open(mcp_config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            print("✅ Updated Codeium MCP config with CodePortal")
        else:
            print("❌ Codeium MCP config not found at", mcp_config_path)
    except Exception as e:
        print(f"Error updating MCP config: {e}")

def main():
    """Main installation function"""
    print("=" * 60)
    print("CodePortal Desktop Setup")
    print("=" * 60)
    
    # Check if running with admin privileges
    if not is_admin() and platform.system() == "Windows":
        print("⚠️ Warning: Not running with administrator privileges")
        print("Some features may not work correctly.")
        print("-" * 60)
    
    # Install dependencies
    install_dependencies()
    print("-" * 60)
    
    # Create desktop shortcut
    create_desktop_shortcut()
    print("-" * 60)
    
    # Update MCP config
    update_mcp_config()
    print("-" * 60)
    
    print("Setup completed!")
    print("You can now start CodePortal by double-clicking the desktop icon")
    print("or by running start_server.bat")
    print("=" * 60)
    
    # Wait for user to read
    input("Press Enter to close...")

if __name__ == "__main__":
    main()