"""
UI Components Module
==================
Provides UI components for the web interface, including the print instructions
button and auto-inactivity shutdown timer.
"""

import os
import datetime
import time
import threading
import webbrowser
from pathlib import Path
import logging
import project_versioning

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ui_components")

# Global variables for inactivity tracking
last_activity_time = time.time()
inactivity_shutdown_thread = None
MAX_INACTIVITY_MINUTES = 15  # Default inactivity timeout

def update_activity():
    """Update the last activity time"""
    global last_activity_time
    last_activity_time = time.time()

def check_inactivity(app, shutdown_callback, max_minutes):
    """
    Check for inactivity and shut down if inactive for too long
    
    Args:
        app: FastAPI app instance
        shutdown_callback: Function to call for shutdown
        max_minutes: Maximum inactivity minutes before shutdown
    """
    global last_activity_time
    
    while True:
        current_time = time.time()
        inactive_seconds = current_time - last_activity_time
        
        if inactive_seconds > (max_minutes * 60):
            logger.info(f"Inactive for {max_minutes} minutes, shutting down...")
            shutdown_callback()
            break
        
        # Check every 30 seconds
        time.sleep(30)

def start_inactivity_monitor(app, shutdown_callback, max_minutes=None):
    """
    Start monitoring for inactivity
    
    Args:
        app: FastAPI app instance
        shutdown_callback: Function to call for shutdown
        max_minutes: Maximum inactivity minutes before shutdown
    """
    global inactivity_shutdown_thread, MAX_INACTIVITY_MINUTES
    
    # Set custom inactivity timeout if provided
    if max_minutes is not None:
        MAX_INACTIVITY_MINUTES = max_minutes
    
    # Create and start the inactivity monitoring thread
    inactivity_shutdown_thread = threading.Thread(
        target=check_inactivity,
        args=(app, shutdown_callback, MAX_INACTIVITY_MINUTES),
        daemon=True
    )
    inactivity_shutdown_thread.start()
    
    logger.info(f"Inactivity monitor started (timeout: {MAX_INACTIVITY_MINUTES} minutes)")

def get_print_instructions_button_html(project_path):
    """
    Generate HTML for the print instructions button
    
    Args:
        project_path: Path to the current project
        
    Returns:
        HTML string for the print instructions button
    """
    return f"""
    <div class="print-instructions">
        <form id="print-instructions-form" action="/print_instructions" method="post">
            <input type="hidden" name="project_path" value="{project_path}">
            <button type="submit" class="print-btn">Print Instructions</button>
        </form>
    </div>
    """

def print_project_instructions(project_path):
    """
    Print the instructions for a project
    
    Args:
        project_path: Path to the project
        
    Returns:
        Path to the printed instructions file or None if not found
    """
    # Initialize versioning system
    versioning = project_versioning.ProjectVersioning()
    
    # Print instructions
    printed_path = versioning.print_instructions(project_path)
    
    if printed_path and os.path.exists(printed_path):
        # Try to open the file in the default text editor
        try:
            webbrowser.open(printed_path)
            return printed_path
        except Exception as e:
            logger.error(f"Error opening printed instructions: {e}")
    
    return None

def get_home_page_html(project_list, api_providers, recent_activity_log):
    """
    Generate HTML for the home page with integrated UI components
    
    Args:
        project_list: List of recent projects
        api_providers: Dictionary of API providers and their status
        recent_activity_log: Recent activity log entries
        
    Returns:
        HTML string for the home page
    """
    # Format project list HTML
    projects_html = ""
    for project in project_list:
        file_list = "<br>".join([f"- {file}" for file in project.get("files", [])])
        projects_html += f"""
        <div class="project-card">
            <div class="glass-overlay"></div>
            <div class="black-overlay"></div>
            <h3>{project.get('name', 'Unnamed')}</h3>
            <p><strong>Path:</strong> {project.get('path', '')}</p>
            <p><strong>Date:</strong> {project.get('date', '')}</p>
            <p><strong>Files:</strong></p>
            <div class="file-list">{file_list}</div>
            <form action="/print_instructions" method="post" style="position: relative; z-index: 4;">
                <input type="hidden" name="project_path" value="{project.get('path', '')}">
                <button type="submit" class="print-btn">Print Instructions</button>
            </form>
        </div>
        """
    
    # Format API providers HTML
    providers_html = ""
    for provider, status in api_providers.items():
        status_class = "configured" if status.get("configured", False) else "not-configured"
        status_text = "✅ Configured" if status.get("configured", False) else "❌ Not Configured"
        providers_html += f"""
        <div class="provider-card {status_class}">
            <div class="glass-overlay"></div>
            <div class="black-overlay"></div>
            <h3>{provider.title()}</h3>
            <p class="status">{status_text}</p>
            <a href="/ai/ui" class="config-btn" style="position: relative; z-index: 4;">Configure</a>
        </div>
        """
    
    # Format activity log HTML
    activity_html = ""
    for entry in recent_activity_log:
        activity_html += f"""
        <div class="activity-entry">
            <div class="glass-overlay"></div>
            <div class="black-overlay"></div>
            <span class="time">{entry.get('time', '')}</span>
            <span class="action">{entry.get('action', '')}</span>
        </div>
        """
    
    # Auto-shutdown timer HTML
    shutdown_html = f"""
    <div class="auto-shutdown">
        <p>Auto-shutdown: <span id="countdown">{MAX_INACTIVITY_MINUTES}:00</span> (resets on activity)</p>
    </div>
    <script>
        // Set the initial countdown time
        var minutes = {MAX_INACTIVITY_MINUTES};
        var seconds = 0;
        
        // Update the countdown every second
        var countdownInterval = setInterval(function() {{
            seconds--;
            if (seconds < 0) {{
                seconds = 59;
                minutes--;
            }}
            
            if (minutes < 0) {{
                clearInterval(countdownInterval);
                document.getElementById("countdown").innerHTML = "Shutting down...";
            }} else {{
                document.getElementById("countdown").innerHTML = 
                    minutes.toString().padStart(2, '0') + ":" + 
                    seconds.toString().padStart(2, '0');
            }}
        }}, 1000);
        
        // Reset countdown on any user interaction
        document.addEventListener('click', function() {{
            minutes = {MAX_INACTIVITY_MINUTES};
            seconds = 0;
            
            // Send activity update to server
            fetch('/update_activity', {{ method: 'POST' }});
        }});
    </script>
    """
    
    # Complete HTML
    return f"""
    <html>
        <head>
            <title>CodePortal MCP</title>
            <style>
                body {{ 
                    font-family: Arial, sans-serif; 
                    margin: 0; 
                    padding: 20px; 
                    line-height: 1.6; 
                    background: linear-gradient(135deg, #1a1a1a 0%, #2d1b69 50%, #1a1a1a 100%);
                    min-height: 100vh;
                    position: relative;
                    overflow-x: hidden;
                }}
                
                /* Purple glow from sides */
                body::before {{
                    content: '';
                    position: fixed;
                    top: 0;
                    left: -50px;
                    width: 100px;
                    height: 100%;
                    background: linear-gradient(90deg, rgba(138, 43, 226, 0.4) 0%, rgba(138, 43, 226, 0) 100%);
                    z-index: 1;
                    pointer-events: none;
                }}
                
                body::after {{
                    content: '';
                    position: fixed;
                    top: 0;
                    right: -50px;
                    width: 100px;
                    height: 100%;
                    background: linear-gradient(270deg, rgba(138, 43, 226, 0.4) 0%, rgba(138, 43, 226, 0) 100%);
                    z-index: 1;
                    pointer-events: none;
                }}
                
                .container {{ 
                    max-width: 1000px; 
                    margin: 0 auto; 
                    position: relative;
                    z-index: 2;
                }}
                
                h1 {{ 
                    color: #00FF88;
                    text-shadow: 0 0 20px rgba(0, 255, 136, 0.6);
                    text-align: center;
                }}
                
                /* Glass morphism layer (highest Z-index) */
                .glass-overlay {{
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: rgba(0, 255, 136, 0.1);
                    backdrop-filter: blur(10px);
                    border: 1px solid rgba(0, 255, 136, 0.2);
                    border-radius: inherit;
                    z-index: 3;
                    pointer-events: none;
                }}
                
                /* Black overlay layer (middle Z-index) */
                .black-overlay {{
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: rgba(0, 0, 0, 0.4);
                    border-radius: inherit;
                    z-index: 2;
                    pointer-events: none;
                }}
                
                .dashboard {{ display: grid; grid-template-columns: 2fr 1fr; gap: 20px; }}
                
                .section {{ 
                    background: rgba(20, 20, 20, 0.8);
                    padding: 15px; 
                    border-radius: 10px; 
                    margin-bottom: 20px;
                    border: 1px solid rgba(0, 255, 136, 0.3);
                    position: relative;
                    backdrop-filter: blur(5px);
                }}
                
                .project-card, .provider-card, .activity-entry {{ 
                    padding: 12px; 
                    margin-bottom: 12px; 
                    border: 1px solid rgba(0, 255, 136, 0.3);
                    border-radius: 8px; 
                    position: relative;
                    background: rgba(10, 10, 10, 0.7);
                    backdrop-filter: blur(5px);
                    color: #e0e0e0;
                    transition: all 0.3s ease;
                }}
                
                .project-card:hover, .provider-card:hover, .activity-entry:hover {{
                    border-color: rgba(0, 255, 136, 0.6);
                    transform: translateY(-2px);
                    box-shadow: 0 8px 25px rgba(0, 255, 136, 0.2);
                }}
                
                .project-card {{ 
                    background: rgba(0, 40, 20, 0.6);
                }}
                
                .provider-card {{ 
                    background: rgba(0, 40, 20, 0.6);
                }}
                
                .provider-card.configured {{ 
                    border-color: rgba(0, 255, 136, 0.6);
                    box-shadow: 0 0 15px rgba(0, 255, 136, 0.3);
                }}
                
                .provider-card.not-configured {{ 
                    border-color: rgba(255, 100, 100, 0.6);
                    background: rgba(40, 0, 0, 0.6);
                }}
                
                .file-list {{ 
                    margin-left: 10px; 
                    font-family: 'Courier New', monospace;
                    color: #b0b0b0;
                }}
                
                .print-btn, .config-btn {{ 
                    background: linear-gradient(135deg, rgba(0, 255, 136, 0.8) 0%, rgba(0, 200, 100, 0.8) 100%);
                    color: white; 
                    padding: 8px 12px; 
                    border: none; 
                    border-radius: 6px; 
                    cursor: pointer; 
                    margin-top: 10px;
                    display: inline-block;
                    text-decoration: none;
                    position: relative;
                    transition: all 0.3s ease;
                    box-shadow: 0 4px 15px rgba(0, 255, 136, 0.3);
                }}
                
                .print-btn:hover, .config-btn:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 6px 20px rgba(0, 255, 136, 0.5);
                }}
                
                .auto-shutdown {{ 
                    position: fixed; 
                    bottom: 20px; 
                    right: 20px; 
                    background: rgba(20, 20, 20, 0.9);
                    backdrop-filter: blur(10px);
                    padding: 12px; 
                    border-radius: 8px; 
                    border: 1px solid rgba(138, 43, 226, 0.5);
                    color: #e0e0e0;
                    z-index: 10;
                }}
                
                #countdown {{ 
                    font-weight: bold; 
                    color: #00FF88;
                }}
                
                .activity-entry .time {{ 
                    color: #888; 
                    margin-right: 10px; 
                }}
                
                .tabs {{ 
                    overflow: hidden; 
                    border: 1px solid rgba(0, 255, 136, 0.3);
                    background: rgba(20, 20, 20, 0.8);
                    backdrop-filter: blur(10px);
                    border-radius: 10px 10px 0 0;
                }}
                
                .tabs button {{ 
                    background: transparent;
                    float: left; 
                    border: none; 
                    cursor: pointer; 
                    padding: 14px 16px;
                    color: #b0b0b0;
                    transition: all 0.3s ease;
                    position: relative;
                }}
                
                .tabs button:hover {{ 
                    background: rgba(0, 255, 136, 0.1);
                    color: #00FF88;
                }}
                
                .tabs button.active {{ 
                    background: rgba(0, 255, 136, 0.2);
                    color: #00FF88;
                    box-shadow: inset 0 0 10px rgba(0, 255, 136, 0.3);
                }}
                
                .tab-content {{ 
                    display: none; 
                    padding: 20px;
                    background: rgba(15, 15, 15, 0.8);
                    backdrop-filter: blur(5px);
                    border: 1px solid rgba(0, 255, 136, 0.3);
                    border-top: none;
                    border-radius: 0 0 10px 10px;
                    color: #e0e0e0;
                }}
                
                .tab-content.active {{ 
                    display: block; 
                }}
                
                h2, h3 {{
                    color: #00FF88;
                    text-shadow: 0 0 10px rgba(0, 255, 136, 0.4);
                }}
                
                p {{
                    color: #d0d0d0;
                }}
                
                /* Scrollbar styling */
                ::-webkit-scrollbar {{
                    width: 8px;
                }}
                
                ::-webkit-scrollbar-track {{
                    background: rgba(0, 0, 0, 0.3);
                }}
                
                ::-webkit-scrollbar-thumb {{
                    background: rgba(0, 255, 136, 0.5);
                    border-radius: 4px;
                }}
                
                ::-webkit-scrollbar-thumb:hover {{
                    background: rgba(0, 255, 136, 0.7);
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <!-- Glass overlay layer -->
                <div class="glass-overlay"></div>
                <!-- Black overlay layer -->
                <div class="black-overlay"></div>
                
                <h1>CodePortal MCP Dashboard</h1>
                
                <div class="tabs">
                    <button class="tab-btn active" onclick="openTab(event, 'Projects')">Recent Projects</button>
                    <button class="tab-btn" onclick="openTab(event, 'API')">API Providers</button>
                    <button class="tab-btn" onclick="openTab(event, 'Activity')">Activity Log</button>
                </div>
                
                <div id="Projects" class="tab-content active">
                    <div class="glass-overlay"></div>
                    <div class="black-overlay"></div>
                    <h2>Recent Projects</h2>
                    <div class="project-list">
                        {projects_html if projects_html else "<p>No recent projects found</p>"}
                    </div>
                </div>
                
                <div id="API" class="tab-content">
                    <div class="glass-overlay"></div>
                    <div class="black-overlay"></div>
                    <h2>API Providers</h2>
                    <div class="provider-list">
                        {providers_html if providers_html else "<p>No API providers configured</p>"}
                    </div>
                </div>
                
                <div id="Activity" class="tab-content">
                    <div class="glass-overlay"></div>
                    <div class="black-overlay"></div>
                    <h2>Activity Log</h2>
                    <div class="activity-list">
                        {activity_html if activity_html else "<p>No recent activity</p>"}
                    </div>
                </div>
                
                {shutdown_html}
            </div>
            
            <script>
                function openTab(evt, tabName) {{
                    var i, tabcontent, tablinks;
                    
                    // Hide all tab content
                    tabcontent = document.getElementsByClassName("tab-content");
                    for (i = 0; i < tabcontent.length; i++) {{
                        tabcontent[i].classList.remove("active");
                    }}
                    
                    // Remove active class from tab buttons
                    tablinks = document.getElementsByClassName("tab-btn");
                    for (i = 0; i < tablinks.length; i++) {{
                        tablinks[i].classList.remove("active");
                    }}
                    
                    // Show the current tab and add active class to button
                    document.getElementById(tabName).classList.add("active");
                    evt.currentTarget.classList.add("active");
                }}
            </script>
        </body>
    </html>
    """