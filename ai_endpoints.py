"""
AI API Endpoints
===============
This module adds FastAPI endpoints to access OpenAI, Google, and other AI providers
directly through your CodePortal server. This lets you use your API keys securely
and get responses directly on your computer.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import ai_providers
import json
import os
from datetime import datetime

# Create a router for AI-related endpoints
router = APIRouter(prefix="/ai", tags=["AI Providers"])

# =================================================
# Data Models
# =================================================
class AIRequest(BaseModel):
    prompt: str
    provider: str = "openai"  # default to OpenAI
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 1000

class KeyUpdateRequest(BaseModel):
    provider: str
    api_key: str
    additional_info: Optional[Dict[str, str]] = None

# =================================================
# Helper Functions
# =================================================
def get_available_providers():
    """Get list of configured providers with key status"""
    keys = ai_providers.load_api_keys()
    
    providers = {}
    for provider, config in keys.items():
        providers[provider] = {
            "configured": bool(config.get("api_key")),
            "additional_fields": {k: bool(v) for k, v in config.items() if k != "api_key"}
        }
    
    return providers

# =================================================
# API Key Management Routes
# =================================================
@router.get("/keys")
async def list_keys():
    """List available AI provider keys (without showing the actual keys)"""
    return get_available_providers()

@router.post("/keys")
async def update_key(key_data: KeyUpdateRequest):
    """Update API key for a specific provider"""
    success = ai_providers.update_api_key(
        key_data.provider,
        key_data.api_key,
        key_data.additional_info
    )
    
    if success:
        return {"status": "success", "message": f"{key_data.provider} API key updated"}
    else:
        raise HTTPException(status_code=500, detail="Failed to update API key")

# =================================================
# Text Generation Routes
# =================================================
@router.post("/generate")
async def generate_text(request: AIRequest):
    """Generate text using the specified AI provider"""
    result = ai_providers.generate_text(
        prompt=request.prompt,
        provider=request.provider,
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens
    )
    
    if "error" in result:
        return JSONResponse(
            status_code=400,
            content={"error": result["error"]}
        )
    
    # Save the response to a file for reference
    try:
        log_dir = os.path.join(os.path.dirname(__file__), "ai_logs")
        os.makedirs(log_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_file = os.path.join(log_dir, f"{request.provider}_{timestamp}.json")
        
        with open(log_file, "w") as f:
            json.dump({
                "prompt": request.prompt,
                "provider": request.provider,
                "model": result.get("model"),
                "response": result.get("text"),
                "timestamp": timestamp
            }, f, indent=2)
    except:
        # Non-critical if logging fails
        pass
    
    return result

# =================================================
# Web UI Routes
# =================================================
@router.get("/ui", response_class=HTMLResponse)
async def ai_ui():
    """Simple web UI for interacting with AI providers"""
    providers = get_available_providers()
    provider_options = ""
    
    for provider, info in providers.items():
        status = "✅ Configured" if info["configured"] else "❌ Not Configured"
        provider_options += f'<option value="{provider}">{provider.title()} ({status})</option>'
    
    html_content = f"""
    <html>
        <head>
            <title>AI Integration</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; line-height: 1.6; }}
                .container {{ max-width: 800px; margin: 0 auto; }}
                h1 {{ color: #4CAF50; }}
                textarea, select, input[type="number"] {{ width: 100%; padding: 8px; margin: 5px 0 15px; }}
                button {{ background-color: #4CAF50; color: white; padding: 10px 15px; border: none; cursor: pointer; }}
                #result {{ 
                    margin-top: 20px; padding: 15px; border: 1px solid #ddd; 
                    border-radius: 5px; white-space: pre-wrap; background: #f9f9f9; 
                }}
                .keys-section {{ margin-top: 30px; }}
                .tab {{ overflow: hidden; border: 1px solid #ccc; background-color: #f1f1f1; }}
                .tab button {{ background-color: inherit; float: left; border: none; outline: none; cursor: pointer; padding: 14px 16px; }}
                .tab button:hover {{ background-color: #ddd; }}
                .tab button.active {{ background-color: #ccc; }}
                .tabcontent {{ display: none; padding: 6px 12px; border: 1px solid #ccc; border-top: none; }}
                .show {{ display: block; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>AI Provider Integration</h1>
                
                <div class="tab">
                    <button class="tablinks active" onclick="openTab(event, 'Generate')">Generate Text</button>
                    <button class="tablinks" onclick="openTab(event, 'Keys')">API Keys</button>
                </div>
                
                <div id="Generate" class="tabcontent show">
                    <h2>Generate Text</h2>
                    <form id="generate-form">
                        <div>
                            <label for="provider">AI Provider:</label>
                            <select id="provider" name="provider">
                                {provider_options}
                            </select>
                        </div>
                        
                        <div>
                            <label for="model">Model (leave blank for default):</label>
                            <input type="text" id="model" name="model" placeholder="e.g., gpt-4, gemini-pro">
                        </div>
                        
                        <div>
                            <label for="temperature">Temperature (0.0-1.0):</label>
                            <input type="number" id="temperature" name="temperature" value="0.7" min="0" max="1" step="0.1">
                        </div>
                        
                        <div>
                            <label for="max_tokens">Max Tokens:</label>
                            <input type="number" id="max_tokens" name="max_tokens" value="1000" min="1">
                        </div>
                        
                        <div>
                            <label for="prompt">Prompt:</label>
                            <textarea id="prompt" name="prompt" rows="5" placeholder="Enter your prompt here..."></textarea>
                        </div>
                        
                        <button type="submit">Generate</button>
                    </form>
                    
                    <div id="result-container" style="display: none;">
                        <h3>Result:</h3>
                        <div id="result"></div>
                    </div>
                </div>
                
                <div id="Keys" class="tabcontent">
                    <h2>Configure API Keys</h2>
                    
                    <form id="openai-form" class="keys-form">
                        <h3>OpenAI</h3>
                        <div>
                            <label for="openai-key">API Key:</label>
                            <input type="password" id="openai-key" name="api_key" placeholder="sk-...">
                        </div>
                        <div>
                            <label for="openai-org">Organization ID (optional):</label>
                            <input type="text" id="openai-org" name="org_id" placeholder="org-...">
                        </div>
                        <button type="submit" data-provider="openai">Save OpenAI Keys</button>
                    </form>
                    
                    <form id="google-form" class="keys-form">
                        <h3>Google AI</h3>
                        <div>
                            <label for="google-key">API Key:</label>
                            <input type="password" id="google-key" name="api_key" placeholder="AIza...">
                        </div>
                        <div>
                            <label for="google-project">Project ID (optional):</label>
                            <input type="text" id="google-project" name="project_id">
                        </div>
                        <button type="submit" data-provider="google">Save Google Keys</button>
                    </form>
                </div>
                
                <script>
                    function openTab(evt, tabName) {
                        var i, tabcontent, tablinks;
                        tabcontent = document.getElementsByClassName("tabcontent");
                        for (i = 0; i < tabcontent.length; i++) {
                            tabcontent[i].style.display = "none";
                        }
                        tablinks = document.getElementsByClassName("tablinks");
                        for (i = 0; i < tablinks.length; i++) {
                            tablinks[i].className = tablinks[i].className.replace(" active", "");
                        }
                        document.getElementById(tabName).style.display = "block";
                        evt.currentTarget.className += " active";
                    }
                    
                    // Generate text form
                    document.getElementById('generate-form').addEventListener('submit', async function(e) {
                        e.preventDefault();
                        
                        const resultContainer = document.getElementById('result-container');
                        const resultElement = document.getElementById('result');
                        resultContainer.style.display = 'block';
                        resultElement.textContent = 'Processing...';
                        
                        const formData = {
                            prompt: document.getElementById('prompt').value,
                            provider: document.getElementById('provider').value,
                            model: document.getElementById('model').value || undefined,
                            temperature: parseFloat(document.getElementById('temperature').value),
                            max_tokens: parseInt(document.getElementById('max_tokens').value)
                        };
                        
                        try {
                            const response = await fetch('/ai/generate', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json'
                                },
                                body: JSON.stringify(formData)
                            });
                            
                            const data = await response.json();
                            
                            if (data.error) {
                                resultElement.textContent = 'Error: ' + data.error;
                            } else {
                                resultElement.textContent = data.text;
                            }
                        } catch (error) {
                            resultElement.textContent = 'Error: ' + error.message;
                        }
                    });
                    
                    // API key forms
                    document.querySelectorAll('.keys-form').forEach(form => {
                        form.addEventListener('submit', async function(e) {
                            e.preventDefault();
                            const provider = e.submitter.dataset.provider;
                            
                            const formData = {
                                provider: provider,
                                api_key: this.querySelector('input[name="api_key"]').value,
                                additional_info: {}
                            };
                            
                            // Get additional fields
                            this.querySelectorAll('input:not([name="api_key"])').forEach(input => {
                                if (input.value) {
                                    formData.additional_info[input.name] = input.value;
                                }
                            });
                            
                            try {
                                const response = await fetch('/ai/keys', {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json'
                                    },
                                    body: JSON.stringify(formData)
                                });
                                
                                const data = await response.json();
                                alert(data.message || 'API key updated');
                                
                                // Reset form
                                this.reset();
                            } catch (error) {
                                alert('Error: ' + error.message);
                            }
                        });
                    });
                </script>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# This function integrates the router with the main app
def setup_ai_routes(app):
    """Add AI endpoints to the main FastAPI app"""
    app.include_router(router)
    print("✅ AI Provider endpoints added")
    return app