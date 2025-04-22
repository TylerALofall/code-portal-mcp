# CodePortal MCP Server

This server helps you organize code files into properly structured projects and provides direct access to AI models like OpenAI and Google.

## Features

- **Project Organization** - Structure projects using your existing Script_starter.py
- **Security First** - All settings are local and secure
- **API Key Management** - Store your OpenAI and Google keys securely
- **Direct AI Access** - Generate text from OpenAI or Google directly on your computer
- **Auto-shutdown** - Server closes after 15 minutes to keep your system clean

## Getting Started

1. **Clone this repository** to your computer
   ```
   git clone https://github.com/TylerALofall/code-portal-mcp.git
   cd code-portal-mcp
   ```

2. **Double-click** `start_server.bat` to start the server

3. **Open your browser** to [http://localhost:8001/setup](http://localhost:8001/setup)
   - Complete the initial setup
   - Configure your Script_starter.py paths

## Using the AI Features

1. Visit [http://localhost:8001/ai/ui](http://localhost:8001/ai/ui) after starting the server
2. Add your API keys in the "API Keys" tab:
   - OpenAI key (starts with `sk-`)
   - Google Generative AI key (starts with `AIza`)
3. Use the "Generate Text" tab to:
   - Choose your provider (OpenAI or Google)
   - Enter your prompt
   - Get AI responses directly on your computer

## Project Management

The server can create properly organized projects from multiple files:

```python
import requests

# Files to organize
files = {
    "main.py": "# Your Python code here",
    "utils.py": "# Utility functions",
    "README.md": "# Project Documentation"
}

# Send to CodePortal
response = requests.post(
    "http://localhost:8001/createProject",
    json={
        "project_path": "C:/Users/tyler/Projects/my_project",
        "project_name": "My Project",
        "files": files
    }
)

print(response.json())
```

## Security

- All API keys are stored locally on your computer
- The server only runs when you start it
- Auto-shutdown after 15 minutes
- Access restricted to localhost by default

## For Advanced Users

You can enable external access by:
1. Going to [http://localhost:8001/setup](http://localhost:8001/setup)
2. Enabling "Public API Mode"
3. Setting a secure API key

This allows you to send files from other computers or AI services.

## Using with Other AI Models

See [external_api.md](external_api.md) for instructions on using with Claude or other external models.