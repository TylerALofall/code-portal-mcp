"""
AI Provider Integration Module
=============================
This module handles communication with various AI services (OpenAI, Google, etc.)
while keeping API keys secure and providing a unified interface.
"""

import os
import json
import requests
from typing import Dict, List, Any, Optional
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_providers")

# Path to API keys file
API_KEYS_FILE = os.path.join(os.path.dirname(__file__), "api_keys.json")

def load_api_keys():
    """Load API keys from the api_keys.json file"""
    try:
        if os.path.exists(API_KEYS_FILE):
            with open(API_KEYS_FILE, 'r') as f:
                return json.load(f)
        else:
            logger.warning(f"API keys file not found: {API_KEYS_FILE}")
            return {}
    except Exception as e:
        logger.error(f"Error loading API keys: {e}")
        return {}

def save_api_keys(keys_data):
    """Save API keys to the api_keys.json file"""
    try:
        with open(API_KEYS_FILE, 'w') as f:
            json.dump(keys_data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving API keys: {e}")
        return False

def update_api_key(provider: str, key: str, additional_info: Dict = None):
    """Update API key for a specific provider"""
    keys = load_api_keys()
    
    if provider not in keys:
        keys[provider] = {}
    
    keys[provider]["api_key"] = key
    
    # Add any additional info fields
    if additional_info:
        for field, value in additional_info.items():
            keys[provider][field] = value
    
    return save_api_keys(keys)

def get_api_key(provider: str):
    """Get API key for a specific provider"""
    keys = load_api_keys()
    return keys.get(provider, {}).get("api_key", "")

def get_provider_config(provider: str):
    """Get full config for a provider"""
    keys = load_api_keys()
    return keys.get(provider, {})

# ============================
# OpenAI Integration
# ============================
def openai_chat_completion(
    messages: List[Dict[str, str]], 
    model: str = "gpt-3.5-turbo",
    temperature: float = 0.7,
    max_tokens: int = 1000
) -> Dict[str, Any]:
    """
    Send a request to OpenAI chat completion API
    
    Args:
        messages: List of message objects (role, content)
        model: OpenAI model to use
        temperature: Randomness of response (0.0-1.0)
        max_tokens: Maximum tokens in response
        
    Returns:
        API response as dictionary
    """
    api_key = get_api_key("openai")
    if not api_key:
        return {"error": "OpenAI API key not configured"}
    
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        data = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {
                "error": f"OpenAI API error: {response.status_code}",
                "details": response.text
            }
    
    except Exception as e:
        return {"error": f"Error calling OpenAI API: {str(e)}"}

# ============================
# Google Generative AI Integration
# ============================
def google_text_generation(
    prompt: str,
    model: str = "gemini-pro",
    temperature: float = 0.7,
    max_tokens: int = 1000
) -> Dict[str, Any]:
    """
    Send a request to Google's Generative AI API
    
    Args:
        prompt: Text prompt
        model: Google AI model to use
        temperature: Randomness of response (0.0-1.0)
        max_tokens: Maximum tokens in response
        
    Returns:
        API response as dictionary
    """
    api_key = get_api_key("google")
    if not api_key:
        return {"error": "Google API key not configured"}
    
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateText"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        params = {
            "key": api_key
        }
        
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": 0.95,
                "topK": 40
            }
        }
        
        response = requests.post(
            url,
            headers=headers,
            params=params,
            json=data
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {
                "error": f"Google AI API error: {response.status_code}",
                "details": response.text
            }
    
    except Exception as e:
        return {"error": f"Error calling Google AI API: {str(e)}"}

# ============================
# Unified API Interface
# ============================
def generate_text(
    prompt: str,
    provider: str = "openai",
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 1000
) -> Dict[str, Any]:
    """
    Generate text using the specified AI provider
    
    Args:
        prompt: Text prompt
        provider: AI provider to use ('openai' or 'google')
        model: Model name (provider-specific)
        temperature: Randomness (0.0-1.0)
        max_tokens: Maximum tokens in response
        
    Returns:
        Generated text and metadata
    """
    # Default models by provider if not specified
    if not model:
        if provider == "openai":
            model = "gpt-3.5-turbo"
        elif provider == "google":
            model = "gemini-pro"
    
    if provider == "openai":
        # Format prompt for OpenAI chat API
        messages = [{"role": "user", "content": prompt}]
        response = openai_chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        # Extract text from response
        if "error" not in response:
            try:
                return {
                    "text": response["choices"][0]["message"]["content"],
                    "model": model,
                    "provider": "openai",
                    "raw_response": response
                }
            except (KeyError, IndexError):
                return {"error": "Could not parse OpenAI response", "raw_response": response}
        return response
        
    elif provider == "google":
        response = google_text_generation(
            prompt=prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        # Extract text from response
        if "error" not in response:
            try:
                return {
                    "text": response["candidates"][0]["content"]["parts"][0]["text"],
                    "model": model,
                    "provider": "google",
                    "raw_response": response
                }
            except (KeyError, IndexError):
                return {"error": "Could not parse Google response", "raw_response": response}
        return response
        
    else:
        return {"error": f"Unsupported AI provider: {provider}"}

# Example usage
if __name__ == "__main__":
    # Update API keys (just for testing)
    # update_api_key("openai", "your-api-key-here")
    # update_api_key("google", "your-api-key-here")
    
    # Test prompt
    test_prompt = "Write a short poem about coding."
    
    # Test OpenAI
    print("Testing OpenAI...")
    openai_result = generate_text(test_prompt, provider="openai")
    print(openai_result.get("text", openai_result.get("error")))
    
    # Test Google
    print("\nTesting Google...")
    google_result = generate_text(test_prompt, provider="google")
    print(google_result.get("text", google_result.get("error")))