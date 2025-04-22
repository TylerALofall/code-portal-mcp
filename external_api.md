# Using CodePortal with External AI Models

This guide explains how to use your CodePortal MCP server with other AI models like Claude or GPT-4 that can generate large files.

## Setting Up API Access

1. In `config.json`, change these settings:

```json
"api_config": {
  "public_mode": true,  // Change this to true
  "api_key": "your_secret_key_here",  // Set a unique string only you know
  "allowed_ips": ["127.0.0.1"],  // Add any other IPs if needed
  "max_file_size_mb": 50  // Increase if needed for very large files
}
```

2. Restart the server using `start_server.bat`

## Option 1: Claude Direct API Integration

If you're working with Claude directly through API:

```python
import requests
import json

# Your CodePortal settings
SERVER_URL = "http://your-ip-address:8001"  # Replace with your IP if needed
API_KEY = "your_secret_key_here"  # Same as in config.json

# Files you want to organize
files = {
    "main.py": "# Your large Python file content...",
    "utils.py": "# Utilities...",
    "README.md": "# Project Documentation..."
}

# Send to CodePortal
response = requests.post(
    f"{SERVER_URL}/createProject",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "project_path": "C:/Users/tyler/Projects/my_large_project",
        "project_name": "My Large Project",
        "files": files,
        "description": "Project created from Claude"
    }
)

print(response.json())
```

## Option 2: Copy-Paste Method

This simpler approach works with any AI model:

1. Ask Claude/GPT-4 to generate your large files
2. Save each file manually to a temp folder 
3. Start CodePortal server (`start_server.bat`)
4. Run this script to have CodePortal organize your files:

```python
import requests
import os

SERVER_URL = "http://localhost:8001"
API_KEY = "your_secret_key_here"  # Same as in config.json
TEMP_FOLDER = "C:/Users/tyler/temp_files"  # Where you saved the AI-generated files
PROJECT_PATH = "C:/Users/tyler/Projects/organized_project"
PROJECT_NAME = "My Organized Project"

# Read all files from the temp folder
files = {}
for filename in os.listdir(TEMP_FOLDER):
    with open(os.path.join(TEMP_FOLDER, filename), 'r', encoding='utf-8') as f:
        files[filename] = f.read()

# Send to CodePortal
response = requests.post(
    f"{SERVER_URL}/createProject",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "project_path": PROJECT_PATH,
        "project_name": PROJECT_NAME,
        "files": files
    }
)

print(response.json())
```

## Security Note

Always follow these guidelines:

1. Only enable public mode when you need it
2. Use a strong, unique API key
3. The server shuts down automatically after 15 minutes
4. Don't share your API key with anyone