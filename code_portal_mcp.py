"""
CodePortal MCP Server
=====================
This server automatically shuts down after 15 minutes to keep things clean.
It caches your recent projects so you won't lose track of them.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
import importlib.util
import sys
import os
import json
import datetime
import threading
import time

# =================================================
# STEP 1: Load your existing Script_starter.py code
# =================================================
script_path = r"C:\Users\tyler\Script_starter.py"
spec = importlib.util.spec_from_file_location("script_starter", script_path)
script_module = importlib.util.module_from_spec(spec)
sys.modules["script_starter"] = script_module

try:
    spec.loader.exec_module(script_module)
    print("✅ Successfully loaded Script_starter.py")
    
    # Get classes from your script
    Config = script_module.Config
    ProjectManager = script_module.ProjectManager
    
    # Create instances we'll use
    config = Config()
    project_manager = ProjectManager(config)
    print("✅ Project manager initialized")
    
except Exception as e:
    print(f"❌ ERROR loading Script_starter.py: {e}")
    print("   The server will start but project creation may not work.")
    print("   Please fix Script_starter.py by adding 'import math' at the top.")

# Cache recent projects locally so we don't need to keep files open
RECENT_PROJECTS_CACHE = config.get_recent_projects()

# =================================================
# STEP 2: Create our API models
# =================================================
class ProjectRequest(BaseModel):
    project_path: str
    project_name: str
    files: Dict[str, str]  # filename → content
    description: Optional[str] = None

class ProjectResponse(BaseModel):
    success: bool
    message: str
    project_path: str
    file_count: int
    project_name: str

# =================================================
# STEP 3: Set up the API server
# =================================================
app = FastAPI(
    title="CodePortal MCP",
    description="Helps organize code files into properly structured projects",
    version="1.0.0"
)

@app.get("/")
def home():
    """Welcome page with basic info"""
    return {
        "name": "CodePortal MCP",
        "status": "running",
        "endpoints": [
            "/createProject - Create a new project from files",
            "/recentProjects - List recent projects"
        ],
        "auto_shutdown": "Server will automatically shut down after 15 minutes"
    }

@app.post("/createProject")
def create_project(project: ProjectRequest) -> ProjectResponse:
    """Creates a new project with proper structure from a set of files."""
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
        
        # If description was provided, save it to a description file
        if project.description:
            desc_path = os.path.join(project.project_path, "[description]")
            with open(desc_path, 'w', encoding='utf-8') as f:
                f.write(project.description)
        
        # Update our cache
        global RECENT_PROJECTS_CACHE
        RECENT_PROJECTS_CACHE = config.get_recent_projects()
            
        return ProjectResponse(
            success=success,
            message=message,
            project_path=project.project_path,
            file_count=len(file_list),
            project_name=project.project_name
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
    """Shut down the server after 15 minutes"""
    time.sleep(15 * 60)  # 15 minutes
    print("\n" + "=" * 60)
    print("⏰ 15-minute auto-shutdown timer reached")
    print("   Server shutting down to keep your system clean")
    print("=" * 60)
    os._exit(0)  # Force exit cleanly

# Run the server directly when the script is executed
if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("🚀 Starting CodePortal MCP Server")
    print("⏰ Auto-shutdown set for 15 minutes from now")
    print("=" * 60)
    
    # Start shutdown timer in background
    shutdown_thread = threading.Thread(target=shutdown_server)
    shutdown_thread.daemon = True
    shutdown_thread.start()
    
    # Start server
    uvicorn.run(app, host="127.0.0.1", port=8001)