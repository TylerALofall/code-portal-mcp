"""
Integration Module
=================
This module connects the main CodePortal MCP server with the AI provider endpoints.
It provides the integration point between the project management and AI generation features.
"""

def register_ai_endpoints(app):
    """
    Register AI endpoints with the main FastAPI app
    
    This function imports the AI endpoints module and registers its routes
    with the main FastAPI application.
    """
    try:
        # Try to import the AI endpoints module
        import ai_endpoints
        
        # Register the endpoints with the app
        ai_endpoints.setup_ai_routes(app)
        
        print("✅ AI provider endpoints registered")
        return True
    except Exception as e:
        print(f"❌ Error registering AI endpoints: {e}")
        return False

def initialize_ai_directory():
    """
    Create necessary directories for AI features
    """
    import os
    
    # Create AI logs directory
    ai_log_dir = os.path.join(os.path.dirname(__file__), "ai_logs")
    os.makedirs(ai_log_dir, exist_ok=True)
    
    return True