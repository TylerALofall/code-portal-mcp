"""
CodePortal MCP Server
=====================
This server automatically shuts down after a configurable time to keep things clean.
It requires proper setup and authorization to work with external models.

SECURITY FEATURES:
- Required setup wizard on first run
- No preconfigured paths or settings
- API key authentication
- IP address filtering
- Auto-shutdown timer
"""

from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Union, Any
import importlib.util
import sys
import os
import json
import datetime
import threading
import time
import shutil
import secrets
import uuid
import socket

# =================================================
# STEP 1: Load configuration
# =================================================
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

def load_config():
    """Load config from config.json"""
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Warning: Could not load config.json: {e}")
        # Return a minimal config that requires setup
        return {
            "script_paths": {
                "primary": "",
                "desktop": ""
            },
            "active_script": "primary",
            "archive_dir": "Desktop",
            "auto_shutdown_minutes": 15,
            "port": 8001,
            "setup_complete": False,
            "api_config": {
                "public_mode": False,
                "api_key": "CHANGE_THIS_KEY_BEFORE_USING",
                "allowed_ips": ["127.0.0.1"],
                "max_file_size_mb": 50
            }
        }

def save_config(config_data):
    """Save config to config.json"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config_data, f, indent=2)
        return True
    except Exception as e:
        print(f"❌ Error saving config: {e}")
        return False

# Load configuration
config = load_config()

# Check if setup has been completed
SETUP_COMPLETE = config.get("setup_complete", False)
if not SETUP_COMPLETE:
    print("\n" + "=" * 60)
    print("⚠️ SETUP REQUIRED")
    print("   Please complete setup by visiting http://localhost:8001/setup")
    print("   when the server starts.")
    print("=" * 60 + "\n")

# Get the active script path
script_path = ""
script_module = None
Config = None
ProjectManager = None
config_obj = None
project_manager = None

def load_script():
    """Load the script_starter.py file"""
    global script_path, script_module, Config, ProjectManager, config_obj, project_manager
    
    if not SETUP_COMPLETE:
        print("⚠️ Setup not complete. Script will not be loaded.")
        return False
        
    active_script_key = config.get("active_script", "primary")
    script_path = config["script_paths"].get(active_script_key, "")
    
    if not script_path or not os.path.exists(script_path):
        # Try the other script if the primary doesn't exist
        for key, path in config["script_paths"].items():
            if path and os.path.exists(path):
                script_path = path
                config["active_script"] = key
                print(f"⚠️ Using alternative script: {key} at {path}")
                break

    if not script_path or not os.path.exists(script_path):
        print("❌ ERROR: Could not find any valid Script_starter.py!")
        print(f"   Checked paths: {list(config['script_paths'].values())}")
        return False

    print(f"🔍 Using script: {script_path}")

    # =================================================
    # STEP 2: Load your existing Script_starter.py code
    # =================================================
    try:
        spec = importlib.util.spec_from_file_location("script_starter", script_path)
        script_module = importlib.util.module_from_spec(spec)
        sys.modules["script_starter"] = script_module
        spec.loader.exec_module(script_module)
        print("✅ Successfully loaded Script_starter.py")
        
        # Get classes from your script
        Config = script_module.Config
        ProjectManager = script_module.ProjectManager
        
        # Create instances we'll use
        config_obj = Config()
        project_manager = ProjectManager(config_obj)
        print("✅ Project manager initialized")
        
        # Override archive directory if specified
        if config.get("archive_dir") == "Desktop":
            script_module.ARCHIVE_DIR = os.path.join(os.path.expanduser("~"), "Desktop", ".codeportal_archive")
            os.makedirs(script_module.ARCHIVE_DIR, exist_ok=True)
            print(f"📁 Archive directory set to: {script_module.ARCHIVE_DIR}")
            
        return True
        
    except Exception as e:
        print(f"❌ ERROR loading Script_starter.py: {e}")
        print("   The server will start but project creation may not work.")
        print("   Please fix Script_starter.py by adding 'import math' at the top.")
        return False

# Try to load script if setup is complete
if SETUP_COMPLETE:
    load_script()

# Cache for recent projects to avoid reopening files
RECENT_PROJECTS_CACHE = config_obj.get_recent_projects() if config_obj else []

# =================================================
# STEP 3: Create our API models
# =================================================
class SetupRequest(BaseModel):
    script_primary_path: str
    script_desktop_path: str
    archive_dir: str
    enable_public_mode: bool
    api_key: str
    auto_shutdown_minutes: int

class ProjectRequest(BaseModel):
    project_path: str
    project_name: str
    files: Dict[str, str]  # filename → content
    description: Optional[str] = None
    instructions: Optional[str] = None
    
class ProjectResponse(BaseModel):
    success: bool
    message: str
    project_path: str
    file_count: int
    project_name: str
    instructions_path: Optional[str] = None

# API key security
api_key_header = APIKeyHeader(name="Authorization")

def get_api_key(api_key_header: str = Depends(api_key_header)):
    """Validate the API key"""
    if not config.get("api_config", {}).get("public_mode", False):
        # If public mode is off, don't check API key
        return True
        
    expected_key = config.get("api_config", {}).get("api_key", "")
    if expected_key == "CHANGE_THIS_KEY_BEFORE_USING":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Default API key not changed. Server is not secure."
        )
    
    if not api_key_header or not api_key_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format. Use: Authorization: Bearer YOUR_KEY"
        )
    
    key = api_key_header.replace("Bearer ", "")
    if key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    return True

# IP filtering middleware
async def validate_client_ip(request: Request):
    if not config.get("api_config", {}).get("public_mode", False):
        # If public mode is off, allow only localhost
        client_host = request.client.host
        if client_host != "127.0.0.1" and client_host != "localhost" and client_host != "::1":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Server is in local-only mode."
            )
        return
        
    # If public mode is on, check allowed IPs
    allowed_ips = config.get("api_config", {}).get("allowed_ips", ["127.0.0.1"])
    client_host = request.client.host
    
    if client_host not in allowed_ips and "0.0.0.0" not in allowed_ips:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied from IP: {client_host}"
        )

# =================================================
# STEP 4: Set up the API server
# =================================================
app = FastAPI(
    title="CodePortal MCP",
    description="Helps organize code files into properly structured projects",
    version="1.0.0"
)

# Add IP validation middleware
@app.middleware("http")
async def ip_validator_middleware(request: Request, call_next):
    # Skip IP validation for setup page
    if request.url.path == "/setup" or request.url.path == "/perform_setup":
        return await call_next(request)
        
    # Validate IP for all other routes
    try:
        await validate_client_ip(request)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
        
    return await call_next(request)

# Allow cross-origin requests for API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Welcome page with basic info"""
    # Redirect to setup if not completed
    if not SETUP_COMPLETE:
        return RedirectResponse(url="/setup")
        
    # Get computer hostname and IP
    hostname = socket.gethostname()
    ip = None
    try:
        ip = socket.gethostbyname(hostname)
    except:
        ip = "Unknown"
    
    html_content = f"""
    <html>
        <head>
            <title>CodePortal MCP Server</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; line-height: 1.6; }}
                .container {{ max-width: 800px; margin: 0 auto; }}
                h1 {{ color: #4CAF50; }}
                .status {{ padding: 15px; background-color: #f8f9fa; border-radius: 5px; margin-bottom: 20px; }}
                .success {{ color: green; }}
                .warning {{ color: orange; }}
                .error {{ color: red; }}
                .security {{ background-color: #fff3cd; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                .endpoints {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; }}
                .footer {{ margin-top: 30px; font-size: 0.8em; color: #6c757d; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>CodePortal MCP Server</h1>
                <div class="status">
                    <h2>Status</h2>
                    <p><span class="success">✅ Server running</span></p>
                    <p>Using script: <code>{script_path}</code></p>
                    <p>Archive directory: <code>{script_module.ARCHIVE_DIR if script_module and hasattr(script_module, 'ARCHIVE_DIR') else 'Not set'}</code></p>
                    <p>Auto-shutdown: <span class="warning">⏰ {config.get('auto_shutdown_minutes', 15)} minutes</span></p>
                    <p>Server Address: <code>http://{ip}:{config.get('port', 8001)}</code></p>
                </div>
                
                <div class="security">
                    <h2>Security Settings</h2>
                    <p>Public API mode: <strong>{'Enabled' if config.get('api_config', {}).get('public_mode') else 'Disabled'}</strong></p>
                    <p>API key: {'Configured' if config.get('api_config', {}).get('api_key') != 'CHANGE_THIS_KEY_BEFORE_USING' else '<span class="error">NOT CHANGED FROM DEFAULT!</span>'}</p>
                    <p>Allowed IPs: {', '.join(config.get('api_config', {}).get('allowed_ips', ['127.0.0.1']))}</p>
                </div>
                
                <div class="endpoints">
                    <h2>API Endpoints</h2>
                    <ul>
                        <li><code>POST /createProject</code> - Create a new project from files</li>
                        <li><code>GET /recentProjects</code> - List recent projects</li>
                        <li><code>GET /config</code> - Show current configuration</li>
                        <li><a href="/setup"><code>GET /setup</code></a> - Change server configuration</li>
                    </ul>
                </div>
                
                <div class="footer">
                    <p>CodePortal MCP Server v1.0 | Running on port {config.get('port', 8001)}</p>
                </div>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/setup", response_class=HTMLResponse)
async def setup():
    """Setup page for configuring the server"""
    # Get computer hostname and IP
    hostname = socket.gethostname()
    ip = None
    try:
        ip = socket.gethostbyname(hostname)
    except:
        ip = "Unknown"
        
    # Generate random API key if still using default
    suggested_api_key = config.get("api_config", {}).get("api_key", "")
    if suggested_api_key == "CHANGE_THIS_KEY_BEFORE_USING":
        suggested_api_key = secrets.token_urlsafe(32)
    
    html_content = f"""
    <html>
        <head>
            <title>CodePortal MCP Setup</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; line-height: 1.6; }}
                .container {{ max-width: 800px; margin: 0 auto; }}
                h1 {{ color: #4CAF50; }}
                label {{ display: block; margin-top: 10px; font-weight: bold; }}
                input[type="text"], input[type="number"], select {{ width: 100%; padding: 8px; margin-top: 5px; margin-bottom: 15px; }}
                input[type="checkbox"] {{ margin-top: 5px; margin-bottom: 15px; }}
                .form-group {{ margin-bottom: 15px; }}
                .submit-btn {{ background-color: #4CAF50; color: white; padding: 10px 15px; border: none; cursor: pointer; }}
                .security {{ background-color: #fff3cd; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                .footer {{ margin-top: 30px; font-size: 0.8em; color: #6c757d; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>CodePortal MCP Setup</h1>
                
                <div class="security">
                    <h2>Initial Configuration</h2>
                    <p>Before using CodePortal, you need to configure it with your specific settings.</p>
                    <p>This will ensure no one else can access your files and that the system works with your setup.</p>
                </div>
                
                <form action="/perform_setup" method="post">
                    <h2>Script Paths</h2>
                    <div class="form-group">
                        <label for="script_primary_path">Primary Script Path:</label>
                        <input type="text" id="script_primary_path" name="script_primary_path" 
                               value="{config['script_paths'].get('primary', 'C:\\Users\\[username]\\Script_starter.py')}" required>
                    </div>
                    
                    <div class="form-group">
                        <label for="script_desktop_path">Desktop Script Path (optional):</label>
                        <input type="text" id="script_desktop_path" name="script_desktop_path" 
                               value="{config['script_paths'].get('desktop', 'C:\\Users\\[username]\\Desktop\\script_Starter.py')}">
                    </div>
                    
                    <h2>Project Settings</h2>
                    <div class="form-group">
                        <label for="archive_dir">Archive Directory:</label>
                        <select id="archive_dir" name="archive_dir">
                            <option value="Default" {'selected' if config.get('archive_dir') == 'Default' else ''}>Default (from Script_starter.py)</option>
                            <option value="Desktop" {'selected' if config.get('archive_dir') == 'Desktop' else ''}>Desktop</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label for="auto_shutdown_minutes">Auto-shutdown Timer (minutes):</label>
                        <input type="number" id="auto_shutdown_minutes" name="auto_shutdown_minutes" 
                               value="{config.get('auto_shutdown_minutes', 15)}" min="1" max="120">
                    </div>
                    
                    <h2>Security Settings</h2>
                    <div class="form-group">
                        <label for="enable_public_mode">
                            <input type="checkbox" id="enable_public_mode" name="enable_public_mode" {'checked' if config.get('api_config', {}).get('public_mode') else ''}>
                            Enable Public API Mode (allows access from other computers)
                        </label>
                    </div>
                    
                    <div class="form-group">
                        <label for="api_key">API Key (required if Public Mode is enabled):</label>
                        <input type="text" id="api_key" name="api_key" value="{suggested_api_key}">
                    </div>
                    
                    <button type="submit" class="submit-btn">Save Configuration</button>
                </form>
                
                <div class="footer">
                    <p>CodePortal MCP Server v1.0 | This computer: {hostname} ({ip})</p>
                </div>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/perform_setup")
async def perform_setup(request: Request):
    """Process the setup form and save configuration"""
    form_data = await request.form()
    
    # Extract values from form
    script_primary_path = form_data.get("script_primary_path", "")
    script_desktop_path = form_data.get("script_desktop_path", "")
    archive_dir = form_data.get("archive_dir", "Desktop")
    auto_shutdown_minutes = int(form_data.get("auto_shutdown_minutes", "15"))
    enable_public_mode = form_data.get("enable_public_mode") == "on"
    api_key = form_data.get("api_key", "")
    
    # Validate API key if public mode is enabled
    if enable_public_mode and (not api_key or api_key == "CHANGE_THIS_KEY_BEFORE_USING"):
        return HTMLResponse(
            content="<html><body><h1>Error</h1><p>You must set a secure API key when enabling public mode.</p>"
                   "<p><a href='/setup'>Go back to setup</a></p></body></html>"
        )
    
    # Update configuration
    config["script_paths"]["primary"] = script_primary_path
    config["script_paths"]["desktop"] = script_desktop_path
    config["archive_dir"] = archive_dir
    config["auto_shutdown_minutes"] = auto_shutdown_minutes
    config["api_config"]["public_mode"] = enable_public_mode
    config["api_config"]["api_key"] = api_key
    config["setup_complete"] = True
    
    # Save configuration
    if save_config(config):
        # Update global variable
        global SETUP_COMPLETE
        SETUP_COMPLETE = True
        
        # Load script with new configuration
        load_script()
        
        return HTMLResponse(
            content="<html><body><h1>Setup Complete!</h1>"
                   "<p>Your CodePortal MCP server is now configured and ready to use.</p>"
                   "<p><a href='/'>Go to homepage</a></p></body></html>"
        )
    else:
        return HTMLResponse(
            content="<html><body><h1>Error</h1><p>Failed to save configuration.</p>"
                   "<p><a href='/setup'>Try again</a></p></body></html>"
        )

@app.get("/config")
def get_config(api_key_valid: bool = Depends(get_api_key)):
    """Get the current configuration (safe version)"""
    # Don't expose any sensitive information
    safe_config = {
        "active_script": config.get("active_script"),
        "archive_dir": config.get("archive_dir"),
        "auto_shutdown_minutes": config.get("auto_shutdown_minutes"),
        "port": config.get("port"),
        "public_mode": config.get("api_config", {}).get("public_mode", False),
        "api_key_configured": config.get("api_config", {}).get("api_key") != "CHANGE_THIS_KEY_BEFORE_USING"
    }
    return safe_config

@app.post("/createProject")
def create_project(project: ProjectRequest, api_key_valid: bool = Depends(get_api_key)) -> ProjectResponse:
    """Creates a new project with proper structure from a set of files."""
    if not SETUP_COMPLETE:
        return ProjectResponse(
            success=False,
            message="Server setup not completed. Please visit /setup first.",
            project_path=project.project_path,
            file_count=0,
            project_name=project.project_name
        )
        
    if not project_manager:
        return ProjectResponse(
            success=False,
            message="Script_starter.py failed to load. Please check the server logs.",
            project_path=project.project_path,
            file_count=0,
            project_name=project.project_name
        )
        
    try:
        # Check file size limit
        total_size_bytes = sum(len(content.encode('utf-8')) for content in project.files.values())
        max_size_bytes = config.get("api_config", {}).get("max_file_size_mb", 50) * 1024 * 1024
        
        if total_size_bytes > max_size_bytes:
            return ProjectResponse(
                success=False,
                message=f"Total file size exceeds limit of {max_size_bytes / 1024 / 1024}MB",
                project_path=project.project_path,
                file_count=0,
                project_name=project.project_name
            )
        
        # Make sure project directory exists
        os.makedirs(project.project_path, exist_ok=True)
        
        # Save all the files first
        file_list = []
        for filename, content in project.files.items():
            # Create any subdirectories needed
            file_path = os.path.join(project.project_path, filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Write the file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            file_list.append(filename)
        
        # Use your ProjectManager to set up the project structure
        success, message = project_manager.create_project(
            project.project_path, 
            project.project_name, 
            file_list
        )
        
        # Create specialized files for AI models to use
        instructions_path = None
        
        # If description was provided, save it to a description file
        if project.description:
            desc_path = os.path.join(project.project_path, "[description]")
            with open(desc_path, 'w', encoding='utf-8') as f:
                f.write(project.description)
        
        # If instructions were provided, save them to an instructions file
        # otherwise generate standard instructions
        instructions_path = os.path.join(project.project_path, "AI_INSTRUCTIONS.md")
        with open(instructions_path, 'w', encoding='utf-8') as f:
            if project.instructions:
                f.write(project.instructions)
            else:
                f.write(f"# AI Instructions for {project.project_name}\n\n")
                f.write("## Project Structure\n\n")
                f.write("This project was created with CodePortal and has the following structure:\n\n")
                f.write("```\n")
                f.write(f"[project]  # Contains the project name: {project.project_name}\n")
                f.write("[root path]  # Contains the project root path\n")
                f.write("[outline]  # Contains an outline of the project files\n")
                f.write(f"[file count][~{len(file_list)}]  # Number of files in the project\n")
                
                for filename in file_list:
                    f.write(f"{filename}\n")
                
                f.write("```\n\n")
                f.write("## How to Update This Project\n\n")
                f.write("When you need to modify this project:\n\n")
                f.write("1. Always preserve the file names exactly as they are\n")
                f.write("2. Don't remove or rename the metadata files ([project], [outline], etc.)\n")
                f.write("3. Update the files in place\n\n")
        
        # Update our cache
        global RECENT_PROJECTS_CACHE
        RECENT_PROJECTS_CACHE = config_obj.get_recent_projects() if config_obj else []
            
        return ProjectResponse(
            success=success,
            message=message,
            project_path=project.project_path,
            file_count=len(file_list),
            project_name=project.project_name,
            instructions_path=instructions_path
        )
    
    except Exception as e:
        return ProjectResponse(
            success=False,
            message=f"Error creating project: {str(e)}",
            project_path=project.project_path,
            file_count=0,
            project_name=project.project_name
        )

@app.get("/recentProjects")
def recent_projects(api_key_valid: bool = Depends(get_api_key)):
    """Get a list of your recent projects from cache"""
    return {"projects": RECENT_PROJECTS_CACHE}

# Auto-shutdown timer
def shutdown_server():
    """Shut down the server after configured minutes"""
    minutes = config.get("auto_shutdown_minutes", 15)
    time.sleep(minutes * 60)
    print("\n" + "=" * 60)
    print(f"⏰ {minutes}-minute auto-shutdown timer reached")
    print("   Server shutting down to keep your system clean")
    print("=" * 60)
    os._exit(0)  # Force exit cleanly

# Run the server directly when the script is executed
if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("🚀 Starting CodePortal MCP Server")
    
    if not SETUP_COMPLETE:
        print("⚠️ Setup required! Visit http://localhost:8001/setup when the server starts")
    else:
        print(f"⏰ Auto-shutdown set for {config.get('auto_shutdown_minutes', 15)} minutes from now")
        print(f"📁 Archive directory: {script_module.ARCHIVE_DIR if script_module and hasattr(script_module, 'ARCHIVE_DIR') else 'Default'}")
    
    print("=" * 60)
    
    # Start shutdown timer in background
    shutdown_thread = threading.Thread(target=shutdown_server)
    shutdown_thread.daemon = True
    shutdown_thread.start()
    
    # Start server
    uvicorn.run(app, host="127.0.0.1", port=config.get("port", 8001))