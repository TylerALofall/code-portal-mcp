# CodePortal MCP Server - AI Agent Instructions

## Architecture Overview

**CodePortal is a FastAPI server that provides two main capabilities:**
1. **Project Organization**: Wraps an external `Script_starter.py` file (user-provided) for project management
2. **AI Integration**: Direct API access to OpenAI and Google AI models via web UI

### Key Components

- **`code_portal_mcp.py`**: Main FastAPI server with setup wizard, API authentication, and auto-shutdown
- **`ai_endpoints.py`**: AI provider UI and API routes (mounted via `setup_ai_routes()`)
- **`ai_providers.py`**: Backend for OpenAI/Google API calls, manages `api_keys.json`
- **`integration.py`**: Bridge module (currently unused, see note below)
- **`project_versioning.py`**: Version control for projects created via Script_starter.py
- **`ui_components.py`**: Auto-shutdown timer and UI helpers

### Critical Architectural Patterns

**External Script Loading**: Server dynamically loads user's `Script_starter.py` using `importlib.util.spec_from_file_location()`. Paths configured in `config.json` during setup wizard. Script must expose `Config` and `ProjectManager` classes. **Security note**: This executes arbitrary Python code - only load trusted scripts and run server in isolated environments for untrusted code.

**AI Route Integration**: AI endpoints MUST be registered in `code_portal_mcp.py` after FastAPI app creation:
```python
import ai_endpoints
app = FastAPI(...)
# ... middleware setup ...
ai_endpoints.setup_ai_routes(app)  # Required - without this /ai/* routes return 404
```

**HTML in f-strings**: JavaScript code in HTML templates uses f-strings - ALL JavaScript braces must be doubled:
```python
html = f"""<script>
    function example() {{  // Note {{ and }} - single braces cause SyntaxError
        const obj = {{ key: 'value' }};
    }}
</script>"""
```

## Development Workflows

### Starting the Server
```bash
python3 code_portal_mcp.py
# Server runs on http://localhost:8001 (configurable in config.json)
# Auto-shuts down after 15 minutes (configurable)
# First run requires setup wizard at /setup
```

### Testing Changes
- **Manual test**: Run server, visit http://localhost:8001/ai/ui for AI features
- **Example client**: `python3 test_client.py` tests project creation endpoint
- No automated test suite currently exists

### Configuration Files
- **`config.json`**: Server settings, Script_starter.py paths, API config, auto-shutdown timer
- **`api_keys.json`**: AI provider API keys (OpenAI, Google) - managed via `/ai/ui` interface
- Both created automatically on first run if missing

## Project-Specific Conventions

### Security Model
- **Setup Required**: `setup_complete: false` in config.json blocks most functionality until wizard completed
- **IP Filtering**: `allowed_ips` array in config - default localhost only
- **API Key Auth**: Required for public_mode, validated via `APIKeyHeader` dependency
- **Auto-Shutdown**: Configurable inactivity timer (default 15min) via `ui_components.py`

### Model Selection Pattern
AI UI provides dropdown with current models (gpt-4, gpt-4o, o1, o1-mini, gemini-pro, etc.) plus "custom" option. **Security note**: Model names are passed directly to provider APIs without server-side validation - this is intentional to support new/beta models, but means users can potentially incur costs from expensive models. See `ai_endpoints.py` lines 172-193 for dropdown structure.

### File Organization
- AI response logs: `ai_logs/` directory (created automatically)
- Project archives: `~/.codeportal_archive/` or `~/Desktop/.codeportal_archive/` based on config

## Common Pitfalls

1. **Missing AI routes**: Forgetting `ai_endpoints.setup_ai_routes(app)` causes 404s on `/ai/*`
2. **F-string braces**: JavaScript in HTML must use `{{` and `}}` or SyntaxError on import
3. **Script_starter.py dependency**: Project features require external script - setup wizard must complete
4. **API keys location**: Stored in `api_keys.json` (NOT config.json), managed via UI not manual editing

## Dependencies

Install with: `pip install -r requirements.txt`
- FastAPI + Uvicorn for server
- Requests for AI provider API calls
- Pydantic for request validation

No build step required - pure Python application.
