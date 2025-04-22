"""
Test Client for CodePortal MCP Server
=====================================
This script tests the CodePortal MCP server by sending a request to process Script_starter.py itself.
It demonstrates how to use the MCP server from Python code.
"""

import requests
import os
import json
import time
from pathlib import Path

# Configuration
SERVER_URL = "http://localhost:8001"
TEST_PROJECT_NAME = "Script_starter_TEST"
TEST_PROJECT_PATH = os.path.join(os.path.expanduser("~"), "Desktop", TEST_PROJECT_NAME)
SCRIPT_PATH = r"C:\Users\tyler\Script_starter.py"

if not os.path.exists(SCRIPT_PATH):
    SCRIPT_PATH = r"C:\Users\tyler\Desktop\script_Starter.py"

if not os.path.exists(SCRIPT_PATH):
    print(f"❌ ERROR: Could not find Script_starter.py!")
    exit(1)

# Give the server a moment to start if we just launched it
print("Waiting for server to be ready...")
time.sleep(2)

# Check if server is running
try:
    response = requests.get(f"{SERVER_URL}/")
    if response.status_code != 200:
        print(f"❌ Server responded with status code {response.status_code}")
        exit(1)
    print("✅ Server is running")
except Exception as e:
    print(f"❌ Could not connect to server: {e}")
    print("   Did you start the server with start_server.bat?")
    exit(1)

# Read the script file
try:
    with open(SCRIPT_PATH, 'r', encoding='utf-8') as f:
        script_content = f.read()
    print(f"✅ Read {len(script_content)} bytes from {SCRIPT_PATH}")
except Exception as e:
    print(f"❌ Error reading script file: {e}")
    exit(1)

# Prepare the request data
request_data = {
    "project_path": TEST_PROJECT_PATH,
    "project_name": TEST_PROJECT_NAME,
    "files": {
        "Script_starter.py": script_content,
        "README.md": f"# {TEST_PROJECT_NAME}\n\nThis is a test project created by CodePortal MCP Server.\n\nThe main file is Script_starter.py.\n"
    },
    "description": "A test project containing the Script_starter.py file itself."
}

# Send the request to the server
print(f"📤 Sending request to {SERVER_URL}/createProject...")
try:
    response = requests.post(
        f"{SERVER_URL}/createProject",
        json=request_data
    )
    
    if response.status_code == 200:
        result = response.json()
        print("\n" + "=" * 60)
        print(f"✅ SUCCESS! Project created at: {result['project_path']}")
        print(f"   Files: {result['file_count']}")
        print(f"   Message: {result['message']}")
        
        if result.get('instructions_path'):
            print(f"   Instructions: {result['instructions_path']}")
        
        print("\nNow check your Desktop for the new project folder!")
        print("=" * 60)
    else:
        print(f"❌ Error: Server responded with status {response.status_code}")
        print(response.text)
except Exception as e:
    print(f"❌ Error sending request: {e}")

# Check recent projects
try:
    response = requests.get(f"{SERVER_URL}/recentProjects")
    if response.status_code == 200:
        recent = response.json().get("projects", [])
        if recent:
            print("\nRecent projects:")
            for proj in recent:
                print(f"- {proj.get('name')} ({proj.get('path')})")
        else:
            print("\nNo recent projects found.")
    else:
        print("Could not get recent projects list.")
except:
    pass