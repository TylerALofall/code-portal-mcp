"""
Create Desktop Shortcut
=======================
This script creates a desktop shortcut for CodePortal with a custom icon.
"""

import os
import sys
import winshell
from win32com.client import Dispatch
import base64
from pathlib import Path
import ctypes

# Define icon data - this is a base64 encoded .ico file with a swirl design
ICON_DATA = """
AAABAAEAICAAAAEAIACoEAAAFgAAACgAAAAgAAAAQAAAAAEAIAAAAAAAABAAAMMOAADDDgAAAAAA
AAAAAAD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A
////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD/
//8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP//
/wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////
AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A
////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD/
//8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP//
/wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////
AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A
////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD/
//8AAAAAANnZ3gDZ2d4A2dneANnZ3gDZ2d4A2dneANnZ3gDZ2d4A2dneANnZ3gDZ2d4A2dneHNnZ
3pHZ2d7V2dne2dnZ3rLZ2d5d2dneC9nZ3gDZ2d4A2dneANnZ3gDZ2d4A2dneANnZ3gDZ2d4A2dne
AP///wD///8AAAAAANnZ3gDZ2d4A2dneANnZ3gDZ2d4A2dneANnZ3gDZ2d4A2dneANnZ3gTZ2d5N
2dne09nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3rLZ2d4v2dneANnZ3gDZ2d4A2dneANnZ3gDZ
2d4A2dneAP///wD///8AAAAAANnZ3gDZ2d4A2dneANnZ3gDZ2d4A2dneANnZ3gDZ2d4A2dneRdnZ
3tHZ2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dneodnZ3hXZ2d4A2dne
ANnZ3gDZ2d4A2dneAP///wD///8AAAAAANnZ3gDZ2d4A2dneANnZ3gDZ2d4A2dneANnZ3g3Z2d6d
2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3u/Z
2d5R2dneANnZ3gDZ2d4A2dneAP///wD///8AAAAAANnZ3gDZ2d4A2dneANnZ3gDZ2d4A2dneQtnZ
3vDZ2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne
/9nZ3v/Z2d7H2dneEtnZ3gDZ2d4A2dneAP///wD///8AAAAAANnZ3gDZ2d4A2dneANnZ3gDZ2d5e
2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z
2d7/2dne/9nZ3v/Z2d7/2dnevNnZ3gfZ2d4A2dneAP///wD///8AAAAAANnZ3gDZ2d4A2dneANnZ
3jHZ2d772dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne
/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3nLZ2d4A2dneAP///wD///8AAAAAANnZ3gDZ2d4A
2dneA9nZ3snZ2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z
2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3vbZ2d4h2dneAP///wD///8AAAAAAP//
/wDZ2d4A2dneTdnZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne
/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d5z////AP///wAAAAAA
////AP///wDZ2d6M2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z
2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3tH///8A////AAAA
AABPT1IAT09SANnZ3rHZ2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne
/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne3k9PUgBPT1IA
AAAAAE9PUgBPT1IA2dneutnZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z
2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7cT09SAE9P
UgAAAAAAT09SAE9PUgDZ2d7X2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne
/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3tpPT1IA
T09SAAAAAAAAAAAAAAAAAM3N2+/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z
2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/zc3b7wAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAANnZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne
/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/2dne/9nZ3v/Z2d7/
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAANnZ3vDNzdv/zc3b/83N2//Nzdv/zc3b/83N2//N
zdv/zc3b/83N2//Nzdv/zc3b/83N2//Nzdv/zc3b/83N2//Nzdv/zc3b/83N2//Nzdv/zc3b/83N
2/DZ2d4AAAAAAAAAAAAAAAAAAAAAAAAAAABTVVcAT09SAE9PUgBPT1IAT09SAE9PUgBPT1IAT09S
AE9PUgBPT1IAT09SAE9PUgBPT1IAT09SAE9PUgBPT1IAT09SAE9PUgBPT1IAT09SAE9PUgBPT1IA
U1VXAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOHj5ADh4+QA4ePkAOHj5ADh4+QA4ePkAOHj5ADh
4+QA4ePkAOHj5ADh4+QA4ePkAOHj5ADh4+QA4ePkAOHj5ADh4+QA4ePkAOHj5ADh4+QA4ePkAOHj
5ADh4+QAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/
//8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP//
/wD///8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAA////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP//
/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA////AP///wD///8A////AP///wD///8A////
AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP///wD///8A////AP///wD/
//8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD///8A////AP///wD///8A////AP///wD///8A////
AP///wD///8A////AP///wD///8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD///8A////AP//
/wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////
AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A
"""

def create_desktop_shortcut():
    """Create a desktop shortcut for CodePortal with swirl icon"""
    try:
        # Get the desktop path
        desktop_path = winshell.desktop()
        
        # Get the path to the CodePortal directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Path to the start_server.bat file
        bat_path = os.path.join(script_dir, "start_server.bat")
        
        # Create icon file
        icon_path = os.path.join(script_dir, "codeportal.ico")
        icon_data = base64.b64decode(ICON_DATA)
        with open(icon_path, 'wb') as icon_file:
            icon_file.write(icon_data)
        
        # Create shortcut
        shortcut_path = os.path.join(desktop_path, "CodePortal.lnk")
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.Targetpath = bat_path
        shortcut.WorkingDirectory = script_dir
        shortcut.IconLocation = icon_path
        shortcut.save()
        
        # Show success message
        message = "CodePortal shortcut created on your desktop!"
        ctypes.windll.user32.MessageBoxW(0, message, "CodePortal Setup", 0x40)
        
        return True
    except Exception as e:
        error_message = f"Error creating shortcut: {str(e)}"
        ctypes.windll.user32.MessageBoxW(0, error_message, "CodePortal Setup", 0x10)
        return False

if __name__ == "__main__":
    create_desktop_shortcut()