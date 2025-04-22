# CodePortal MCP Server

This server helps your AI assistant (like Cascade) organize files into properly structured projects. It works with your existing `Script_starter.py` to handle all the project setup details.

## Super Simple Setup

1. **Clone this repository** to your computer at `C:\Users\tyler\CascadeProjects\code-portal-mcp`
2. **Double-click** `start_server.bat` to start the server
3. That's it! The server will be running at http://localhost:8001

## What This Does

When Cascade (or any AI) needs to create a project:

1. It sends all the files to this server
2. The server organizes them using your Script_starter.py system
3. Everything is properly structured, documented and backed up

No coding needed - just start the server and let the AI handle everything!

## Auto-Shutdown

The server automatically shuts down after 15 minutes to keep your system clean and prevent resource leaks.

## For Cascade/Codeium

Add this to your MCP config file (C:\\Users\\tyler\\.codeium\\windsurf\\mcp_config.json):

```json
"codePortal": {
  "command": "python",
  "args": ["C:/Users/tyler/CascadeProjects/code-portal-mcp/code_portal_mcp.py"]
}
```