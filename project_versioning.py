"""
Project Versioning Module
========================
This module handles versioning and tracking project history.
It keeps track of project versions, API keys, and maintains persistent records.
"""

import os
import json
import csv
import datetime
import shutil
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("project_versioning")

class ProjectVersioning:
    def __init__(self, archive_dir=None):
        """
        Initialize the versioning system
        
        Args:
            archive_dir: Custom archive directory path (optional)
        """
        # Determine archive directory
        if archive_dir:
            self.archive_dir = archive_dir
        else:
            self.archive_dir = os.path.join(os.path.expanduser("~"), "Desktop", ".codeportal_archive")
            
        # Ensure archive directories exist
        os.makedirs(self.archive_dir, exist_ok=True)
        
        # Path to history CSV file
        self.history_file = os.path.join(self.archive_dir, "project_history.csv")
        
        # Path to API keys storage file
        self.api_keys_file = os.path.join(self.archive_dir, "api_keys.json")
        
        # Initialize history file if needed
        self._init_history_file()
        
        # Initialize API keys file if needed
        self._init_api_keys_file()
        
    def _init_history_file(self):
        """Create the history CSV file with headers if it doesn't exist"""
        if not os.path.exists(self.history_file):
            with open(self.history_file, 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow([
                    "UID", 
                    "PROJECT_NAME", 
                    "CHILD_FILENAME", 
                    "VERSION",
                    "PATH", 
                    "DATE", 
                    "DESCRIPTION"
                ])
            logger.info(f"Created new project history file at {self.history_file}")
    
    def _init_api_keys_file(self):
        """Create the API keys JSON file if it doesn't exist"""
        if not os.path.exists(self.api_keys_file):
            default_keys = {
                "openai": {"api_key": ""},
                "google": {"api_key": ""},
                "azure": {"api_key": ""},
                "anthropic": {"api_key": ""}
            }
            with open(self.api_keys_file, 'w') as file:
                json.dump(default_keys, file, indent=2)
            logger.info(f"Created new API keys file at {self.api_keys_file}")
    
    def get_api_keys(self):
        """Get API keys from the archive storage"""
        try:
            with open(self.api_keys_file, 'r') as file:
                return json.load(file)
        except Exception as e:
            logger.error(f"Error loading API keys: {e}")
            return {}
    
    def save_api_keys(self, keys_data):
        """Save API keys to the archive storage"""
        try:
            with open(self.api_keys_file, 'w') as file:
                json.dump(keys_data, file, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving API keys: {e}")
            return False
    
    def update_api_key(self, provider, key, additional_info=None):
        """Update a specific API key"""
        keys = self.get_api_keys()
        
        if provider not in keys:
            keys[provider] = {}
        
        keys[provider]["api_key"] = key
        
        # Add any additional info fields
        if additional_info:
            for field, value in additional_info.items():
                keys[provider][field] = value
        
        return self.save_api_keys(keys)
    
    def get_api_key(self, provider):
        """Get API key for a specific provider"""
        keys = self.get_api_keys()
        return keys.get(provider, {}).get("api_key", "")
    
    def log_project(self, project_path, project_name, files, description=None):
        """
        Log a project into the history file
        
        Args:
            project_path: Path to the project
            project_name: Name of the project
            files: List of files in the project
            description: Optional project description
        """
        # Generate a unique ID for this project entry
        uid = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        
        # Get current date
        date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Record each file
        rows = []
        for file_name in files:
            # Check if this file exists in history to determine version
            version = self._get_next_version(project_name, file_name)
            
            rows.append([
                uid,
                project_name,
                f"{file_name} [V{version}]",
                version,
                project_path,
                date,
                description or ""
            ])
        
        # Write to history file
        try:
            with open(self.history_file, 'a', newline='') as file:
                writer = csv.writer(file)
                writer.writerows(rows)
            logger.info(f"Logged project {project_name} with {len(files)} files")
            return True
        except Exception as e:
            logger.error(f"Error logging project: {e}")
            return False
    
    def _get_next_version(self, project_name, file_name):
        """Get the next version number for a project file"""
        max_version = 0
        
        try:
            with open(self.history_file, 'r', newline='') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header
                
                for row in reader:
                    if len(row) >= 3:
                        # Check if project name matches
                        if row[1] == project_name:
                            # Extract file name and version
                            child_file = row[2]
                            if file_name in child_file:
                                # Parse version number
                                try:
                                    version_str = child_file.split("[V")[-1].split("]")[0]
                                    version = int(version_str)
                                    max_version = max(max_version, version)
                                except:
                                    pass
        except Exception as e:
            logger.error(f"Error reading project history: {e}")
        
        # Return next version number
        return max_version + 1
    
    def get_recent_projects(self, limit=3):
        """
        Get the most recent projects
        
        Args:
            limit: Maximum number of projects to return
            
        Returns:
            List of dictionaries with project information
        """
        projects = {}
        
        try:
            with open(self.history_file, 'r', newline='') as file:
                reader = csv.DictReader(file)
                
                for row in reader:
                    uid = row.get("UID", "")
                    if uid not in projects:
                        projects[uid] = {
                            "name": row.get("PROJECT_NAME", ""),
                            "path": row.get("PATH", ""),
                            "date": row.get("DATE", ""),
                            "description": row.get("DESCRIPTION", ""),
                            "files": []
                        }
                    
                    projects[uid]["files"].append(row.get("CHILD_FILENAME", ""))
        except Exception as e:
            logger.error(f"Error getting recent projects: {e}")
        
        # Sort by date (newest first) and take only the specified limit
        sorted_projects = sorted(
            projects.values(), 
            key=lambda x: x["date"] if x["date"] else "", 
            reverse=True
        )
        
        return sorted_projects[:limit]
    
    def print_instructions(self, project_path):
        """
        Print instructions for a project
        
        Args:
            project_path: Path to the project
            
        Returns:
            Path to the printed instructions file
        """
        # Check if AI instructions file exists
        instructions_path = os.path.join(project_path, "AI_INSTRUCTIONS.md")
        if not os.path.exists(instructions_path):
            # Fall back to regular instructions
            instructions_path = os.path.join(project_path, "INSTRUCTIONS.md")
        
        if not os.path.exists(instructions_path):
            return None
        
        # Create a printable copy with timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        print_path = os.path.join(project_path, f"PRINTED_INSTRUCTIONS_{timestamp}.md")
        
        try:
            shutil.copy2(instructions_path, print_path)
            logger.info(f"Instructions printed to {print_path}")
            return print_path
        except Exception as e:
            logger.error(f"Error printing instructions: {e}")
            return None