"""
CodePortal MCP Server
=====================
This server automatically shuts down after a configurable time to keep things clean.
It caches your recent projects so you won't lose track of them.

This server handles both versions of your Script_starter.py and makes the archive
location configurable through the config.json file.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
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
        return {
            "script_paths": {
                "primary": r"C:\Users\tyler\Script_starter.py",
                "desktop": r"C:\Users\tyler\Desktop\script_Starter.py"
            },
            "active_script": "primary",
            "archive_dir": "Desktop",
            "auto_shutdown_minutes": 15,
            "port": 8001
        }

config = load_config()

# Get the active script path
active_script_key = config.get("active_script", "primary")
script_path = config["script_paths"].get(active_script_key)
if not script_path or not os.path.exists(script_path):
    # Try the other script if the primary doesn't exist
    for key, path in config["script_paths"].items():
        if os.path.exists(path):
            script_path = path
            config["active_script"] = key
            print(f"⚠️ Using alternative script: {key} at {path}")
            break

if not script_path or not os.path.exists(script_path):
    print("❌ ERROR: Could not find any valid Script_starter.py!")
    print(f"   Checked paths: {list(config['script_paths'].values())}")
    script_path = config["script_paths"].get("primary", "")  # Use primary even if it doesn't exist

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
    
except Exception as e:
    print(f"❌ ERROR loading Script_starter.py: {e}")
    print("   The server will start but project creation may not work.")
    print("   Please fix Script_starter.py by adding 'import math' at the top.")
    Config = None
    ProjectManager = None
    config_obj = None
    project_manager = None

# Cache for recent projects to avoid reopening files
RECENT_PROJECTS_CACHE = config_obj.get_recent_projects() if config_obj else []

# =================================================
# STEP 3: Create our API models
# =================================================
class ProjectRequest(BaseModel):
    project_path: str
    project_name: str
    files: Dict[str, str]  # filename → content
    description: Optional[str] = None
    instructions: Optional[str] = None  # Added field for model instructions
    
class ProjectResponse(BaseModel):
    success: bool
    message: str
    project_path: str
    file_count: int
    project_name: str
    instructions_path: Optional[str] = None

# =================================================
# STEP 4: Set up the API server
# =================================================
app = FastAPI(
    title="CodePortal MCP",
    description="Helps organize code files into properly structured projects",
    version="1.0.0"
)

# Allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
def home():
    """Welcome page with basic info"""
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
                    <p>Archive directory: <code>{script_module.ARCHIVE_DIR if 'script_module' in globals() and hasattr(script_module, 'ARCHIVE_DIR') else 'Not set'}</code></p>
                    <p>Auto-shutdown: <span class="warning">⏰ {config.get('auto_shutdown_minutes', 15)} minutes</span></p>
                </div>
                
                <div class="endpoints">
                    <h2>API Endpoints</h2>
                    <ul>
                        <li><code>POST /createProject</code> - Create a new project from files</li>
                        <li><code>GET /recentProjects</code> - List recent projects</li>
                        <li><code>GET /config</code> - Show current configuration</li>
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

@app.get("/config")
def get_config():
    """Get the current configuration (safe version)"""
    # Don't expose any sensitive information
    safe_config = {
        "active_script": config.get("active_script"),
        "archive_dir": config.get("archive_dir"),
        "auto_shutdown_minutes": config.get("auto_shutdown_minutes"),
        "port": config.get("port"),
    }
    return safe_config

@app.post("/createProject")
def create_project(project: ProjectRequest) -> ProjectResponse:
    """Creates a new project with proper structure from a set of files."""
    if not project_manager:
        return ProjectResponse(
            success=False,
            message="Script_starter.py failed to load. Please check the server logs.",
            project_path=project.project_path,
            file_count=0,
            project_name=project.project_name
        )
        
    try:
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
def recent_projects():
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
    print(f"⏰ Auto-shutdown set for {config.get('auto_shutdown_minutes', 15)} minutes from now")
    print(f"📁 Archive directory: {script_module.ARCHIVE_DIR if 'script_module' in globals() and hasattr(script_module, 'ARCHIVE_DIR') else 'Default'}")
    print("=" * 60)
    
    # Start shutdown timer in background
    shutdown_thread = threading.Thread(target=shutdown_server)
    shutdown_thread.daemon = True
    shutdown_thread.start()
    
    # Start server
    uvicorn.run(app, host="127.0.0.1", port=config.get("port", 8001))